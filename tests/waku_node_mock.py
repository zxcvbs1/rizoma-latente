from fastapi import FastAPI, Request
import uvicorn
import base64
import json

app = FastAPI()

# Memoria efímera del "Océano de Datos"
ocean_of_data = []

@app.post("/relay/v1/messages")
async def post_message(request: Request):
    msg = await request.json()
    content_topic = msg.get("contentTopic")
    payload_b64 = msg.get("payload")
    
    # Decodificamos para ver qué llegó
    decoded = base64.b64decode(payload_b64).decode()
    event = json.loads(decoded)
    
    print(f"\n[WAKU-NODE] 🌊 Mensaje recibido en topic: {content_topic}")
    print(f"[WAKU-NODE] Actor: {event['actor_id']}")
    print(f"[WAKU-NODE] Acción: {event['action']}")
    
    ocean_of_data.append(msg)
    return {"status": "success"}

@app.get("/relay/v1/messages/{content_topic}")
async def get_messages(content_topic: str):
    print(f"[WAKU-NODE] 🔍 Sirviendo mensajes del topic: {content_topic}")
    return ocean_of_data

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8645)
