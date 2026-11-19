import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime, timezone
import uuid
import time

API_URL = "http://localhost:8000"

# 1. Identidad
private_key = Account.create().key.hex()
account = Account.from_key(private_key)
actor_id = account.address

print(f"--- Identidad Generada: {actor_id} ---\n")

def sign_and_send(method, endpoint, action, extra_payload=None):
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    nonce = uuid.uuid4().hex
    
    # Construir mensaje para firma
    if action == "rizoma.emit":
        msg = f"{action}|{actor_id}|{timestamp}|{nonce}|{extra_payload['text']}"
    elif action == "rizoma.link":
        msg = f"{action}|{actor_id}|{timestamp}|{nonce}|{extra_payload['node_a']}|{extra_payload['node_b']}"
    elif action == "rizoma.node.patch":
        msg = f"{action}|{actor_id}|{timestamp}|{nonce}|{extra_payload['node_id']}|{extra_payload['action']}"
    
    signature = Account.sign_message(encode_defunct(text=msg), private_key=private_key).signature.hex()
    
    payload = {
        "actor_id": actor_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": signature
    }
    if extra_payload:
        payload.update(extra_payload)
        
    print(f"{method} -> {endpoint} ({action})...")
    if method == "POST":
        return httpx.post(f"{API_URL}{endpoint}", json=payload, timeout=60.0)
    elif method == "PATCH":
        return httpx.patch(f"{API_URL}{endpoint}", json=payload, timeout=60.0)

def search(query):
    print(f"\nBusca -> '{query}'...")
    r = httpx.get(f"{API_URL}/search", params={"q": query}, timeout=60.0)
    if r.status_code == 200:
        results = r.json()['results']
        if not results:
            print("  (Sin resultados activos)")
        for res in results:
            print(f"  [{res['score']:.4f}] {res['node']['text_raw']} (ID: {res['node']['id']}, Estado: {res['node']['state']})")
    else:
        print(f"  Error: {r.status_code}")

# --- FLUJO ---
try:
    # Emitir
    r1 = sign_and_send("POST", "/emit", "rizoma.emit", {"text": "!ofrezco semillas de tomate"})
    node1 = r1.json()['node_id']
    print(f"  Nodo 1: {node1}")

    r2 = sign_and_send("POST", "/emit", "rizoma.emit", {"text": "!busco huerta"})
    node2 = r2.json()['node_id']
    print(f"  Nodo 2: {node2}")

    print("\nEsperando a la IA (10s)...")
    time.sleep(10)

    # Enlazar
    sign_and_send("POST", "/link", "rizoma.link", {"node_a": node1, "node_b": node2})
    print("  Enlace creado.")

    # Buscar ANTES de cerrar
    search("semillas")

    # Cerrar (AHORA CON PATCH)
    sign_and_send("PATCH", f"/node/{node1}", "rizoma.node.patch", {"node_id": node1, "action": "close"})
    print("  Nodo 1 cerrado.")

    # Buscar DESPUÉS de cerrar
    search("semillas")

except Exception as e:
    print(f"\nERROR: {e}")
