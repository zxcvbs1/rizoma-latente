"""
La cola de razonamiento delegado (09 §2.6; apps/motor_simulacion/delegacion.py):
el buzón en memoria que sirven las tools `corrida_pedidos`/`corrida_responder`,
su muerte con la corrida (INV-07) y la auditoría de mal alimento sobre el
tránsito. El end-to-end con Concordia real se saltea si la librería no está.

Corre sin servicios:
    .venv/bin/python tests/test_delegacion_cola.py
"""
import hashlib
import os
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_simulacion import delegacion
from apps.motor_simulacion.modelo_delegado import ModeloDelegadoMCP
from apps.motor_simulacion.runtime_concordia import _concordia_instalada
from apps.motor_aventura import motor as motor_aventura
from packages.domain.models import Corrida, Partida, Tension, PesoContribucion, Injerto
from packages.domain import frontera

CONCORDIA = _concordia_instalada()


def _db():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Partida.__table__, Tension.__table__,
                  PesoContribucion.__table__, Injerto.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def test_buzon_ida_y_vuelta_en_memoria():
    buzon = delegacion.BuzonEnMemoria()
    rid = buzon.depositar_pedido({"kind": "text", "prompt": "¿qué hace el rol?"})
    assert buzon.pedidos_pendientes()[0]["id"] == rid
    assert buzon.responder(rid, text=" reparte", llave="0x" + "a" * 40)
    assert buzon.esperar_respuesta(rid, timeout_s=1)["text"] == " reparte"
    assert buzon.servidos == 1
    assert buzon.pedidos_pendientes() == [], "un pedido servido deja de estar pendiente"
    assert not buzon.responder(rid, text="otra"), "un pedido no se sirve dos veces"


def test_modelo_delegado_habla_con_el_buzon_en_memoria():
    buzon = delegacion.BuzonEnMemoria()
    modelo = ModeloDelegadoMCP(buzon, timeout_s=5)

    def cliente():
        while not buzon.pedidos_pendientes():
            time.sleep(0.01)
        pend = buzon.pedidos_pendientes()[0]
        buzon.responder(pend["id"], text="acto pensado por el cliente")

    threading.Thread(target=cliente, daemon=True).start()
    assert modelo.sample_text("componé el turno") == "acto pensado por el cliente"


def test_la_cola_muere_con_la_corrida():
    db = _db()
    db.add(Corrida(id="c-viva", operador_llave="0x" + "b" * 40, marco="cuidado"))
    db.flush()
    from apps.motor_simulacion import motor as motor_sim
    motor_sim._corridas["c-viva"] = {}  # estado vivo mínimo para poder cerrarla
    buzon = delegacion.abrir_cola("c-viva")
    buzon.depositar_pedido({"kind": "text", "prompt": "algo"})
    motor_sim.cerrar_corrida(db, "c-viva")
    assert delegacion.cola("c-viva") is None, "el cierre destruye la cola"
    assert buzon.cerrado and buzon.vacio, "nada reconstruible tras el cierre (INV-07)"


def test_cerrar_despierta_a_la_engine_que_espera():
    buzon = delegacion.BuzonEnMemoria()
    rid = buzon.depositar_pedido({"kind": "text", "prompt": "algo"})
    threading.Timer(0.1, buzon.cerrar).start()
    try:
        buzon.esperar_respuesta(rid, timeout_s=5)
        assert False, "la engine no espera a una corrida muerta"
    except delegacion.ColaCerrada:
        pass


def test_auditoria_encuentra_transito_sobreviviente():
    db = _db()
    db.add(Corrida(id="c-cerrada", operador_llave="0x" + "c" * 40,
                   marco="cuidado", estado="cerrada"))
    db.flush()
    delegacion.abrir_cola("c-cerrada")  # una cola que sobrevivió al cierre: mal alimento
    hallazgos = motor_aventura.auditar_mal_alimento(db)
    assert any("c-cerrada" in h for h in hallazgos), "la auditoría ve el tránsito vivo"
    delegacion.cerrar_cola("c-cerrada")
    assert not any("c-cerrada" in h for h in motor_aventura.auditar_mal_alimento(db))


