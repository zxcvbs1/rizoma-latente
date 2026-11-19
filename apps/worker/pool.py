"""
Pool de cómputo del común (WP-23; 09_procomun §2.2, INV-18/17/11/10/03).

El nodo publica tareas semióticas abiertas sobre material YA despersonalizado
(surcos, matrices materiales, formas candidatas). Un cliente con fierro toma
una, la procesa con su modelo, y devuelve una propuesta. La propuesta se valida
POR RESULTADO con los validadores locales, no se confía en quien aporta. Si
valida, la tarea se resuelve y el aportante gana peso de contribución en ese
dominio; el peso prioriza pero decae, no se transfiere y no es ranking. Si no
valida, no hay castigo: la tarea vuelve a estar abierta y el aporte no acredita.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from packages.domain import frontera
from packages.domain.models import PesoContribucion, TareaComun

TIPOS_TAREA = ("cristalizar", "proponer_forma", "densificar")
TTL_TAREA_DIAS = 7
TTL_PESO_DIAS = 30
CADUCIDAD_TOMA_HORAS = 24  # si el que tomó no resuelve, la tarea se libera


class PoolError(Exception):
    pass


def _uid() -> str:
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def crear_tarea(db, tipo: str, dominio: str, material: dict, ttl_dias: int = TTL_TAREA_DIAS) -> TareaComun:
    """El nodo abre una tarea. El material tiene que ser YA anónimo: la frontera
    rechaza cualquier identidad antes de que la tarea exista (INV-17)."""
    if tipo not in TIPOS_TAREA:
        raise PoolError(f"tipo de tarea inválido: {tipo} (catálogo: {list(TIPOS_TAREA)})")
    if not (dominio or "").strip():
        raise PoolError("la tarea declara su dominio")
    frontera.validar_salida(material or {})
    tarea = TareaComun(id=_uid(), tipo=tipo, dominio=dominio.strip(),
                       material=json.dumps(material or {}), estado="abierta",
                       ttl_dias=ttl_dias)
    db.add(tarea)
    db.flush()
    return tarea


def _tarea(db, tarea_id: str) -> TareaComun:
    tarea = db.query(TareaComun).filter(TareaComun.id == tarea_id).first()
    if not tarea:
        raise PoolError("tarea inexistente")
    return tarea


def _toma_caduca(tarea, ahora=None) -> bool:
    if tarea.estado != "tomada" or not tarea.tomada_at:
        return False
    ahora = ahora or _ahora()
    return (ahora - _aware(tarea.tomada_at)) > timedelta(hours=CADUCIDAD_TOMA_HORAS)


def listar_abiertas(db, ahora=None) -> list:
    """Las tareas que un cliente puede tomar: abiertas, o tomadas cuya toma
    caducó (el que la agarró no la resolvió a tiempo). Solo material anónimo."""
    ahora = ahora or _ahora()
    abiertas = []
    for t in db.query(TareaComun).all():
        if t.estado == "abierta" or (t.estado == "tomada" and _toma_caduca(t, ahora)):
            abiertas.append({"id": t.id, "tipo": t.tipo, "dominio": t.dominio,
                             "material": json.loads(t.material or "{}")})
    return abiertas


def tomar_tarea(db, tarea_id: str, aportante: str) -> dict:
    """Reserva la tarea para un aportante. Si ya está tomada y no caducó, no se
    puede robar; si caducó, se libera y la agarra el nuevo."""
    tarea = _tarea(db, tarea_id)
    if tarea.estado == "resuelta":
        raise PoolError("la tarea ya está resuelta")
    if tarea.estado == "tomada" and not _toma_caduca(tarea):
        raise PoolError("la tarea ya está tomada por otro")
    tarea.estado = "tomada"
    tarea.tomada_por = aportante
    tarea.tomada_at = _ahora()
    db.flush()
    return {"tarea_id": tarea.id, "tipo": tarea.tipo, "dominio": tarea.dominio,
            "material": json.loads(tarea.material or "{}")}


def _validar_propuesta(tipo: str, propuesta: dict) -> None:
    """Validación por resultado (INV-18). Siempre pasa la frontera; según el
    tipo, un esquema mínimo. No se persuade a estos gates: no son modelos."""
    frontera.validar_salida(propuesta or {})
    if tipo == "proponer_forma":
        from apps.acervo import acervo
        acervo.despersonalizar(propuesta)
    elif tipo == "cristalizar":
        for campo in ("nombre", "tension_que_ataca", "regla_logica", "flujo", "senales_alivio"):
            if not (propuesta.get(campo) or "").strip():
                raise PoolError(f"la cristalización exige {campo}")
    elif tipo == "densificar":
        vec = propuesta.get("vector")
        if not isinstance(vec, list) or not vec or not all(isinstance(x, (int, float)) for x in vec):
            raise PoolError("densificar exige un vector no vacío de números")


def acreditar_peso(db, llave: str, dominio: str, delta: float = 1.0) -> PesoContribucion:
    """El peso de contribución: prioriza tareas propias, decae, no transferible,
    no ranking. Es la reputación por hacer, ensanchada a las contribuciones."""
    fila = next((p for p in db.query(PesoContribucion).all()
                 if p.llave.lower() == llave.lower() and p.dominio == dominio), None)
    if fila is None:
        fila = PesoContribucion(id=_uid(), llave=llave, dominio=dominio, peso=0.0)
        db.add(fila)
    fila.peso = float(fila.peso or 0.0) + delta
    fila.last_touched = _ahora()
    db.flush()
    return fila


def peso_de(db, llave: str, dominio: str | None = None) -> float:
    """Solo el propio dueño consulta su peso (no hay ranking de actores)."""
    total = 0.0
    for p in db.query(PesoContribucion).all():
        if p.llave.lower() == llave.lower() and (dominio is None or p.dominio == dominio):
            total += float(p.peso or 0.0)
    return total


def resolver_tarea(db, tarea_id: str, aportante: str, propuesta: dict) -> dict:
    """El cliente devuelve su propuesta. Se valida por resultado; si pasa, la
    tarea se resuelve y acredita peso. Si no pasa, NO penaliza (no hay
    slashing): la tarea vuelve a abierta y el aporte no acredita."""
    tarea = _tarea(db, tarea_id)
    if tarea.estado == "resuelta":
        raise PoolError("la tarea ya está resuelta")
    if tarea.tomada_por and tarea.tomada_por.lower() != aportante.lower() and not _toma_caduca(tarea):
        raise PoolError("la tarea la tomó otro aportante")
    try:
        _validar_propuesta(tarea.tipo, propuesta)
    except Exception as exc:
        tarea.estado = "abierta"
        tarea.tomada_por = None
        tarea.tomada_at = None
        db.flush()
        raise PoolError(f"propuesta inválida (sin castigo, no acredita): {exc}")
    tarea.estado = "resuelta"
    tarea.resultado = json.dumps(propuesta)
    db.flush()
    peso = acreditar_peso(db, aportante, tarea.dominio, 1.0)
    return {"tarea_id": tarea.id, "estado": "resuelta",
            "peso_contribucion_dominio": float(peso.peso)}


# --- Barridos de olvido (INV-03) ---

def vencer_tarea(tarea, ahora=None) -> bool:
    if tarea.estado in ("resuelta", "vencida"):
        return False
    creada = _aware(tarea.created_at)
    if creada is None:
        return False
    ahora = ahora or _ahora()
    if (ahora - creada) > timedelta(days=int(tarea.ttl_dias or TTL_TAREA_DIAS)):
        tarea.estado = "vencida"
        return True
    return False


def decaer_peso(fila, ahora=None, ttl_dias: int = TTL_PESO_DIAS) -> bool:
    if not fila.peso:
        return False
    ultima = _aware(fila.last_touched)
    if ultima is None:
        return False
    ahora = ahora or _ahora()
    if (ahora - ultima) > timedelta(days=ttl_dias):
        fila.peso = 0.0
        return True
    return False
