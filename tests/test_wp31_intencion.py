"""
WP-31 · El puente lee la intención por resonancia (01_red §12 bis).

El puente no adivina por keywords: embebe la frase y la compara contra
prototipos de los verbos de la lengua (packages/puentes/kit.py). Sin
resonancia sobre el umbral, el deseo puro es una emisión legítima (comando
None, jamás una excepción). Los vectores de los prototipos se cachean:
solo el texto del usuario se embebe por lectura.

Corre sin servicios (embedder falso determinista, sin Ollama):
    .venv/bin/python tests/test_wp31_intencion.py
"""
import asyncio
import hashlib
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from packages.puentes import kit


def _embedder_controlado(vectores: dict, default=(0.0, 1.0, 0.0)):
    """Embedder falso: vectores exactos para las claves dadas, un vector fijo
    y distinto (por eso "no resuena con nada") para cualquier otro texto."""
    async def embedder(texto):
        return list(vectores.get(texto, default))
    return embedder


def _embedder_determinista_contador():
    """Embedder local falso (sin Ollama): vector estable por texto (hash),
    con contador de llamadas para verificar el cache de prototipos."""
    llamadas = {"count": 0}

    async def embedder(texto: str):
        llamadas["count"] += 1
        h = hashlib.sha256(texto.encode()).digest()
        return [b / 255.0 for b in (h * 2)[:16]]

    return embedder, llamadas


def test_texto_que_resuena_con_prototipo_de_busco_devuelve_busco():
    prototipos = {"busco": ["prototipo busco"], "ofrezco": ["prototipo ofrezco"]}
    embedder = _embedder_controlado({
        "prototipo busco": (1.0, 0.0, 0.0),
        "prototipo ofrezco": (0.0, 1.0, 0.0),
        "quiero encontrar algo urgente": (1.0, 0.0, 0.0),  # mismo vector: coseno 1.0
    })
    lectura = asyncio.run(kit.leer_intencion(
        "quiero encontrar algo urgente", embedder, prototipos=prototipos))
    assert lectura["comando"] == "busco", lectura
    assert lectura["afinidad"] > kit.UMBRAL_INTENCION, lectura


def test_texto_que_no_resuena_devuelve_comando_none_sin_excepcion():
    prototipos = {"busco": ["prototipo busco"], "ofrezco": ["prototipo ofrezco"]}
    embedder = _embedder_controlado({
        "prototipo busco": (1.0, 0.0, 0.0),
        "prototipo ofrezco": (0.0, 1.0, 0.0),
        # "viva la libertad" cae al default: (0, 1, 0) contra (1,0,0) y (0,1,0)...
    }, default=(0.0, 0.0, 1.0))  # ortogonal a ambos prototipos: coseno 0 con los dos
    lectura = asyncio.run(kit.leer_intencion(
        "viva la libertad", embedder, prototipos=prototipos))
    assert lectura["comando"] is None, "deseo puro: comando None, jamás una excepción"
    assert lectura["afinidad"] == 0.0, lectura


def test_cache_de_prototipos_evita_reembeber():
    embedder, llamadas = _embedder_determinista_contador()
    total_prototipos = sum(len(frases) for frases in kit.PROTOTIPOS_INTENCION.values())

    asyncio.run(kit.leer_intencion("frase de prueba uno", embedder))
    llamadas_primera_lectura = llamadas["count"]
    assert llamadas_primera_lectura == total_prototipos + 1, (
        f"la primera lectura embebe los {total_prototipos} prototipos + 1 texto, "
        f"llamó {llamadas_primera_lectura}")

    asyncio.run(kit.leer_intencion("frase de prueba dos", embedder))
    llamadas_segunda_lectura = llamadas["count"] - llamadas_primera_lectura
    assert llamadas_segunda_lectura == 1, (
        "la segunda lectura solo embebe el texto nuevo: los prototipos ya están "
        f"cacheados; llamó {llamadas_segunda_lectura} veces de más")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests OK")
    sys.exit(1 if failures else 0)
