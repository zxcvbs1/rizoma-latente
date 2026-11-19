"""
WP-09 · El mundo-espejo (03 §7, INV-09; CU-T1 y adversarios).

Estructuralmente sin persona: vistas de agregados y formas, fallo cerrado si
una identidad se coló al store, cero escrituras (verificado sobre el fuente),
ninguna vista acepta consultar por alguien.

Corre sin servicios:
    .venv/bin/python tests/test_wp09_espejo.py
"""
import inspect
import os
import sys
from datetime import datetime
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.espejo import espejo
from packages.domain import frontera
from packages.domain.models import Forma, Node

LLAVE = "0x" + "a1" * 20


def db_formas():
    engine = create_engine("sqlite://")
    Forma.__table__.create(engine)
    return sessionmaker(bind=engine)()


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, nodes=(), formas=(), comandos=()):
        from packages.domain.models import ComandoVivo
        self.data = {Node: list(nodes), Forma: list(formas),
                     ComandoVivo: list(comandos)}

    def query(self, modelo):
        return FakeQuery(self.data[modelo])


def forma_limpia(**extra):
    base = dict(id="f1", tipo="tension_tipo", nombre="el filtro",
                descripcion="lo inclasificable se descarta", contexto_material="{}",
                marco="cuidado", procedencia="comunidad anónima, 2026-07-08",
                regla_consentimiento="unanimidad", licencia="abierta", linaje=None,
                estado="publicada", mass=1.0, created_at=datetime(2026, 7, 8))
    base.update(extra)
    return Forma(**base)


def test_vista_formas_limpia_y_con_linaje():
    db = db_formas()
    db.add(forma_limpia())
    db.add(forma_limpia(id="f2", nombre="el filtro, torcido", linaje="f1"))
    db.add(forma_limpia(id="f3", estado="retirada"))
    db.commit()
    vista = espejo.vista_formas(db)
    assert len(vista["formas"]) == 2, "la retirada no se navega"
    assert vista["linaje"] == [{"de": "f1", "a": "f2"}], "el linaje es enlace lateral"
    assert vista["por_tipo"] == {"tension_tipo": 2}


def test_fallo_cerrado_ante_identidad_en_el_store():
    db = db_formas()
    db.add(forma_limpia(descripcion=f"la administra {LLAVE}"))  # veneno directo al store
    db.commit()
    try:
        espejo.vista_formas(db)
        assert False, "el espejo debe negarse a servir, no filtrar en silencio"
    except frontera.FronteraViolada:
        pass


def test_lengua_es_agregado_sin_actor():
    """WP-28: la lengua del espejo sale de ComandoVivo (la fuente con
    olvido), no de agregar Nodes: lo apagado (masa 0) no aparece."""
    import json
    db = FakeDB(comandos=[
        SimpleNamespace(slug="ofrezco", mass=2.0),
        SimpleNamespace(slug="permuto", mass=5.0),
        SimpleNamespace(slug="sueno", mass=0.0),  # desgramaticalizado: fuera
    ])
    vista = espejo.vista_lengua(db)
    assert vista["lengua"][0] == {"comando": "permuto", "masa": 5.0}
    assert all(fila["comando"] != "sueno" for fila in vista["lengua"]), \
        "un comando olvidado no aparece en el espejo (la lengua olvida)"
    assert not frontera.contiene_identidades(json.dumps(vista)), \
        "los actores existen en el store y JAMÁS en la vista"


def test_epocas_solo_conteos():
    db = FakeDB(
        nodes=[SimpleNamespace(command_slug="ofrezco", mass=1, created_at=datetime(2026, 6, 5)),
               SimpleNamespace(command_slug="busco", mass=1, created_at=datetime(2026, 7, 2))],
        formas=[forma_limpia()])
    vista = espejo.vista_epocas(db)
    assert vista["epocas"] == [
        {"epoca": "2026-06", "intenciones": 1, "formas": 0},
        {"epoca": "2026-07", "intenciones": 1, "formas": 1}]


def test_salud_es_alarma_no_kpi():
    contadores = {"prevision:global:predicciones": 10, "prevision:global:aciertos": 7}
    vista = espejo.vista_salud(lambda k: contadores.get(k, 0))
    assert vista["prevision"]["tasa_acierto"] == 0.7
    assert "previsible" in vista["prevision"]["lectura"]


def test_cero_escrituras_por_construccion():
    fuente = open(os.path.join(REPO, "apps/espejo/espejo.py")).read()
    for prohibido in ("db.add", ".commit(", "db.delete", ".flush("):
        assert prohibido not in fuente, f"el espejo no escribe jamás: encontré {prohibido}"


def test_ninguna_vista_consulta_por_persona():
    for nombre, fn in inspect.getmembers(espejo, inspect.isfunction):
        if not nombre.startswith("vista_"):
            continue
        parametros = list(inspect.signature(fn).parameters)
        assert len(parametros) == 1, \
            f"{nombre} no acepta más que la fuente: no existe 'mostrame a X'"


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
