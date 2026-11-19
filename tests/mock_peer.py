from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Rizoma Peer Mock (Rosario)")

@app.get("/search")
async def search(q: str):
    # Simula que encontró algo en Rosario
    return {
        "results": [
            {
                "node": {
                    "id": "ofrezco-rosario-01",
                    "state": "active",
                    "text_raw": f"!ofrezco lo que buscas ('{q}') pero en Rosario",
                    "command_slug": "ofrezco",
                    "groups": ["rosario"],
                    "mass": 2.0,
                    "actor_id": "0x1234567890123456789012345678901234567890",
                    "created_at": "2026-04-18T10:00:00Z"
                },
                "score": 0.85, # Le damos un score alto para que aparezca primero
                "server_origin": "rizoma-rosario"
            }
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
