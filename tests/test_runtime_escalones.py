"""
Escalones de runtime de corrida (06 §2.1; WP-16): el cliente-en-el-bucle
distribuido, el stub, y Concordia como escalón centralizado opcional, todos bajo
la MISMA interfaz. Prueba que se enchufan por config y que Concordia degrada con
honestidad cuando la librería no está.

Corre sin servicios (y sin Concordia instalada):
    .venv/bin/python tests/test_runtime_escalones.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.motor_simulacion import runtime
from apps.motor_simulacion.runtime_concordia import (
    RuntimeConcordia, ConcordiaNoDisponible, _concordia_instalada)
from packages.domain import frontera


def test_los_tres_cumplen_el_puerto():
    for r in (runtime.RuntimeStub(), runtime.RuntimeClienteMCP(), RuntimeConcordia()):
        assert isinstance(r, runtime.RuntimeCorrida), f"{r.nombre} cumple el contrato"
        assert hasattr(r, "producir_acto") and hasattr(r, "analizar_tensiones")


def test_seleccion_por_config():
    assert runtime.crear_runtime("").nombre == "cliente_mcp", "default = engine distribuida"
    assert runtime.crear_runtime("stub").nombre == "stub"
    assert runtime.crear_runtime("concordia").nombre == "concordia"
    try:
        runtime.crear_runtime("inventado")
        assert False, "un runtime desconocido se rechaza"
    except ValueError:
        pass


def test_stub_produce_acto_material_y_tension():
    r = runtime.RuntimeStub()
    acto = r.producir_acto({"rol": "la que riega", "inventario": {"agua": 3}})
    assert acto["costo"] == {"agua": 1} and "la que riega" in acto["descripcion"]
    tensiones = r.analizar_tensiones([(0, "rol-a", "hizo"), (0, "rol-b", "hizo")], "cuidado")
    assert tensiones and tensiones[0]["roles"] == ["rol-a", "rol-b"]


def test_cliente_mcp_delega_no_produce():
    r = runtime.RuntimeClienteMCP()
    try:
        r.producir_acto({"rol": "x", "inventario": {}})
        assert False, "el runtime distribuido delega en el cliente externo"
    except runtime.RuntimeExterno:
        pass


def test_concordia_degrada_con_honestidad_sin_modelo():
    r = RuntimeConcordia()  # sin modelo (esté o no la librería)
    assert r.disponible() is False, "sin modelo no está disponible, aunque la librería esté"
    desc = r.describir()
    assert desc["engine"].startswith("centralizada")
    assert "distribuido" in desc["frente_al_distribuido"]
    assert desc["instalada"] == _concordia_instalada(), "reporta el estado real de instalación"
    assert desc["genera"] is False, "sin modelo, la mecánica corre pero no hay contenido"
    try:
        r.producir_acto({})
        assert False, "sin Concordia, degrada al cliente-en-el-bucle, no finge"
    except ConcordiaNoDisponible:
        pass
    try:
        r.analizar_tensiones([], "cuidado")
        assert False, "las tensiones declinan por diseño (híbrido), no por falta"
    except runtime.RuntimeExterno:
        pass  # lo interpretativo vive en el borde, aun con Concordia disponible


def test_concordia_envuelve_el_modelo_con_frontera():
    LLAVE = "0x" + "a1" * 20

    class ModeloFalso:
        def sample_text(self, prompt, **kw):
            return "una escena sin identidades"

    r = RuntimeConcordia(modelo=ModeloFalso())
    envuelto = r._envolver_modelo()
    assert envuelto.sample_text("componé algo") == "una escena sin identidades"

    class ModeloFuga:
        def sample_text(self, prompt, **kw):
            return f"la maneja {LLAVE}"

    fuga = RuntimeConcordia(modelo=ModeloFuga())._envolver_modelo()
    try:
        fuga.sample_text("dale")
        assert False, "una salida del modelo con identidad la bloquea la frontera (INV-17)"
    except frontera.FronteraViolada:
        pass


def test_construir_agente_valida_frontera_antes_de_la_libreria():
    r = RuntimeConcordia(modelo=object(), embedder=object())
    try:
        r._construir_agente("rol-a", [f"sigue a 0x{'b' * 40}"])
        assert False, "un agente construido con una identidad en sus disposiciones se bloquea"
    except frontera.FronteraViolada:
        pass  # la frontera muerde ANTES de tocar la librería, esté o no instalada


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
