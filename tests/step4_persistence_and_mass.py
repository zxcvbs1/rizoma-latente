import sys
import os
import asyncio

# Aseguramos que el path incluya la raíz para importar packages
sys.path.append(os.getcwd())

from packages.domain.database import SessionLocal, init_db
from packages.domain.models import Node, Actor
from packages.adapters.adapter import OllamaAdapter
from eth_account import Account
import uuid

async def test_persistence_and_mass():
    print(f"--- PERSISTENCIA Y MASA EN GATEWAY ---")
    
    # 1. Intentar inicializar DB (Crear tablas y extensiones)
    print(f"[1] Inicializando base de datos...")
    try:
        init_db()
        print(f"    - DB inicializada ✅")
    except Exception as e:
        print(f"    - ❌ Error inicializando DB: {e}")
        return

    db = SessionLocal()
    adapter = OllamaAdapter()
    
    try:
        # 2. Generar datos reales para el guardado
        acc = Account.create()
        actor_id = acc.address
        text = "!ofrezco servicios de diseño en #remoto"
        
        parsed = adapter.parse_emission(text)
        vector = await adapter.generate_embedding(parsed['clean_text'])
        
        # 3. Crear Actor y Nodo
        print(f"\n[2] Guardando Actor y Nodo...")
        actor = Actor(id=actor_id, alias="TestActor")
        db.add(actor)
        
        node_id = f"{parsed['command_slug']}-{uuid.uuid4().hex[:6]}"
        new_node = Node(
            id=node_id,
            state="active",
            text_raw=text,
            command_raw=parsed['command_raw'],
            command_slug=parsed['command_slug'],
            groups=parsed['groups'],
            content_vector=vector,
            actor_id=actor_id,
            mass=1.0 # Masa inicial fundamental
        )
        db.add(new_node)
        db.commit()
        print(f"    - Nodo {node_id} guardado con Masa 1.0 ✅")
        
        # 4. Verificar recuperación
        print(f"\n[3] Verificando persistencia...")
        retrieved = db.query(Node).filter(Node.id == node_id).first()
        if retrieved:
            print(f"    - Recuperación exitosa: {retrieved.text_raw}")
            print(f"    - Masa en DB: {retrieved.mass}")
            print(f"    - Dimensiones del vector en DB: {len(retrieved.content_vector)}")
            
            print(f"\n[RESULTADO] >>> 💾 El Gateway ha consolidado la intención en su memoria histórica.")
        else:
            print(f"    - ❌ No se pudo recuperar el nodo.")

    except Exception as e:
        print(f"    - ❌ Error durante el guardado: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_persistence_and_mass())
