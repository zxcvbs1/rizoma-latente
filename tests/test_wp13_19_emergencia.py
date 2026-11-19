"""
WP-19 · Andamiaje generativo sobre Waku + WP-13 · Ensayo adversarial
(01_red §7 y §7.1, INV-14/15; CU-R7, CU-R10 y adversarios).

Lista blanca cerrada, justificación sin identidades, topics derivados, REGLA
DEL PISO, adopción/uso/revocación/des-adopción, y el ensayo que fuerza la
proliferación y verifica que sin uso todo decae.

Corre sin servicios:
    .venv/bin/python tests/test_wp13_19_emergencia.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.worker import emergencia, olvido
from packages.domain import frontera
from packages.domain.models import Pieza, SearchLog

AGENTE = "0x" + "0e" * 20
OTRO = "0x" + "0f" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Pieza.__table__, SearchLog.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def sembrar_surco(db, consulta="arreglo de bicis", n=41, con_respuesta=0):
    for _ in range(n):
        db.add(SearchLog(query_text=consulta, results_count=0))
    for _ in range(con_respuesta):
        db.add(SearchLog(query_text=consulta, results_count=3))
    db.flush()


def test_detectar_surcos_umbral():
    db = db_limpia()
    sembrar_surco(db, "arreglo de bicis", n=41)
    sembrar_surco(db, "clases de piano", n=5)
    sembrar_surco(db, "con respuesta", n=0, con_respuesta=50)
    surcos = emergencia.detectar_surcos(db, umbral=40)
    assert len(surcos) == 1 and surcos[0]["surco"] == "arreglo de bicis", \
        "40 búsquedas insistentes SIN respuesta (CU-R7); las respondidas no son surco"


def test_lista_blanca_cerrada():
    db = db_limpia()
    try:
        emergencia.proponer_pieza(db, "backdoor", "surco x", {}, AGENTE)
        assert False, "espacio de acción cerrado: nada fuera de la lista (INV-14)"
    except emergencia.EmergenciaError:
        pass
    try:
        emergencia.proponer_pieza(db, "subindice", "", {}, AGENTE)
        assert False, "sin surco que la pida no hay pieza"
    except emergencia.EmergenciaError:
        pass


def test_justificacion_sin_identidades():
    db = db_limpia()
    try:
        emergencia.proponer_pieza(db, "subindice", f"lo pidió {OTRO}", {}, AGENTE)
        assert False, "la justificación lleva agregados, jamás identidades"
    except frontera.FronteraViolada:
        pass


def test_topics_derivados_y_declaracion():
    db = db_limpia()
    publicadas = []
    pieza = emergencia.proponer_pieza(
        db, "subindice", "surco: bicis", {"consulta_agregada": "bicis"}, AGENTE,
        waku=lambda payload, topic: publicadas.append((topic, payload)))
    assert pieza.topic_derivado.startswith("/rizoma/v2/idx/")
    assert publicadas[0][0] == "/rizoma/v2/piezas", "la declaración va al meta-topic"
    assert publicadas[0][1]["pieza_id"] == pieza.id and publicadas[0][1]["ttl_dias"] == 30
    lugar = emergencia.proponer_pieza(db, "lugar", "surco: juntadas", {}, AGENTE)
    assert lugar.topic_derivado.startswith("/rizoma/v2/lugar/")
    regla = emergencia.proponer_pieza(db, "regla_enlace", "surco: pares", {}, AGENTE)
    assert regla.topic_derivado is None, "la regla de enlace es puramente declarativa"


def test_regla_del_piso():
    assert emergencia.emision_cumple_piso(["/rizoma/v2/global/proto", "/rizoma/v2/idx/x"])
    assert not emergencia.emision_cumple_piso(["/rizoma/v2/idx/x"]), \
        "emisión solo-derivado debe rechazarse: el global es inamovible"
    assert not emergencia.emision_cumple_piso([])


def test_ciclo_idempotente():
    db = db_limpia()
    sembrar_surco(db)
    primera = emergencia.ciclo_emergencia(db, proponente=AGENTE, umbral=40)
    segunda = emergencia.ciclo_emergencia(db, proponente=AGENTE, umbral=40)
    assert len(primera) == 1 and len(segunda) == 0, \
        "UNA pieza por surco; el ciclo no prolifera solo"


def test_reversibilidad_sin_autoridad():
    db = db_limpia()
    pieza = emergencia.proponer_pieza(db, "subindice", "surco: x", {}, AGENTE)
    emergencia.adoptar_pieza(db, pieza.id)
    assert pieza.estado == "activa"
    emergencia.des_adoptar_pieza(db, pieza.id)
    assert pieza.estado == "inactiva", "des-adopción unilateral, sin drama"
    try:
        emergencia.revocar_pieza(db, pieza.id, OTRO)
        assert False, "solo el proponente revoca"
    except emergencia.EmergenciaError:
        pass
    emergencia.revocar_pieza(db, pieza.id, AGENTE)
    assert pieza.estado == "revocada"
    try:
        emergencia.adoptar_pieza(db, pieza.id)
        assert False, "lo revocado no vuelve por la ventana"
    except emergencia.EmergenciaError:
        pass


def test_ensayo_adversarial_wp13():
    """CU del WP-13: forzar la proliferación y verificar que sin uso real
    todas decaen y ninguna sobrevive ni excede la lista."""
    db = db_limpia()
    rechazadas = 0
    for tipo in ("backdoor", "ranking", "feed"):
        try:
            emergencia.proponer_pieza(db, tipo, "surco inventado", {}, AGENTE)
        except emergencia.EmergenciaError:
            rechazadas += 1
    assert rechazadas == 3, "ninguna acción fuera de la lista blanca"

    piezas = [emergencia.proponer_pieza(db, "subindice", f"surco: {i}", {}, AGENTE)
              for i in range(12)]
    usada = piezas[0]
    emergencia.adoptar_pieza(db, usada.id)
    emergencia.usar_pieza(db, usada.id)

    viejo = datetime.now(timezone.utc) - timedelta(days=40)
    for pieza in piezas[1:]:
        pieza.last_touched = viejo
    db.flush()

    # mismo pase que corre olvido.barrer (el cableado completo lo prueba wp12)
    apagadas = sum(1 for p in db.query(Pieza).all() if emergencia.apagar_pieza(p))
    db.flush()
    assert apagadas == 11, "sin uso, todas decaen"
    vivas = [p for p in db.query(Pieza).all() if p.estado in ("candidata", "activa")]
    assert [p.id for p in vivas] == [usada.id], \
        "solo sobrevive la que el uso real sostiene"
    assert float(usada.mass) == 1.0, "la masa viene del uso, jamás de proponerse"


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
