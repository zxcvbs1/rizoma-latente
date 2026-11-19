"""
Marcos teóricos (lentes de la escala comunidad; 03_comunidad §4).

Conmutables y explícitos: el marco activo se declara en TODO output. La
ideología es un parámetro, no un defecto. Heredados del simSocial original
(deprecated/simSocial), reescritos como datos del protocolo.
"""

MARCOS = {
    "bienes_comunes": {
        "nombre": "Bienes comunes (Ostrom)",
        "estresa": "gobernanza del recurso compartido: reglas, monitoreo, sanciones graduadas, resolución de conflictos",
        "crisis_tipicas": ["sobreuso del recurso", "free riding", "fallo de gobernanza", "captura por minoría"],
        "metricas": ["salud del recurso", "participación en reglas", "conflictos resueltos"],
    },
    "cuidado": {
        "nombre": "Ética del cuidado (feminista)",
        "estresa": "trabajo invisible, cargas asimétricas, quién sostiene a quién",
        "crisis_tipicas": ["burnout de cuidadoras", "trabajo invisible no reconocido", "cadenas de cuidado rotas"],
        "metricas": ["distribución de cargas", "reconocimiento", "sostenibilidad del cuidado"],
    },
    "decrecimiento": {
        "nombre": "Decrecimiento",
        "estresa": "suficiencia frente a acumulación, ritmos, límites materiales",
        "crisis_tipicas": ["aceleración insostenible", "dependencia de flujos externos", "acumulación que rompe lazos"],
        "metricas": ["suficiencia material", "autonomía de flujos", "ritmo sostenible"],
    },
    "colonialidad": {
        "nombre": "Colonialidad del poder",
        "estresa": "jerarquías heredadas, voces subordinadas, saberes descalificados",
        "crisis_tipicas": ["fragmentación epistémica", "extractivismo interno", "jerarquía naturalizada"],
        "metricas": ["diversidad de voces con peso", "saberes locales en uso", "decisiones descentradas"],
    },
    "capitales": {
        "nombre": "Materialismo de capitales (Bourdieu)",
        "estresa": "conversión y concentración de capital social, cultural y económico",
        "crisis_tipicas": ["concentración de capital social", "gatekeeping", "desigualdad reproducida"],
        "metricas": ["distribución de capitales", "movilidad interna", "puentes entre grupos"],
    },
    "economia_social": {
        "nombre": "Economía social y solidaria",
        "estresa": "reciprocidad, redistribución, viabilidad sin acumulación",
        "crisis_tipicas": ["colapso de reciprocidad", "dependencia de subsidios", "burocratización del lazo"],
        "metricas": ["circuitos de reciprocidad", "viabilidad material", "densidad de intercambios"],
    },
}


def _lente_publicada(db, marco: str):
    """Una forma-lente publicada del acervo usable como marco (tesis: la lente
    es parámetro abierto). Resuelve por nombre exacto (case-insensitive) o por
    forma_id; si hay empate de nombre, la de mayor masa y más reciente."""
    if db is None or not marco:
        return None
    from packages.domain.models import Forma
    candidatas = [f for f in db.query(Forma).all()
                  if f.tipo == "lente" and f.estado == "publicada"
                  and (f.id == marco or (f.nombre or "").strip().lower() == marco.strip().lower())]
    if not candidatas:
        return None
    candidatas.sort(key=lambda f: (f.mass or 0, f.last_touched or f.created_at), reverse=True)
    return candidatas[0]


def marco_valido(nombre: str, db=None) -> bool:
    return nombre in MARCOS or _lente_publicada(db, nombre) is not None


def reglas_de(nombre: str, db=None) -> dict:
    if nombre in MARCOS:
        return MARCOS[nombre]
    forma = _lente_publicada(db, nombre)
    if forma is None:
        raise KeyError(f"marco desconocido: {nombre}")
    import json
    try:
        ctx = json.loads(forma.contexto_material or "{}")
    except Exception:
        ctx = {}
    return {
        "nombre": forma.nombre,
        "estresa": forma.cuerpo or "",
        "crisis_tipicas": ctx.get("crisis_tipicas", []),
        "metricas": ctx.get("metricas", []),
        "del_acervo": True,
        "forma_id": forma.id,
    }
