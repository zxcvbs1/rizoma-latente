"""
Identidad y firma (WP-01, INV-12).

La entidad mínima es la llave secp256k1: dirección (EIP-55), firma de cada
emisión (EIP-191) y base del cifrado del túnel. Ninguna emisión sin firma
verificada entra al índice. Los agentes MCP firman con llave propia; los
puentes firman con la llave delegada de cada persona (escalera de custodia,
Formato canónico y operación: README.md.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_defunct


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_nonce() -> str:
    return uuid.uuid4().hex


def canonical_emit(actor_id: str, timestamp: str, nonce: str, text: str) -> str:
    # README.md: rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}
    return f"rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}"


def _hex(value) -> str:
    h = value.hex() if not isinstance(value, str) else value
    return h if h.startswith("0x") else "0x" + h


def sign_text(private_key: str, message_text: str) -> str:
    signed = Account.sign_message(encode_defunct(text=message_text), private_key=private_key)
    return _hex(signed.signature)


def build_emit_event(private_key: str, text: str, tags=None) -> dict:
    """Construye un evento `emit` completo y firmado, listo para Waku."""
    account = Account.from_key(private_key)
    actor_id = account.address  # checksum EIP-55, exigido por el contrato
    timestamp = now_iso()
    nonce = new_nonce()
    return {
        "protocol": "rizoma.v2",
        "action": "emit",
        "actor_id": actor_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "payload": {"text": text, "tags": tags or []},
        "signature": sign_text(private_key, canonical_emit(actor_id, timestamp, nonce, text)),
    }


class KeyStore:
    """
    Custodia delegada del primer escalón (01_red §5 y §10): el puente guarda la
    llave de quien todavía no autocustodia; subir de escalón migra la custodia
    sin cambiar identidad ni perder historial.

    Archivo JSON: { "<scope>": {"private_key": "0x..", "address": "0x.."} }.
    Scope: "tg:<chat_id>" para usuarios del puente Telegram, "mcp:<nombre>"
    para agentes. Migra en el acto el formato histórico plano de
    user_keys.json ( { "<telegram_id>": "<hex>" } ).
    """

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("RIZOMA_KEYSTORE", "user_keys.json")
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as fh:
            raw = json.load(fh) or {}
        data = {}
        for scope, entry in raw.items():
            if isinstance(entry, str):  # formato histórico: valor = private key
                pk = _hex(entry)
                data[scope] = {"private_key": pk, "address": Account.from_key(pk).address}
            else:
                data[scope] = entry
        return data

    def _save(self, data: dict):
        # El keystore vive donde el cliente lo declare (RIZOMA_KEYSTORE): crear
        # el directorio si no existe, para que el primer acto no tropiece.
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get_or_create(self, scope: str) -> tuple[str, str]:
        """Devuelve (address, private_key) del scope, creando la llave si no existe."""
        with self._lock:
            data = self._load()
            if scope in data:
                return data[scope]["address"], data[scope]["private_key"]
            account = Account.create()
            pk = _hex(account.key)
            data[scope] = {"private_key": pk, "address": account.address}
            self._save(data)
            return account.address, pk

    def scope_for_address(self, address: str) -> str | None:
        """Búsqueda inversa: a qué scope (ej: chat de Telegram) notificar."""
        target = (address or "").lower()
        for scope, entry in self._load().items():
            if entry["address"].lower() == target:
                return scope
        return None

    def identidades(self) -> list[tuple[str, str]]:
        """Todas las identidades que este cliente custodia: (scope, address),
        jamás la clave privada. Para descubrir bajo qué llave vive el material
        del dueño sin depender de que nadie adivine el nombre del scope."""
        return [(scope, entry["address"]) for scope, entry in self._load().items()]
