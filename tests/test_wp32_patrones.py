"""
WP-32 · Los patrones de coordinación (01_red §7.2; CU-R12 y adversarios).

El surco de confirmación es agregado anónimo (pares de comandos, jamás llaves
ni textos); el patrón es una forma del acervo con cuerpo declarativo, sin
castigo (INV-12) ni automatismo (INV-01); el puente lo ofrece por resonancia
y calla sin ella; sin uso, decae como toda forma.

Corre sin servicios:
    .venv/bin/python tests/test_wp32_patrones.py
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.acervo import acervo
from apps.worker import emergencia
from packages.domain.models import Forma, Node, PropuestaForma, Synapse
from packages.puentes import kit

LLAVE = "0x" + "ab" * 20


# --- Fakes para la detección (Synapse/Node no son portables a sqlite) ------

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


def db_confirmaciones(pares, extras_proposed=0):
    """Arma sinapsis activas para una lista de (cmd_a, cmd_b, veces)."""
    nodos, sinapsis, contador = [], [], 0
    for cmd_a, cmd_b, veces in pares:
        for _ in range(veces):
            na, nb = f"n{contador}", f"n{contador + 1}"
            contador += 2
            nodos.append(SimpleNamespace(id=na, command_slug=cmd_a))
            nodos.append(SimpleNamespace(id=nb, command_slug=cmd_b))
            sinapsis.append(SimpleNamespace(status="active",
                                            origin_node_id=na, target_node_id=nb))
    for _ in range(extras_proposed):
        na, nb = f"n{contador}", f"n{contador + 1}"
        contador += 2
        nodos.append(SimpleNamespace(id=na, command_slug="presto"))
        nodos.append(SimpleNamespace(id=nb, command_slug="busco"))
        sinapsis.append(SimpleNamespace(status="proposed",
                                        origin_node_id=na, target_node_id=nb))
    return FakeDB({Node: nodos, Synapse: sinapsis})


def db_acervo():
    engine = create_engine("sqlite://")
    for tabla in (Forma.__table__, PropuestaForma.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


CUERPO_SANO = (
    "Patrón de préstamo con devolución declarada. Pasos: quien presta emite "
    "su ofrecimiento; quien recibe emite su pedido; al coordinar, quien "
    "presta declara la expectativa de una devolución en un plazo dicho con "
    "sus palabras; el recordatorio lo lleva el cliente de cada quien; la "
    "devolución se emite como una intención más. La expectativa incumplida "
    "decae en silencio, como todo silencio.")


def publicar_patron(db, nombre="préstamo con devolución declarada",
                    cuerpo=CUERPO_SANO):
    propuesta = acervo.proponer_rubrica(db, {
        "tipo": "patron_coordinacion", "nombre": nombre,
        "descripcion": "flujo de préstamo entre vecinos, paso a paso",
        "cuerpo": cuerpo, "marco": "general"}, LLAVE)
    acervo.firmar_consentimiento(db, propuesta.id, LLAVE)
    return acervo.publicar_forma(db, propuesta.id)


def embedder_fake():
    """Embedder determinista por bolsa de palabras: suficiente para probar el
    contrato (resonancia alta con vocabulario compartido, baja sin él)."""
    vocab = {}

    async def embed(texto):
        vector = [0.0] * 32
        for palabra in (texto or "").lower().replace(":", " ").split():
            idx = vocab.setdefault(palabra, len(vocab) % 32)
            vector[idx] += 1.0
        return vector

    return embed


# --- Tests -----------------------------------------------------------------

def test_surco_de_confirmacion_agregado_y_anonimo():
    db = db_confirmaciones([("presto", "busco", 12), ("ofrezco", "permuto", 3)],
                           extras_proposed=5)
    surcos = emergencia.detectar_surcos_confirmacion(db, umbral=10)
    assert surcos == [{"par": ["busco", "presto"], "confirmaciones": 12}], \
        "solo el par sobre umbral, con solo proposed no cuenta"
    crudo = json.dumps(surcos)
    assert "0x" not in crudo and "n0" not in crudo, \
        "el surco es de la lengua: ni llaves ni ids de intención salen (CU-R12)"


def test_par_bajo_umbral_no_es_surco():
    db = db_confirmaciones([("presto", "busco", 9)])
    assert emergencia.detectar_surcos_confirmacion(db, umbral=10) == []


def test_patron_pasa_el_ciclo_del_acervo():
    db = db_acervo()
    forma = publicar_patron(db)
    assert forma.tipo == "patron_coordinacion" and forma.estado == "publicada"
    assert forma.cuerpo and "expectativa" in forma.cuerpo
    # la lista blanca de piezas NO se tocó (INV-14): el patrón vive en el acervo
    assert "patron" not in " ".join(emergencia.LISTA_BLANCA)


def test_patron_sin_cuerpo_rebota():
    db = db_acervo()
    try:
        acervo.proponer_rubrica(db, {
            "tipo": "patron_coordinacion", "nombre": "vacío",
            "descripcion": "sin pasos", "marco": "general"}, LLAVE)
        assert False, "un patrón sin cuerpo declarativo no debería entrar"
    except acervo.AcervoError as exc:
        assert "cuerpo" in str(exc)


def test_patron_con_castigo_rebota():
    db = db_acervo()
    for veneno in (
        CUERPO_SANO + " Si no devuelve a tiempo, se reduce la masa del prestatario.",
        CUERPO_SANO + " El moroso entra a una lista negra del barrio.",
        CUERPO_SANO + " Tres incumplimientos y se penaliza su reputación.",
    ):
        try:
            acervo.proponer_rubrica(db, {
                "tipo": "patron_coordinacion", "nombre": "punitivo",
                "descripcion": "préstamo con sanción", "cuerpo": veneno,
                "marco": "general"}, LLAVE)
            assert False, f"el castigo debería rebotar (INV-12): {veneno[-60:]}"
        except acervo.AcervoError as exc:
            assert "castigo" in str(exc) or "automatismo" in str(exc)


def test_patron_con_automatismo_rebota():
    db = db_acervo()
    veneno = (CUERPO_SANO + " Llegado el plazo, el recordatorio se emite solo, "
              "sin confirmación de la persona.")
    try:
        acervo.proponer_rubrica(db, {
            "tipo": "patron_coordinacion", "nombre": "automático",
            "descripcion": "préstamo que emite solo", "cuerpo": veneno,
            "marco": "general"}, LLAVE)
        assert False, "el automatismo debería rebotar (INV-01)"
    except acervo.AcervoError as exc:
        assert "automatismo" in str(exc) or "castigo" in str(exc)


def test_lente_puede_analizar_lo_que_el_patron_no_puede_ejecutar():
    # la ideología es un parámetro: una lente ANALIZA dinámicas punitivas;
    # el guard de castigo es solo para patrones (que las ejecutarían)
    db = db_acervo()
    propuesta = acervo.proponer_rubrica(db, {
        "tipo": "lente", "nombre": "lente del castigo",
        "descripcion": "mirar dónde una comunidad penaliza",
        "cuerpo": "Mirar dónde aparece la multa, el escrache o la lista negra "
                  "como respuesta a lo incumplido, y qué produce en el lazo.",
        "marco": "general"}, LLAVE)
    assert propuesta.estado == "juntando"


def test_puente_ofrece_patron_por_resonancia_y_calla_sin_ella():
    db = db_acervo()
    forma = publicar_patron(db)
    patrones = acervo.listar_formas(db)
    embed = embedder_fake()

    async def correr():
        con = await kit.leer_patron(
            "préstamo de un taladro con devolución entre vecinos",
            embed, patrones, umbral=0.3)
        sin = await kit.leer_patron(
            "xilófono cromático zumbando", embed, patrones, umbral=0.3)
        return con, sin

    con, sin = asyncio.run(correr())
    assert con and con["forma_id"] == forma.id, "la frase afín ofrece el patrón"
    assert sin is None, "sin resonancia el puente calla: no fuerza patrones"


def test_patron_retirado_no_se_ofrece():
    db = db_acervo()
    forma = publicar_patron(db)
    acervo.revocar_forma(db, forma.id, LLAVE)
    patrones = acervo.listar_formas(db, incluir_retiradas=True)
    embed = embedder_fake()
    resultado = asyncio.run(
        kit.leer_patron("préstamo con devolución declarada entre vecinos",
                        embed, patrones, umbral=0.1))
    assert resultado is None, "una forma retirada no se ofrece jamás"


def test_patron_decae_sin_uso_como_toda_forma():
    from datetime import datetime, timedelta, timezone
    from apps.worker import olvido
    db = db_acervo()
    forma = publicar_patron(db)
    viejo = datetime.now(timezone.utc) - timedelta(days=120)
    forma.last_touched = viejo
    forma.created_at = viejo
    db.flush()
    asi_quedo = olvido.decaer_arista(forma)
    assert asi_quedo and float(forma.mass) == 0.0, \
        "sin retoma humana el patrón se olvida (INV-03)"


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
