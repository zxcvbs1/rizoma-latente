"""
WP-30 · El antagonista de doctrina: canon servible y herejías como corpus
de regresión (jul 2026). Un GM explicó el ciclo de la lengua y los
injertos poniéndole cerebro al nodo tres veces en un mismo texto; esto
mide cualquier explicación del protocolo contra el canon
(apps/api/brujula.py, guía "resonancias") con un catálogo de herejías
regex-detectables (tests/fixtures/herejias_doctrina.json).

Corre sin servicios:
    .venv/bin/python tests/test_wp30_doctrina.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from tests.eval_doctrina import CASO_REGRESION, evaluar


def test_canon_pasa_limpio():
    """Las guías del canon (incluida 'resonancias') dan cero herejías: el
    canon AFIRMA, jamás nombra las herejías que evita."""
    from apps.api.brujula import guia_de
    for familia in ("aventura", "corrida", "acervo", "sesion", "pool", "resonancias"):
        reporte = evaluar(guia_de(familia)["guia"])
        assert not reporte["herejias"], \
            f"guia_de('{familia}'): herejías detectadas: " \
            f"{[h['id'] for h in reporte['herejias']]}"


def test_caso_sintetico_da_infiel():
    """El caso sintético de regresión marca las tres herejías que dispararon WP-30."""
    with open(CASO_REGRESION, encoding="utf-8") as fh:
        texto = fh.read()
    reporte = evaluar(texto)
    assert reporte["veredicto"] == "INFIEL"
    ids = {h["id"] for h in reporte["herejias"]}
    esperadas = {"nodo-con-cerebro", "masa-dispara-generacion", "nodo-procesa-personas"}
    assert esperadas <= ids, f"faltan: {esperadas - ids}"


def test_negacion_no_es_herejia():
    """matchmaking-central es 'solo_afirmativo': una negación legítima no
    debe contar como herejía."""
    reporte = evaluar("en Rizoma no hay un algoritmo central de matchmaking, "
                       "cada nodo sirve su propia lectura")
    ids = {h["id"] for h in reporte["herejias"]}
    assert "matchmaking-central" not in ids


def test_verdades_requeridas():
    """Un texto sobre la lengua sin 'masa' ni 'decae/olvid' reporta esas
    verdades como faltantes."""
    texto = ("La lengua de Rizoma es un vocabulario de comandos que "
             "cualquiera puede acuñar emitiendo con !palabra.")
    reporte = evaluar(texto, temas=["lengua"])
    ids_faltantes = {v["id"] for v in reporte["verdades_faltantes"]}
    assert "masa-por-uso" in ids_faltantes
    assert "olvido" in ids_faltantes


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
