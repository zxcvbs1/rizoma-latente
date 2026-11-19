import httpx
import os
import json
import base64

class WakuAdapter:
    def __init__(self):
        # Intentar detectar si estamos en docker o usar la URL de entorno
        self.base_url = os.getenv("WAKU_URL", "http://rizoma-waku:8645")
        self.content_topic = "/rizoma/v2/global/proto"

    async def subscribe(self):
        """
        Suscribe el nodo al topic de Rizoma. Necesario en nwaku para publicar.
        """
        url = f"{self.base_url.rstrip('/')}/relay/v1/subscriptions"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # La API espera una lista de topics
                response = await client.post(url, json=[self.content_topic])
                if response.status_code in [200, 204]:
                    print(f"[WAKU] Suscrito exitosamente a {self.content_topic} ✅")
                    return True
                else:
                    print(f"[WAKU] Error suscribiendo: {response.text}")
                    return False
            except Exception as e:
                print(f"[WAKU] Fallo de conexión para suscripción: {e}")
                return False

    async def broadcast(self, payload: dict, content_topic: str | None = None):
        """
        Envía un mensaje al Océano de Datos (Waku Relay). `content_topic`
        permite publicar en meta-topics (ej: /rizoma/v2/piezas) sin tocar el
        global; las EMISIONES siguen yendo siempre al global (regla del piso).
        """
        topic = content_topic or self.content_topic
        # 1. Asegurar suscripción primero
        await self.subscribe()

        import urllib.parse
        topic_encoded = urllib.parse.quote(topic, safe='')
        url = f"{self.base_url.rstrip('/')}/relay/v1/messages/{topic_encoded}"

        data_json = json.dumps(payload)
        data_b64 = base64.b64encode(data_json.encode()).decode()

        message = {
            "payload": data_b64,
            "contentTopic": topic,
            "timestamp": 0
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=message)
                response.raise_for_status()
                print(f"[WAKU] Mensaje propagado al Océano ✅")
                return True
            except Exception as e:
                print(f"[WAKU] Error de propagación en {url}: {e}")
                return False

    async def get_messages(self):
        """
        Obtiene mensajes del Océano de Datos (vía Store API para persistencia).
        """
        import urllib.parse
        topic_encoded = urllib.parse.quote(self.content_topic, safe='')
        # NWaku usa /store/v1/messages para mensajes históricos persistidos
        url = f"{self.base_url.rstrip('/')}/store/v1/messages"
        params = {"contentTopic": self.content_topic, "pageSize": 100}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    # Si falla Store, intentamos Relay como fallback (nwaku v0.32 puede variar)
                    topic_encoded = urllib.parse.quote(self.content_topic, safe='')
                    relay_url = f"{self.base_url.rstrip('/')}/relay/v1/messages/{topic_encoded}"
                    response = await client.get(relay_url)
                
                response.raise_for_status()
                data = response.json()
                
                # NWaku Store API devuelve un objeto con { "messages": [...] }
                messages = data.get("messages", []) if isinstance(data, dict) else data
                
                decoded_events = []
                for msg in messages:
                    try:
                        raw_payload = base64.b64decode(msg["payload"]).decode()
                        decoded_events.append(json.loads(raw_payload))
                    except:
                        continue
                
                if decoded_events:
                    print(f"[WAKU] Recuperadas {len(decoded_events)} intenciones del Store.")
                return decoded_events
            except Exception as e:
                # print(f"[WAKU] Error recuperando mensajes: {e}")
                return []
