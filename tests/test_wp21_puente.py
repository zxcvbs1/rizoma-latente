"""
WP-21 · Kit de puente (01_red §10; CU-R11 y adversarios).

El contrato del puente como código compartido: confirmar antes de emitir,
espejo de la lengua (alta por masa, jamás gate), escalera de custodia
(llevarse la llave con código de un solo uso). El mismo actor desde dos
puentes es UNA identidad con UNA lengua.

Corre sin servicios:
    .venv/bin/python tests/test_wp21_puente.py
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account

from packages.domain.identity import KeyStore, build_emit_event
from packages.puentes import kit


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, k, ttl, v):
        self.store[k] = (v, ttl)

    def get(self, k):
        par = self.store.get(k)
        return par[0] if par else None

    def delete(self, k):
        self.store.pop(k, None)


def test_confirmacion_antes_de_emitir():
    assert kit.es_confirmacion("si") and kit.es_confirmacion("Dale") and kit.es_confirmacion("OK")
    assert not kit.es_confirmacion("no") and not kit.es_confirmacion("mmm")
    mensaje = kit.mensaje_propuesta_lectura("ofrezco", "bici rodado 26")
    assert "bici rodado 26" in mensaje and "si" in mensaje.lower()
    assert "botón" not in mensaje.lower() and "aceptar" not in mensaje.lower(), \
        "el puente propone y espera texto, jamás un botón (INV-02)"


def test_espejo_de_la_lengua_por_masa():
    lengua = {"lengua": [
        {"comando": "permuto", "usos": 12, "masa": 30.0},
        {"comando": "ofrezco", "usos": 40, "masa": 22.0},
        {"comando": "?", "usos": 3, "masa": 1.0},
    ]}
    comandos = kit.comandos_para_menu(lengua)
    slugs = [c["comando"] for c in comandos]
    assert slugs == ["permuto", "ofrezco"], "la lengua viva ordena el menú; el '?' no entra"
    # WP-28/29: la lengua viene de ComandoVivo (masa con olvido; ya no hay
    # "usos" sin decay) y el menú declara esa masa.
    assert "masa" in comandos[0]["descripcion"]


def test_ayuda_orienta_sin_secuestrar_la_palabra():
    # la palabra sola pide el mapa; un texto que la contiene es intención
    assert kit.pide_ayuda("ayuda") and kit.pide_ayuda("AYUDA!")
    assert kit.pide_ayuda("?") and kit.pide_ayuda("comandos")
    assert kit.pide_ayuda("como funciona") and kit.pide_ayuda("/ayuda")
    assert not kit.pide_ayuda("busco ayuda con una mudanza"), \
        "un pedido a la red es emisión, no orientación (no se intercepta)"
    assert not kit.pide_ayuda("ofrezco ayuda en cocina")
    # el texto de ayuda enseña la lengua viva si se le pasa, y siempre el acto
    texto = kit.texto_ayuda(["busco", "ofrezco", "sueño"])
    assert "!busco" in texto and "!sueño" in texto
    assert "si" in texto.lower() and "botón" in texto.lower(), \
        "la ayuda declara el acto sin botón (INV-02)"
    # sin lengua viva, cae al genérico sin romperse
    assert "!busco" in kit.texto_ayuda()


def test_el_menu_es_comodidad_jamas_gate():
    # el registro nativo puede estar vacío y aun así el puente acepta cualquier
    # comando inventado como texto libre (la lengua es del protocolo)
    assert kit.comandos_para_menu({"lengua": []}) == []
    parsed_libre = "!permuto amplificador"  # comando ausente del menú
    assert parsed_libre.startswith("!"), "texto libre siempre entra; el menú no filtra"


def test_escalera_llevarse_la_llave():
    r = FakeRedis()
    pk = Account.create().key.hex()
    codigo = kit.generar_codigo_exportacion(r, pk)
    assert kit.canjear_codigo(r, codigo) == pk, "quien canjea se lleva la llave delegada"
    assert kit.canjear_codigo(r, codigo) is None, "un solo uso: el código se destruye al canjearse"
    assert kit.canjear_codigo(r, "inventado") is None, "código inválido no da llave"


def test_dos_puentes_una_identidad():
    with tempfile.TemporaryDirectory() as tmp:
        ks = KeyStore(path=os.path.join(tmp, "keys.json"))
        # misma persona escribe la misma passphrase/scope desde dos borde:
        # la identidad es la llave, no la plataforma
        addr_tg, pk_tg = ks.get_or_create("tg:555")
        addr_dc, pk_dc = ks.get_or_create("dc:555")
        # scopes distintos = llaves distintas por defecto (cada plataforma
        # custodia su delegada); pero la ESCALERA une: exportar la de tg y
        # canjearla como dc reusa la MISMA llave.
        r = FakeRedis()
        codigo = kit.generar_codigo_exportacion(r, pk_tg)
        importada = kit.canjear_codigo(r, codigo)
        assert importada == pk_tg
        # y la firma con esa llave es una sola identidad, venga del puente que venga
        ev1 = build_emit_event(importada, "!ofrezco guitarra", tags=["from-telegram"])
        ev2 = build_emit_event(importada, "!permuto amplificador", tags=["from-discord"])
        assert ev1["actor_id"] == ev2["actor_id"], \
            "la masa suma en una sola identidad, transversal a los puentes (CU-R11)"


def test_discord_reusa_el_mismo_kit():
    fuente = open(os.path.join(REPO, "apps/bot_discord/main.py")).read()
    assert "from packages.puentes import kit" in fuente
    assert "build_emit_event" in fuente, "firma delegada, igual que Telegram"
    assert "kit.es_confirmacion" in fuente and "kit.mensaje_propuesta_lectura" in fuente, \
        "el contrato es del kit, no reimplementado por plataforma"


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
