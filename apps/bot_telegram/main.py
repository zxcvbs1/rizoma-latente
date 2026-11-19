import logging
import os
import sys
import asyncio
import json
import redis
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Aseguramos que Python encuentre las librerías locales
sys.path.append(os.getcwd())
from packages.adapters.waku_adapter import WakuAdapter
from packages.adapters.adapter import OllamaAdapter
from packages.domain.identity import KeyStore, build_emit_event
from packages.puentes import kit

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURACIÓN ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://rizoma-redis:6379/0")
WAKU_URL = os.getenv("WAKU_URL", "http://rizoma-waku:8645")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rizoma@db:5432/rizoma")
API_URL = os.getenv("RIZOMA_API_URL", "http://rizoma-api:8000")
MINIAPP_URL = os.getenv("MINIAPP_URL", "http://localhost:5173")

# Adaptadores
waku = WakuAdapter()
waku.base_url = WAKU_URL
ollama = OllamaAdapter()

# WP-01 (INV-12) + contrato del puente (01_red §10): el bot custodia la llave
# delegada de cada persona (primer escalón de la escalera) y firma con ELLA.
# La identidad es la dirección; apagar el bot no borra a nadie.
keystore = KeyStore()

# La inferencia PROPONE y la persona confirma antes de emitir (01_red §10).
PENDING_TTL = 600
CONFIRM_WORDS = {"si", "sí", "dale", "ok", "confirmo", "emiti", "emití"}

def pending_key(chat_id: int) -> str:
    return f"pending_emit:tg:{chat_id}"

