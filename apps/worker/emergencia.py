"""
Emergencia generativa (WP-19 construye lo que WP-13 testea; 01_red §7 y §7.1,
INV-14/15/11).

El agente detecta surcos (insistencia agregada) y PROPONE piezas de una lista
blanca cerrada: subíndice, regla de enlace, lugar. Toda pieza queda
registrada con su justificación (agregados, jamás identidades), es auditable,
reversible (revocación del proponente o des-adopción del nodo) y decae sin
uso. El andamiaje emerge de los surcos, nunca antes que ellos.

REGLA DEL PISO: el canal global es inamovible; los topics derivados suman y
jamás reemplazan. `emision_cumple_piso` es el validador que el gateway usa.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from packages.domain import frontera
from packages.domain.models import Node, Pieza, SearchLog, Synapse

LISTA_BLANCA = ("subindice", "regla_enlace", "lugar")
TOPIC_GLOBAL = "/rizoma/v2/global/proto"
TOPIC_PIEZAS = "/rizoma/v2/piezas"
UMBRAL_SURCO = 40  # búsquedas insistentes sin respuesta (CU-R7); configurable por nodo
UMBRAL_SURCO_CONFIRMACION = 10  # confirmaciones del mismo par de comandos (WP-32)


class EmergenciaError(Exception):
    pass


def _uid() -> str:
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


def detectar_surcos(db, umbral: int = UMBRAL_SURCO) -> list:
    """Insistencia agregada: búsquedas repetidas SIN respuesta. Ningún actor:
    el surco es del uso, no de alguien."""
    conteo = {}
    for registro in db.query(SearchLog).all():
        if (registro.results_count or 0) > 0:
            continue
        consulta = (registro.query_text or "").strip().lower()
        if consulta:
            conteo[consulta] = conteo.get(consulta, 0) + 1
    surcos = [{"surco": consulta, "busquedas_sin_respuesta": n}
              for consulta, n in conteo.items() if n >= umbral]
    return sorted(surcos, key=lambda s: -s["busquedas_sin_respuesta"])


def detectar_surcos_confirmacion(db, umbral: int = UMBRAL_SURCO_CONFIRMACION) -> list:
    """Surcos de confirmación (WP-32; 01_red §7): pares de comandos cuyas
    intenciones confirman juntas una y otra vez (!presto con !busco, !ofrezco
    con !permuto). El agregado es de la lengua, jamás de alguien: se cuenta el
    par de comandos, y ni una llave ni un texto salen de acá. De estos surcos
    no nace ninguna pieza: nacen los PATRONES de coordinación, que un cliente
    redacta y el ciclo del acervo consiente (la lista blanca no se toca)."""
    comando_de = {n.id: (n.command_slug or "").strip().lower()
                  for n in db.query(Node).all()}
    conteo = {}
    for sinapsis in db.query(Synapse).all():
        if sinapsis.status != "active":
            continue
        a = comando_de.get(sinapsis.origin_node_id, "")
        b = comando_de.get(sinapsis.target_node_id, "")
        if not a or not b:
            continue
        par = tuple(sorted((a, b)))
        conteo[par] = conteo.get(par, 0) + 1
    surcos = [{"par": list(par), "confirmaciones": n}
              for par, n in conteo.items() if n >= umbral]
    return sorted(surcos, key=lambda s: -s["confirmaciones"])


def topic_para(tipo: str, semilla: str) -> str | None:
    """Punto de encuentro derivado (§7.1): el índice rico sigue local (INV-11)."""
    hashed = hashlib.sha256(semilla.encode()).hexdigest()[:16]
    if tipo == "subindice":
        return f"/rizoma/v2/idx/{hashed}"
    if tipo == "lugar":
        return f"/rizoma/v2/lugar/{hashed}"
    return None  # la regla de enlace es puramente declarativa


def emision_cumple_piso(topics) -> bool:
    """REGLA DEL PISO (dura): toda emisión va SIEMPRE al global. Una emisión
    publicada solo en derivados debe rechazarse."""
    return TOPIC_GLOBAL in (topics or [])


def proponer_pieza(db, tipo: str, justificacion: str, spec: dict,
                   proponente: str, ttl_dias: int = 30, waku=None) -> Pieza:
    """El agente PROPONE, jamás impone. Lista blanca cerrada; justificación
    con agregados del surco (una llave ahí la voltea); declaración firmada
    publicada al meta-topic si hay transporte a mano."""
    if tipo not in LISTA_BLANCA:
        raise EmergenciaError(
            f"fuera de la lista blanca: {tipo} (espacio de acción cerrado, INV-14)")
    if not (justificacion or "").strip():
        raise EmergenciaError("sin surco que la pida no hay pieza: falta justificación")
    frontera.validar_salida({"justificacion": justificacion, "spec": spec})

    pieza = Pieza(id=_uid(), tipo=tipo, justificacion=justificacion.strip(),
                  spec=json.dumps(spec or {}),
                  topic_derivado=topic_para(tipo, justificacion),
                  proponente_llave=proponente, estado="candidata",
                  mass=0.0, ttl_dias=ttl_dias)
    db.add(pieza)
    db.flush()

    if waku is not None:
        declaracion = {"pieza_id": pieza.id, "tipo": pieza.tipo,
                       "justificacion": pieza.justificacion, "spec": spec or {},
                       "topic_derivado": pieza.topic_derivado,
                       "llave": proponente, "ttl_dias": ttl_dias}
        try:
            waku(declaracion, TOPIC_PIEZAS)
        except Exception as exc:
            print(f"[EMERGENCIA] Declaración no propagada (queda local): {exc}")
    return pieza


def _pieza(db, pieza_id: str) -> Pieza:
    pieza = db.query(Pieza).filter(Pieza.id == pieza_id).first()
    if not pieza:
        raise EmergenciaError("pieza inexistente")
    return pieza


def adoptar_pieza(db, pieza_id: str) -> Pieza:
    """Adopción del nodo: la pieza es real en la medida en que se adopta y se
    usa (INV-15 generalizado)."""
    pieza = _pieza(db, pieza_id)
    if pieza.estado == "revocada":
        raise EmergenciaError("una pieza revocada no se adopta")
    pieza.estado = "activa"
    pieza.last_touched = _ahora()
    db.flush()
    return pieza


def des_adoptar_pieza(db, pieza_id: str) -> Pieza:
    """Reversibilidad sin autoridad: des-adopción unilateral, sin drama."""
    pieza = _pieza(db, pieza_id)
    pieza.estado = "inactiva"
    db.flush()
    return pieza


def usar_pieza(db, pieza_id: str) -> Pieza:
    """La masa viene del USO real, jamás de proponerse."""
    pieza = _pieza(db, pieza_id)
    if pieza.estado not in ("candidata", "activa"):
        raise EmergenciaError(f"pieza {pieza.estado}: no se usa")
    pieza.mass = float(pieza.mass or 0.0) + 1.0
    pieza.last_touched = _ahora()
    db.flush()
    return pieza


def revocar_pieza(db, pieza_id: str, llave: str) -> Pieza:
    """Revocación firmada: solo el proponente."""
    pieza = _pieza(db, pieza_id)
    if (pieza.proponente_llave or "").lower() != llave.lower():
        raise EmergenciaError("solo el proponente revoca su pieza")
    pieza.estado = "revocada"
    db.flush()
    return pieza


def apagar_pieza(pieza, ahora=None) -> bool:
    """Sin uso dentro de su TTL, la pieza decae y se desactiva sola (INV-14)."""
    if pieza.estado not in ("candidata", "activa"):
        return False
    ultima = pieza.last_touched or pieza.created_at
    if ultima is None:
        return False
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    ahora = ahora or _ahora()
    if (ahora - ultima) <= timedelta(days=int(pieza.ttl_dias or 30)):
        return False
    pieza.mass = 0.0
    pieza.estado = "inactiva"
    return True


def ciclo_emergencia(db, proponente: str, umbral: int = UMBRAL_SURCO, waku=None) -> list:
    """El bucle reactivo del agente: surcos detectados -> UNA pieza propuesta
    por surco (subíndice), idempotente: si ya hay pieza viva para ese surco,
    no propone otra."""
    vivas = {p.justificacion for p in db.query(Pieza).all()
             if p.estado in ("candidata", "activa")}
    propuestas = []
    for surco in detectar_surcos(db, umbral):
        justificacion = (f"surco: {surco['busquedas_sin_respuesta']} búsquedas sin "
                         f"respuesta sobre '{surco['surco']}'")
        if justificacion in vivas:
            continue
        propuestas.append(proponer_pieza(
            db, "subindice", justificacion,
            {"consulta_agregada": surco["surco"]}, proponente, waku=waku))
    return propuestas
