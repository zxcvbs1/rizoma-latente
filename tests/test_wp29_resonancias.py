"""
WP-29 · El módulo de resonancias afinado por el banco de comportamiento
(jul 2026, del goal del autor: "que sea útil sin que tenga que probar yo
por Telegram").

Cubre las piezas PURAS (sin servicios): el piso semántico existe como
parámetro del engine, la deduplicación por texto, el corpus del banco está
bien formado, y el menú de plataforma filtra lo que Telegram no acepta sin
tirar abajo el registro entero. Las piezas con servicios viven en
tests/eval_resonancias.py (banco aislado, necesita Ollama) y
tests/eval_resonancias_e2e.py (antagonista contra el nodo vivo).

Corre sin servicios:
    .venv/bin/python tests/test_wp29_resonancias.py
"""
import inspect
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from packages.adapters.engine import RelevanceEngine
from packages.puentes.kit import comandos_para_menu


def test_el_piso_es_parametro_del_engine():
    """El umbral semántico se aplica sobre el coseno puro EN el engine, no
    como filtro cosmético del caller."""
    sig = inspect.signature(RelevanceEngine.search_nodes)
    assert "umbral_semantico" in sig.parameters
    assert sig.parameters["umbral_semantico"].default == 0.0, \
        "sin pedirlo explícito, el engine no filtra (compatibilidad)"


def test_dedup_colapsa_textos_identicos():
    resultados = [
        {"node": {"text_raw": "Busco miel"}, "score": 0.9},
        {"node": {"text_raw": "busco miel "}, "score": 0.8},
        {"node": {"text_raw": "Busco miel"}, "score": 0.7},
        {"node": {"text_raw": "otra cosa"}, "score": 0.6},
    ]
    unicos = RelevanceEngine.deduplicar_resultados(resultados)
    assert len(unicos) == 2, "el mismo texto N veces es UNA resonancia"
    assert unicos[0]["score"] == 0.9, "conserva el de mayor score (primero)"
    assert unicos[1]["node"]["text_raw"] == "otra cosa"


def test_corpus_del_banco_bien_formado():
    with open(os.path.join(REPO, "tests", "fixtures", "corpus_resonancias.json")) as fh:
        corpus = json.load(fh)
    emisiones, sondas = corpus["emisiones"], corpus["sondas"]
    assert len(emisiones) == 30
    assert len(sondas) == 10
    for sonda in sondas:
        assert sonda["esperados"], f"{sonda['id']}: sin esperados no hay verdad que medir"
        assert sonda["prohibidos"], f"{sonda['id']}: sin prohibidos no hay antagonista"
        for eid in sonda["esperados"] + sonda["prohibidos"]:
            assert eid in emisiones, f"{sonda['id']}: id {eid} no existe en el corpus"
    # Toda emisión porta comando (el banco también prueba que el comando NO
    # pese en el vector, así que tiene que estar presente en el texto crudo).
    assert all(t.startswith("!") for t in emisiones.values())


def test_menu_de_plataforma_filtra_sin_censurar_la_lengua():
    """Telegram solo acepta a-z0-9_: !sueño (con ñ) tiraba abajo el registro
    ENTERO del menú. El filtro deja pasar lo mostrable y saltea el resto; el
    comando filtrado sigue vivo en la lengua (el menú es comodidad, no gate)."""
    lengua = {"lengua": [
        {"comando": "sueño", "masa": 2.0},
        {"comando": "!busco", "masa": 5.0},
        {"comando": "invoco", "masa": 1.0},
        {"comando": "?", "masa": 1.0},
    ]}
    menu = comandos_para_menu(lengua)
    slugs = [c["comando"] for c in menu]
    assert "busco" in slugs, "el ! se pela para el menú nativo"
    assert "invoco" in slugs
    assert all("ñ" not in s and "?" not in s for s in slugs), \
        "lo que la plataforma no acepta se saltea sin romper el resto"
    assert len(menu) == 2


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
            print(f"ERROR {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} tests OK")
    sys.exit(1 if failures else 0)
