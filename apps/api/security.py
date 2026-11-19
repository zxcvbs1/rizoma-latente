from eth_account.messages import encode_defunct, _hash_eip191_message
from eth_account import Account
from eth_utils import is_address, to_checksum_address
from eth_keys.datatypes import Signature as EthSignature
from hexbytes import HexBytes
from datetime import datetime, timedelta, timezone
import redis
import os

class SecurityService:
    """
    Validación de emisiones según README.md (WP-01, INV-12):
    dirección EIP-55, firma EIP-191 sobre mensaje canónico, ventana de tiempo,
    nonce único y rate limit por edad del actor. Sin actores de confianza.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client or redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        self.max_age_minutes = 5
        self.new_actor_days = 7
        self.limit_new_per_day = 5      # contrato: nuevo actor, 5 emisiones/día
        self.limit_stable_per_day = 50  # contrato: actor estable, 50 emisiones/día

    def normalize_actor_id(self, actor_id) -> str | None:
        """
        El actor_id DEBE ser una dirección Ethereum; se normaliza a checksum
        EIP-55. Cualquier otra cosa ("mcp-agent-*", "tg:...", "Unknown") se
        rechaza: no existen actores de confianza (WP-01).
        """
        if not isinstance(actor_id, str) or not is_address(actor_id):
            return None
        try:
            return to_checksum_address(actor_id)
        except Exception:
            return None

    def verify_eip191_signature(self, actor_id: str, signature: str, message_text: str) -> bool:
        """
        Verifica que la firma corresponda al actor_id para el mensaje dado.
        """
        try:
            message = encode_defunct(text=message_text)
            recovered_address = Account.recover_message(message, signature=signature)
            return recovered_address.lower() == actor_id.lower()
        except Exception:
            return False

    def recover_public_key(self, signature: str, message_text: str) -> str | None:
        """
        Recupera la clave pública secp256k1 (sin comprimir, formato 0x04||x||y)
        desde una firma EIP-191. La firma ya la hace pública por diseño; el
        nodo la registra para que la Mini App pueda cifrar la primera palabra
        al topic derivado (ECDH) sin ningún intercambio extra (01_red §4.2).
        """
        try:
            sig = HexBytes(signature)
            if len(sig) != 65:
                return None
            v = sig[64]
            v = v - 27 if v >= 27 else v
            eth_sig = EthSignature(vrs=(
                v,
                int.from_bytes(sig[0:32], "big"),
                int.from_bytes(sig[32:64], "big"),
            ))
            msg_hash = _hash_eip191_message(encode_defunct(text=message_text))
            pub = eth_sig.recover_public_key_from_msg_hash(msg_hash)
            return "0x04" + pub.to_hex()[2:]
        except Exception:
            return None

    def is_valid_timestamp(self, timestamp_iso: str) -> bool:
        """
        Verifica que el timestamp esté dentro de la ventana de 5 minutos.
        """
        try:
            # Soportar formato Z o +00:00
            dt = datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return abs((now - dt).total_seconds()) < (self.max_age_minutes * 60)
        except Exception:
            return False

    def is_nonce_new(self, actor_id: str, nonce: str) -> bool:
        """
        Verifica si el nonce es nuevo para este actor (TTL 24h).
        """
        key = f"nonce:{actor_id}:{nonce}"
        if self.redis.exists(key):
            return False

        # Guardar nonce por 24 horas
        self.redis.setex(key, timedelta(hours=24), "1")
        return True

    def check_rate_limit(self, actor_id: str) -> tuple[bool, str]:
        """
        Rate limit del contrato: 5/día para actores con menos de 7 días desde
        su primera emisión, 50/día para el resto. Devuelve (permitido, motivo).
        """
        now = datetime.now(timezone.utc)
        first_seen_key = f"first_seen:{actor_id}"
        self.redis.set(first_seen_key, now.isoformat(), nx=True)

        raw = self.redis.get(first_seen_key)
        try:
            first_seen = datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw)
        except Exception:
            first_seen = now
        age_days = (now - first_seen).total_seconds() / 86400
        limit = self.limit_new_per_day if age_days < self.new_actor_days else self.limit_stable_per_day

        day_key = f"emits:{actor_id}:{now.strftime('%Y%m%d')}"
        count = int(self.redis.incr(day_key))
        if count == 1:
            self.redis.expire(day_key, int(timedelta(hours=25).total_seconds()))

        if count > limit:
            return False, f"rate limit: {count} emisiones hoy (límite {limit}/día)"
        return True, "ok"
