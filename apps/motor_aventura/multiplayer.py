"""
Multiplayer semiótico: el árbitro que emerge (WP-25; 09_procomun §2.4).

Servidor autoritativo de ESTADO, jamás de sentido. El nodo mantiene el estado
compartido (turno, quién compone, quién participa) y no interpreta; cada cliente
aporta su semiótica. El cómputo neutral que compone la ficción no lo pone un
servidor central ni una de las partes: emerge de una quota rotativa, con la
neutralidad garantizada por procedimiento y no por un juez:

- Sorteo de quién compone el turno (nadie es GM permanente).
- Rúbrica-forma pública como arbitraje común (la misma para todos, legible).
- Validación cruzada barata: los otros chequean el turno; un rechazo lo tumba.

El contenido de la ficción es efímero y muere al cierre; solo persiste el
metadato de la sesión. Toda escena ofrece el puente consentido a la emisión
real (05 §6): el multiplayer es ensayo, jamás realidad-sustituta. Sin clientes
con fierro, degrada al camino asincrónico simple.
"""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from packages.domain import frontera
from packages.domain.models import Forma, SesionMultiplayer

TTL_SESION_DIAS = 7  # sesión abierta sin cierre: huérfana


class MultiplayerError(Exception):
    pass


# Memoria efímera: la historia de lo dicho vive en proceso y muere al cierre.
_sesiones: dict[str, list] = {}


def _uid() -> str:
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


def _sesion(db, sesion_id: str) -> SesionMultiplayer:
    s = db.query(SesionMultiplayer).filter(SesionMultiplayer.id == sesion_id).first()
    if not s:
        raise MultiplayerError("sesión inexistente")
    return s


def _sesion_viva(db, sesion_id: str) -> SesionMultiplayer:
    s = _sesion(db, sesion_id)
    if s.estado == "cerrada":
        raise MultiplayerError("la sesión está cerrada")
    if sesion_id not in _sesiones:
        _sesiones[sesion_id] = []
    return s


def abrir_sesion(db, convocante: str, rubrica_gm_id: str | None = None) -> SesionMultiplayer:
    """Un miembro convoca. La rúbrica-forma pública (WP-22) es el GM común:
    todos componen bajo la misma, legible. Sin rúbrica, el nodo usa una mínima."""
    if rubrica_gm_id:
        forma = db.query(Forma).filter(Forma.id == rubrica_gm_id).first()
        if not forma or forma.tipo not in ("rubrica", "lente") or forma.estado != "publicada":
            raise MultiplayerError("la rúbrica del GM debe ser una forma-rúbrica publicada")
    sesion = SesionMultiplayer(
        id=_uid(), convocante_llave=convocante, rubrica_gm_id=rubrica_gm_id,
        participantes=json.dumps([{"llave": convocante, "con_fierro": True}]),
        estado="abierta", turno=0)
    db.add(sesion)
    db.flush()
    _sesiones[sesion.id] = []
    return sesion


def entrar(db, sesion_id: str, participante: str, con_fierro: bool = False) -> dict:
    """Acto individual: nadie es sumado por defecto. `con_fierro` declara si el
    cliente puede componer turnos (tiene modelo). El que no entra no aparece."""
    sesion = _sesion_viva(db, sesion_id)
    participantes = json.loads(sesion.participantes)
    if not any(p["llave"].lower() == participante.lower() for p in participantes):
        participantes.append({"llave": participante, "con_fierro": bool(con_fierro)})
        sesion.participantes = json.dumps(participantes)
        db.flush()
    return {"sesion_id": sesion.id, "participantes": len(participantes)}


def _con_fierro(sesion) -> list:
    return [p["llave"] for p in json.loads(sesion.participantes) if p.get("con_fierro")]


