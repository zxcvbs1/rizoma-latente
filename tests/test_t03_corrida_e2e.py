"""
T-03 · Corrida aleatoria completa de punta a punta (CU-C1, CU-C4; INV-07/16/17).

El bucle entero de la escala comunidad con un cliente stub (sin modelo real):
iniciar, poblar con agentes aleatorios (sin dobles), rondas con contexto y actos
validados, tensiones, cristalizar injerto, A/B, exportar partida jugable, cerrar.
Verifica que las auditorías de mal alimento dan cero.

Corre sin servicios:
    .venv/bin/python tests/test_t03_corrida_e2e.py
"""
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
from packages.domain.models import (Corrida, Deslizamiento, Forma, Injerto, Partida,
                                    Tension, TerminoMapa)

OPERADOR = "0x" + "0a" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Tension.__table__, Injerto.__table__,
                  Partida.__table__, TerminoMapa.__table__, Deslizamiento.__table__,
                  Forma.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


# --- Cliente stub: lo que un modelo real devolvería, sin modelo ---

def stub_acto(rol, contexto):
    """El cliente propone un acto materialmente posible dado el inventario."""
    inventario = contexto["inventario"]
    recurso = next((r for r, c in inventario.items() if c > 0), None)
    costo = {recurso: 1} if recurso else {}
    return {"descripcion": f"{rol} usa lo que hay", "costo": costo}


def stub_tensiones(roles):
    return [{"tipo": "carga desigual", "roles": roles[:2],
             "evidencia": f"{roles[0]}: 'siempre termino haciéndolo yo'"}]


def test_corrida_completa_demo_aleatoria():
    db = db_limpia()

    # 1. iniciar (modo demo: población aleatoria, sin topologías reales)
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado",
                                  inventario={"horas": 6, "salon": 1}, presupuesto_rondas=3)
    roles = ["la que cocina", "el que abre", "la tesorera"]
    for rol in roles:
        r = sim.sumar_participante(db, corrida.id, rol, security=None, token=None)
        assert r["poblacion"] == "aleatoria", "sin token: agentes aleatorios (demo segura)"

    # 2. bucle de rondas: contexto -> acto validado -> avanzar
    for _ in range(2):
        for rol in roles:
            ctx = sim.contexto_ronda(db, corrida.id, rol)
            assert set(ctx) <= sim.CAMPOS_CONTEXTO_RONDA, "contexto mínimo (INV-17)"
            assert not frontera.contiene_identidades(str(ctx)), "roles, jamás llaves"
            sim.acto_ronda(db, corrida.id, rol, stub_acto(rol, ctx))
        sim.avanzar_ronda(db, corrida.id)

    # 3. tensiones leídas del cliente, validadas y por rol
    n = sim.leer_tensiones(db, corrida.id, stub_tensiones(roles))
    assert n == 1

    # 4. premisas -> injerto (regla de oro) -> A/B -> exportar partida jugable
    pre = sim.premisas(db, corrida.id)
    assert pre["marco"] == "cuidado" and "salon" in pre["sobra"]
    injerto = sim.registrar_injerto(db, corrida.id, {
        "nombre": "turnos de apertura rotativos",
        "tension_que_ataca": "carga desigual",
        "regla_logica": "abrir el salón rota entre tres, a la vista",
        "flujo": "cada semana pasa al siguiente",
        "requisitos_materiales": {"salon": 1},
        "senales_alivio": "abre gente distinta; nadie carga solo"})
    sim.validar_ab(db, injerto.id, "APROBADO",
                   "con la regla, la carga se reparte en la ronda 2",
                   metricas_sin={"carga_concentrada": 3}, metricas_con={"carga_concentrada": 1})
    guion = sim.exportar_protocolo(db, injerto.id)
    assert "turnos de apertura rotativos" in guion["titulo"]

    # 5. cierre + auditorías en cero (el mal alimento no existe)
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["marco"] == "cuidado" and cierre["tensiones"]
    assert corrida.id not in sim._corridas, "toda la memoria de corrida murió"
    assert sim.auditar_corridas(db) == [], "ninguna corrida cerrada conserva memoria viva"
    assert aventura.auditar_mal_alimento(db) == [], \
        "ningún store puede retener dobles, tokens ni topologías (CU-T5)"


def test_acto_imposible_no_avanza_el_estado():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "bienes_comunes", inventario={"madera": 1})
    sim.sumar_participante(db, corrida.id, "el carpintero", security=None, token=None)
    ctx = sim.contexto_ronda(db, corrida.id, "el carpintero")
    try:
        sim.acto_ronda(db, corrida.id, "el carpintero",
                       {"descripcion": "hace diez mesas", "costo": {"madera": 10}})
        assert False, "un acto materialmente imposible se rechaza"
    except sim.MotorSimError:
        pass
    assert sim._corridas[corrida.id].inventario == {"madera": 1}, "el estado quedó intacto"


def test_marco_desconocido_ensena_el_camino():
    db = db_limpia()
    try:
        sim.iniciar_corrida(db, OPERADOR, "marco-que-no-existe")
        assert False, "un marco desconocido no arranca la corrida"
    except sim.MotorSimError as exc:
        assert "acervo_proponer_rubrica" in str(exc) and "tipo='lente'" in str(exc), \
            "el error carga el camino completo para publicar una lente"


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
