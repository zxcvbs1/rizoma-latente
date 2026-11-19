from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime, timezone
import uuid
import json

def create_sovereign_emission(text: str, priv_key: str = None):
    # 1. El Actor genera su identidad o usa la provista
    if not priv_key:
        priv_key = Account.create().key.hex()
    account = Account.from_key(priv_key)
    actor_id = account.address

    print(f"--- PASO 1: IDENTIDAD SOBERANA ---")
    print(f"Actor ID (Public Key): {actor_id}")
    
    # 2. Preparar metadatos de red
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    nonce = uuid.uuid4().hex

    # 3. Construir mensaje canónico según el protocolo
    # Formato: rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}
    msg_text = f"rizoma.emit|{actor_id}|{ts}|{nonce}|{text}"
    
    print(f"\n--- PASO 2: MENSAJE CANÓNICO ---")
    print(f"Mensaje a firmar: {msg_text}")

    # 4. Firmar el mensaje (EIP-191)
    message = encode_defunct(text=msg_text)
    signature = Account.sign_message(message, private_key=priv_key).signature.hex()

    print(f"\n--- PASO 3: FIRMA CRIPTOGRÁFICA ---")
    print(f"Firma: {signature}")

    # 5. Generar el Objeto de Red (Listo para Waku)
    event = {
        "protocol": "rizoma.v2",
        "action": "emit",
        "actor_id": actor_id,
        "timestamp": ts,
        "nonce": nonce,
        "payload": {
            "text": text
        },
        "signature": signature
    }

    print(f"\n--- PASO 4: EVENTO LISTO PARA EL OCÉANO DE DATOS ---")
    print(json.dumps(event, indent=2))
    
    return event

if __name__ == "__main__":
    # Probamos con una intención real
    create_sovereign_emission("!ofrezco talleres de huerta urbana en #palermo")