def test_gradiente_propuesta_cubierta_activa():
    """La corrida cara no arranca sin cobertura (09 §2.6): la garantía es
    física, la engine no puede depositar en una cola propuesta."""
    buzon = delegacion.BuzonEnMemoria(presupuesto_estimado=10)
    assert buzon.estado == "propuesta"
    try:
        buzon.depositar_pedido({"kind": "text", "prompt": "algo"})
        assert False, "sin cobertura, la engine no pide razonamiento"
    except delegacion.GradienteIncompleto:
        pass
    buzon.declarar_presupuesto("0x" + "a" * 40, 6)
    assert buzon.estado == "propuesta", "6/10 no cubre"
    r = buzon.declarar_presupuesto("0x" + "b" * 40, 4)
    assert r["estado"] == "cubierta" and r["comprometido"] == 10
    buzon.depositar_pedido({"kind": "text", "prompt": "ahora sí"})
    assert buzon.estado == "activa", "el primer pedido activa la corrida"


def test_retiro_antes_de_activar_revierte_a_propuesta():
    buzon = delegacion.BuzonEnMemoria(presupuesto_estimado=5)
    buzon.declarar_presupuesto("0x" + "a" * 40, 5)
    assert buzon.estado == "cubierta"
    r = buzon.declarar_presupuesto("0x" + "a" * 40, 0)  # retirarse
    assert r["estado"] == "propuesta", "la cobertura cayó antes de activarse"


def test_corrida_barata_nace_activa():
    buzon = delegacion.BuzonEnMemoria()  # sin presupuesto estimado
    assert buzon.estado == "activa"
    buzon.depositar_pedido({"kind": "text", "prompt": "directo"})


def test_cosecha_acredita_peso_al_cerrar():
    """El único residuo vivo de la cola: el contador agregado, acreditado al
    peso de contribución (09 §4). Jamás contenido, jamás qué acto razonó quién."""
    from apps.worker import pool as pool_comun
    db = _db()
    LLAVE = "0x" + "e" * 40
    db.add(Corrida(id="c-peso", operador_llave="0x" + "f" * 40, marco="cuidado"))
    db.flush()
    from apps.motor_simulacion import motor as motor_sim
    motor_sim._corridas["c-peso"] = {}
    buzon = delegacion.abrir_cola("c-peso")
    for _ in range(3):
        rid = buzon.depositar_pedido({"kind": "text", "prompt": "pensá"})
        buzon.responder(rid, text=" acto", llave=LLAVE)
    motor_sim.cerrar_corrida(db, "c-peso")
    assert pool_comun.peso_de(db, LLAVE, "corridas") == 3.0, "3 servidos = 3 de peso"
    assert delegacion.cola("c-peso") is None, "y la cola murió igual"


def test_engine_demo_respeta_gradiente_y_produce():
    """La engine demo hospedada (sin Concordia): con presupuesto estimado nace
    propuesta y NO deposita hasta la cobertura; después produce por turnos y
    los actos mueren con la cola."""
    buzon = delegacion.lanzar_engine_demo(
        "c-demo", turnos=2, presupuesto_estimado=2, timeout_s=10)
    time.sleep(0.3)
    assert buzon.estado == "propuesta" and buzon.pedidos_pendientes() == [], \
        "sin cobertura la engine espera, no deposita"
    buzon.declarar_presupuesto("0x" + "a" * 40, 2)
    # ahora la engine puede depositar; el pool scripteado sirve los 2 turnos
    limite = time.time() + 8
    while time.time() < limite and len(buzon.actos) < 2:
        for p in buzon.pedidos_pendientes():
            buzon.responder(p["id"], text=" acto del turno", llave="0x" + "a" * 40)
        time.sleep(0.02)
    assert len(buzon.actos) == 2, f"la engine produjo {len(buzon.actos)}/2 actos"
    assert buzon.estado == "activa" and buzon.servidos == 2
    delegacion.cerrar_cola("c-demo")
    assert buzon.actos == [], "los actos mueren con la cola (tránsito efímero)"


