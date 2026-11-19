"""
WP-10 · Federación desde el cliente (01_red §8, INV-11; CU-R8).

El nodo sirve solo su lectura local; el cliente consulta N nodos con su lista
propia (texto plano), mergea localmente y la divergencia entre embedders se
muestra, no se resuelve. Sin registro central de nodos.

Corre sin servicios:
    .venv/bin/python tests/test_wp10_federacion.py
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from packages.adapters import federacion


def test_lista_de_nodos_como_texto_plano():
    texto = "http://nodo-a:8000, http://nodo-b:8000/\nhttp://nodo-a:8000\n"
    assert federacion.parse_lista_nodos(texto) == [
        "http://nodo-a:8000", "http://nodo-b:8000"], \
        "la lista viaja como texto, se deduplica y se normaliza"


def test_divergencia_se_muestra_no_se_resuelve():
    respuestas = {
        "http://a": {"results": [
            {"node": {"id": "ofrezco-1", "text_raw": "!ofrezco bici"}, "score": 0.91},
            {"node": {"id": "busco-9", "text_raw": "!busco funda"}, "score": 0.55}]},
        "http://b": {"results": [
            {"node": {"id": "ofrezco-1", "text_raw": "!ofrezco bici"}, "score": 0.74}]},
    }
    merged = federacion.mergear(respuestas)
    primera = merged["resultados"][0]
    assert primera["intencion"]["id"] == "ofrezco-1"
    assert primera["divergencia"] is True and len(primera["lecturas"]) == 2, \
        "dos embedders, dos lecturas: ambas visibles (INV-11)"
    assert primera["lecturas"][0] == {"nodo": "http://a", "score": 0.91}
    assert merged["resultados"][1]["divergencia"] is False


def test_orden_por_la_mejor_lectura_y_limite():
    respuestas = {"http://a": {"results": [
        {"node": {"id": f"n-{i}"}, "score": i / 10} for i in range(1, 6)]}}
    merged = federacion.mergear(respuestas, limite=3)
    assert [r["mejor_score"] for r in merged["resultados"]] == [0.5, 0.4, 0.3]


def test_nodo_caido_no_voltea_la_lectura():
    async def fetch(url):
        if "caido" in url:
            raise ConnectionError("nodo apagado")
        return {"results": [{"node": {"id": "x-1"}, "score": 0.8}]}

    merged = asyncio.run(federacion.consultar_nodos(
        ["http://vivo:8000", "http://caido:8000"], "bici", fetch=fetch))
    assert merged["nodos_respondieron"] == ["http://vivo:8000"]
    assert merged["nodos_caidos"] == ["http://caido:8000"]
    assert len(merged["resultados"]) == 1
    assert "divergencia" in merged["nota"] or "propiedad" in merged["nota"]


def test_sin_registro_central_por_construccion():
    fuente = open(os.path.join(REPO, "packages/adapters/federacion.py")).read()
    for prohibido in ("models", "SessionLocal", "db.query", "Peer"):
        assert prohibido not in fuente, \
            f"la lista de nodos es del cliente: nada de {prohibido} en la federación"


def test_el_nodo_ya_no_federa_por_su_cuenta():
    fuente = open(os.path.join(REPO, "apps/api/main.py")).read()
    assert "db.query(Peer)" not in fuente, \
        "el merge server-side con reputación de peers quedó retirado (lectura coronada)"
    assert "peer.reputation" not in fuente


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
