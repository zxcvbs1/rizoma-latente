"""
Modelo DELEGADO por MCP (apps/motor_simulacion/modelo_delegado.py; WP-16): el
razonamiento de Concordia lo sirve el CLIENTE por un buzón, sin clave de API ni
LLM local. Es la vía probada en terreno (Gemini Code / Codex vía MCP) y la que
hace que un cliente MCP pueda SER el modelo de la engine centralizada.

El grueso corre sin Concordia (prueba el protocolo del buzón y la frontera). La
corrida end-to-end con Concordia se saltea si la librería no está.

    .venv/bin/python tests/test_modelo_delegado.py
"""
import hashlib
import os
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.motor_simulacion.modelo_delegado import (
    ModeloDelegadoMCP, pedidos_pendientes, responder)
from apps.motor_simulacion.runtime_concordia import _concordia_instalada
from packages.domain import frontera

CONCORDIA = _concordia_instalada()


def _responder_en_thread(buzon, *, text=None, idx=None, una_vez=True):
    """Un cliente de mentira: sirve el buzón desde otro hilo (como haría la
    sesión MCP, pero determinista, para el test)."""
    def loop():
        while True:
            pend = pedidos_pendientes(buzon)
            if pend:
                responder(buzon, pend[0]["id"], text=text, idx=idx)
                if una_vez:
                    return
            time.sleep(0.02)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def test_protocolo_ida_y_vuelta():
    buzon = tempfile.mkdtemp()
    m = ModeloDelegadoMCP(buzon, timeout_s=5, poll_s=0.02)
    _responder_en_thread(buzon, text=" reparte el agua")
    salida = m.sample_text("¿qué hace la-que-riega?")
    assert salida == " reparte el agua", "el modelo devuelve lo que razonó el cliente"


def test_sample_choice_delegado():
    buzon = tempfile.mkdtemp()
    m = ModeloDelegadoMCP(buzon, timeout_s=5, poll_s=0.02)
    _responder_en_thread(buzon, idx=2)
    idx, elegido, _ = m.sample_choice("elegí", ["a", "b", "c", "d"])
    assert idx == 2 and elegido == "c", "la elección delegada vuelve por índice"


def test_frontera_corta_prompt_con_identidad():
    # Dirección de entrada: ni identidades se DELEGAN (no salen del nodo).
    m = ModeloDelegadoMCP(tempfile.mkdtemp(), timeout_s=1, poll_s=0.02)
    try:
        m.sample_text("seguí a 0x" + "b" * 40)
        assert False, "un prompt con identidad no se delega (INV-17)"
    except frontera.FronteraViolada:
        pass


def test_frontera_corta_fuga_del_cliente():
    # Dirección de salida: si el cliente devuelve una identidad, la frontera corta.
    buzon = tempfile.mkdtemp()
    m = ModeloDelegadoMCP(buzon, timeout_s=5, poll_s=0.02)
    _responder_en_thread(buzon, text="la maneja 0x" + "a1" * 20)
    try:
        m.sample_text("dale")
        assert False, "una identidad en la respuesta del cliente se corta (INV-17)"
    except frontera.FronteraViolada:
        pass


def test_corrida_concordia_con_cliente_delegado():
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    import numpy as np
    from concordia.associative_memory import basic_associative_memory
    from concordia.prefabs.entity import minimal as entity_minimal
    from concordia.typing import entity as entity_lib

    def emb(t):
        h = hashlib.sha256(t.encode()).digest()
        return np.frombuffer((h * 24)[:768 * 4], dtype=np.float32).copy()

    buzon = tempfile.mkdtemp()
    modelo = ModeloDelegadoMCP(buzon, timeout_s=10, poll_s=0.02)
    # El "cliente" scripteado razona todo acto con una marca reconocible.
    _responder_en_thread(buzon, text=" reparte el agua antes de acumularla", una_vez=False)

    mem = basic_associative_memory.AssociativeMemoryBank(sentence_embedder=emb)
    agente = entity_minimal.Entity(
        description="rol desde disposiciones",
        params={"name": "la-que-riega", "goal": "reparte antes de acumular"},
    ).build(model=modelo, memory_bank=mem)
    agente.observe("El pozo está casi seco.")
    acto = agente.act(entity_lib.free_action_spec(call_to_action="¿Qué hace?"))
    assert "reparte el agua" in acto, "Concordia produjo el acto con el razonamiento delegado"


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
