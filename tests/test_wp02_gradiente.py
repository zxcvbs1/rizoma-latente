"""
WP-02 · Handshake por gradiente (INV-01, INV-02).

Aceptación de 04_backlog (lado servidor): estados proposed/addressed/active/
expired; el paso a active exige el acto de AMBAS partes; propuesta sin
dirigirse expira en silencio; no existe "aceptar" en ninguna notificación.

Corre sin servicios:
    .venv/bin/python tests/test_wp02_gradiente.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account

from apps.api.security import SecurityService
from apps.m2_handshake import gradiente


class FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, key):
        return 1 if key in self.store else 0

    def setex(self, key, ttl, value):
        self.store[key] = str(value)


ANA = "0x" + "a1" * 20
BRUNO = "0x" + "b2" * 20


def test_flujo_feliz():
    estado, addressed_by = gradiente.transicionar(gradiente.PROPOSED, None, ANA)
    assert (estado, addressed_by) == (gradiente.ADDRESSED, ANA)
    estado, addressed_by = gradiente.transicionar(estado, addressed_by, BRUNO)
    assert estado == gradiente.ACTIVE, "la palabra de la otra parte activa el vínculo"


def test_mismo_actor_no_activa_solo():
    estado, addressed_by = gradiente.transicionar(gradiente.PROPOSED, None, ANA)
    try:
        gradiente.transicionar(estado, addressed_by, ANA)
        assert False, "una sola parte no puede activar el vínculo (INV-01)"
    except gradiente.TransicionInvalida as exc:
        assert exc.codigo == 409


def test_active_y_expired_no_retransicionan():
    for estado, codigo in [(gradiente.ACTIVE, 409), (gradiente.EXPIRED, 410)]:
        try:
            gradiente.transicionar(estado, ANA, BRUNO)
            assert False, f"{estado} no debe transicionar"
        except gradiente.TransicionInvalida as exc:
            assert exc.codigo == codigo


def test_legacy_matched_es_proposed():
    estado, addressed_by = gradiente.transicionar(gradiente.LEGACY_PROPOSED, None, ANA)
    assert estado == gradiente.ADDRESSED


def test_vencimiento_silencioso():
    hace_diez_dias = datetime.now(timezone.utc) - timedelta(days=10)
    ayer = datetime.now(timezone.utc) - timedelta(days=1)
    assert gradiente.esta_vencida(hace_diez_dias, gradiente.PROPOSED)
    assert gradiente.esta_vencida(hace_diez_dias, gradiente.ADDRESSED)
    assert gradiente.esta_vencida(hace_diez_dias, gradiente.LEGACY_PROPOSED)
    assert not gradiente.esta_vencida(ayer, gradiente.PROPOSED)
    assert not gradiente.esta_vencida(hace_diez_dias, gradiente.ACTIVE), \
        "un vínculo activo no expira por esta vía"


def test_es_parte():
    syn = SimpleNamespace(origin_actor_id=ANA, target_actor_id=BRUNO.upper())
    assert gradiente.es_parte(syn, ANA)
    assert gradiente.es_parte(syn, BRUNO), "insensible a mayúsculas"
    assert not gradiente.es_parte(syn, "0x" + "c3" * 20), "un tercero no es parte"


def test_firma_del_acto():
    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    actor = Account.from_key(pk).address
    msg = gradiente.canonical_link(actor, "2026-07-07T00:00:00Z", "n1", "ofrezco-abc", "busco-def")
    from packages.domain.identity import sign_text
    firma = sign_text(pk, msg)
    assert sec.verify_eip191_signature(actor, firma, msg)
    otro_pk = Account.create().key.hex()
    firma_ajena = sign_text(otro_pk, msg)
    assert not sec.verify_eip191_signature(actor, firma_ajena, msg), \
        "nadie se dirige en nombre de otro"


def test_sin_boton_y_con_texto_original():
    texto = "!ofrezco bicicleta rodado 26"
    enlace = gradiente.enlace_sinapsis("abc-123", "http://miniapp.local")
    propuesta = gradiente.mensaje_propuesta(texto, enlace)
    mensajes = [propuesta, gradiente.mensaje_addressed(enlace), gradiente.mensaje_active(enlace)]
    for mensaje in mensajes:
        assert "aceptar" not in mensaje.lower(), "no existe el botón de aceptar (INV-02)"
    assert texto in propuesta, "la propuesta lleva el texto ORIGINAL, no un resumen"
    assert enlace in propuesta
    assert "campo vacío" in propuesta, "el enlace abre un campo vacío, y se dice"
    assert "expira" in propuesta, "el silencio que decae se declara, sin costo social"



def test_recover_public_key():
    from hexbytes import HexBytes
    from eth_keys import keys
    from packages.domain.identity import build_emit_event, canonical_emit
    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    pk = pk if pk.startswith("0x") else "0x" + pk
    event = build_emit_event(pk, "!ofrezco mi clave publica")
    msg = canonical_emit(event["actor_id"], event["timestamp"], event["nonce"],
                         event["payload"]["text"])
    recovered = sec.recover_public_key(event["signature"], msg)
    esperada = "0x04" + keys.PrivateKey(HexBytes(pk)).public_key.to_hex()[2:]
    assert recovered == esperada, "la clave recuperada de la firma es la del emisor"


def test_recover_public_key():
    from hexbytes import HexBytes
    from eth_keys import keys
    from packages.domain.identity import build_emit_event, canonical_emit
    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    pk = pk if pk.startswith("0x") else "0x" + pk
    event = build_emit_event(pk, "!ofrezco mi clave publica")
    msg = canonical_emit(event["actor_id"], event["timestamp"], event["nonce"],
                         event["payload"]["text"])
    recovered = sec.recover_public_key(event["signature"], msg)
    esperada = "0x04" + keys.PrivateKey(HexBytes(pk)).public_key.to_hex()[2:]
    assert recovered == esperada, "la clave recuperada de la firma es la del emisor"

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
    total = len(TESTS)
    print(f"\n{total - failures}/{total} tests OK")
    sys.exit(1 if failures else 0)