def sortear_gm(db, sesion_id: str, rng=None) -> str | None:
    """El neutralizador: se sortea quién compone el turno entre los que tienen
    fierro, evitando repetir al anterior cuando hay más de uno. Como nadie
    eligió serlo, no sesga la ficción sostenidamente. Sin fierro: degrada."""
    sesion = _sesion_viva(db, sesion_id)
    candidatos = _con_fierro(sesion)
    if not candidatos:
        sesion.estado = "degradada"
        sesion.gm_actual = None
        db.flush()
        return None
    rng = rng or random.Random()
    elegibles = [c for c in candidatos if c != sesion.gm_anterior] or candidatos
    gm = rng.choice(elegibles)
    sesion.estado = "activa"
    sesion.gm_actual = gm
    sesion.escena_propuesta = None
    sesion.veredictos = json.dumps({})
    db.flush()
    return gm


def estado_sesion(db, sesion_id: str) -> dict:
    """El espejo de la sesión: lo dicho hasta ahora (historia efímera), el
    manual que arbitra (rúbrica GM, si hay), de quién es el turno y qué hay
    pendiente de validar. El compositor compone MIRANDO esto, no a ciegas.
    Muere al cierre como todo lo efímero (INV-07)."""
    sesion = _sesion_viva(db, sesion_id)
    rubrica = None
    if sesion.rubrica_gm_id:
        forma = db.query(Forma).filter(Forma.id == sesion.rubrica_gm_id).first()
        if forma:
            from apps.acervo import acervo
            rubrica = acervo.envolver_rubrica(forma)
    return {
        "sesion_id": sesion.id,
        "turno": sesion.turno,
        "gm_actual": sesion.gm_actual,
        "participantes": [p["llave"] for p in json.loads(sesion.participantes)],
        "historia": list(_sesiones.get(sesion_id, [])),
        "escena_propuesta": (json.loads(sesion.escena_propuesta)
                             if sesion.escena_propuesta else None),
        "manual": rubrica,
        "nota": "historia efímera: muere al cierre; componé bajo el manual si hay",
    }


def proponer_turno(db, sesion_id: str, gm: str, composicion: dict) -> dict:
    """El GM sorteado compone la escena del turno con su modelo, bajo la rúbrica
    pública. El nodo valida lo OBJETIVO (frontera: sin identidades); lo
    subjetivo lo validan los pares."""
    sesion = _sesion_viva(db, sesion_id)
    if not sesion.gm_actual or sesion.gm_actual.lower() != gm.lower():
        raise MultiplayerError("no te tocó componer este turno (no sos el GM sorteado)")
    frontera.validar_salida(composicion or {})
    if not (composicion.get("texto") or "").strip():
        raise MultiplayerError("la escena del turno necesita texto")
    sesion.escena_propuesta = json.dumps(composicion)
    sesion.veredictos = json.dumps({})
    db.flush()
    return {"sesion_id": sesion.id, "turno": sesion.turno, "a_validar_por": [
        p["llave"] for p in json.loads(sesion.participantes)
        if p["llave"].lower() != gm.lower()]}


def validar_turno(db, sesion_id: str, par: str, acepta: bool) -> dict:
    """Validación cruzada: un par que no es el GM chequea que la escena respete
    el estado y la rúbrica. Su veredicto se registra."""
    sesion = _sesion_viva(db, sesion_id)
    if not sesion.escena_propuesta:
        raise MultiplayerError("no hay escena propuesta para validar")
    if sesion.gm_actual and par.lower() == sesion.gm_actual.lower():
        raise MultiplayerError("el GM no valida su propio turno")
    if not any(p["llave"].lower() == par.lower() for p in json.loads(sesion.participantes)):
        raise MultiplayerError("solo un participante valida")
    veredictos = json.loads(sesion.veredictos)
    veredictos[par.lower()] = bool(acepta)
    sesion.veredictos = json.dumps(veredictos)
    db.flush()
    return {"veredictos": len(veredictos)}