def test_concordia_end_to_end_por_la_cola():
    """La corrida real: Concordia en un thread del nodo, el cliente sirviendo
    por el mismo protocolo que las tools MCP."""
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    import numpy as np
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia

    def emb(t):
        h = hashlib.sha256(t.encode()).digest()
        return np.frombuffer((h * 24)[:768 * 4], dtype=np.float32).copy()

    buzon = delegacion.abrir_cola("c-e2e")
    runtime = RuntimeConcordia.con_delegacion(buzon, embedder=emb, timeout_s=15)
    resultado = {}

    def engine():
        resultado["acto"] = runtime.producir_acto({
            "rol": "la-que-riega",
            "disposiciones": "reparte antes de acumular",
            "situacion": "El pozo está casi seco.",
        })

    hilo = threading.Thread(target=engine, daemon=True)
    hilo.start()
    # El "cliente MCP" scripteado: polea la cola y sirve (lo que hace la tool).
    limite = time.time() + 10
    while time.time() < limite and "acto" not in resultado:
        for pedido in buzon.pedidos_pendientes():
            frontera.validar_salida({"respuesta": " reparte el agua que queda"})
            buzon.responder(pedido["id"], text=" reparte el agua que queda",
                            llave="0x" + "d" * 40)
        time.sleep(0.02)
    hilo.join(timeout=5)
    assert "acto" in resultado, "la engine produjo con el pool sirviendo"
    assert "reparte el agua" in resultado["acto"]["descripcion"]
    assert buzon.servidos >= 1, "el contador agregado registró el servicio"
    delegacion.cerrar_cola("c-e2e")


def test_turnos_del_presupuesto_resuelve_desde_la_corrida():
    """turnos<=0 (corrección jul 2026: el 3 de antes era un resabio de la
    demo) resuelve al presupuesto_rondas de la corrida, sea cual sea el
    punto de resolución (delegacion._turnos_del_presupuesto, usado por
    lanzar_engine_demo y lanzar_engine_concordia)."""
    db = _db()
    db.add(Corrida(id="c-arco", operador_llave="0x" + "9" * 40, marco="cuidado",
                   presupuesto_rondas=7))
    db.flush()
    assert delegacion._turnos_del_presupuesto("c-arco", db) == 7
    assert delegacion._turnos_del_presupuesto("c-inexistente", db) == 12, \
        "sin corrida, el default duro (12) no debe romper"


def test_engine_concordia_turnos_cero_usa_presupuesto_rondas():
    """El default turnos=0 de la engine hospedada corre el ARCO ENTERO de la
    corrida (su presupuesto_rondas), no el 3 heredado de la demo."""
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from apps.motor_simulacion import motor as motor_sim
    from apps.motor_simulacion.motor import MemoriaCorrida

    db = _db()
    db.add(Corrida(id="c-arco-entero", operador_llave="0x" + "4" * 40,
                   marco="cuidado", presupuesto_rondas=1))
    db.flush()
    motor_sim._corridas["c-arco-entero"] = MemoriaCorrida(
        sinteticos={"la-que-riega": {"disposiciones": ["reparte antes de acumular"],
                                     "forma_id": "forma-x"}})

    buzon = delegacion.lanzar_engine_concordia(
        db, "c-arco-entero", turnos=0, situacion="El pozo está casi seco.",
        timeout_s=15)

    servido = False
    limite = time.time() + 12
    while time.time() < limite and not (servido and buzon.actos):
        for pedido in buzon.pedidos_pendientes():
            frontera.validar_salida({"respuesta": " reparte el agua que queda"})
            buzon.responder(pedido["id"], text=" reparte el agua que queda",
                            llave="0x" + "5" * 40)
            servido = True
        time.sleep(0.02)
    assert servido, "turnos=0 tiene que producir al menos el presupuesto_rondas=1"
    assert len(buzon.actos) >= 1
    delegacion.cerrar_cola("c-arco-entero")
    motor_sim._corridas.pop("c-arco-entero", None)


def test_engine_concordia_rebota_sin_poblacion():
    """Concordia conduce por defecto (corrección jul 2026): una corrida sin
    dobles ni sintéticos no tiene de dónde construir agentes y rebota ANTES
    de tocar la librería (el chequeo de población no depende de que
    gdm-concordia esté instalada)."""
    from apps.motor_simulacion import motor as motor_sim
    db = _db()
    db.add(Corrida(id="c-despoblada", operador_llave="0x" + "1" * 40, marco="cuidado"))
    db.flush()
    try:
        delegacion.lanzar_engine_concordia(db, "c-despoblada", turnos=1)
        assert False, "una corrida despoblada no puede lanzar la engine Concordia"
    except motor_sim.MotorSimError as exc:
        assert "población" in str(exc), f"el rebote no explica la causa: {exc}"
    motor_sim._corridas.pop("c-despoblada", None)


