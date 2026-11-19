"""
Alarmas de salud (WP-11; INV-13, INV-16; 02_sujeto §6, 01_red §9).

Señales agregadas y ANÓNIMAS, visibles en el propio sistema: el espejo las
muestra, nadie las consume. Son alarmas, jamás KPIs: este módulo no escribe
nada (el test lo verifica sobre el fuente) y ningún motor lo importa.
"""

MESES_SOSTENIDOS = 3


def _mes(dt) -> str:
    return dt.strftime("%Y-%m") if dt else "?"


def _decreciente_sostenida(valores, tramo: int = MESES_SOSTENIDOS) -> bool:
    if len(valores) < tramo:
        return False
    cola = valores[-tramo:]
    return all(cola[i] > cola[i + 1] for i in range(len(cola) - 1))


def _creciente_sostenida(valores, tramo: int = MESES_SOSTENIDOS) -> bool:
    if len(valores) < tramo:
        return False
    cola = valores[-tramo:]
    return all(cola[i] < cola[i + 1] for i in range(len(cola) - 1))


def senal_surco_riel(sinapsis, nodos_por_id) -> dict:
    """INV-16: los surcos deben ensanchar el repertorio de coordinaciones.
    Diversidad (tipos de intención por mes) decreciente sostenida = alarma.
    Jamás optimización: la señal se muestra y nada más."""
    por_mes = {}
    for sinapsis_fila in sinapsis:
        if sinapsis_fila.status != "active":
            continue
        mes = _mes(sinapsis_fila.created_at)
        fila = por_mes.setdefault(mes, {"mes": mes, "coordinaciones": 0, "_tipos": set()})
        fila["coordinaciones"] += 1
        for nodo_id in (sinapsis_fila.origin_node_id, sinapsis_fila.target_node_id):
            nodo = nodos_por_id.get(nodo_id)
            if nodo is not None:
                fila["_tipos"].add(nodo.command_slug or "?")
    serie = sorted(por_mes.values(), key=lambda fila: fila["mes"])
    for fila in serie:
        fila["diversidad"] = len(fila.pop("_tipos"))
    alarma = _decreciente_sostenida([fila["diversidad"] for fila in serie])
    return {
        "serie": serie,
        "alarma": alarma,
        "lectura": ("diversidad decreciente sostenida: el surco se está volviendo riel"
                    if alarma else "el repertorio se sostiene"),
    }


def senal_absorcion(partidas) -> dict:
    """INV-13: duración media de las partidas cerradas, por mes. Creciente
    sostenida = las sesiones no quieren terminar. Agregado sin persona: acá
    entran filas con llave y salen números sin nadie."""
    por_mes = {}
    for partida in partidas:
        if partida.estado != "cerrada" or not partida.closed_at or not partida.created_at:
            continue
        mes = _mes(partida.created_at)
        duracion = (partida.closed_at - partida.created_at).total_seconds() / 60.0
        fila = por_mes.setdefault(mes, {"mes": mes, "partidas": 0, "_total": 0.0})
        fila["partidas"] += 1
        fila["_total"] += duracion
    serie = sorted(por_mes.values(), key=lambda fila: fila["mes"])
    for fila in serie:
        fila["duracion_media_min"] = round(fila.pop("_total") / fila["partidas"], 1)
    alarma = _creciente_sostenida([fila["duracion_media_min"] for fila in serie])
    return {
        "serie": serie,
        "alarma": alarma,
        "lectura": ("las sesiones no quieren terminar: la aventura está cambiando de familia"
                    if alarma else "toda partida tiene final propio"),
    }
