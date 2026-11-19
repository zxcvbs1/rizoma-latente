import redis
import json
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime, timezone
import uuid
import os

r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

# Identidad ficticia del usuario externo
priv_key = Account.create().key.hex()
account = Account.from_key(priv_key)
actor_id = account.address

def emit_to_network(text):
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    nonce = uuid.uuid4().hex
    
    # Mensaje según protocolo v2
    msg_text = f"rizoma.emit|{actor_id}|{ts}|{nonce}|{text}"
    sig = Account.sign_message(encode_defunct(text=msg_text), private_key=priv_key).signature.hex()

    event = {
        "protocol": "rizoma.v2",
        "action": "emit",
        "actor_id": actor_id,
        "timestamp": ts,
        "nonce": nonce,
        "payload": {
            "text": text
        },
        "signature": sig
    }

    print(f"[*] Lanzando intención al 'aire' (Waku): {text}")
    r.publish("rizoma.v2.global", json.dumps(event))

if __name__ == "__main__":
    emit_to_network("!ofrezco herramientas de carpinteria en alquiler")
    emit_to_network("!busco clases de piano zona norte")
