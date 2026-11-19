"""
Prueba de que el escalón Concordia CORRE de verdad acá cuando la librería está
(WP-16; 06_motor_simulacion §2.1). Verificado contra gdm-concordia==2.4.0.

Se SALTEA limpio si `gdm-concordia` no está instalada (es una dependencia
opcional): la batería pasa en un clon fresco sin ella. Cuando está, ejercita el
mapeo real: memoria asociativa con un embedder local + modelo envuelto por la
frontera + agente construido desde disposiciones. Usa NoLanguageModel (mock, sin
LLM) y un embedder determinista: no necesita Ollama ni una clave de API, así que
mide la MECÁNICA, no el contenido (sin un LLM, el acto sale vacío, y eso es
exactamente el punto honesto de la comparación).

    .venv/bin/python tests/test_runtime_concordia_real.py
"""
import hashlib
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.motor_simulacion.runtime_concordia import RuntimeConcordia, _concordia_instalada
from packages.domain import frontera

CONCORDIA = _concordia_instalada()


def _embedder_determinista(texto: str):
    """Embedder local falso (sin Ollama): un vector estable por texto. Cumple el
    contrato que pide Concordia (str -> ndarray) sin depender de un servicio."""
    import numpy as np
    h = hashlib.sha256(texto.encode()).digest()
    return np.frombuffer((h * 24)[:768 * 4], dtype=np.float32).copy()


def test_corre_la_mecanica_con_embedder_local_y_frontera():
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from concordia.language_model import no_language_model
    r = RuntimeConcordia(modelo=no_language_model.NoLanguageModel(),
                         embedder=_embedder_determinista)
    assert r.disponible() is True, "con librería + modelo, disponible"
    assert r.describir()["genera"] is True

    acto = r.producir_acto({
        "rol": "la-que-riega",
        "disposiciones": "cuando el recurso escasea, lo comparte antes de acumularlo",
        "situacion": "El pozo está casi seco y otro rol pide agua.",
    })
    assert isinstance(acto, dict) and "descripcion" in acto and acto["costo"] == {}
    # Con NoLanguageModel el contenido es vacío/mínimo: la mecánica corrió, no hay LLM.
    assert isinstance(acto["descripcion"], str)


def test_la_frontera_envuelve_el_modelo_real():
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from concordia.language_model import no_language_model
    LLAVE = "0x" + "a1" * 20

    class ModeloFuga(no_language_model.NoLanguageModel):
        def sample_text(self, prompt, **kw):
            return f"la maneja {LLAVE}"  # el modelo intenta filtrar una identidad

    envuelto = RuntimeConcordia(modelo=ModeloFuga())._envolver_modelo()
    try:
        envuelto.sample_text("dale")
        assert False, "la frontera corta una fuga de identidad del modelo (INV-17)"
    except frontera.FronteraViolada:
        pass


def test_agente_no_se_construye_desde_identidad():
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    r = RuntimeConcordia(modelo=object(), embedder=_embedder_determinista)
    try:
        r._construir_agente("rol-x", [f"sigue a 0x{'c' * 40}"])
        assert False, "una disposición con identidad se bloquea antes de construir"
    except frontera.FronteraViolada:
        pass


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    print(f"gdm-concordia instalada: {CONCORDIA}")
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
