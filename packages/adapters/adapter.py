import httpx
import os

class OllamaAdapter:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = "nomic-embed-text"

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Envía texto a Ollama y retorna un vector de 768 dimensiones.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                }
            )
            response.raise_for_status()
            return response.json()["embedding"]

    def parse_emission(self, text: str) -> dict:
        """
        Extrae la intención de forma inteligente (con o sin '!').
        """
        text = text.strip()
        if not text:
            return {"command_slug": None, "groups": [], "clean_text": ""}

        parts = text.split()
        command_slug = None
        
        # 1. Detección por prefijo explícito (Gramática Rizoma)
        if text.startswith("!"):
            command_slug = parts[0].lstrip("!").lower()
            clean_text = " ".join(parts[1:])
        else:
            # 2. Inferencia Semántica (Lenguaje Natural)
            low = text.lower()
            trigger_words = ["busco", "necesito", "hay", "tenes", "tiene", "alguien", "conseguir", "ofrezco", "tengo", "doy", "regalo", "vendo", "dispongo", "una", "un", "algun", "alguna", "unas", "unos"]
            
            if any(w in low for w in ["busco", "necesito", "hay", "tenes", "tiene", "alguien", "conseguir"]):
                command_slug = "busco"
            elif any(w in low for w in ["ofrezco", "tengo", "doy", "regalo", "vendo", "dispongo"]):
                command_slug = "ofrezco"
            
            # Limpiar el texto de palabras vacías y disparadores
            words = text.split()
            clean_parts = [w for w in words if w.lower().strip("¿?") not in trigger_words]
            clean_text = " ".join(clean_parts) if clean_parts else text

        # Extraer hashtags si los hay
        groups = [p.lstrip("#").lower() for p in parts if p.startswith("#")]
        # Limpiar hashtags del texto limpio
        clean_text = " ".join([p for p in clean_text.split() if not p.startswith("#")])

        return {
            "command_raw": f"!{command_slug}" if command_slug else None,
            "command_slug": command_slug,
            "groups": groups,
            "clean_text": clean_text
        }
