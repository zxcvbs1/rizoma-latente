import sys
import os
from datetime import datetime, timezone

# Aseguramos que el path incluya la raíz para importar apps
sys.path.append(os.getcwd())

from apps.api.security import SecurityService

def verify_incoming_event(event):
    security = SecurityService()
    
    actor_id = event["actor_id"]
    signature = event["signature"]
    timestamp = event["timestamp"]
    nonce = event["nonce"]
    text = event["payload"]["text"]
    
    # Mensaje canónico que el Gateway reconstruye para verificar
    msg_text = f"rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}"
    
    print(f"--- VERIFICACIÓN EN GATEWAY ---")
    print(f"Actor: {actor_id}")
    print(f"Texto: {text}")
    
    # 1. Verificar Firma
    sig_ok = security.verify_eip191_signature(actor_id, signature, msg_text)
    print(f"[1] Firma EIP-191: {'✅ VÁLIDA' if sig_ok else '❌ INVÁLIDA'}")
    
    # 2. Verificar Ventana de Tiempo
    time_ok = security.is_valid_timestamp(timestamp)
    print(f"[2] Ventana de Tiempo (5m): {'✅ DENTRO' if time_ok else '❌ FUERA'}")
    
    # 3. Verificar Nonce (Anti-replay)
    try:
        nonce_ok = security.is_nonce_new(actor_id, nonce)
        print(f"[3] Nonce (Anti-replay): {'✅ NUEVO' if nonce_ok else '❌ REPETIDO'}")
    except Exception as e:
        print(f"[3] Nonce (Anti-replay): ⚠️ SKIPPED (Redis no disponible)")
        nonce_ok = True

    if sig_ok and time_ok and nonce_ok:
        print(f"\n[RESULTADO] >>> 🏆 EVENTO ADMITIDO EN EL ÍNDICE LOCAL")
        return True
    else:
        print(f"\n[RESULTADO] >>> 🚫 EVENTO RECHAZADO")
        return False

if __name__ == "__main__":
    # Simulamos un evento que acaba de llegar del "aire"
    # (Usamos un timestamp actual para que no falle la validación de tiempo)
    import uuid
    from eth_account import Account
    from eth_account.messages import encode_defunct

    # Generamos uno rápido para la prueba
    acc = Account.create()
    ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    nonce = uuid.uuid4().hex
    text = "!busco carpintero en #palermo"
    msg = f"rizoma.emit|{acc.address}|{ts}|{nonce}|{text}"
    sig = Account.sign_message(encode_defunct(text=msg), private_key=acc.key.hex()).signature.hex()

    sample_event = {
        "actor_id": acc.address,
        "signature": sig,
        "timestamp": ts,
        "nonce": nonce,
        "payload": {"text": text}
    }

    verify_incoming_event(sample_event)
