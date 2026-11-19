"""
Controles del perfil a escala red (WP-04, INV-05; CU-T6).

Ver y llevarse: la huella completa de una llave (lo que la red sabe: nada más
existe). Borrar: cascada real sobre nodos (texto y vector viven juntos),
vínculos, sinapsis y actor. Solo el dueño de la llave, con firma.

Canonical (extiende contracts/security.md):
    rizoma.actor.patch|{actor_id}|{timestamp}|{nonce}|{action}
    action: export | erase
"""
from packages.domain.models import Actor, Deslizamiento, Link, Node, Partida, Synapse, TerminoMapa


def canonical_actor(actor_id: str, timestamp: str, nonce: str, action: str) -> str:
    return f"rizoma.actor.patch|{actor_id}|{timestamp}|{nonce}|{action}"


def _es_del_actor(valor, actor_id: str) -> bool:
    return (valor or "").lower() == actor_id.lower()


def armar_huella(db, actor_id: str) -> dict:
    """CU-T6: llave, intenciones (vivas y archivadas), vínculos, sinapsis,
    reputación con su decay. Exportable y legible; nada más existe."""
    actor = None
    for fila in db.query(Actor).all():
        if _es_del_actor(fila.id, actor_id):
            actor = fila
            break

    nodos = [n for n in db.query(Node).all() if _es_del_actor(n.actor_id, actor_id)]
    links = [l for l in db.query(Link).all() if _es_del_actor(l.actor_id, actor_id)]
    sinapsis = [s for s in db.query(Synapse).all()
                if _es_del_actor(s.origin_actor_id, actor_id)
                or _es_del_actor(s.target_actor_id, actor_id)]

    terminos = [t for t in db.query(TerminoMapa).all() if _es_del_actor(t.jugador_llave, actor_id)]
    aristas = [d for d in db.query(Deslizamiento).all() if _es_del_actor(d.jugador_llave, actor_id)]
    partidas = [p for p in db.query(Partida).all() if _es_del_actor(p.jugador_llave, actor_id)]

    return {
        "llave": actor_id,
        "reputacion": float(actor.reputation) if actor else None,
        "ultima_actividad": actor.last_seen_at.isoformat() if actor and actor.last_seen_at else None,
        "intenciones": [{
            "id": n.id, "texto": n.text_raw, "estado": n.state,
            "masa": float(n.mass) if n.mass is not None else None,
            "creada": n.created_at.isoformat() if n.created_at else None,
        } for n in nodos],
        "vinculos": [{
            "id": str(l.id), "nodo_a": l.node_a_id, "nodo_b": l.node_b_id,
            "creado": l.created_at.isoformat() if l.created_at else None,
        } for l in links],
        "sinapsis": [{
            "id": str(s.id), "estado": s.status,
            "con": s.target_actor_id if _es_del_actor(s.origin_actor_id, actor_id) else s.origin_actor_id,
            "creada": s.created_at.isoformat() if s.created_at else None,
        } for s in sinapsis],
        "topologia": {
            "terminos": [t.termino for t in terminos],
            "deslizamientos": [{
                "de": d.de_termino, "hacia": d.hacia_termino, "evidencia": d.evidencia,
                "escena": d.escena_contexto, "intensidad": d.intensidad,
                "masa": float(d.mass) if d.mass is not None else None,
            } for d in aristas],
        },
        "partidas": [{"id": p.id, "estado": p.estado} for p in partidas],
        "nota": "Esto es todo lo que la red sabe de esta llave. Nada más existe.",
    }


def borrar_actor(db, actor_id: str) -> dict:
    """Borrar borra (INV-05): cascada sobre sinapsis, vínculos, nodos (texto y
    vector) y el actor. Tras esto, ninguna búsqueda ni resonancia puede
    referenciar a la persona. El caller hace commit."""
    contadores = {"sinapsis": 0, "vinculos": 0, "intenciones": 0, "actor": 0}

    for s in list(db.query(Synapse).all()):
        if _es_del_actor(s.origin_actor_id, actor_id) or _es_del_actor(s.target_actor_id, actor_id):
            db.delete(s)
            contadores["sinapsis"] += 1

    for l in list(db.query(Link).all()):
        if _es_del_actor(l.actor_id, actor_id):
            db.delete(l)
            contadores["vinculos"] += 1

    for n in list(db.query(Node).all()):
        if _es_del_actor(n.actor_id, actor_id):
            db.delete(n)
            contadores["intenciones"] += 1

    contadores["topologia"] = 0
    for t in list(db.query(TerminoMapa).all()):
        if _es_del_actor(t.jugador_llave, actor_id):
            db.delete(t)
            contadores["topologia"] += 1
    for d in list(db.query(Deslizamiento).all()):
        if _es_del_actor(d.jugador_llave, actor_id):
            db.delete(d)
            contadores["topologia"] += 1

    contadores["partidas"] = 0
    from apps.motor_aventura import motor as motor_aventura
    for p in list(db.query(Partida).all()):
        if _es_del_actor(p.jugador_llave, actor_id):
            motor_aventura._memorias.pop(p.id, None)
            db.delete(p)
            contadores["partidas"] += 1

    for a in list(db.query(Actor).all()):
        if _es_del_actor(a.id, actor_id):
            db.delete(a)
            contadores["actor"] += 1

    return contadores


def borrar_rastros_redis(redis_client, actor_id: str, hoy: str) -> None:
    """La huella operativa también se borra (first_seen, contador del día).
    Los nonces expiran solos en 24h y no contienen más que la llave."""
    try:
        redis_client.delete(f"first_seen:{actor_id}")
        redis_client.delete(f"emits:{actor_id}:{hoy}")
    except Exception:
        pass
