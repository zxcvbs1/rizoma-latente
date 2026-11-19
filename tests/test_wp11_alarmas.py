"""
WP-11 · Alarmas de salud (INV-13, INV-16; CU-T3, CU-T4).

Señales agregadas y anónimas, visibles en el espejo: surco/riel (diversidad
decreciente sostenida) y absorción (sesiones que no quieren terminar). Son
alarmas, jamás KPIs: el módulo no escribe y nada las consume.

Corre sin servicios:
    .venv/bin/python tests/test_wp11_alarmas.py
"""
import json
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.worker import alarmas
from packages.domain import frontera

LLAVE = "0x" + "a1" * 20


def sinapsis(mes, nodo_a="n1", nodo_b="n2", status="active"):
    return SimpleNamespace(status=status, created_at=datetime(2026, mes, 5),
                           origin_node_id=nodo_a, target_node_id=nodo_b,
                           origin_actor_id=LLAVE, target_actor_id=LLAVE)


def nodo(nid, slug):
    return SimpleNamespace(id=nid, command_slug=slug, actor_id=LLAVE)


def test_surco_riel_decreciente_dispara():
    nodos = {f"n{i}": nodo(f"n{i}", f"slug-{i}") for i in range(10)}
    filas = (
        [sinapsis(3, f"n{i}", f"n{i+1}") for i in range(4)]      # marzo: diversidad alta
        + [sinapsis(4, "n1", "n2"), sinapsis(4, "n3", "n4")]      # abril: baja
        + [sinapsis(5, "n1", "n2")]                                # mayo: mínima
    )
    senal = alarmas.senal_surco_riel(filas, nodos)
    assert [f["mes"] for f in senal["serie"]] == ["2026-03", "2026-04", "2026-05"]
    assert senal["alarma"] is True
    assert "riel" in senal["lectura"]


def test_surco_riel_sano_no_dispara():
    nodos = {f"n{i}": nodo(f"n{i}", f"slug-{i}") for i in range(8)}
    filas = [sinapsis(3, "n1", "n2")] + \
            [sinapsis(4, f"n{i}", f"n{i+1}") for i in range(3)] + \
            [sinapsis(5, f"n{i}", f"n{i+1}") for i in range(6)]
    senal = alarmas.senal_surco_riel(filas, nodos)
    assert senal["alarma"] is False
    proposed = alarmas.senal_surco_riel([sinapsis(5, status="proposed")], nodos)
    assert proposed["serie"] == [], "solo cuentan coordinaciones activas"


def test_absorcion_creciente_dispara():
    def partida(mes, minutos):
        inicio = datetime(2026, mes, 3, 20, 0)
        return SimpleNamespace(estado="cerrada", created_at=inicio,
                               closed_at=inicio + timedelta(minutes=minutos),
                               jugador_llave=LLAVE)
    senal = alarmas.senal_absorcion([partida(3, 20), partida(4, 45), partida(5, 90)])
    assert senal["alarma"] is True
    assert "familia" in senal["lectura"], "la regla de familia de 02_sujeto §6"
    corta = alarmas.senal_absorcion([partida(3, 90), partida(4, 45), partida(5, 20)])
    assert corta["alarma"] is False
    abierta = SimpleNamespace(estado="abierta", created_at=datetime(2026, 5, 1), closed_at=None)
    assert alarmas.senal_absorcion([abierta])["serie"] == []


def test_agregado_sin_persona():
    nodos = {"n1": nodo("n1", "ofrezco"), "n2": nodo("n2", "busco")}
    surco = alarmas.senal_surco_riel([sinapsis(5)], nodos)
    partida = SimpleNamespace(estado="cerrada", created_at=datetime(2026, 5, 1, 20),
                              closed_at=datetime(2026, 5, 1, 21), jugador_llave=LLAVE)
    absorcion = alarmas.senal_absorcion([partida])
    assert not frontera.contiene_identidades(json.dumps(surco)), \
        "entran filas con llaves, salen números sin nadie"
    assert not frontera.contiene_identidades(json.dumps(absorcion))


def test_cero_escrituras_y_nadie_las_consume():
    fuente = open(os.path.join(REPO, "apps/worker/alarmas.py")).read()
    for prohibido in ("db.add", ".commit(", ".flush(", "redis"):
        assert prohibido not in fuente, f"las alarmas no escriben: encontré {prohibido}"
    motor_busqueda = open(os.path.join(REPO, "packages/adapters/engine.py")).read()
    assert "alarma" not in motor_busqueda.lower(), \
        "la señal jamás alimenta el ranking (INV-16)"


def test_vista_del_espejo_integrada():
    from apps.espejo import espejo
    from packages.domain.models import Node, Partida, Synapse, Forma

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return list(self.rows)

    class FakeDB:
        def __init__(self):
            self.data = {Node: [nodo("n1", "ofrezco"), nodo("n2", "busco")],
                         Synapse: [sinapsis(5)],
                         Partida: [], Forma: []}

        def query(self, modelo):
            return FakeQuery(self.data[modelo])

    vista = espejo.vista_alarmas(FakeDB())
    assert "surco_riel" in vista and "absorcion" in vista
    assert "ningún motor las consume" in vista["nota"]


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
