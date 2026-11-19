"""
LSH: el índice semántico distribuido (WP-24; 09_procomun §2.3, INV-11).

El problema honesto: un DHT (BitTorrent, Waku/discv5) encuentra por CLAVE exacta,
pero la resonancia semántica es por PROXIMIDAD (vecinos cercanos en el espacio
de embeddings). El k-NN distribuido perfecto es un problema abierto. El primer
paso real es el hashing que PRESERVA la proximidad: LSH de hiperplanos
aleatorios (random projection), la técnica estándar para similitud coseno.

Con hiperplanos comunes a toda la red (semilla fija del protocolo), dos vectores
con coseno alto caen en el mismo bucket, o en buckets a distancia de Hamming
pequeña, con alta probabilidad. Así la búsqueda por parecido se descompone en
lookups por bucket, y cada bucket es un content topic derivado que un semi-nodo
puede indexar. Ningún índice central: cada semi-nodo indexa los buckets que
elige, y el cliente mergea las lecturas (INV-11). La divergencia entre nodos
sigue siendo propiedad, no bug.

Alcance: LSH resuelve el MAPEO de la búsqueda semántica a lookups distribuidos.
El recall es aproximado (dos vecinos pueden caer en buckets lejanos): se sube
consultando un radio de Hamming y usando varias tablas. La red de semi-nodos
corriendo es despliegue (lo vivo).
"""
import hashlib

import numpy as np

# Semilla fija del protocolo: TODOS los nodos generan los MISMOS hiperplanos,
# así el hash de un vector es consistente en toda la red (como el content topic
# global es inamovible). Cambiarla re-particiona el índice entero.
SEMILLA_RED = 20260709
N_BITS_DEFAULT = 16          # bits por tabla: 2^16 buckets
N_TABLAS_DEFAULT = 4         # varias tablas independientes suben el recall
TOPIC_LSH = "/rizoma/v2/idx-lsh"


def hiperplanos(dim: int, n_bits: int = N_BITS_DEFAULT, tabla: int = 0,
                semilla: int = SEMILLA_RED) -> np.ndarray:
    """Matriz determinista de n_bits hiperplanos aleatorios en R^dim. Igual en
    todo nodo que use la misma semilla y tabla."""
    rng = np.random.default_rng(semilla + tabla * 1_000_003)
    return rng.standard_normal((n_bits, dim))


def hash_lsh(vector, n_bits: int = N_BITS_DEFAULT, tabla: int = 0,
             semilla: int = SEMILLA_RED) -> int:
    """El bucket de un vector en una tabla: el signo del producto con cada
    hiperplano, empaquetado en un entero de n_bits. Preserva proximidad coseno."""
    vec = np.asarray(vector, dtype=float)
    planos = hiperplanos(vec.shape[0], n_bits, tabla, semilla)
    bits = (planos @ vec) >= 0
    valor = 0
    for b in bits:
        valor = (valor << 1) | int(b)
    return valor


def firmas(vector, n_bits: int = N_BITS_DEFAULT, n_tablas: int = N_TABLAS_DEFAULT,
           semilla: int = SEMILLA_RED) -> list:
    """Un vector cae en un bucket por tabla. Varias tablas: si dos vecinos se
    separan en una, es probable que coincidan en otra (recall)."""
    return [hash_lsh(vector, n_bits, t, semilla) for t in range(n_tablas)]


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def buckets_candidatos(bucket: int, n_bits: int = N_BITS_DEFAULT, radio: int = 1) -> list:
    """Los buckets a consultar para un bucket dado: el propio y los que están a
    distancia de Hamming <= radio (voltear hasta `radio` bits). Sube el recall
    a costa de más lookups."""
    candidatos = {bucket}
    frontera = {bucket}
    for _ in range(radio):
        nueva = set()
        for b in frontera:
            for i in range(n_bits):
                nueva.add(b ^ (1 << i))
        candidatos |= nueva
        frontera = nueva
    return sorted(candidatos)


def bucket_topic(bucket: int, tabla: int = 0) -> str:
    """Cada bucket es un content topic derivado: un semi-nodo se suscribe a los
    buckets que indexa, y ahí llegan las intenciones cuyo vector cae en él. El
    índice rico (los vectores) sigue siendo local por nodo (INV-11)."""
    h = hashlib.sha256(f"{tabla}:{bucket}".encode()).hexdigest()[:16]
    return f"{TOPIC_LSH}/{h}"


def topics_de_consulta(vector, n_bits: int = N_BITS_DEFAULT,
                       n_tablas: int = N_TABLAS_DEFAULT, radio: int = 1) -> list:
    """Los topics que un cliente debe consultar para buscar por parecido: por
    cada tabla, el bucket del query y su vecindario de Hamming."""
    topics = []
    for tabla, bucket in enumerate(firmas(vector, n_bits, n_tablas)):
        for cand in buckets_candidatos(bucket, n_bits, radio):
            topics.append(bucket_topic(cand, tabla))
    seen, orden = set(), []
    for t in topics:
        if t not in seen:
            seen.add(t)
            orden.append(t)
    return orden


def topics_de_publicacion(vector, n_bits: int = N_BITS_DEFAULT,
                          n_tablas: int = N_TABLAS_DEFAULT) -> list:
    """Los topics donde una intención se anuncia (uno por tabla, su bucket
    exacto). Un semi-nodo suscripto a ese bucket la indexa."""
    return [bucket_topic(bucket, tabla)
            for tabla, bucket in enumerate(firmas(vector, n_bits, n_tablas))]
