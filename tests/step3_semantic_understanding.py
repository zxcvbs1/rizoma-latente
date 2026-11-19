import asyncio
import os
import sys

# Aseguramos que el path incluya la raíz para importar packages
sys.path.append(os.getcwd())

from packages.adapters.adapter import OllamaAdapter

async def test_semantic_understanding(text):
    adapter = OllamaAdapter()
    
    print(f"--- ENTENDIMIENTO SEMÁNTICO EN GATEWAY ---")
    print(f"Intención Cruda: {text}")
    
    # 1. Análisis Estructural
    parsed = adapter.parse_emission(text)
    print(f"\n[1] Análisis Estructural:")
    print(f"    - Comando: {parsed['command_raw']} (slug: {parsed['command_slug']})")
    print(f"    - Grupos: {parsed['groups']}")
    print(f"    - Texto para IA: '{parsed['clean_text']}'")
    
    # 2. Generación de Vector (Semántica)
    print(f"\n[2] Generando Vector Semántico (Ollama)...")
    try:
        vector = await adapter.generate_embedding(parsed['clean_text'])
        print(f"    - Vector generado exitosamente ✅")
        print(f"    - Dimensiones: {len(vector)}")
        print(f"    - Primeros 5 valores: {vector[:5]}")
        
        print(f"\n[RESULTADO] >>> 🧠 El Gateway ahora 'entiende' la intención como un punto en el espacio.")
        return True
    except Exception as e:
        print(f"    - ❌ Error conectando con Ollama: {e}")
        return False

if __name__ == "__main__":
    # Probamos con una intención compleja
    text = "!ofrezco semillas organicas de tomate platense #huerta #sustentabilidad"
    asyncio.run(test_semantic_understanding(text))
