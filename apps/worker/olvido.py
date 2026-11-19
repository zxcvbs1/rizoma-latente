"""
Olvido estructural (WP-12, INV-03; 01_red §6).

Nada pesa para siempre: la intención sin interacción decae a masa ~0 y se
archiva (renovable por su autor); la reputación cae a peso nulo con ~30 días
de inactividad; las propuestas no dirigidas expiran en silencio (regla del
gradiente). Funciones puras sobre filas; el barrido las aplica y cuenta.
"""
from datetime import datetime, timedelta, timezone

from apps.m2_handshake import gradiente

TTL_INTENCION_DIAS = 30
TTL_REPUTACION_DIAS = 30
TTL_PARTIDA_DIAS = 7  # partida abierta sin cierre: huérfana; su memoria ya murió con el proceso


def _aware(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def decaer_intencion(node, ahora=None, ttl_dias: int = TTL_INTENCION_DIAS) -> bool:
    """Intención activa sin interacción por ttl_dias: masa ~0 y archivada, no
    borrada. Devuelve True si cambió. WP-28: si el emisor declaró su propio
    ttl_dias en la señal, ese gobierna sobre el TTL global del nodo."""
    ahora = ahora or datetime.now(timezone.utc)
    if node.state != "active":
        return False
    ttl = getattr(node, "ttl_dias", None) or ttl_dias
    ultima = _aware(node.last_touched) or _aware(node.created_at)
    if ultima is None or (ahora - ultima) <= timedelta(days=ttl):
        return False
    node.mass = 0.0
    node.state = "archived"
    return True


def renovar_intencion(node, ahora=None) -> None:
    """La renovación es un acto del autor (INV-03): vuelve viva con masa base."""
    ahora = ahora or datetime.now(timezone.utc)
    node.state = "active"
    node.mass = max(float(node.mass or 0.0), 1.0)
    node.last_touched = ahora


def decaer_reputacion(actor, ahora=None, ttl_dias: int = TTL_REPUTACION_DIAS) -> bool:
    """Reputación sin actividad por ttl_dias: peso nulo. El peso es huella de
    coordinaciones recientes, no capital acumulable (INV-12)."""
    ahora = ahora or datetime.now(timezone.utc)
    if not actor.reputation:
        return False
    ultima = _aware(actor.last_seen_at)
    if ultima is None or (ahora - ultima) <= timedelta(days=ttl_dias):
        return False
    actor.reputation = 0.0
    return True


def decaer_arista(fila, ahora=None, ttl_dias: int = TTL_INTENCION_DIAS) -> bool:
    """Términos y deslizamientos sin uso pierden masa hasta apagarse; el mapa
    también olvida (INV-03): perfil sin uso se archiva muerto."""
    ahora = ahora or datetime.now(timezone.utc)
    if not fila.mass:
        return False
    ultima = _aware(fila.last_touched) or _aware(fila.created_at)
    if ultima is None or (ahora - ultima) <= timedelta(days=ttl_dias):
        return False
    fila.mass = 0.0
    return True


def expirar_sinapsis(synapse, ahora=None) -> bool:
    """Propuestas y addressed sin respuesta decaen por la regla del gradiente."""
    if gradiente.esta_vencida(synapse.created_at, synapse.status, ahora=ahora):
        synapse.status = gradiente.EXPIRED
        return True
    return False


def cerrar_partida_huerfana(partida, ahora=None, ttl_dias: int = TTL_PARTIDA_DIAS) -> bool:
    """Toda partida tiene final propio (INV-13): la que quedó abierta y sin
    cierre se cierra sola; su memoria efímera murió hace rato."""
    ahora = ahora or datetime.now(timezone.utc)
    if partida.estado != "abierta":
        return False
    creada = _aware(partida.created_at)
    if creada is None or (ahora - creada) <= timedelta(days=ttl_dias):
        return False
    partida.estado = "cerrada"
    partida.closed_at = ahora
    from apps.motor_aventura import motor as motor_aventura
    motor_aventura._memorias.pop(partida.id, None)
    return True


def barrer(db, ahora=None) -> dict:
    """Un pase completo de olvido. El caller hace commit."""
    from packages.domain.models import (Actor, ComandoVivo, Deslizamiento, Forma, Node,
                                        Partida, Pieza, PesoContribucion, SesionMultiplayer,
                                        Synapse, TareaComun, TerminoMapa)

    ahora = ahora or datetime.now(timezone.utc)
    contadores = {"intenciones_archivadas": 0, "reputaciones_nulas": 0,
                  "sinapsis_expiradas": 0, "topologia_apagada": 0,
                  "partidas_cerradas": 0, "formas_apagadas": 0,
                  "piezas_apagadas": 0, "tareas_vencidas": 0, "pesos_nulos": 0,
                  "sesiones_cerradas": 0, "comandos_olvidados": 0}

    for node in db.query(Node).all():
        if decaer_intencion(node, ahora):
            contadores["intenciones_archivadas"] += 1

    for actor in db.query(Actor).all():
        if decaer_reputacion(actor, ahora):
            contadores["reputaciones_nulas"] += 1

    for syn in db.query(Synapse).all():
        if expirar_sinapsis(syn, ahora):
            contadores["sinapsis_expiradas"] += 1

    for tabla in (TerminoMapa, Deslizamiento):
        for fila in db.query(tabla).all():
            if decaer_arista(fila, ahora):
                contadores["topologia_apagada"] += 1

    for partida in db.query(Partida).all():
        if cerrar_partida_huerfana(partida, ahora):
            contadores["partidas_cerradas"] += 1

    # Las formas tienen masa por reutilización y decay por abandono (INV-03):
    # la masa solo la escriben retomas humanas; el abandono la apaga.
    for forma in db.query(Forma).all():
        if decaer_arista(forma, ahora):
            contadores["formas_apagadas"] += 1

    # INV-14: toda pieza generada decae sin uso y se desactiva sola.
    from apps.worker.emergencia import apagar_pieza
    for pieza in db.query(Pieza).all():
        if apagar_pieza(pieza, ahora):
            contadores["piezas_apagadas"] += 1

    # WP-23 (INV-03): tareas del pool sin resolver vencen; el peso de
    # contribución inactivo cae a nulo (no es capital acumulable).
    from apps.worker.pool import vencer_tarea, decaer_peso
    for tarea in db.query(TareaComun).all():
        if vencer_tarea(tarea, ahora):
            contadores["tareas_vencidas"] += 1
    for fila in db.query(PesoContribucion).all():
        if decaer_peso(fila, ahora):
            contadores["pesos_nulos"] += 1

    # WP-25 (INV-13): toda sesión multiplayer abierta sin cierre se cierra sola;
    # su ficción efímera ya murió.
    from apps.motor_aventura.multiplayer import cerrar_sesion_huerfana
    for sesion in db.query(SesionMultiplayer).all():
        if cerrar_sesion_huerfana(sesion, ahora):
            contadores["sesiones_cerradas"] += 1

    # WP-28 (INV-03): la gramática que nadie usa se olvida; masa 0 y queda,
    # regramaticalizable si alguien retoma el comando.
    for cmd in db.query(ComandoVivo).all():
        if decaer_arista(cmd, ahora):
            contadores["comandos_olvidados"] += 1

    return contadores