def test_engine_concordia_produce_actos_con_poblacion():
    """Con un rol poblado (sintético), la engine Concordia hospedada arma el
    agente desde sus disposiciones, pide razonamiento por la cola y produce
    actos que viven en el buzón (mismo protocolo que la demo)."""
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from apps.motor_simulacion import motor as motor_sim
    from apps.motor_simulacion.motor import MemoriaCorrida

    db = _db()
    db.add(Corrida(id="c-poblada", operador_llave="0x" + "2" * 40, marco="cuidado"))
    db.flush()
    motor_sim._corridas["c-poblada"] = MemoriaCorrida(
        sinteticos={"la-que-riega": {"disposiciones": ["reparte antes de acumular"],
                                     "forma_id": "forma-x"}})

    buzon = delegacion.lanzar_engine_concordia(
        db, "c-poblada", turnos=1, situacion="El pozo está casi seco.", timeout_s=15)

    servido = False
    limite = time.time() + 12
    while time.time() < limite and not (servido and buzon.actos):
        for pedido in buzon.pedidos_pendientes():
            frontera.validar_salida({"respuesta": " reparte el agua que queda"})
            buzon.responder(pedido["id"], text=" reparte el agua que queda",
                            llave="0x" + "3" * 40)
            servido = True
        time.sleep(0.02)
    assert servido, "la engine Concordia pidió razonamiento por el rol poblado"
    assert len(buzon.actos) >= 1, f"la engine produjo {len(buzon.actos)} actos"
    delegacion.cerrar_cola("c-poblada")
    motor_sim._corridas.pop("c-poblada", None)


def test_engine_concordia_arco_completo_marca_rondas_y_motivo():
    """Corrección jul 2026 (primer playtest de una corrida larga): un run
    corto que termina de verdad incrementa rondas_completadas por cada
    vuelta entera del bucle y deja motivo_fin='arco completo' (el cierre
    honesto de 06 §2.1)."""
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from apps.motor_simulacion import motor as motor_sim
    from apps.motor_simulacion.motor import MemoriaCorrida

    db = _db()
    db.add(Corrida(id="c-arco-honesto", operador_llave="0x" + "6" * 40,
                   marco="cuidado", presupuesto_rondas=1))
    db.flush()
    motor_sim._corridas["c-arco-honesto"] = MemoriaCorrida(
        sinteticos={"la-que-riega": {"disposiciones": ["reparte antes de acumular"],
                                     "forma_id": "forma-x"}})

    buzon = delegacion.lanzar_engine_concordia(
        db, "c-arco-honesto", turnos=1, situacion="El pozo está casi seco.",
        timeout_s=15)

    limite = time.time() + 12
    while time.time() < limite and not buzon.actos:
        for pedido in buzon.pedidos_pendientes():
            frontera.validar_salida({"respuesta": " reparte el agua que queda"})
            buzon.responder(pedido["id"], text=" reparte el agua que queda",
                            llave="0x" + "7" * 40)
        time.sleep(0.02)
    assert buzon.actos, "el run tiene que producir al menos un acto"

    memoria = motor_sim._corridas["c-arco-honesto"]
    limite = time.time() + 5
    while time.time() < limite and memoria.motivo_fin == "":
        time.sleep(0.02)
    assert memoria.arco_turnos == 1
    assert memoria.rondas_completadas == 1, "una vuelta entera del bucle exterior"
    assert memoria.motivo_fin == "arco completo"

    delegacion.cerrar_cola("c-arco-honesto")
    motor_sim._corridas.pop("c-arco-honesto", None)


def test_delegada_degrada_a_demo_declarado():
    """El endpoint de corrida_delegada (main.py) resuelve "auto" a concordia
    si está instalada, y a demo si no; "concordia"/"demo" fuerzan. Se prueba
    la función de resolución pura, sin levantar servicios."""
    from apps.api.main import _resolver_engine_delegada

    assert _resolver_engine_delegada("auto", concordia_instalada=True) == "concordia"
    assert _resolver_engine_delegada("auto", concordia_instalada=False) == "demo", \
        "sin la librería, 'auto' degrada a la demo declarada"
    assert _resolver_engine_delegada("demo", concordia_instalada=True) == "demo", \
        "'demo' fuerza el fallback aunque la librería esté"
    assert _resolver_engine_delegada("concordia", concordia_instalada=False) == "concordia", \
        "la resolución fuerza; el 422 por librería faltante lo decide el caller"
    try:
        _resolver_engine_delegada("lo-que-sea", concordia_instalada=True)
        assert False, "una engine desconocida no se resuelve en silencio"
    except ValueError:
        pass


