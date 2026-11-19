"""
WP-07 · El ciclo del injerto (06 §6; CU-C4, CU-C9).

Premisas desde la matriz material, regla de oro dura, veredicto A/B con
evidencia por roles, export a partida jugable y adopción como único residuo
colectivo. El ciclo cierra en juego.

Corre sin servicios:
    .venv/bin/python tests/test_wp07_injerto.py
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_aventura import motor as aventura
from apps.motor_simulacion import motor as sim
from packages.domain import frontera
from packages.domain.models import (Corrida, Deslizamiento, Injerto, Partida,
                                    Tension, TerminoMapa)

OPERADOR = "0x" + "0a" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Tension.__table__, Injerto.__table__,
                  Partida.__table__, TerminoMapa.__table__, Deslizamiento.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def corrida_con_tension(db, inventario=None):
    corrida = sim.iniciar_corrida(db, OPERADOR, "bienes_comunes",
                                  inventario or {"horas": 10, "salon": 1, "dinero": 0})
    for rol in ("la que riega", "el que presta la llave", "la tesorera"):
        sim.sumar_participante(db, corrida.id, rol, security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    sim.leer_tensiones(db, corrida.id, [{
        "tipo": "acceso desigual al salon",
        "roles": ["el que presta la llave", "la tesorera"],
        "evidencia": "el que presta la llave: 'si no estoy yo, no se abre'"}])
    return corrida


SPEC_OK = {
    "nombre": "llave compartida rotativa",
    "tension_que_ataca": "acceso desigual al salon",
    "regla_logica": "la llave rota semanalmente entre tres personas listadas a la vista",
    "flujo": "cada domingo pasa a la siguiente; la lista vive pegada en el salon",
    "requisitos_materiales": {"salon": 1},
    "senales_alivio": "nadie espera en la puerta; abre gente distinta cada semana",
}


def test_premisas_desde_la_matriz():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    pre = sim.premisas(db, corrida.id)
    assert pre["marco"] == "bienes_comunes", "el marco se declara siempre"
    assert "salon" in pre["sobra"] and "dinero" in pre["falta"]
    assert pre["duele"][0]["tipo"] == "acceso desigual al salon"
    assert "no puede requerir lo que el grupo no tiene" in pre["regla_de_oro"]


def test_regla_de_oro():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    for requisitos in ({"camioneta": 1}, {"horas": 99}):
        try:
            sim.registrar_injerto(db, corrida.id, {**SPEC_OK, "requisitos_materiales": requisitos})
            assert False, "la propuesta no puede requerir lo que el grupo no tiene"
        except sim.MotorSimError:
            pass
    injerto = sim.registrar_injerto(db, corrida.id, SPEC_OK)
    assert injerto.estado == "propuesto"


def test_plantilla_completa_o_nada():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    incompleto = {k: v for k, v in SPEC_OK.items() if k != "senales_alivio"}
    try:
        sim.registrar_injerto(db, corrida.id, incompleto)
        assert False, "sin señales de alivio no hay injerto"
    except sim.MotorSimError:
        pass


def test_frontera_en_el_injerto():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    try:
        sim.registrar_injerto(db, corrida.id,
                              {**SPEC_OK, "regla_logica": f"la administra {OPERADOR}"})
        assert False, "un injerto jamás porta identidades"
    except frontera.FronteraViolada:
        pass


def test_veredicto_del_catalogo_y_con_evidencia():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    injerto = sim.registrar_injerto(db, corrida.id, SPEC_OK)
    try:
        sim.validar_ab(db, injerto.id, "MAS_O_MENOS", "evidencia x")
        assert False, "veredicto fuera del catálogo"
    except sim.MotorSimError:
        pass
    try:
        sim.validar_ab(db, injerto.id, "APROBADO", f"lo confirmó {OPERADOR}")
        assert False, "evidencia con llave no pasa la frontera"
    except frontera.FronteraViolada:
        pass
    sim.validar_ab(db, injerto.id, "NECESITA_AJUSTES",
                   "la tesorera sigue esperando en la ronda 3", metricas_sin={"esperas": 4})
    assert injerto.estado == "necesita_ajustes"


def test_exportar_solo_lo_aprobado():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    injerto = sim.registrar_injerto(db, corrida.id, SPEC_OK)
    try:
        sim.exportar_protocolo(db, injerto.id)
        assert False, "lo propuesto no se juega todavía"
    except sim.MotorSimError:
        pass
    sim.validar_ab(db, injerto.id, "APROBADO",
                   "con la regla, la tesorera abre en la ronda 2 sin esperar",
                   metricas_sin={"esperas": 4}, metricas_con={"esperas": 1})
    guion = sim.exportar_protocolo(db, injerto.id)
    assert guion["marco"] == "bienes_comunes" and "la tesorera" in guion["roles"]
    assert guion["reglas"] == [SPEC_OK["regla_logica"]]
    assert "condicion_de_cierre" in guion and "jugab" not in guion["titulo"].lower()


def test_adopcion_requiere_aprobado():
    db = db_limpia()
    corrida = corrida_con_tension(db)
    injerto = sim.registrar_injerto(db, corrida.id, SPEC_OK)
    try:
        sim.resolver_adopcion(db, injerto.id, "adoptado")
        assert False, "solo se adopta lo aprobado y jugado"
    except sim.MotorSimError:
        pass
    sim.validar_ab(db, injerto.id, "APROBADO", "alivio visible por roles")
    try:
        sim.resolver_adopcion(db, injerto.id, "ni")
        assert False, "la decisión es adoptado o descartado"
    except sim.MotorSimError:
        pass
    sim.resolver_adopcion(db, injerto.id, "descartado")
    assert injerto.estado == "descartado" and injerto.decidido_at is not None


def test_ciclo_completo_cierra_en_juego():
    """CU-C4 + CU-C9 (stub): tensión -> injerto -> A/B -> guion -> la comunidad
    lo juega (cada jugador su partida, su lector, su mapa) -> adopción."""
    db = db_limpia()
    corrida = corrida_con_tension(db)
    injerto = sim.registrar_injerto(db, corrida.id, SPEC_OK)
    sim.validar_ab(db, injerto.id, "APROBADO",
                   "con la regla, la tesorera abre en la ronda 2 sin esperar",
                   metricas_sin={"esperas": 4}, metricas_con={"esperas": 1})
    guion = sim.exportar_protocolo(db, injerto.id)
    sim.cerrar_corrida(db, corrida.id)  # los dobles y el transcript mueren acá

    jugadores = ["0x" + str(i) * 40 for i in (1, 2, 3)]
    for i, llave in enumerate(jugadores):
        partida = aventura.iniciar_partida(db, llave, marco=guion["marco"])
        aventura.resolver_decision(db, partida.id, guion["titulo"], "entrar a jugar",
                                   deslizamientos=[{
                                       "de_termino": f"esperar-{i}",
                                       "hacia_termino": f"abrir-{i}",
                                       "evidencia": f"en la escena dije que abro yo ({i})"}])
        aventura.cerrar_partida(db, partida.id, lo_pide_el_jugador=True)

    sim.resolver_adopcion(db, injerto.id, "adoptado")
    assert injerto.estado == "adoptado", "el residuo colectivo único"

    for llave in jugadores:
        propias = [d for d in db.query(Deslizamiento).all()
                   if d.jugador_llave.lower() == llave.lower()]
        assert len(propias) == 1, "cada jugador solo escribe en SU mapa (sin topología grupal)"

    assert aventura.auditar_mal_alimento(db) == []
    assert sim.auditar_corridas(db) == []
    persistido = json.loads(db.query(Injerto).all()[0].guion)
    assert persistido["titulo"] == guion["titulo"], "la partida jugable quedó exportada"


def test_sin_injertos_marca_diagnostico_sin_remedio():
    """Cerrar con tensiones leídas y cero injertos declara sin_injertos=True
    con su nota; con al menos un injerto propuesto, False."""
    db = db_limpia()
    corrida = corrida_con_tension(db)
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["injertos_propuestos"] == 0
    assert cierre["sin_injertos"] is True
    assert "nota_sin_injertos" in cierre

    db2 = db_limpia()
    corrida2 = corrida_con_tension(db2)
    sim.registrar_injerto(db2, corrida2.id, SPEC_OK)
    cierre2 = sim.cerrar_corrida(db2, corrida2.id)
    assert cierre2["injertos_propuestos"] == 1
    assert cierre2["sin_injertos"] is False
    assert "nota_sin_injertos" not in cierre2


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
