"""
WP-01 · Firma obligatoria (INV-12).

Aceptación de 04_backlog: emisión sin firma válida es rechazada con error
explícito; los tres caminos que bypasseaban (mcp-agent-*, wallet del servidor,
Unknown) quedan cerrados; los agentes MCP firman con llave propia.

Corre sin red, sin Postgres y sin Redis reales:
    .venv/bin/python tests/test_wp01_firma.py
"""
import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eth_account import Account

from apps.api.security import SecurityService
from apps.m1_ingestor.ingestor import NetworkIngestor
from packages.domain.identity import (
    KeyStore, build_emit_event, canonical_emit, new_nonce, now_iso, sign_text,
)

SERVER_WALLET = Account.create().address


def test_gateway_genera_identidad_propia_y_la_conserva():
    from apps.worker.broadcaster import NetworkBroadcaster

    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"GATEWAY_PRIVATE_KEY": "", "RIZOMA_KEYSTORE": os.path.join(tmp, "keys.json")}):
            primero = NetworkBroadcaster()
            segundo = NetworkBroadcaster()
        with patch.dict(os.environ, {"GATEWAY_PRIVATE_KEY": "", "RIZOMA_KEYSTORE": os.path.join(tmp, "otro.json")}):
            otro = NetworkBroadcaster()
        assert primero.gateway_id == segundo.gateway_id
        assert primero.gateway_id != otro.gateway_id
        assert primero.private_key != "0x" + "a" * 64


def test_gateway_respeta_la_clave_configurada():
    from apps.worker.broadcaster import NetworkBroadcaster

    account = Account.create()
    with patch.dict(os.environ, {"GATEWAY_PRIVATE_KEY": account.key.hex()}):
        gateway = NetworkBroadcaster()
    assert gateway.gateway_id == account.address


def test_cli_emite_un_evento_firmado():
    import runpy
    from unittest.mock import AsyncMock
    from packages.adapters.waku_adapter import WakuAdapter

    cli = runpy.run_path(os.path.join(REPO, "rizoma"))
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"RIZOMA_KEYSTORE": os.path.join(tmp, "keys.json")}):
            with patch.object(sys, "argv", ["rizoma", "!ofrezco semillas"]):
                with patch.object(WakuAdapter, "broadcast", new_callable=AsyncMock, return_value=True) as broadcast:
                    assert asyncio.run(cli["main"]()) == 0
        event = broadcast.call_args.args[0]
    security = SecurityService(redis_client=FakeRedis())
    message = canonical_emit(event["actor_id"], event["timestamp"], event["nonce"], event["payload"]["text"])
    assert event["payload"]["text"] == "!ofrezco semillas"
    assert security.verify_eip191_signature(event["actor_id"], event["signature"], message)


class FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, key):
        return 1 if key in self.store else 0

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    def get(self, key):
        value = self.store.get(key)
        return value.encode() if isinstance(value, str) else value

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def expire(self, key, ttl):
        return True


def fresh_ingestor():
    ing = NetworkIngestor()
    ing.security = SecurityService(redis_client=FakeRedis())
    ing.accepted = []

    async def record(actor_id, text, public_key=None):
        ing.accepted.append((actor_id, text, public_key))

    ing.ingest_with_profile = record
    return ing


def run(ing, event):
    asyncio.run(ing.process_event(event))


def test_bypass_mcp_agent_rechazado():
    ing = fresh_ingestor()
    run(ing, {"protocol": "rizoma.v2", "action": "emit", "actor_id": "mcp-agent-local",
              "payload": {"text": "!ofrezco humo"}, "timestamp": "now"})
    run(ing, {"protocol": "rizoma.v2", "action": "emit", "actor_id": "mcp-agent-gemini",
              "payload": {"text": "!ofrezco humo"}, "timestamp": now_iso(), "nonce": new_nonce()})
    assert ing.accepted == [], "mcp-agent-* ya no puede entrar sin firma"


def test_bypass_wallet_servidor_rechazado():
    ing = fresh_ingestor()
    run(ing, {"protocol": "rizoma.v2", "action": "emit", "actor_id": SERVER_WALLET,
              "payload": {"text": "!ofrezco privilegios"}, "timestamp": now_iso(),
              "nonce": new_nonce()})
    assert ing.accepted == [], "la wallet del servidor sin firma ya no entra"


