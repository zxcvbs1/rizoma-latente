import asyncio
import os
import sys

# Aseguramos que el path incluya la raíz
sys.path.append(os.getcwd())

from packages.adapters.waku_adapter import WakuAdapter
from tests.step1_actor_setup import create_sovereign_emission

async def fire_test():
    print(f"--- FUEGO: LANZANDO INTENCIÓN AL OCÉANO REAL ---")
    
    adapter = WakuAdapter()
    
    # 1. Crear intención firmada
    text = "!ofrezco clases de yoga solar en #parque-centenario"
    event = create_sovereign_emission(text)
    
    # 2. Lanzar a Waku
    print(f"\n[BROADCAST] Enviando a nwaku (localhost:8645)...")
    success = await adapter.broadcast(event)
    
    if success:
        print(f"\n[OK] Intención lanzada con éxito. Esperando a que el Ingestor la capture...")
    else:
        print(f"\n[ERROR] No se pudo conectar con el nodo Waku.")

if __name__ == "__main__":
    asyncio.run(fire_test())
