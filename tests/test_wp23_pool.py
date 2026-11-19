"""
WP-23 · Pool de cómputo del común (09_procomun §2.2; INV-18/17/11/10/03).

Un cliente con fierro toma tareas sobre material anónimo y devuelve propuestas
validadas POR RESULTADO. El peso de contribución prioriza pero decae, no se
transfiere y no es ranking. Un aporte inválido no penaliza (no hay slashing).

Corre sin servicios:
    .venv/bin/python tests/test_wp23_pool.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.worker import pool
from packages.domain import frontera
from packages.domain.models import PesoContribucion, TareaComun

APORTANTE = "0x" + "0a" * 20
OTRO = "0x" + "0b" * 20
LLAVE = "0x" + "cc" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (TareaComun.__table__, PesoContribucion.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


FORMA_OK = {"tipo": "tension_tipo", "nombre": "x", "descripcion": "y", "marco": "cuidado"}


def test_crear_tarea_material_anonimo():
    db = db_limpia()
    t = pool.crear_tarea(db, "proponer_forma", "huerta", {"surco": "arreglo de bicis", "n": "decenas"})
    assert t.estado == "abierta"
    try:
        pool.crear_tarea(db, "proponer_forma", "huerta", {"pidio": LLAVE})
        assert False, "material con identidad lo bloquea la frontera"
    except frontera.FronteraViolada:
        pass
    try:
        pool.crear_tarea(db, "backdoor", "huerta", {})
        assert False, "tipo fuera del catálogo"
    except pool.PoolError:
        pass


def test_tomar_no_se_roba():
    db = db_limpia()
    t = pool.crear_tarea(db, "densificar", "lengua", {"texto": "trueque"})
    pool.tomar_tarea(db, t.id, APORTANTE)
    try:
        pool.tomar_tarea(db, t.id, OTRO)
        assert False, "una tarea tomada y no caduca no se roba"
    except pool.PoolError:
        pass
    # caduca la toma: se libera
    t.tomada_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db.flush()
    r = pool.tomar_tarea(db, t.id, OTRO)
    assert r["tarea_id"] == t.id, "toma caducada se libera al siguiente"


def test_resolver_acredita_peso():
    db = db_limpia()
    t = pool.crear_tarea(db, "proponer_forma", "huerta", {"surco": "bicis"})
    pool.tomar_tarea(db, t.id, APORTANTE)
    r = pool.resolver_tarea(db, t.id, APORTANTE, FORMA_OK)
    assert r["estado"] == "resuelta" and r["peso_contribucion_dominio"] == 1.0
    assert pool.peso_de(db, APORTANTE, "huerta") == 1.0
    assert pool.peso_de(db, OTRO) == 0.0, "el peso es del que aportó, de nadie más"


def test_aporte_invalido_no_penaliza():
    db = db_limpia()
    t = pool.crear_tarea(db, "proponer_forma", "huerta", {"surco": "bicis"})
    pool.tomar_tarea(db, t.id, APORTANTE)
    try:
        pool.resolver_tarea(db, t.id, APORTANTE, {"tipo": "tension_tipo"})  # sin nombre/desc
        assert False, "propuesta incompleta se rechaza"
    except pool.PoolError:
        pass
    assert t.estado == "abierta", "sin castigo: la tarea vuelve a estar abierta"
    assert pool.peso_de(db, APORTANTE) == 0.0, "un aporte inválido no acredita"


def test_frontera_en_la_propuesta():
    db = db_limpia()
    t = pool.crear_tarea(db, "cristalizar", "salon", {"falta": "llave"})
    pool.tomar_tarea(db, t.id, APORTANTE)
    veneno = {"nombre": "n", "tension_que_ataca": "t", "regla_logica": f"la maneja {LLAVE}",
              "flujo": "f", "senales_alivio": "s"}
    try:
        pool.resolver_tarea(db, t.id, APORTANTE, veneno)
        assert False, "una propuesta con identidad no toca el estado"
    except pool.PoolError:
        pass
    assert t.estado == "abierta"


def test_frontera_rechaza_alias_en_la_propuesta():
    """Corrección 2026-07-10 (playtest del procomún): antes la frontera solo
    miraba llaves 0x y un alias como mcp:antigravity pasaba."""
    db = db_limpia()
    t = pool.crear_tarea(db, "cristalizar", "salon", {"falta": "llave"})
    pool.tomar_tarea(db, t.id, APORTANTE)
    veneno = {"nombre": "n", "tension_que_ataca": "t", "regla_logica": "f",
              "flujo": "f", "senales_alivio": "s", "identidad": "mcp:antigravity"}
    try:
        pool.resolver_tarea(db, t.id, APORTANTE, veneno)
        assert False, "una propuesta con alias tampoco toca el estado"
    except pool.PoolError:
        pass
    assert t.estado == "abierta", "sin castigo: la tarea vuelve a estar abierta"


def test_esquema_por_tipo():
    db = db_limpia()
    tc = pool.crear_tarea(db, "cristalizar", "salon", {})
    pool.tomar_tarea(db, tc.id, APORTANTE)
    try:
        pool.resolver_tarea(db, tc.id, APORTANTE, {"nombre": "n"})  # faltan campos
        assert False
    except pool.PoolError:
        pass
    td = pool.crear_tarea(db, "densificar", "lengua", {"texto": "x"})
    pool.tomar_tarea(db, td.id, APORTANTE)
    try:
        pool.resolver_tarea(db, td.id, APORTANTE, {"vector": "no soy lista"})
        assert False, "densificar exige vector de números"
    except pool.PoolError:
        pass
    pool.resolver_tarea(db, td.id, APORTANTE, {"vector": [0.1, 0.2, 0.3]})
    assert td.estado == "resuelta"


def test_no_es_transferible_ni_ranking():
    import inspect
    fuente = open(os.path.join(REPO, "apps/worker/pool.py")).read()
    assert "transferir" not in fuente.lower(), "no existe transferir peso: no es plata"
    assert "order_by" not in fuente, "el peso no se ordena: no hay ranking de actores (INV-10)"
    # peso_de exige una llave concreta: no hay 'traer todos ordenados por peso'
    assert "llave" in inspect.signature(pool.peso_de).parameters, \
        "el peso se consulta por dueño, no como tabla de posiciones"
    db = db_limpia()
    pool.acreditar_peso(db, APORTANTE, "huerta", 5.0)
    pool.acreditar_peso(db, OTRO, "huerta", 1.0)
    assert pool.peso_de(db, APORTANTE, "huerta") == 5.0
    assert pool.peso_de(db, OTRO, "huerta") == 1.0, "cada quien ve el suyo, no el del otro"


def test_decay():
    db = db_limpia()
    t = pool.crear_tarea(db, "densificar", "lengua", {"texto": "x"}, ttl_dias=7)
    t.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    assert pool.vencer_tarea(t) and t.estado == "vencida"
    p = pool.acreditar_peso(db, APORTANTE, "lengua", 3.0)
    p.last_touched = datetime.now(timezone.utc) - timedelta(days=40)
    assert pool.decaer_peso(p) and p.peso == 0.0, "el peso inactivo cae a nulo (INV-03)"


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
