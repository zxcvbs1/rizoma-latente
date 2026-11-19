"""
Bot de Discord: segunda instancia del kit de puente (WP-21; 01_red §10).

Prueba de que el contrato del puente es reutilizable: el MISMO kit
(confirmar antes de emitir, firma delegada, espejo de la lengua, escalera de
llave) sobre otra plataforma. La lógica vive en `packages/puentes/kit.py` y
`packages/domain/identity.py`; acá solo está el pegamento de Discord.

Requiere `discord.py` (no es dependencia del núcleo). Si no está instalado,
el módulo se importa igual y explica qué falta, sin romper el resto del repo.
"""
import asyncio
import os
import sys

sys.path.append(os.getcwd())

import redis

from packages.adapters.adapter import OllamaAdapter
from packages.adapters.waku_adapter import WakuAdapter
from packages.domain.identity import KeyStore, build_emit_event
from packages.puentes import kit

TOKEN = os.getenv("DISCORD_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://rizoma-redis:6379/0")
MINIAPP_URL = os.getenv("MINIAPP_URL", "http://localhost:5173")

keystore = KeyStore()
ollama = OllamaAdapter()
waku = WakuAdapter()


def scope(user_id) -> str:
    # Misma identidad-por-plataforma que el puente de Telegram (tg:<id>).
    return f"dc:{user_id}"


async def manejar_mensaje(user_id, texto: str, responder, enviar_emit) -> None:
    """Contrato del puente, agnóstico de Discord: propone la lectura, espera
    confirmación escrita, emite firmado con la llave delegada. `responder` y
    `enviar_emit` los inyecta el adaptador (o un test)."""
    r = redis.from_url(REDIS_URL)
    import json
    pendiente_key = f"pending_emit:{scope(user_id)}"

    pendiente = r.get(pendiente_key)
    if pendiente and kit.es_confirmacion(texto):
        datos = json.loads(pendiente)
        r.delete(pendiente_key)
        await enviar_emit(datos["intent"], datos["clean_text"])
        return

    parsed = ollama.parse_emission(texto)
    intent = parsed["command_slug"]
    if intent in ("busco", "ofrezco"):
        r.setex(pendiente_key, kit.TTL_CODIGO_SEGUNDOS,
                json.dumps({"intent": intent, "clean_text": parsed["clean_text"]}))
        await responder(kit.mensaje_propuesta_lectura(intent, parsed["clean_text"]))
    else:
        await responder("Hablame natural (ej: 'busco quien arregle bicis') y te "
                        "propongo la intención antes de emitir nada.")


def emitir_firmado(user_id, intent: str, clean_text: str) -> bool:
    address, private_key = keystore.get_or_create(scope(user_id))
    event = build_emit_event(private_key, f"!{intent} {clean_text}", tags=["from-discord"])
    return asyncio.get_event_loop().run_until_complete(waku.broadcast(event))


def main():
    if not TOKEN:
        print("Falta DISCORD_TOKEN. El bot no arranca sin su token.")
        return
    try:
        import discord
    except ImportError:
        print("Falta discord.py: pip install discord.py. El contrato ya está en el kit.")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if message.content.strip() == "!llave":
            r = redis.from_url(REDIS_URL)
            _, pk = keystore.get_or_create(scope(message.author.id))
            codigo = kit.generar_codigo_exportacion(r, pk)
            await message.channel.send(
                f"Tu llave es tuya. Pegá este código en la Mini App "
                f"({MINIAPP_URL}/#/importar), un solo uso, vence en 5 min:\n`{codigo}`")
            return
        await manejar_mensaje(
            message.author.id, message.content,
            responder=message.channel.send,
            enviar_emit=lambda i, t: message.channel.send(
                "Emitido y firmado con tu llave 🌊" if emitir_firmado(message.author.id, i, t)
                else "No pude propagar en la red, probá de nuevo."))

    client.run(TOKEN)


if __name__ == "__main__":
    main()
