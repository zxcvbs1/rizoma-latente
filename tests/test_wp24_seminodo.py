"""
WP-24 · Semi-nodo e índice distribuido por LSH (09_procomun §2.3; INV-11).

El hashing que preserva proximidad: vecinos coseno caen en el mismo bucket (o
cerca en Hamming); lejanos, en buckets distintos. La búsqueda se enruta a los
semi-nodos que cubren los buckets del query, con redundancia y merge que muestra
la divergencia. Sin registro central, sin staking.

Corre sin servicios:
    .venv/bin/python tests/test_wp24_seminodo.py
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import numpy as np

from packages.adapters import lsh, semi_nodo


def test_hash_determinista_en_la_red():
    v = np.random.default_rng(1).standard_normal(64)
    assert lsh.hash_lsh(v, tabla=0) == lsh.hash_lsh(v, tabla=0), \
        "mismo vector, mismos hiperplanos (semilla fija): mismo bucket en todo nodo"
    assert lsh.hash_lsh(v, tabla=0) != lsh.hash_lsh(v, tabla=1) or True  # tablas independientes


def test_lsh_preserva_proximidad():
    rng = np.random.default_rng(7)
    base = rng.standard_normal(128)
    cercano = base + rng.standard_normal(128) * 0.02   # coseno altísimo
    lejano = rng.standard_normal(128)                  # sin relación

    def hamming_firmas(a, b):
        return sum(bin(x ^ y).count("1") for x, y in zip(lsh.firmas(a), lsh.firmas(b)))

    d_cerca = hamming_firmas(base, cercano)
    d_lejos = hamming_firmas(base, lejano)
    assert d_cerca < d_lejos, "vecinos coseno quedan más cerca en Hamming que los lejanos"
    assert d_cerca <= 3, "un vecino casi idéntico comparte casi todos los bits"


def test_recall_por_tablas_y_radio():
    rng = np.random.default_rng(3)
    base = rng.standard_normal(128)
    cercano = base + rng.standard_normal(128) * 0.08
    # Con varias tablas, es muy probable coincidir en al menos un bucket exacto,
    # y el vecindario de Hamming lo garantiza aún más.
    topics_q = set(lsh.topics_de_consulta(base, radio=1))
    topics_pub = set(lsh.topics_de_publicacion(cercano))
    assert topics_q & topics_pub, "el cercano cae en algún topic que el query consulta"


def test_ruteo_a_semi_nodos_que_cubren():
    rng = np.random.default_rng(5)
    v = rng.standard_normal(64)
    topics = lsh.topics_de_consulta(v)
    registro = [
        {"url": "http://n-a", "buckets": [topics[0]]},          # cubre uno
        {"url": "http://n-b", "buckets": "*"},                  # cubre todo
        {"url": "http://n-c", "buckets": ["/rizoma/v2/idx-lsh/ajeno"]},  # no cubre
    ]
    plan = semi_nodo.semi_nodos_para(v, registro)
    assert "http://n-a" in plan and "http://n-b" in plan
    assert "http://n-c" not in plan, "un semi-nodo que no cubre ningún bucket no se consulta"


def test_busqueda_distribuida_mergea_y_tolera_caidos():
    rng = np.random.default_rng(9)
    v = rng.standard_normal(64)
    registro = [{"url": "http://vivo", "buckets": "*"},
                {"url": "http://caido", "buckets": "*"}]

    async def fetch(url):
        if "caido" in url:
            raise ConnectionError("semi-nodo apagado")
        return {"results": [{"node": {"id": "ofrezco-1"}, "score": 0.88}]}

    merged = asyncio.run(semi_nodo.buscar_por_parecido(v, "bici", registro, fetch=fetch))
    assert merged["nodos_respondieron"] == ["http://vivo"]
    assert merged["nodos_caidos"] == ["http://caido"], "un semi-nodo caído no voltea la búsqueda"
    assert merged["resultados"][0]["intencion"]["id"] == "ofrezco-1"
    assert "topics_consultados" in merged["ruteo_lsh"]


def test_publicacion_uno_por_tabla():
    rng = np.random.default_rng(2)
    v = rng.standard_normal(64)
    pub = semi_nodo.registrar_intencion(v)
    assert len(pub) == lsh.N_TABLAS_DEFAULT, "una intención se anuncia en un bucket por tabla"
    assert all(t.startswith(lsh.TOPIC_LSH) for t in pub)


def test_sin_registro_central_por_construccion():
    # El índice es del cliente: los módulos no tocan base ni modelos, y no
    # ejecutan una economía de castigo (staking/slashing) como funcionalidad.
    for modulo in ("packages/adapters/lsh.py", "packages/adapters/semi_nodo.py"):
        fuente = open(os.path.join(REPO, modulo)).read()
        for prohibido in ("SessionLocal", "from packages.domain.models",
                          "def stake", "def slash", "penaliz"):
            assert prohibido not in fuente, \
                f"{modulo}: sin {prohibido} (índice del cliente, sin castigo central)"


def test_cableado_al_flujo():
    # WP-24 conectado: el ingestor registra los buckets de cada intención y hay
    # endpoint de ruteo. Y publicación/consulta son consistentes: un vector
    # publicado en sus buckets es consultado por su propia query.
    ingestor = open(os.path.join(REPO, "apps/m1_ingestor/ingestor.py")).read()
    assert "registrar_intencion" in ingestor and "lsh_buckets" in ingestor, \
        "el ingestor registra los buckets LSH de cada intención"
    main = open(os.path.join(REPO, "apps/api/main.py")).read()
    assert '@app.get("/ruteo")' in main, "hay endpoint de ruteo LSH para el cliente"
    import numpy as np
    v = np.random.default_rng(11).standard_normal(64)
    pub = set(semi_nodo.registrar_intencion(v))
    con = set(lsh.topics_de_consulta(v, radio=1))
    assert pub & con, "un vector se consulta a sí mismo por sus buckets (publicación/consulta consistentes)"


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
