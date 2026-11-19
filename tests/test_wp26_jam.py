"""
WP-26 · Modo jam, la capa semántica sobre el CRDT (09_procomun §2.5; INV-11/18/19).

El transporte (CRDT sobre Waku que sincroniza el estado compartido P2P) es lo
VIVO. Acá se prueba lo que va ENCIMA: en el jam cualquiera propone ediciones a
la vez (sin turnos), pero una edición entra al estado legítimo solo si pasó la
validación cruzada. El más rápido no corona: escribir no es ser aceptado.

Corre sin servicios:
    .venv/bin/python tests/test_wp26_jam.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_aventura import multiplayer as mp
from packages.domain import frontera
from packages.domain.models import Forma, PesoContribucion, SesionMultiplayer

A = "0x" + "a1" * 20
B = "0x" + "b2" * 20
C = "0x" + "c3" * 20
LLAVE = "0x" + "dd" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (SesionMultiplayer.__table__, Forma.__table__, PesoContribucion.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def jam_tres(db):
    s = mp.abrir_jam(db, A)
    mp.entrar(db, s.id, B, con_fierro=True)
    mp.entrar(db, s.id, C, con_fierro=True)
    return s


def test_jam_es_sincrono_sin_gm():
    db = db_limpia()
    s = jam_tres(db)
    assert s.estado == "jam" and s.gm_actual is None, "en el jam no hay GM sorteado"


def test_cualquiera_propone_y_frontera_bloquea_identidad():
    db = db_limpia()
    s = jam_tres(db)
    r = mp.proponer_edicion(db, s.id, B, {"texto": "una línea del sueño"})
    assert r["estado"] == "pendiente"
    try:
        mp.proponer_edicion(db, s.id, B, {"texto": f"la firma {LLAVE}"})
        assert False, "una edición con identidad la bloquea la frontera"
    except frontera.FronteraViolada:
        pass


def test_el_mas_rapido_no_corona():
    db = db_limpia()
    s = jam_tres(db)
    # A propone; queda PENDIENTE aunque el CRDT ya la haya sincronizado
    eid = mp.proponer_edicion(db, s.id, A, {"texto": "propongo esto"})["edicion_id"]
    assert mp._jams[s.id]["historia"] == [], "proponer no es ser aceptado"
    # un par rechaza -> no entra
    mp.validar_edicion(db, s.id, B, eid, acepta=False)
    r = mp.resolver_edicion(db, s.id, eid)
    assert r["aceptada"] is False and mp._jams[s.id]["historia"] == []


def test_edicion_avalada_entra_y_acredita():
    db = db_limpia()
    s = jam_tres(db)
    eid = mp.proponer_edicion(db, s.id, A, {"texto": "una que va"})["edicion_id"]
    mp.validar_edicion(db, s.id, B, eid, acepta=True)
    mp.validar_edicion(db, s.id, C, eid, acepta=True)
    r = mp.resolver_edicion(db, s.id, eid)
    assert r["aceptada"] is True and len(mp._jams[s.id]["historia"]) == 1
    from apps.worker import pool
    assert pool.peso_de(db, A, "jam") == 1.0, "componer en la jam aporta al común"


def test_autor_no_valida_su_edicion():
    db = db_limpia()
    s = jam_tres(db)
    eid = mp.proponer_edicion(db, s.id, A, {"texto": "mía"})["edicion_id"]
    try:
        mp.validar_edicion(db, s.id, A, eid, acepta=True)
        assert False, "el autor no valida su propia edición"
    except mp.MultiplayerError:
        pass


def test_ediciones_concurrentes_independientes():
    db = db_limpia()
    s = jam_tres(db)
    e1 = mp.proponer_edicion(db, s.id, A, {"texto": "linea A"})["edicion_id"]
    e2 = mp.proponer_edicion(db, s.id, B, {"texto": "linea B"})["edicion_id"]
    assert len(mp._jams[s.id]["pendientes"]) == 2, "varias ediciones a la vez, sin turnos"
    mp.validar_edicion(db, s.id, C, e1, acepta=True)
    mp.resolver_edicion(db, s.id, e1)
    assert len(mp._jams[s.id]["pendientes"]) == 1 and len(mp._jams[s.id]["historia"]) == 1


def test_jam_muere_al_cierre():
    db = db_limpia()
    s = jam_tres(db)
    mp.proponer_edicion(db, s.id, A, {"texto": "algo"})
    mp.cerrar_jam(db, s.id)
    assert s.id not in mp._jams, "la historia y pendientes efímeras murieron"
    assert mp.auditar_sesiones(db) == [], "ninguna ficción viva en jam cerrada"


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