def test_bypass_unknown_rechazado():
    ing = fresh_ingestor()
    for actor in ["Unknown", "Unknown-XMTP", "tg:12345"]:
        run(ing, {"protocol": "rizoma.v2", "action": "emit", "actor_id": actor,
                  "payload": {"text": "!busco entrar sin llave"}, "timestamp": now_iso(),
                  "nonce": new_nonce(), "signature": "0x" + "ab" * 65})
    assert ing.accepted == [], "actor_id que no es dirección EIP-55 se rechaza"


def test_emision_firmada_entra():
    ing = fresh_ingestor()
    pk = Account.create().key.hex()
    event = build_emit_event(pk, "!ofrezco bicicleta rodado 26", tags=["test"])
    run(ing, event)
    assert len(ing.accepted) == 1, "la emisión firmada válida debe ingresar"
    assert ing.accepted[0][1] == "!ofrezco bicicleta rodado 26"
    assert ing.accepted[0][0].startswith("0x")
    assert ing.accepted[0][2] and ing.accepted[0][2].startswith("0x04"), \
        "la clave pública se recupera de la firma (para cifrar la primera palabra)"


def test_texto_adulterado_rechazado():
    ing = fresh_ingestor()
    pk = Account.create().key.hex()
    event = build_emit_event(pk, "!ofrezco pan")
    event["payload"]["text"] = "!ofrezco pan envenenado"
    run(ing, event)
    assert ing.accepted == [], "firma sobre otro texto no verifica"


def test_replay_rechazado():
    ing = fresh_ingestor()
    pk = Account.create().key.hex()
    event = build_emit_event(pk, "!busco eco")
    run(ing, event)
    run(ing, event)
    assert len(ing.accepted) == 1, "el mismo nonce no entra dos veces"


def test_timestamp_viejo_rechazado():
    ing = fresh_ingestor()
    pk = Account.create().key.hex()
    actor = Account.from_key(pk).address
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    nonce = new_nonce()
    text = "!ofrezco mensajes del pasado"
    event = {"protocol": "rizoma.v2", "action": "emit", "actor_id": actor,
             "timestamp": stale, "nonce": nonce, "payload": {"text": text},
             "signature": sign_text(pk, canonical_emit(actor, stale, nonce, text))}
    run(ing, event)
    assert ing.accepted == [], "fuera de la ventana de 5 minutos se rechaza"


def test_rate_limit_actor_nuevo():
    ing = fresh_ingestor()
    pk = Account.create().key.hex()
    for i in range(6):
        run(ing, build_emit_event(pk, f"!ofrezco cosa {i}"))
    assert len(ing.accepted) == 5, "actor nuevo: 5 emisiones por día, la sexta se rechaza"


def test_helper_y_contrato():
    sec = SecurityService(redis_client=FakeRedis())
    pk = Account.create().key.hex()
    event = build_emit_event(pk, "!ofrezco verificación")
    msg = canonical_emit(event["actor_id"], event["timestamp"], event["nonce"],
                         event["payload"]["text"])
    assert sec.verify_eip191_signature(event["actor_id"], event["signature"], msg)
    assert sec.normalize_actor_id(event["actor_id"]) == event["actor_id"]
    assert sec.normalize_actor_id("mcp-agent-local") is None
    assert sec.normalize_actor_id("Unknown") is None
    assert sec.normalize_actor_id("tg:99") is None


def test_keystore_delegado():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "keys.json")
        ks = KeyStore(path=path)
        addr1, pk1 = ks.get_or_create("tg:111")
        addr2, pk2 = ks.get_or_create("tg:111")
        assert (addr1, pk1) == (addr2, pk2), "la llave delegada es estable"
        assert ks.scope_for_address(addr1) == "tg:111"

        # migración del formato histórico plano
        legacy_pk = Account.create().key.hex()
        legacy_pk = legacy_pk if legacy_pk.startswith("0x") else "0x" + legacy_pk
        with open(path, "w") as fh:
            json.dump({"555": legacy_pk.replace("0x", "")}, fh)
        ks2 = KeyStore(path=path)
        addr, pk = ks2.get_or_create("555")
        assert pk == legacy_pk and addr == Account.from_key(legacy_pk).address


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
