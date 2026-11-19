"""
WP-04 · Controles del perfil (INV-05; CU-T6, CU-S5 a escala red).

Ver: la huella completa y nada más. Llevarse: la misma huella, exportable.
Borrar: cascada real; tras borrar, nada puede referenciar a la persona.

Corre sin servicios:
    .venv/bin/python tests/test_wp04_controles.py
"""
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account

from apps.api import controles
from apps.api.security import SecurityService
from packages.domain.identity import sign_text
from packages.domain.models import (Actor, Deslizamiento, Link, Node, Partida,
                                    Synapse, TerminoMapa)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class FakeDB:
    """Almacén en memoria por modelo; filter se resuelve en el módulo, no acá."""

    def __init__(self, **stores):
        self.stores = {Actor: [], Node: [], Link: [], Synapse: [],
                       TerminoMapa: [], Deslizamiento: [], Partida: []}
        for nombre, filas in stores.items():
            modelo = {"actors": Actor, "nodes": Node, "links": Link, "synapses": Synapse}[nombre]
            self.stores[modelo] = filas

    def query(self, modelo):
        return FakeQuery(self.stores[modelo])

    def delete(self, obj):
        for filas in self.stores.values():
            if obj in filas:
                filas.remove(obj)


ANA = "0x" + "a1" * 20
BRUNO = "0x" + "b2" * 20
AHORA = datetime.now(timezone.utc)


def fixture_db():
    return FakeDB(
        actors=[
            SimpleNamespace(id=ANA, reputation=0.8, last_seen_at=AHORA),
            SimpleNamespace(id=BRUNO, reputation=0.5, last_seen_at=AHORA),
        ],
        nodes=[
            SimpleNamespace(id="ofrezco-1", actor_id=ANA, text_raw="!ofrezco bici",
                            state="active", mass=2.0, created_at=AHORA),
            SimpleNamespace(id="busco-2", actor_id=BRUNO, text_raw="!busco bici",
                            state="active", mass=1.0, created_at=AHORA),
        ],
        links=[
            SimpleNamespace(id="l1", actor_id=ANA, node_a_id="ofrezco-1",
                            node_b_id="busco-2", created_at=AHORA),
        ],
        synapses=[
            SimpleNamespace(id="s1", origin_actor_id=ANA, target_actor_id=BRUNO,
                            status="active", created_at=AHORA),
        ],
    )


def test_huella_completa_y_nada_mas():
    huella = controles.armar_huella(fixture_db(), ANA)
    assert huella["llave"] == ANA
    assert len(huella["intenciones"]) == 1, "solo las intenciones de la llave"
    assert huella["intenciones"][0]["texto"] == "!ofrezco bici"
    assert len(huella["vinculos"]) == 1
    assert len(huella["sinapsis"]) == 1
    assert huella["sinapsis"][0]["con"] == BRUNO, "el vínculo dice con quién, es de dos firmas"
    assert "nada más existe" in huella["nota"].lower()


def test_borrar_borra_en_cascada():
    db = fixture_db()
    contadores = controles.borrar_actor(db, ANA)
    assert contadores == {"sinapsis": 1, "vinculos": 1, "intenciones": 1, "actor": 1,
                          "topologia": 0, "partidas": 0}
    # tras borrar, ninguna estructura puede referenciar a la persona
    assert all(n.actor_id != ANA for n in db.stores[Node])
    assert all(l.actor_id != ANA for l in db.stores[Link])
    assert all(ANA not in (s.origin_actor_id, s.target_actor_id) for s in db.stores[Synapse])
    assert all(a.id != ANA for a in db.stores[Actor])
    # y el resto del mundo sigue intacto
    assert len(db.stores[Node]) == 1 and db.stores[Node][0].actor_id == BRUNO
    assert len(db.stores[Actor]) == 1


def test_huella_tras_borrar_esta_vacia():
    db = fixture_db()
    controles.borrar_actor(db, ANA)
    huella = controles.armar_huella(db, ANA)
    assert huella["reputacion"] is None
    assert huella["intenciones"] == [] and huella["vinculos"] == [] and huella["sinapsis"] == []


def test_firma_del_control():
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def exists(self, k):
            return 1 if k in self.store else 0

        def setex(self, k, ttl, v):
            self.store[k] = str(v)

    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    actor = Account.from_key(pk).address
    msg = controles.canonical_actor(actor, "2026-07-07T00:00:00Z", "n1", "erase")
    assert sec.verify_eip191_signature(actor, sign_text(pk, msg), msg)
    otro = Account.create().key.hex()
    assert not sec.verify_eip191_signature(actor, sign_text(otro, msg), msg), \
        "nadie borra el perfil de otro"


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
