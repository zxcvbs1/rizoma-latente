"""
WP-28 · La gramática de las resonancias (INV-03/11/12/17).

Los comandos no son un vocabulario fijo: viven por uso. Cada emisión que
porta un !comando le suma masa (gramaticalización); el barrido de olvido
apaga los que nadie usa (desgramaticalización) y quedan en masa 0,
regramaticalizables si alguien los retoma. El vocabulario vivo es el
agregado de lo que tiene masa > 0. El TTL de una señal lo puede declarar
quien la emite; sin declaración rige el TTL global del nodo.

Corre sin servicios:
    .venv/bin/python tests/test_wp28_gramatica.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.worker import gramatica, olvido
from packages.domain.models import ComandoVivo

AHORA = datetime.now(timezone.utc)
VIEJO = AHORA - timedelta(days=40)
RECIENTE = AHORA - timedelta(days=2)


def db_limpia():
    engine = create_engine("sqlite://")
    ComandoVivo.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_comando_nuevo_nace_y_gana_masa():
    db = db_limpia()
    gramatica.gramaticalizar(db, "sueño")
    gramatica.gramaticalizar(db, "sueño")
    fila = db.query(ComandoVivo).filter(ComandoVivo.slug == "sueño").first()
    assert fila is not None, "el comando nace con el primer uso"
    assert fila.mass == 2.0, "cada emisión que lo porta le suma masa"


def test_comando_invalido_no_gramaticaliza():
    db = db_limpia()
    largo = "a" * (gramatica.COMANDO_MAX_LARGO + 1)
    assert not gramatica.comando_valido(largo)
    assert gramatica.gramaticalizar(db, largo) is None

    con_identidad = "0x" + "ab" * 20
    assert not gramatica.comando_valido(con_identidad)
    assert gramatica.gramaticalizar(db, con_identidad) is None

    assert not gramatica.comando_valido("")
    assert gramatica.gramaticalizar(db, "") is None

    assert db.query(ComandoVivo).count() == 0, "ningún inválido crea fila"


def test_desgramaticalizacion_y_revivir():
    db = db_limpia()
    gramatica.gramaticalizar(db, "invoco")
    fila = db.query(ComandoVivo).filter(ComandoVivo.slug == "invoco").first()
    fila.last_touched = VIEJO
    db.flush()

    assert olvido.decaer_arista(fila, AHORA), "sin uso por ttl_dias, se apaga"
    assert fila.mass == 0.0, "olvidado: masa 0, la fila queda"

    gramatica.gramaticalizar(db, "invoco")
    fila = db.query(ComandoVivo).filter(ComandoVivo.slug == "invoco").first()
    assert fila.mass == 1.0, "retomarlo lo revive con masa nueva"


def test_vocabulario_solo_lo_vivo():
    db = db_limpia()
    gramatica.gramaticalizar(db, "busco")
    gramatica.gramaticalizar(db, "busco")
    gramatica.gramaticalizar(db, "ofrezco")
    olvidado = ComandoVivo(slug="olvidado", mass=0.0, last_touched=VIEJO)
    db.add(olvidado)
    db.flush()

    vivos = [c for c in db.query(ComandoVivo).all() if (c.mass or 0) > 0]
    vivos.sort(key=lambda c: c.mass, reverse=True)
    slugs = [c.slug for c in vivos]
    assert "olvidado" not in slugs, "masa 0 no aparece en el vocabulario"
    assert slugs == ["busco", "ofrezco"], "orden por masa descendente"


def test_ttl_declarado_gobierna_el_decay():
    # ttl_dias propio (5 días): con RECIENTE (2 días) sigue vivo, con VIEJO
    # calibrado a 6 días atrás decae aunque el TTL global sea 30.
    hace_6_dias = AHORA - timedelta(days=6)
    con_ttl_propio = SimpleNamespace(state="active", last_touched=hace_6_dias,
                                      created_at=hace_6_dias, mass=1.0, ttl_dias=5)
    assert olvido.decaer_intencion(con_ttl_propio, AHORA), "el ttl propio (5d) manda, no el global (30d)"
    assert con_ttl_propio.state == "archived" and con_ttl_propio.mass == 0.0

    sin_ttl_propio = SimpleNamespace(state="active", last_touched=hace_6_dias,
                                      created_at=hace_6_dias, mass=1.0, ttl_dias=None)
    assert not olvido.decaer_intencion(sin_ttl_propio, AHORA), "sin ttl propio rige el global (30d)"
    assert sin_ttl_propio.state == "active" and sin_ttl_propio.mass == 1.0


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
