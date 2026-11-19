import sys
import os
import asyncio
import math

# Aseguramos que el path incluya la raíz para importar packages
sys.path.append(os.getcwd())

from packages.domain.database import SessionLocal
from packages.domain.models import Node
from packages.adapters.adapter import OllamaAdapter
from sqlalchemy import select, func, text

async def test_semantic_search(query_text):
    print(f"--- BÚSQUEDA SEMÁNTICA EN GATEWAY ---")
    print(f"Consulta del usuario: '{query_text}'")
    
    db = SessionLocal()
    adapter = OllamaAdapter()
    
    try:
        # 1. Convertir búsqueda en vector
        print(f"[1] Vectorizando consulta...")
        query_vector = await adapter.generate_embedding(query_text)
        
        # 2. Búsqueda en DB usando pgvector (distancia de coseno)
        # La distancia de coseno en pgvector es <-> (L2), <=> (coseno) o <#> (producto punto)
        # Usamos 1 - (vector <=> columna) para obtener la similitud de coseno (0 a 1)
        print(f"[2] Buscando en el espacio semántico (768 dimensiones)...")
        
        # Fórmula: similitud_coseno * ln(masa + 1)
        # Nota: pgvector usa <=> para distancia de coseno, así que 1 - (distancia) = similitud
        stmt = select(
            Node,
            (1 - Node.content_vector.cosine_distance(query_vector)).label("similarity")
        ).filter(
            Node.state == "active",
            Node.content_vector.isnot(None)
        ).order_by(
            text("similarity DESC")
        ).limit(5)
        
        from sqlalchemy import text as sa_text
        # Ejecutamos con una pequeña corrección para SQLAlchemy y pgvector
        results = db.execute(stmt).all()
        
        print(f"\n[3] Resultados encontrados: {len(results)}")
        
        for node, similarity in results:
            # Aplicar peso de masa (ln(masa + 1))
            mass_weight = math.log(node.mass + 1)
            final_score = similarity * mass_weight
            
            print(f"\n    >> NODO: {node.id}")
            print(f"       Texto: {node.text_raw}")
            print(f"       Similitud: {similarity:.4f}")
            print(f"       Masa: {node.mass}")
            print(f"       SCORE FINAL: {final_score:.4f}")
            
        if results:
            print(f"\n[RESULTADO] >>> 🎯 El Gateway ha conectado la necesidad con la oferta exitosamente.")
        else:
            print(f"\n[RESULTADO] >>> ❌ No se encontraron coincidencias semánticas.")

    except Exception as e:
        print(f"    - ❌ Error durante la búsqueda: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Buscamos algo relacionado con el nodo que guardamos antes 
    # (Antes guardamos: "!ofrezco servicios de diseño en #remoto")
    query = "necesito un diseñador grafico para un logo"
    asyncio.run(test_semantic_search(query))
