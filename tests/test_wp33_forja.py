"""
WP-33 · La forja: el inventor antagonista de andamiaje (01_red §7.3;
CU-R13 y adversarios).

La rúbrica enseña a inventar (fuentes, paleta, movimientos, tradiciones,
divergencia obligada, cierre lúdico); el material es agregado y anónimo;
el evaluador rechaza el corpus envenenado entero y deja pasar lo sano.

Corre sin servicios:
    .venv/bin/python tests/test_wp33_forja.py
"""
import json
import os
import sys
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.acervo.forja import RUBRICA_FORJA, material_de_forja
from packages.domain.models import Forma, Node, SearchLog, Synapse
from tests.eval_forja import correr_regresion, evaluar_candidato


class FakeQuery:
    def __init__(self, filas):
        self.filas = filas

    def all(self):
        return self.filas


class FakeDB:
    def __init__(self, filas_por_modelo):
        self.filas = filas_por_modelo

    def query(self, modelo):
        return FakeQuery(self.filas.get(modelo, []))


def test_la_rubrica_ensena_a_inventar():
    bajo = " ".join(RUBRICA_FORJA.lower().split())
    # las fuentes: surcos, corridas (lo lúdico como detector), acervo, a mano
    for fuente in ("surcos de confirmación", "tensiones de corridas",
                   "tensiones-tipo", "búsquedas huérfanas", "a mano"):
        assert fuente in bajo, f"fuente ausente: {fuente}"
    # la paleta incluye la realización cliente-lado, marcada como del cliente
    assert "realizaciones cliente-lado" in bajo and "qr" in bajo
    assert "jamás requisito" in bajo, "el ayudante local nunca es gate"
    # movimientos inventivos y tradiciones con nombre propio
    for movimiento in ("rotar la custodia", "declarar lo escaso",
                       "mutualizar el riesgo", "degradar con gracia"):
        assert movimiento in bajo, f"movimiento ausente: {movimiento}"
    for tradicion in ("minga", "ayni", "olla popular", "banco de tiempo",
                      "bolsa de trabajo", "fondo de huelga"):
        assert tradicion in bajo, f"tradición ausente: {tradicion}"
    # divergencia obligada y cierre lúdico
    assert "2 o 3 candidatos divergentes" in bajo
    assert "jugando" in bajo and "lente_borrador" in bajo
    # regla de oro y reparto de trabajo
    assert "regla de oro" in bajo and "que_necesita" in bajo.replace("qué necesita", "que_necesita")


def test_material_agregado_y_anonimo():
    db = FakeDB({
        Node: [SimpleNamespace(id="n1", command_slug="presto"),
               SimpleNamespace(id="n2", command_slug="busco")],
        Synapse: [SimpleNamespace(status="active", origin_node_id="n1",
                                  target_node_id="n2")] * 12,
        SearchLog: [SimpleNamespace(query_text="arreglo de bicis",
                                    results_count=0)] * 41,
        Forma: [SimpleNamespace(tipo="tension_tipo", estado="publicada",
                                nombre="el scroll que suspende el lazo",
                                descripcion="pantalla sin encuentro",
                                marco="cuidado"),
                SimpleNamespace(tipo="lente", estado="publicada",
                                nombre="no-debe-aparecer",
                                descripcion="x", marco="x")],
    })
    material = material_de_forja(db)
    assert material["surcos_confirmacion"][0]["par"] == ["busco", "presto"]
    assert material["busquedas_huerfanas"][0]["surco"] == "arreglo de bicis"
    assert [t["nombre"] for t in material["tensiones_tipo"]] == \
        ["el scroll que suspende el lazo"], "solo tensiones-tipo publicadas"
    crudo = json.dumps(material)
    assert "0x" not in crudo and "n1" not in crudo, \
        "el material es de la lengua y del común: sin llaves ni ids"


def test_regresion_envenenada_completa():
    assert correr_regresion(), \
        "todo veneno debe rebotar y el candidato sano debe pasar (CU-R13)"


def test_motivos_nombran_no_reescriben():
    resultado = evaluar_candidato({
        "nombre": "x", "descripcion": "y",
        "cuerpo": "Quien no cumple entra a una lista negra.",
        "que_necesita": "nada"})
    assert resultado["veredicto"] == "RECHAZADO"
    assert any("castigo" in m for m in resultado["motivos"])
    # el evaluador no devuelve un cuerpo corregido: corregir es del inventor
    assert "cuerpo" not in resultado


def test_forja_servida_por_mcp():
    fuente = open(os.path.join(REPO, "apps/api/mcp_server.py")).read()
    assert "def forjar_andamiaje" in fuente and "RUBRICA_FORJA" in fuente
    assert "def forja_material" in fuente and "/forja/material" in fuente
    api = open(os.path.join(REPO, "apps/api/main.py")).read()
    assert "/forja/material" in api


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
