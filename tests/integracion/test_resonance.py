# Test de INTEGRACIÓN: necesita Waku vivo y el ingestor corriendo. No
# pertenece a la batería sin servicios; por eso vive en tests/integracion/.
import asyncio
import os
import sys

# Aseguramos que el path incluya la raíz
sys.path.append(os.getcwd())

from packages.adapters.waku_adapter import WakuAdapter
from tests.step1_actor_setup import create_sovereign_emission

async def dual_launch():
    adapter = WakuAdapter()
    await adapter.subscribe()
    
    # 1. La Oferta
    print("\n--- LANZANDO OFERTA ---")
    event_off = create_sovereign_emission("!ofrezco clases de guitarra flamenca #musica")
    await adapter.broadcast(event_off)
    
    # Pausa para que el ingestor procese la primera
    print("Esperando procesamiento de oferta...")
    await asyncio.sleep(5)
    
    # 2. La Búsqueda (que debería disparar el Match)
    print("\n--- LANZANDO BÚSQUEDA ---")
    event_seek = create_sovereign_emission("!busco profesor de guitarra")
    await adapter.broadcast(event_seek)
    print("\n[OK] Intenciones en el aire. Revisa los logs del Ingestor.")

if __name__ == "__main__":
    asyncio.run(dual_launch())
