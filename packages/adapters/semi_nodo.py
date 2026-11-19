"""
Semi-nodo y enrutamiento del índice distribuido (WP-24; INV-11).

Un semi-nodo es un cliente con fierro que corre embedder local e indexa: en vez
de solo consumir nodos ajenos, DECLARA qué buckets LSH sirve y responde queries
de esos buckets. Sin registro central: cada cliente arma su propia lista de
semi-nodos (como la federación), texto plano compartible.

La búsqueda por parecido se enruta a los semi-nodos que cubren los buckets del
query, sus lecturas se mergean localmente, y la divergencia entre embedders
sigue siendo propiedad (INV-11). Un semi-nodo que miente se disuelve en la
redundancia: cada bucket puede servirlo más de uno, y el cliente descarta al mal
lector de su lista, como en la federación. Sin staking, sin castigo.
"""
from packages.adapters import federacion, lsh


def cubre(declaracion: dict, topic: str) -> bool:
    """Un semi-nodo declara { url, buckets: [topic, ...] } (o buckets: "*" para
    indexar todo). ¿Cubre este topic de bucket?"""
    buckets = declaracion.get("buckets", "*")
    return buckets == "*" or topic in buckets


def semi_nodos_para(vector, registro: list, n_bits: int = lsh.N_BITS_DEFAULT,
                    n_tablas: int = lsh.N_TABLAS_DEFAULT, radio: int = 1) -> dict:
    """A qué semi-nodos consultar para un query: los que cubren alguno de los
    topics de bucket del vector. Devuelve {url: [topics que cubre]}. La
    redundancia (varios que cubren el mismo bucket) es deseada."""
    topics = lsh.topics_de_consulta(vector, n_bits, n_tablas, radio)
    plan = {}
    for decl in registro:
        url = decl.get("url")
        if not url:
            continue
        cubiertos = [t for t in topics if cubre(decl, t)]
        if cubiertos:
            plan[url] = cubiertos
    return plan


async def buscar_por_parecido(vector, q_texto: str, registro: list, limite: int = 10,
                              fetch=None, **lsh_kw) -> dict:
    """Enruta la búsqueda semántica a los semi-nodos que cubren los buckets del
    query y mergea localmente (reusa el merge de la federación: conserva TODAS
    las lecturas por nodo, la divergencia visible). Un semi-nodo caído no voltea
    la búsqueda: simplemente no participa."""
    plan = semi_nodos_para(vector, registro, **lsh_kw)
    urls = list(plan.keys())
    merged = await federacion.consultar_nodos(urls, q_texto, limite, fetch=fetch)
    merged["ruteo_lsh"] = {"topics_consultados": lsh.topics_de_consulta(vector, **lsh_kw),
                           "semi_nodos_consultados": urls}
    merged["nota_lsh"] = ("índice por proximidad (LSH): el recall es aproximado; "
                          "se sube con más tablas y mayor radio de Hamming (INV-11)")
    return merged


def registrar_intencion(vector, n_bits: int = lsh.N_BITS_DEFAULT,
                        n_tablas: int = lsh.N_TABLAS_DEFAULT) -> list:
    """Dónde se anuncia una intención para que los semi-nodos la indexen: sus
    topics de bucket (uno por tabla). Se suma a la REGLA DEL PISO: la emisión va
    SIEMPRE al global; estos topics derivados agregan, jamás reemplazan."""
    return lsh.topics_de_publicacion(vector, n_bits, n_tablas)