async def redis_listener(application):
    """Escucha mensajes salientes desde Redis para enviar a Telegram."""
    r = redis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    pubsub.subscribe("telegram_outbound")

    logger.info("[*] Redis Listener activo para mensajes salientes de Telegram.")

    while True:
        try:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                data = json.loads(message['data'])
                actor_id = data.get("actor_id")
                text = data.get("text")

                chat_id = None
                if actor_id and actor_id.startswith("tg:"):
                    chat_id = int(actor_id.split(":")[1])
                elif actor_id and actor_id.startswith("0x"):
                    # Routing inverso: dirección -> scope del puente
                    scope = keystore.scope_for_address(actor_id)
                    if scope and scope.startswith("tg:"):
                        chat_id = int(scope.split(":")[1])

                if chat_id:
                    logger.info(f"[Outbound] Enviando mensaje a {chat_id}")
                    await application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')

            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error en redis_listener: {e}")
            await asyncio.sleep(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    address, _ = keystore.get_or_create(f"tg:{chat_id}")
    await update.message.reply_text(
        f"🌿 *Bienvenido a Rizoma*\n\n"
        f"Tu identidad en la red es la llave `{address}`.\n"
        f"Por ahora la custodio yo (primer escalón); es tuya y podés "
        f"llevártela cuando quieras.\n\n"
        f"Escribime lo que buscás u ofrecés de forma natural. Antes de emitir "
        f"nada te muestro cómo lo leí y espero tu confirmación.",
        parse_mode='Markdown'
    )

async def enviar_ayuda(update: Update):
    """La prueba de los dos minutos (01_red §2): el mapa de cómo hablarle al
    puente, con la lengua viva del nodo tal cual está ahora. Comparte el texto
    con todo puente (kit.texto_ayuda); si no puedo traer la lengua, cae al
    listado genérico sin romperse."""
    comandos = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(f"{API_URL}/espejo/lengua")
            if resp.status_code == 200:
                comandos = [fila.get("comando") for fila in resp.json().get("lengua", [])
                            if fila.get("comando")]
    except Exception as exc:
        logger.warning(f"No pude traer la lengua viva para la ayuda: {exc}")
    await update.message.reply_text(kit.texto_ayuda(comandos), parse_mode='Markdown')

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda (y /help): la explicación extensa de cómo usar el bot."""
    await enviar_ayuda(update)

async def telegram_ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lee la intención, la propone, y emite FIRMADO recién tras la confirmación."""
    chat_id = update.effective_chat.id
    text = update.message.text
    r = redis.from_url(REDIS_URL)

    try:
        # 1. ¿Hay una emisión pendiente y esto es una confirmación?
        pending_raw = r.get(pending_key(chat_id))
        if pending_raw and text.strip().lower() in CONFIRM_WORDS:
            pending = json.loads(pending_raw)
            r.delete(pending_key(chat_id))
            await emit_signed(update, chat_id, pending["intent"], pending["clean_text"])
            return

        # 1 bis. La palabra de orientación SOLA ("ayuda", "?", "comandos")
        #        pide el mapa, no emite. Un texto más largo que la contenga
        #        ("busco ayuda con...") es intención y sigue de largo: la
        #        ayuda no secuestra la palabra propia (01_red §2).
        if kit.pide_ayuda(text):
            await enviar_ayuda(update)
            return

        # 2. Si YA trae !comando explícito, se respeta tal cual (léxico).
        #    Si no, se lee por RESONANCIA (WP-31): el puente no adivina por
        #    keywords, embebe la frase y la compara contra prototipos de los
        #    verbos de la lengua. Sin resonancia, el deseo puro también se
        #    ofrece: nunca hay callejón enlatado para un texto con contenido.
        if text.strip().startswith("!"):
            parsed = ollama.parse_emission(text)
            intent = parsed['command_slug']
            clean_text = parsed['clean_text']
            afinidad = None
        else:
            lectura = await kit.leer_intencion(text, ollama.generate_embedding)
            intent = lectura["comando"]
            afinidad = lectura["afinidad"]
            clean_text = ollama.parse_emission(text)['clean_text'] if intent else text.strip()

        if intent:
            r.setex(pending_key(chat_id), PENDING_TTL,
                    json.dumps({"intent": intent, "clean_text": clean_text}))
            nota_afinidad = f" (afinidad {afinidad:.2f})" if afinidad is not None else ""
            sufijo_patron = await ofrecer_patron(text)
            await update.message.reply_text(
                f"Te leí así: *!{intent} {clean_text}*{nota_afinidad}\n\n"
                f"Si está bien, respondé *si* y lo emito firmado con tu llave. "
                f"Si no, escribilo de nuevo con tus palabras." + sufijo_patron,
                parse_mode='Markdown'
            )
        elif clean_text:
            r.setex(pending_key(chat_id), PENDING_TTL,
                    json.dumps({"intent": None, "clean_text": clean_text}))
            await update.message.reply_text(
                f"Te leí como un deseo sin comando: '{clean_text}'. Un deseo "
                f"también se siembra: queda vectorizado, esperando resonancias "
                f"imprevistas. ¿Lo emito así, tal cual? (si / o reescribilo)"
            )
        else:
            await update.message.reply_text(
                "🤖 Hablame naturalmente (ej: 'busco alguien que sepa Python') "
                "y te propongo la intención antes de emitir nada."
            )
    except Exception as e:
        logger.error(f"Error IA Telegram: {e}")
        await update.message.reply_text("⚠️ No pude procesar tu mensaje semánticamente.")

async def ofrecer_patron(text: str) -> str:
    """WP-32: si la frase resuena con un patrón de coordinación publicado del
    acervo, el puente lo OFRECE como sufijo de la propuesta. Es una invitación
    a jugar el flujo entero (cada paso se emite con confirmación, como
    siempre); si el acervo no responde o nada resuena, no agrega nada."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{API_URL}/formas")
            formas = resp.json().get("formas", []) if resp.status_code == 200 else []
        patron = await kit.leer_patron(text, ollama.generate_embedding, formas)
    except Exception as exc:
        logger.warning(f"No pude consultar patrones del acervo: {exc}")
        return ""
    if not patron:
        return ""
    return (f"\n\n🧩 Esto resuena con el patrón del común "
            f"*{patron['nombre']}*. Si querés jugarlo entero, decímelo y "
            f"vamos paso a paso: cada emisión la confirmás vos.")

async def emit_signed(update: Update, chat_id: int, intent: str | None, clean_text: str):
    """Emite la intención confirmada, firmada con la llave delegada del usuario.
    intent None es deseo puro (WP-31): se emite sin prefijo de comando, tal
    cual, y sigue el mismo camino de resonancias tras emitir."""
    address, private_key = keystore.get_or_create(f"tg:{chat_id}")
    formatted_text = f"!{intent} {clean_text}" if intent else clean_text

    event = build_emit_event(private_key, formatted_text, tags=["from-telegram"])
    ok = await waku.broadcast(event)
    if not ok:
        await update.message.reply_text("⚠️ No pude propagar tu intención en la red. Probá de nuevo.")
        return

    reply = f"✅ Emitido y firmado por `{address[:10]}...`: '{clean_text}'. 🌊"

    if intent == "busco":
        # Una sola fuente de verdad: la lectura del NODO (/search), que trae
        # el piso honesto de resonancia y la deduplicación. El SQL propio del
        # bot (sin piso, sin dedup) mostraba "resonancias" que eran ruido:
        # corrección jul 2026, banco de resonancias.
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20.0) as http:
                resp = await http.get(f"{API_URL}/search",
                                      params={"q": clean_text, "limit": 3})
                datos = resp.json() if resp.status_code == 200 else {"results": []}
        except Exception as exc:
            logger.warning(f"No pude consultar /search: {exc}")
            datos = {"results": []}

        resultados = datos.get("results", [])
        if resultados:
            reply += "\n\n🔍 *Resonancias encontradas:*\n"
            for r in resultados:
                texto = (r.get("node", {}).get("text_raw") or "")
                display_text = texto.replace("!ofrezco ", "✨ ").replace("!busco ", "🔍 ")
                reply += f"• {display_text}\n"
            reply += "\n💡 *Si hay resonancia real, te llega una propuesta con el texto del otro.*"
        else:
            reply += ("\n\n🌱 Nadie resuena con esto todavía: tu señal queda "
                      "sembrada, esperando a su intérprete. Si aparece, te aviso.")

    await update.message.reply_text(reply, parse_mode='Markdown')

async def llevarme_la_llave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Escalera de custodia (01_red §5, WP-21): la persona se lleva su llave
    delegada a la Mini App con un código de un solo uso y vida corta. Subir de
    escalón nunca pide permiso."""
    chat_id = update.effective_chat.id
    _, private_key = keystore.get_or_create(f"tg:{chat_id}")
    r = redis.from_url(REDIS_URL)
    codigo = kit.generar_codigo_exportacion(r, private_key)
    await update.message.reply_text(
        "🔑 *Llevarte tu llave*\n\n"
        "Tu identidad es tuya. Abrí la Mini App y pegá este código para "
        "custodiarla vos (vence en 5 minutos, un solo uso):\n\n"
        f"`{codigo}`\n\n"
        f"{MINIAPP_URL}/#/importar\n\n"
        "Cuando la tengas vos, dejo de ser tu custodio: nada cambia de tu "
        "identidad ni de tu historial.",
        parse_mode='Markdown'
    )

# Los comandos fijos de orientación encabezan el menú nativo: son del puente,
# no de la lengua viva (que brota del uso). La ayuda es lo primero visible.
COMANDOS_FIJOS = [
    ("start", "empezar y ver tu identidad"),
    ("ayuda", "cómo hablarme (y la lengua viva)"),
    ("llave", "llevarte tu identidad"),
]

async def precalentar_caches():
    """Los lectores por resonancia (intención WP-31, patrones WP-32) cachean
    los vectores de sus prototipos a nivel de módulo, pero nacen vacíos: sin
    esto, el PRIMER mensaje tras un reinicio paga solo la vectorización de ~50
    frases (~30s de espera visible). Precalentamos en segundo plano con una
    frase títere para que el primer mensaje real ya los encuentre listos.
    Falla silenciosa: si Ollama o el nodo no están, el caché se llena en el
    primer mensaje como antes (más lento, no roto)."""
    try:
        await kit.leer_intencion("hola", ollama.generate_embedding)
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{API_URL}/formas")
            formas = resp.json().get("formas", []) if resp.status_code == 200 else []
        await kit.leer_patron("hola", ollama.generate_embedding, formas)
        logger.info("[*] Cachés de resonancia precalentados: el primer mensaje "
                    "responde sin espera.")
    except Exception as exc:
        logger.warning(f"No pude precalentar los cachés (se llenan al primer "
                       f"mensaje, más lento): {exc}")

async def post_init(application):
    """Tareas a ejecutar tras iniciar el bot."""
    asyncio.create_task(redis_listener(application))
    asyncio.create_task(precalentar_caches())
    try:
        async def registrar(comandos):
            vivos = [(c["comando"], c["descripcion"][:250]) for c in comandos]
            await application.bot.set_my_commands(COMANDOS_FIJOS + vivos)
        n = await kit.sync_lengua(API_URL, registrar)
        logger.info(f"[*] Menú: {len(COMANDOS_FIJOS)} comandos fijos + {n} "
                    f"comandos vivos de la lengua.")
    except Exception as e:
        logger.warning(f"No pude sincronizar la lengua viva (el menú es comodidad, no gate): {e}")
        try:
            await application.bot.set_my_commands(COMANDOS_FIJOS)
        except Exception as exc:
            logger.warning(f"Tampoco pude registrar los comandos fijos: {exc}")

if __name__ == '__main__':
    if not TOKEN:
        logger.error("Falta TELEGRAM_TOKEN en el entorno. El bot no arranca sin su token.")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('ayuda', ayuda))
    app.add_handler(CommandHandler('help', ayuda))
    app.add_handler(CommandHandler('llave', llevarme_la_llave))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_ai_handler))

    logger.info("[*] Bot de Telegram iniciado (contrato del puente: firma delegada + confirmación).")
    app.run_polling()
