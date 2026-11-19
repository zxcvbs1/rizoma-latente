import asyncio
import os
import sys
import subprocess
import time

# Aseguramos que el path incluya la raíz
sys.path.append(os.getcwd())

from packages.adapters.waku_adapter import WakuAdapter
from tests.step1_actor_setup import create_sovereign_emission

async def test_waku_transport():
    print(f"--- TRANSPORTE DISTRIBUIDO (WAKU) ---")
    
    # 1. Iniciar Mock de Waku en segundo plano
    print(f"[1] Iniciando simulador de Nodo Waku...")
    waku_proc = subprocess.Popen(
        [sys.executable, "tests/waku_node_mock.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(2) # Esperar a que FastAPI levante

    try:
        adapter = WakuAdapter()
        
        # 2. Crear una intención firmada soberana
        print(f"\n[2] Generando intención firmada...")
        event = create_sovereign_emission("!busco clases de carpinteria en #tigre")
        
        # 3. Lanzar al Océano de Datos
        print(f"\n[3] Lanzando al Océano de Datos (Waku Relay)...")
        success = await adapter.broadcast(event)
        
        if success:
            print(f"    - Broadcast exitoso ✅")
            
            # 4. Recuperar para verificar (Simulando lo que haría un Ingestor)
            print(f"\n[4] Recuperando mensajes del Océano (Waku Store/Relay)...")
            messages = await adapter.get_messages()
            print(f"    - Mensajes recuperados: {len(messages)}")
            
            for msg in messages:
                print(f"    - Evento recuperado de {msg['actor_id'][:10]}...: {msg['payload']['text']}")
            
            print(f"\n[RESULTADO] >>> 🌊 El transporte P2P es funcional. La intención ya no depende de una DB local.")
        else:
            print(f"    - ❌ Falló el transporte.")

    finally:
        # Limpieza
        waku_proc.terminate()
        print(f"\n[INFO] Simulador de Waku cerrado.")

if __name__ == "__main__":
    asyncio.run(test_waku_transport())