def resolver_turno(db, sesion_id: str) -> dict:
    """Cuenta la validación cruzada. Un turno se acepta si ningún par lo rechazó
    y al menos uno lo validó; entonces la escena entra a la historia efímera, se
    avanza el turno y se re-sortea GM. Un rechazo lo tumba y se re-sortea."""
    sesion = _sesion_viva(db, sesion_id)
    if not sesion.escena_propuesta:
        raise MultiplayerError("no hay turno que resolver")
    pares = [p["llave"] for p in json.loads(sesion.participantes)
             if p["llave"].lower() != (sesion.gm_actual or "").lower()]
    veredictos = json.loads(sesion.veredictos)
    if pares:
        if any(v is False for v in veredictos.values()):
            sesion.escena_propuesta = None
            sesion.gm_anterior = sesion.gm_actual
            db.flush()
            gm = sortear_gm(db, sesion_id)
            return {"aceptado": False, "motivo": "rechazado por validación cruzada", "gm": gm}
        if not any(v is True for v in veredictos.values()):
            raise MultiplayerError("falta al menos una validación de un par")

    escena = json.loads(sesion.escena_propuesta)
    _sesiones.setdefault(sesion_id, []).append(escena)
    compuso = sesion.gm_actual
    sesion.turno += 1
    sesion.gm_anterior = sesion.gm_actual
    sesion.escena_propuesta = None
    sesion.veredictos = json.dumps({})
    db.flush()

    # Componer un turno aceptado es aportar cómputo al común (WP-23).
    try:
        from apps.worker import pool
        pool.acreditar_peso(db, compuso, "multiplayer", 1.0)
    except Exception:
        pass

    gm = sortear_gm(db, sesion_id)
    return {"aceptado": True, "turno": sesion.turno, "proximo_gm": gm}


def ofrecer_puente(db, sesion_id: str) -> dict:
    """Toda escena compartida conserva la puerta de salida a la emisión real
    (05 §6): el multiplayer es ensayo, jamás realidad-sustituta."""
    _sesion_viva(db, sesion_id)
    return {"puente_disponible": True,
            "nota": ("cualquier participante puede sacar lo que se buscó en la "
                     "ficción a la red real vía emisión consentida (01_red §4)")}


def cerrar_sesion(db, sesion_id: str) -> dict:
    """La ficción muere al cierre: la historia efímera se destruye y el metadato
    queda sin contenido. Solo persiste que la sesión existió y cuántos turnos."""
    sesion = _sesion(db, sesion_id)
    sesion.estado = "cerrada"
    sesion.closed_at = _ahora()
    sesion.escena_propuesta = None
    sesion.veredictos = json.dumps({})
    sesion.gm_actual = None
    _sesiones.pop(sesion_id, None)
    _jams.pop(sesion_id, None)
    db.flush()
    return {"sesion_id": sesion.id, "turnos": sesion.turno, "estado": "cerrada"}


def cerrar_sesion_huerfana(sesion, ahora=None, ttl_dias: int = TTL_SESION_DIAS) -> bool:
    """Sesión abierta sin cierre: se cierra sola (INV-13), su ficción ya murió."""
    if sesion.estado == "cerrada":
        return False
    creada = sesion.created_at
    if creada is not None and creada.tzinfo is None:
        creada = creada.replace(tzinfo=timezone.utc)
    ahora = ahora or _ahora()
    if creada is None or (ahora - creada) <= timedelta(days=ttl_dias):
        return False
    sesion.estado = "cerrada"
    sesion.closed_at = ahora
    sesion.escena_propuesta = None
    _sesiones.pop(sesion.id, None)
    _jams.pop(sesion.id, None)
    return True


def auditar_sesiones(db) -> list:
    """Ninguna sesión cerrada conserva contenido de ficción (escena o memoria)."""
    hallazgos = []
    for s in db.query(SesionMultiplayer).all():
        if s.estado == "cerrada" and (s.escena_propuesta or s.id in _sesiones or s.id in _jams):
            hallazgos.append(f"ficción viva en sesión cerrada: {s.id}")
    return hallazgos


# --- Modo jam (WP-26): la capa semántica sobre el CRDT ---
#
# El transporte síncrono (CRDT sobre Waku que sincroniza el estado compartido
# P2P sin nodo autoritativo) es lo VIVO: vive en el cliente (editor colaborativo
# tipo Flok) y necesita clientes concurrentes de verdad. Lo que sigue es la capa
# que va ENCIMA: en el jam no hay GM sorteado, cualquiera propone ediciones a la
# vez, pero una edición entra al estado LEGÍTIMO solo si pasó la validación
# cruzada. El CRDT converge bytes; acá se decide qué de eso se acepta. El más
# rápido no corona: escribir no es ser aceptado.

