"""
WP-05 · Reglas del doble + WP-15 · Frontera + WP-16 · Cliente en el bucle
(INV-07, INV-17; 06_motor_simulacion; CU-C2, CU-C5, CU-T2).

Token por corrida o agente aleatorio; el doble muere al cierre y no es
regenerable; ningún contexto servido ni lectura aceptada porta identidades;
un acto materialmente imposible no toca el estado.

Corre sin servicios:
    .venv/bin/python tests/test_wp05_dobles.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.acervo import acervo
from apps.api.controles import canonical_actor
from apps.api.security import SecurityService
from apps.motor_aventura import motor as aventura
from apps.motor_simulacion import marcos as marcos_mod
from apps.motor_simulacion import motor as sim
from packages.domain import frontera
from packages.domain.identity import new_nonce, now_iso, sign_text
from packages.domain.models import (Corrida, Deslizamiento, Forma, Injerto, Partida,
                                    PropuestaForma, Tension, TerminoMapa)


class FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, k):
        return 1 if k in self.store else 0

    def setex(self, k, ttl, v):
        self.store[k] = str(v)


SEC = SecurityService(redis_client=FakeRedis())
OPERADOR = "0x" + "0a" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Tension.__table__, Partida.__table__,
                  TerminoMapa.__table__, Deslizamiento.__table__,
                  Forma.__table__, PropuestaForma.__table__, Injerto.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def persona_con_topologia(db, n=3):
    pk = Account.create().key.hex()
    llave = Account.from_key(pk).address
    partida = aventura.iniciar_partida(db, llave)
    for i in range(n):
        aventura.resolver_decision(db, partida.id, f"e{i}", "x", deslizamientos=[{
            "de_termino": f"cuidar-{i}", "hacia_termino": f"controlar-{i}",
            "evidencia": f"lo dijo así {i}"}])
    return pk, llave


def token_para(pk, llave, corrida_id):
    timestamp, nonce = now_iso(), new_nonce()
    return {"actor_id": llave, "timestamp": timestamp, "nonce": nonce,
            "signature": sign_text(pk, canonical_actor(llave, timestamp, nonce,
                                                       sim.token_action(corrida_id)))}


def test_marco_explicito_o_nada():
    db = db_limpia()
    try:
        sim.iniciar_corrida(db, OPERADOR, "objetivo")
        assert False, "no existe el marco neutro: la ideología es un parámetro"
    except sim.MotorSimError:
        pass
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado", {"horas": 10})
    assert corrida.marco == "cuidado"


def test_token_valido_calibra_desde_topologia():
    db = db_limpia()
    pk, llave = persona_con_topologia(db)
    corrida = sim.iniciar_corrida(db, OPERADOR, "bienes_comunes")
    resultado = sim.sumar_participante(db, corrida.id, "la cocinera", security=SEC,
                                       token=token_para(pk, llave, corrida.id))
    assert resultado == {"rol": "la cocinera", "calibrado": True, "poblacion": "doble"}
    disposiciones = sim._corridas[corrida.id].dobles["la cocinera"]["disposiciones"]
    assert len(disposiciones) == 3 and all("tiende a" in d for d in disposiciones), \
        "cada arista del mapa se vuelve regla condicional (06 §3)"


def test_sin_token_degrada_a_aleatorio():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    resultado = sim.sumar_participante(db, corrida.id, "el vecino", security=SEC, token=None)
    assert resultado["poblacion"] == "aleatoria", \
        "sin token su lugar lo ocupa un agente aleatorio (CU-C2)"


def test_token_ajeno_o_de_otra_corrida_rechaza():
    db = db_limpia()
    pk, llave = persona_con_topologia(db)
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    otra = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    for token in [token_para(pk, llave, otra.id),
                  {**token_para(pk, llave, corrida.id), "actor_id": OPERADOR}]:
        try:
            sim.sumar_participante(db, corrida.id, "rol", security=SEC, token=token)
            assert False, "el consentimiento es POR CORRIDA y de la persona (INV-07)"
        except sim.MotorSimError:
            pass


def test_contexto_cruza_frontera():
    import json
    db = db_limpia()
    pk, llave = persona_con_topologia(db)
    corrida = sim.iniciar_corrida(db, OPERADOR, "decrecimiento", {"dinero": 5})
    sim.sumar_participante(db, corrida.id, "la tesorera", security=SEC,
                           token=token_para(pk, llave, corrida.id))
    contexto = sim.contexto_ronda(db, corrida.id, "la tesorera")
    assert set(contexto) <= sim.CAMPOS_CONTEXTO_RONDA, "contexto mínimo por operación"
    assert not frontera.contiene_identidades(json.dumps(contexto)), \
        "roles y disposiciones cruzan; llaves jamás (INV-17)"
    assert contexto["marco"] == "decrecimiento" and contexto["disposiciones"]


def test_lectura_con_identidad_no_toca_estado():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "capitales")
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    sim.acto_ronda(db, corrida.id, "rol-a", {"descripcion": "hace algo", "costo": {}})
    try:
        sim.leer_tensiones(db, corrida.id, [{
            "tipo": "gatekeeping", "roles": ["rol-a"],
            "evidencia": f"lo controla {OPERADOR}"}])
        assert False, "una lectura con llaves no puede tocar el estado (CU-T2)"
    except frontera.FronteraViolada:
        pass
    assert db.query(Tension).all() == [], "el incidente no dejó residuo"


def test_acto_imposible_no_toca_y_el_posible_descuenta():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "economia_social", {"madera": 2})
    sim.sumar_participante(db, corrida.id, "el carpintero", security=SEC, token=None)
    try:
        sim.acto_ronda(db, corrida.id, "el carpintero",
                       {"descripcion": "hacer diez mesas", "costo": {"madera": 10}})
        assert False, "la restricción material manda (CU-C5)"
    except sim.MotorSimError:
        pass
    assert sim._corridas[corrida.id].inventario == {"madera": 2}, "el estado quedó intacto"
    resultado = sim.acto_ronda(db, corrida.id, "el carpintero",
                               {"descripcion": "hacer una mesa", "costo": {"madera": 1}})
    assert resultado["inventario"] == {"madera": 1}


def test_rol_desconocido_en_lectura_rechaza():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    sim.acto_ronda(db, corrida.id, "rol-a", {"descripcion": "hace algo", "costo": {}})
    try:
        sim.leer_tensiones(db, corrida.id, [{
            "tipo": "carga", "roles": ["rol-fantasma"], "evidencia": "dijo tal cosa"}])
        assert False, "los roles nacen en la generación, no en la lectura"
    except sim.MotorSimError:
        pass


def test_tensiones_rebotan_sin_actos():
    """Corrección jul 2026 (el playtest del GM que narró seis rondas sin
    servir un solo pedido): la evidencia cita lo que pasó EN la corrida, no
    una narración externa. Sin actos, no hay lectura válida."""
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    try:
        sim.leer_tensiones(db, corrida.id, [{
            "tipo": "carga", "roles": ["rol-a"], "evidencia": "rol-a: 'siempre yo'"}])
        assert False, "sin actos en el transcript no hay lectura válida"
    except sim.MotorSimError as exc:
        assert "sin actos" in str(exc)
    # Actos VACÍOS no cuentan: 24 respuestas en blanco no son actos (corrección
    # jul 2026, el subagente que drenó la cola con texto vacío).
    for r in range(1, 4):
        sim._corridas[corrida.id].transcript.append((r, "rol-a", ""))
    try:
        sim.leer_tensiones(db, corrida.id, [{
            "tipo": "carga", "roles": ["rol-a"], "evidencia": "rol-a: 'siempre yo'"}])
        assert False, "actos vacíos no habilitan la lectura"
    except sim.MotorSimError as exc:
        assert "CONTENIDO" in str(exc) or "vacías" in str(exc)
    sim.acto_ronda(db, corrida.id, "rol-a", {"descripcion": "hace algo", "costo": {}})
    n = sim.leer_tensiones(db, corrida.id, [{
        "tipo": "carga", "roles": ["rol-a"], "evidencia": "rol-a: 'siempre yo'"}])
    assert n == 1, "con un acto CON CONTENIDO, la misma lectura pasa"


def test_muerte_del_doble_y_no_regenerabilidad():
    db = db_limpia()
    pk, llave = persona_con_topologia(db)
    corrida = sim.iniciar_corrida(db, OPERADOR, "bienes_comunes", {"agua": 3})
    sim.sumar_participante(db, corrida.id, "la regadora", security=SEC,
                           token=token_para(pk, llave, corrida.id))
    sim.acto_ronda(db, corrida.id, "la regadora",
                   {"descripcion": "reparte el agua", "costo": {}})
    sim.leer_tensiones(db, corrida.id, [{
        "tipo": "sobreuso", "roles": ["la regadora"],
        "evidencia": "la regadora: 'el agua no alcanza para todos'"}])
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert corrida.id not in sim._corridas, "el doble y su token murieron con la corrida"
    assert sim.auditar_corridas(db) == []
    assert aventura.auditar_mal_alimento(db) == [], \
        "ninguna tabla puede retener dobles, tokens ni topologías (por construcción)"
    assert cierre["tensiones"][0]["marco"] == "bienes_comunes", "el marco se declara siempre"
    assert "la regadora" in cierre["tensiones"][0]["roles"]
    try:
        sim.contexto_ronda(db, corrida.id, "la regadora")
        assert False, "sobre una corrida cerrada no se opera"
    except sim.MotorSimError:
        pass


def test_presupuesto_corta_limpio():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado", presupuesto_rondas=1)
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    avance = sim.avanzar_ronda(db, corrida.id)
    assert avance["presupuesto_agotado"] is True
    try:
        sim.contexto_ronda(db, corrida.id, "rol-a")
        assert False, "agotado el presupuesto, la corrida pide cierre limpio"
    except sim.MotorSimError:
        pass


def publicar_lente(db, nombre="maquinas_deseantes",
                   cuerpo="estresa la tensión entre desterritorialización y reterritorialización",
                   crisis_tipicas=None, metricas=None):
    """La lente se crea por el flujo del acervo QUE YA EXISTE (WP-22): se
    propone como cualquier rúbrica-forma y se publica; no hay mecanismo
    nuevo de propuesta."""
    borrador = {
        "tipo": "lente", "nombre": nombre,
        "descripcion": f"lente {nombre} propuesta al acervo",
        "cuerpo": cuerpo, "marco": "general",
        "contexto_material": {
            "crisis_tipicas": crisis_tipicas or ["desterritorialización forzada"],
            "metricas": metricas or ["flujos deseantes en juego"],
        },
    }
    propuesta = acervo.proponer_rubrica(db, borrador, OPERADOR)
    acervo.firmar_consentimiento(db, propuesta.id, OPERADOR)
    return acervo.publicar_forma(db, propuesta.id)


def test_marco_lente_del_acervo():
    db = db_limpia()
    forma = publicar_lente(db)
    assert marcos_mod.marco_valido("maquinas_deseantes", db) is True, \
        "la tesis dice que la lente es un parámetro abierto, no un enum"
    reglas = marcos_mod.reglas_de("maquinas_deseantes", db)
    assert reglas["nombre"] == "maquinas_deseantes"
    assert "desterritorialización" in reglas["estresa"]
    assert reglas["crisis_tipicas"] == ["desterritorialización forzada"]
    assert reglas["metricas"] == ["flujos deseantes en juego"]
    assert reglas["del_acervo"] is True and reglas["forma_id"] == forma.id

    corrida = sim.iniciar_corrida(db, OPERADOR, "maquinas_deseantes")
    assert corrida.marco == "maquinas_deseantes", \
        "el marco canónico es el nombre real de la lente, jamás otra etiqueta"


def test_marco_inexistente_sigue_rebotando():
    db = db_limpia()
    assert marcos_mod.marco_valido("cualquier_cosa", db) is False
    try:
        sim.iniciar_corrida(db, OPERADOR, "cualquier_cosa")
        assert False, "un marco que no es ni semilla ni lente publicada rebota"
    except sim.MotorSimError:
        pass


def test_lente_no_publicada_no_sirve_de_marco():
    db = db_limpia()
    forma = publicar_lente(db, nombre="lente_retirada")
    forma.estado = "retirada"
    forma.retirada_motivo = "revocación de un aportante"
    db.flush()
    assert marcos_mod.marco_valido("lente_retirada", db) is False, \
        "una lente retirada no valida como marco"
    try:
        sim.iniciar_corrida(db, OPERADOR, "lente_retirada")
        assert False, "una lente retirada no habilita corrida"
    except sim.MotorSimError:
        pass

    # tampoco una propuesta que nunca se publicó
    borrador_pendiente = {
        "tipo": "lente", "nombre": "lente_pendiente",
        "descripcion": "propuesta sin publicar", "cuerpo": "estresa algo",
        "marco": "general",
    }
    acervo.proponer_rubrica(db, borrador_pendiente, OPERADOR)
    assert marcos_mod.marco_valido("lente_pendiente", db) is False, \
        "una propuesta 'juntando' aún no es forma del acervo"


def test_lente_borrador_corre_sin_publicar():
    db = db_limpia()
    lente_borrador = {
        "nombre": "lente_de_prueba", "estresa": "estresa la tensión de prueba",
        "crisis_tipicas": ["crisis de prueba"], "metricas": ["métrica de prueba"],
    }
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado",
                                  lente_borrador=lente_borrador)
    assert corrida.marco == "lente_de_prueba"
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    contexto = sim.contexto_ronda(db, corrida.id, "rol-a")
    assert contexto["marco_reglas"]["nombre"] == "lente_de_prueba"
    assert contexto["marco_reglas"]["estresa"] == "estresa la tensión de prueba"
    assert contexto["marco_reglas"]["borrador"] is True
    assert marcos_mod.marco_valido("lente_de_prueba", db) is False, \
        "la lente borrador jamás se publica sola en el acervo"


def test_lente_borrador_exige_nombre_y_estresa():
    db = db_limpia()
    try:
        sim.iniciar_corrida(db, OPERADOR, "cuidado",
                            lente_borrador={"nombre": "sin_estresa"})
        assert False, "una lente borrador sin 'estresa' debe rebotar"
    except sim.MotorSimError as exc:
        assert "nombre" in str(exc) and "estresa" in str(exc)


def test_borrador_muere_con_la_corrida():
    db = db_limpia()
    lente_borrador = {"nombre": "lente_efimera", "estresa": "estresa algo efímero"}
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado",
                                  lente_borrador=lente_borrador)
    assert corrida.id in sim._corridas
    sim.cerrar_corrida(db, corrida.id)
    assert corrida.id not in sim._corridas, \
        "el borrador vive solo en la memoria efímera y muere con la corrida"
    persistidas = db.query(Forma).filter(Forma.nombre == "lente_efimera").all()
    assert persistidas == [], "ninguna tabla persistió la lente borrador"


def test_los_seis_siguen_andando_sin_db():
    assert marcos_mod.marco_valido("bienes_comunes") is True, \
        "backward compat: db es opcional para los seis marcos semilla"


def test_cosecha_vacia_en_corrida_despoblada():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["cosecha_vacia"] is True
    assert cierre["poblacion"] == 0
    assert "no produjo conocimiento" in cierre["nota_cosecha"], \
        "el vacío tiene que ser legible, no solo un booleano"
    assert "siguiente_paso" not in cierre, \
        "sin tensiones ya está la nota del vacío; no hay camino de soluciones que señalar"


def test_cosecha_no_vacia_con_poblacion():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["cosecha_vacia"] is False
    assert cierre["poblacion"] >= 1


def test_cosecha_no_vacia_con_tension():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "capitales")
    sim.sumar_participante(db, corrida.id, "rol-a", security=SEC, token=None)
    sim.acto_ronda(db, corrida.id, "rol-a", {"descripcion": "hace algo", "costo": {}})
    sim.leer_tensiones(db, corrida.id, [{
        "tipo": "gatekeeping", "roles": ["rol-a"],
        "evidencia": "rol-a: 'no me dejan entrar'"}])
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["cosecha_vacia"] is False
    assert len(cierre["tensiones"]) == 1
    assert cierre["tensiones"][0]["tipo"] == "gatekeeping"
    assert "corrida_injerto" in cierre["siguiente_paso"], \
        "con tensiones, el cierre señala el ciclo del injerto como camino de soluciones"


def test_corrida_delegada_request_acepta_100_rechaza_101():
    """Corrección jul 2026 (primer playtest de una corrida larga): el tope de
    turnos sube de 24 a 100 (arco largo cuesta, pero ya no está prohibido)."""
    from pydantic import ValidationError

    from apps.api.schemas import CorridaDelegadaRequest

    base = {"actor_id": OPERADOR, "timestamp": "t", "nonce": "n", "signature": "s"}
    req = CorridaDelegadaRequest(**base, turnos=100)
    assert req.turnos == 100
    try:
        CorridaDelegadaRequest(**base, turnos=101)
        assert False, "101 turnos supera el tope declarado (le=100)"
    except ValidationError:
        pass


def test_transcript_de_devuelve_actos_y_no_persiste():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado", {"agua": 5})
    sim.sumar_participante(db, corrida.id, "la regadora", security=SEC, token=None)
    sim.acto_ronda(db, corrida.id, "la regadora",
                   {"descripcion": "reparte el agua", "costo": {"agua": 1}})
    transcript = sim.transcript_de(db, corrida.id)
    assert transcript["corrida"] == corrida.id
    assert transcript["actos"] == [{"ronda": 0, "rol": "la regadora",
                                    "descripcion": "reparte el agua"}]
    assert transcript["rondas_completadas"] == 0
    # corrió y no leyó tensiones: sin sin_cosecha=True el cierre rebota
    # (corrección jul 2026, cierre sin cosecha); acá probamos que el transcript
    # muere con la corrida, no el gate.
    sim.cerrar_corrida(db, corrida.id, sin_cosecha=True)
    try:
        sim.transcript_de(db, corrida.id)
        assert False, "el transcript muere con la corrida (INV-07)"
    except sim.MotorSimError:
        pass


def test_cierre_honesto_declara_arco_incompleto():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    mem = sim._corridas[corrida.id]
    mem.arco_turnos = 24
    mem.rondas_completadas = 8
    mem.motivo_fin = "un pedido no fue respondido a tiempo (el cliente dejó de prestar la mente)"
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["arco"]["turnos_pedidos"] == 24
    assert cierre["arco"]["rondas_completadas"] == 8
    assert cierre["arco"]["motivo_fin"] == \
        "un pedido no fue respondido a tiempo (el cliente dejó de prestar la mente)"
    assert "nota" in cierre["arco"], \
        "un arco incompleto tiene que declarar que el GM no puede narrarlo entero"
    assert "8" in cierre["arco"]["nota"] and "24" in cierre["arco"]["nota"]


def test_cierre_declara_arco_completo_sin_nota():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    mem = sim._corridas[corrida.id]
    mem.arco_turnos = 3
    mem.rondas_completadas = 3
    mem.motivo_fin = "arco completo"
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["arco"]["motivo_fin"] == "arco completo"
    assert "nota" not in cierre["arco"], "el arco completo no necesita advertencia"


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
