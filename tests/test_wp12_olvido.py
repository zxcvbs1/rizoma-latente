"""
WP-12 · Olvido estructural (INV-03; 01_red §6; CU-R5).

Nada pesa para siempre: intención sin interacción decae a masa ~0 y se
archiva (renovable por su autor); reputación inactiva cae a peso nulo;
propuestas sin dirigirse expiran en silencio.

Corre sin servicios:
    .venv/bin/python tests/test_wp12_olvido.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.worker import olvido
from apps.m2_handshake import gradiente

AHORA = datetime.now(timezone.utc)
VIEJO = AHORA - timedelta(days=40)
RECIENTE = AHORA - timedelta(days=2)


def nodo(state="active", tocado=VIEJO, masa=2.0):
    return SimpleNamespace(state=state, last_touched=tocado, created_at=tocado, mass=masa)


def test_intencion_vieja_decae_y_se_archiva():
    n = nodo()
    assert olvido.decaer_intencion(n, AHORA)
    assert n.state == "archived" and n.mass == 0.0, "masa ~0, archivada, no borrada"


def test_intencion_reciente_no_decae():
    n = nodo(tocado=RECIENTE)
    assert not olvido.decaer_intencion(n, AHORA)
    assert n.state == "active" and n.mass == 2.0


def test_renovar_es_acto_del_autor():
    n = nodo()
    olvido.decaer_intencion(n, AHORA)
    olvido.renovar_intencion(n, AHORA)
    assert n.state == "active" and n.mass >= 1.0, "renovable por su autor (CU-R5)"


def test_reputacion_inactiva_cae_a_nulo():
    actor = SimpleNamespace(reputation=0.9, last_seen_at=VIEJO)
    assert olvido.decaer_reputacion(actor, AHORA)
    assert actor.reputation == 0.0, "~30 días de inactividad = peso nulo (INV-12)"


def test_reputacion_activa_se_mantiene():
    actor = SimpleNamespace(reputation=0.9, last_seen_at=RECIENTE)
    assert not olvido.decaer_reputacion(actor, AHORA)
    assert actor.reputation == 0.9


def test_barrido_completo():
    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return list(self.rows)

    class FakeDB:
        def __init__(self):
            from packages.domain.models import (Actor, ComandoVivo, Deslizamiento, Forma,
                                                Node, Partida, Pieza, PesoContribucion,
                                                SesionMultiplayer, Synapse,
                                                TareaComun, TerminoMapa)
            self.data = {
                ComandoVivo: [SimpleNamespace(slug="viejo", mass=1.0, last_touched=VIEJO,
                                              created_at=VIEJO),
                              SimpleNamespace(slug="reciente", mass=1.0, last_touched=RECIENTE,
                                              created_at=RECIENTE)],
                SesionMultiplayer: [SimpleNamespace(estado="abierta", created_at=VIEJO,
                                                    escena_propuesta=None, id="s-vieja"),
                                    SimpleNamespace(estado="abierta", created_at=RECIENTE,
                                                    escena_propuesta=None, id="s-nueva")],
                TareaComun: [SimpleNamespace(estado="abierta", ttl_dias=7, created_at=VIEJO),
                             SimpleNamespace(estado="abierta", ttl_dias=7, created_at=RECIENTE)],
                PesoContribucion: [SimpleNamespace(peso=2.0, last_touched=VIEJO),
                                   SimpleNamespace(peso=2.0, last_touched=RECIENTE)],
                Pieza: [SimpleNamespace(estado="candidata", mass=0.0, ttl_dias=30,
                                        last_touched=VIEJO, created_at=VIEJO),
                        SimpleNamespace(estado="activa", mass=3.0, ttl_dias=30,
                                        last_touched=RECIENTE, created_at=RECIENTE)],
                Forma: [SimpleNamespace(mass=1.0, last_touched=VIEJO, created_at=VIEJO),
                        SimpleNamespace(mass=1.0, last_touched=RECIENTE, created_at=RECIENTE)],
                Node: [nodo(), nodo(tocado=RECIENTE)],
                Actor: [SimpleNamespace(reputation=0.5, last_seen_at=VIEJO),
                        SimpleNamespace(reputation=0.5, last_seen_at=RECIENTE)],
                Synapse: [SimpleNamespace(status=gradiente.PROPOSED, created_at=VIEJO),
                          SimpleNamespace(status=gradiente.ACTIVE, created_at=VIEJO),
                          SimpleNamespace(status=gradiente.PROPOSED, created_at=RECIENTE)],
                TerminoMapa: [SimpleNamespace(mass=1.0, last_touched=VIEJO, created_at=VIEJO)],
                Deslizamiento: [SimpleNamespace(mass=1.0, last_touched=RECIENTE, created_at=RECIENTE)],
                Partida: [SimpleNamespace(id="p-vieja", estado="abierta", created_at=VIEJO, closed_at=None),
                          SimpleNamespace(id="p-nueva", estado="abierta", created_at=RECIENTE, closed_at=None),
                          SimpleNamespace(id="p-cerrada", estado="cerrada", created_at=VIEJO, closed_at=VIEJO)],
            }

        def query(self, modelo):
            return FakeQuery(self.data[modelo])

    db = FakeDB()
    contadores = olvido.barrer(db, AHORA)
    assert contadores == {"intenciones_archivadas": 1, "reputaciones_nulas": 1,
                          "sinapsis_expiradas": 1, "topologia_apagada": 1,
                          "partidas_cerradas": 1, "formas_apagadas": 1,
                          "piezas_apagadas": 1, "tareas_vencidas": 1, "pesos_nulos": 1,
                          "sesiones_cerradas": 1, "comandos_olvidados": 1}
    from packages.domain.models import Pieza
    vieja_pieza = db.data[Pieza][0]
    assert vieja_pieza.estado == "inactiva", "la pieza sin uso se desactiva sola (INV-14)" 
    from packages.domain.models import Partida
    vieja = db.data[Partida][0]
    assert vieja.estado == "cerrada" and vieja.closed_at is not None, \
        "la partida huérfana se cierra sola (INV-13)" 
    from packages.domain.models import Synapse
    estados = [s.status for s in db.data[Synapse]]
    assert estados == [gradiente.EXPIRED, gradiente.ACTIVE, gradiente.PROPOSED], \
        "el vínculo activo no expira; la propuesta fresca tampoco"


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