_jams: dict[str, dict] = {}  # sesion_id -> {"historia": [...], "pendientes": {eid: {...}}}


def abrir_jam(db, convocante: str, rubrica_gm_id: str | None = None) -> SesionMultiplayer:
    """Convoca una sesión síncrona (jam). Misma rúbrica pública como partitura
    común; sin turnos ni GM: todos componen a la vez."""
    sesion = abrir_sesion(db, convocante, rubrica_gm_id)
    sesion.estado = "jam"
    db.flush()
    _jams[sesion.id] = {"historia": [], "pendientes": {}}
    return sesion


def _jam_vivo(db, sesion_id: str) -> SesionMultiplayer:
    s = _sesion(db, sesion_id)
    if s.estado == "cerrada":
        raise MultiplayerError("la sesión está cerrada")
    if s.estado != "jam":
        raise MultiplayerError("esta sesión no está en modo jam")
    _jams.setdefault(sesion_id, {"historia": [], "pendientes": {}})
    return s


def proponer_edicion(db, sesion_id: str, autor: str, edicion: dict) -> dict:
    """Cualquiera propone una edición al estado compartido (no hay turno). El
    nodo valida lo objetivo (frontera); lo subjetivo lo validan los pares. La
    edición queda PENDIENTE hasta que la validación cruzada la acepte."""
    sesion = _jam_vivo(db, sesion_id)
    if not any(p["llave"].lower() == autor.lower() for p in json.loads(sesion.participantes)):
        raise MultiplayerError("solo un participante propone")
    frontera.validar_salida(edicion or {})
    if not (edicion.get("texto") or "").strip():
        raise MultiplayerError("la edición necesita texto")
    eid = _uid()
    _jams[sesion_id]["pendientes"][eid] = {"autor": autor, "edicion": edicion, "veredictos": {}}
    return {"edicion_id": eid, "estado": "pendiente"}


def validar_edicion(db, sesion_id: str, par: str, edicion_id: str, acepta: bool) -> dict:
    """Validación cruzada de una edición concreta: un par que no es el autor
    chequea que respete el estado y la rúbrica."""
    _jam_vivo(db, sesion_id)
    pend = _jams[sesion_id]["pendientes"].get(edicion_id)
    if not pend:
        raise MultiplayerError("edición inexistente o ya resuelta")
    if par.lower() == pend["autor"].lower():
        raise MultiplayerError("el autor no valida su propia edición")
    pend["veredictos"][par.lower()] = bool(acepta)
    return {"veredictos": len(pend["veredictos"])}


def resolver_edicion(db, sesion_id: str, edicion_id: str) -> dict:
    """Cuenta la validación cruzada de una edición. Entra al estado legítimo si
    ningún par la rechazó y al menos uno la validó; entonces se suma a la
    historia efímera. Un rechazo la descarta. El CRDT ya la sincronizó como
    bytes; acá se decide si es LEGÍTIMA."""
    _jam_vivo(db, sesion_id)
    jam = _jams[sesion_id]
    pend = jam["pendientes"].get(edicion_id)
    if not pend:
        raise MultiplayerError("edición inexistente o ya resuelta")
    veredictos = pend["veredictos"]
    if any(v is False for v in veredictos.values()):
        del jam["pendientes"][edicion_id]
        return {"aceptada": False, "motivo": "rechazada por validación cruzada"}
    if not any(v is True for v in veredictos.values()):
        raise MultiplayerError("falta al menos una validación de un par")
    jam["historia"].append(pend["edicion"])
    del jam["pendientes"][edicion_id]
    try:
        from apps.worker import pool
        pool.acreditar_peso(db, pend["autor"], "jam", 1.0)
    except Exception:
        pass
    return {"aceptada": True, "ediciones_en_estado": len(jam["historia"])}


def cerrar_jam(db, sesion_id: str) -> dict:
    """La jam muere al cierre como toda ficción: la historia y las pendientes
    efímeras se destruyen; solo persiste el metadato."""
    _jams.pop(sesion_id, None)
    return cerrar_sesion(db, sesion_id)