class _ModeloCapturaPrompt:
    """Stub de modelo delegado que solo guarda el prompt recibido (para
    verificar QUÉ se le pide al cliente, sin depender de gdm-concordia)."""

    def __init__(self):
        self.prompts = []

    def sample_text(self, prompt, **kw):
        self.prompts.append(prompt)
        return "acto de prueba"

    def sample_choice(self, prompt, responses, **kw):
        self.prompts.append(prompt)
        return 0


def test_liviano_incluye_lente_e_inventario_y_pide_escena():
    """Corrección jul 2026 (diagnóstico de corridas chatas): el prompt liviano
    lleva la lente (marco_reglas) y el inventario, y pide una ESCENA (3 a 5
    frases), no una línea de log. `_producir_acto_liviano` no exige Concordia
    instalada (solo pasa por la frontera y el modelo inyectado)."""
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia

    modelo = _ModeloCapturaPrompt()
    runtime = RuntimeConcordia(modelo=modelo, liviano=True)
    disposiciones = [f"regla {i}" for i in range(17)]
    marco_reglas = {"nombre": "Bienes comunes", "estresa": "extracción sin reposición",
                    "crisis_tipicas": ["sobreexplotación", "cercamiento"]}
    inventario = {"agua": 3, "semillas": 10}

    acto = runtime._producir_acto_liviano(
        "la-que-riega", disposiciones, "El pozo está casi seco.",
        historial=["algo pasó antes"], marco_reglas=marco_reglas, inventario=inventario)

    assert acto["descripcion"] == "acto de prueba"
    prompt = modelo.prompts[0]
    assert "lente" in prompt.lower(), "el prompt tiene que declarar la lente"
    assert marco_reglas["estresa"] in prompt, "lo que estresa la lente viaja al prompt"
    assert "ESCENA" in prompt or "3 a 5 frases" in prompt, \
        "se pide una escena, no una línea de log"
    assert "agua=3" in prompt, "el inventario viaja al prompt"

    # Sin lente ni inventario: no rompe y sigue pidiendo una escena.
    runtime._producir_acto_liviano("la-que-riega", disposiciones, "situación", historial=None)
    ultimo = modelo.prompts[-1]
    assert "ESCENA" in ultimo or "3 a 5 frases" in ultimo


def test_engine_concordia_computa_lente_desde_lente_borrador():
    """Smoke (09/06 §2.1): lanzar_engine_concordia computa la lente UNA vez
    (memoria.lente_borrador o reglas_de(marco)) y la mete en el contexto
    delegado; el pedido que llega al buzón contiene la palabra de la lente
    (estresa). No rompe con una lente borrador (corrida sin marco publicado)."""
    if not CONCORDIA:
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return
    from apps.motor_simulacion import motor as motor_sim
    from apps.motor_simulacion.motor import MemoriaCorrida

    db = _db()
    db.add(Corrida(id="c-lente", operador_llave="0x" + "8" * 40,
                   marco="lente-propia-del-autor", presupuesto_rondas=1))
    db.flush()
    memoria = MemoriaCorrida(
        sinteticos={"la-que-riega": {"disposiciones": ["reparte antes de acumular"],
                                     "forma_id": "forma-x"}},
        inventario={"agua": 5})
    memoria.lente_borrador = {"nombre": "Sequía comunitaria",
                              "estresa": "reciprocidad bajo escasez",
                              "crisis_tipicas": ["acaparamiento"]}
    motor_sim._corridas["c-lente"] = memoria

    buzon = delegacion.lanzar_engine_concordia(
        db, "c-lente", turnos=1, situacion="El pozo está casi seco.", timeout_s=15)

    pedido_prompt = {}
    limite = time.time() + 12
    while time.time() < limite and not pedido_prompt:
        for pedido in buzon.pedidos_pendientes():
            pedido_prompt["prompt"] = pedido.get("prompt", "")
            frontera.validar_salida({"respuesta": " reparte el agua que queda"})
            buzon.responder(pedido["id"], text=" reparte el agua que queda",
                            llave="0x" + "f" * 40)
        time.sleep(0.02)
    assert pedido_prompt, "la engine tiene que pedir razonamiento"
    assert "reciprocidad bajo escasez" in pedido_prompt["prompt"], \
        "la lente (estresa) de lente_borrador viaja al pedido delegado"

    delegacion.cerrar_cola("c-lente")
    motor_sim._corridas.pop("c-lente", None)


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
