"""
WP-03 · Cliente MCP de referencia (la mitad que semiotiza).

La rúbrica dice lo que la tesis exige; la firma del acto verifica contra el
contrato; la guía de turno traduce el estado del nodo a instrucciones de
juego. Corre sin servicios:
    .venv/bin/python tests/test_wp03_cliente.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account

from apps.api.controles import canonical_actor
from apps.api.security import SecurityService
from apps.motor_aventura import cliente
from apps.motor_simulacion import cliente as sim_cliente


class FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, k):
        return 1 if k in self.store else 0

    def setex(self, k, ttl, v):
        self.store[k] = str(v)


def test_firma_del_acto_verifica():
    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    actor = Account.from_key(pk).address
    body = cliente.firmar_acto(pk, actor, "aventura.iniciar")
    msg = canonical_actor(body["actor_id"], body["timestamp"], body["nonce"], "aventura.iniciar")
    assert sec.verify_eip191_signature(body["actor_id"], body["signature"], msg)
    msg_otro = canonical_actor(body["actor_id"], body["timestamp"], body["nonce"], "aventura.cerrar")
    assert not sec.verify_eip191_signature(body["actor_id"], body["signature"], msg_otro), \
        "la firma es del acto exacto, no un pase libre"


def test_rubrica_dice_lo_que_la_tesis_exige():
    rubrica = cliente.rubrica_completa()
    for obligatorio in ["CITA TEXTUAL", "taxonomía", "ANTES", "EN SILENCIO",
                       "sin\n   ganador", "apreciación", "final propio", "respuesta libre",
                       "descarrilamiento", "preguntas de mundo", "divergir",
                       "VOCABULARIO NUEVO NO ES DESVÍO"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"
    assert "—" not in rubrica


def test_rubrica_prohibe_recetar_la_devolucion():
    """La devolución lee, no receta (regla 10, corrección jul 2026: el GM
    que se coronó consejero)."""
    rubrica = cliente.rubrica_completa()
    for obligatorio in ["no receta", "transgresión por encargo", "espejo de juego"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"


def test_rubrica_exige_que_la_devolucion_declare_su_base():
    """La devolución declara su base (regla 11, corrección jul 2026: el test
    de especificidad de Gabriel, "siempre lo biológico va a primar")."""
    rubrica = cliente.rubrica_completa()
    for obligatorio in ["declara su base", "conjetura", "valdría para cualquier persona"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"


def test_gramatica_exige_leer_las_semillas_del_contexto():
    """Contra la saturación (corrección jul 2026, playtest de la
    saturación): la gramática manda a generar la escena donde el mapa está
    roto, no a recalentar el mismo racimo."""
    for obligatorio in ["semillas", "re-instancies", "no se agota en el turno cero"]:
        assert obligatorio.lower() in cliente.GRAMATICA_ESCENAS.lower(), \
            f"falta en la gramática de escenas: {obligatorio}"


def test_guia_canvas_blanco():
    guia = cliente.guia_de_turno({"terminos": [], "aristas": [], "prevision_despierta": False,
                                  "salir_del_mapa": False, "marcador": {}})
    assert "elicitación de mundo" in guia
    assert "calla" in guia


def test_guia_prevision_despierta():
    guia = cliente.guia_de_turno({"terminos": ["t"], "aristas": [1] * 5,
                                  "prevision_despierta": True, "salir_del_mapa": False})
    assert "ANTES" in guia
    assert "marcador" not in guia.lower(), \
        "el puntaje trabaja en silencio: la guía no lo narra (corrección jul 2026)"


def test_guia_salir_del_mapa():
    guia = cliente.guia_de_turno({"terminos": ["t"], "aristas": [1] * 8,
                                  "prevision_despierta": True, "salir_del_mapa": True,
                                  "marcador": {}})
    assert "LEJOS del mapa" in guia


def test_guia_menu_agotado():
    """El menú es un préstamo: con menu_agotado=true, la guía ordena escena
    sin opciones numeradas (corrección jul 2026, segunda del playtest a puro
    número)."""
    guia = cliente.guia_de_turno({"terminos": ["t"], "aristas": [1] * 5,
                                  "prevision_despierta": True, "salir_del_mapa": False,
                                  "menu_agotado": True})
    assert "SIN opciones numeradas" in guia
    assert "pregunta" in guia.lower()


def test_gramatica_exige_la_deriva():
    """La deriva (el portal de la obra, corrección jul 2026, playtest del
    monotema): sin territorio nuevo el mapa solo recombina su racimo."""
    for obligatorio in ["La deriva", "encuentros", "mundo_hambriento"]:
        assert obligatorio in cliente.GRAMATICA_ESCENAS, \
            f"falta en la gramática de escenas: {obligatorio}"


def test_guia_mundo_hambriento():
    guia = cliente.guia_de_turno({"mundo_hambriento": True})
    assert "DERIVA" in guia


def test_rubrica_mesa_sin_tablero():
    """Regla 12 (corrección jul 2026, del playtest "le ganaste las tres
    apuestas al Dojo"): ni ganar/perder narrado ni negado, revelación en
    primera persona, la maquinaria no es un personaje."""
    rubrica = cliente.rubrica_completa()
    for obligatorio in ["ni siquiera negándolo", "primera persona", "no es un personaje"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"


def test_rubrica_nombra_nodos_de_fuga_como_hecho_y_conjetura_aparte():
    """Extensión de la regla 11 (corrección jul 2026, del playtest "la ia
    como atajo"): nodos_fuga es hecho del mapa; la evasión con objeto
    distinto es conjetura tuya, firmada."""
    rubrica = cliente.rubrica_completa()
    for obligatorio in ["nodos_fuga", "conjetura tuya"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"


def test_verificar_sello_local():
    import hashlib
    pre = "e3|1|siempre el lazo|388a8609f5596b3c"
    ok = cliente.verificar_sello(pre, hashlib.sha256(pre.encode()).hexdigest())
    assert ok["coincide"] and "existió antes" in ok["veredicto"]
    mal = cliente.verificar_sello(pre, "a" * 64)
    assert not mal["coincide"] and "NO coincide" in mal["veredicto"], \
        "una apuesta reescrita no verifica"


def test_rubrica_corrida_ancla_escala_y_exige_tensiones():
    """Corrección jul 2026 (playtest cruzado Gemini/Antigravity): la escala la
    declara la comunidad, afirmativa y sin prohibir géneros (se retiró la
    regla negativa de "inflación de género"); las tensiones son EL PRODUCTO,
    proporcionales al arco, y el ciclo sigue hasta el injerto."""
    rubrica = sim_cliente.RUBRICA_CORRIDA
    for obligatorio in ["corrida_tensiones", "proporcional", "corrida_injerto"]:
        assert obligatorio.lower() in rubrica.lower(), f"falta en la rúbrica: {obligatorio}"
    assert "—" not in rubrica


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
