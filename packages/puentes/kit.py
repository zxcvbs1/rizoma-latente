"""
Kit de puente (WP-21): el contrato del puente (01_red §10) como código
compartido, para que Telegram, Discord o el próximo entren por el mismo molde.

Deberes que este kit implementa:
- La inferencia PROPONE y la persona confirma antes de emitir (texto, jamás
  botón): `mensaje_propuesta_lectura` + `es_confirmacion`.
- Espejo de la lengua (INV-15): `comandos_para_menu` traduce la lengua viva
  del nodo al registro nativo de cada plataforma; lo que decae, se des-lista.
  El registro es comodidad, jamás gate.
- La escalera de custodia (01_red §5): `generar_codigo_exportacion` deja que
  la persona se LLEVE su llave delegada a la Mini App con un código de un
  solo uso y vida corta. Subir de escalón nunca pide permiso.
"""
import uuid

CONFIRMACIONES = {"si", "sí", "dale", "ok", "confirmo", "emiti", "emití"}
PREFIJO_CODIGO = "llave_export:"
TTL_CODIGO_SEGUNDOS = 300

# La prueba de los dos minutos (01_red §2): un recién llegado aprende la lengua
# entera pidiendo ayuda. Estos disparadores son la palabra SOLA (orientación),
# no un pedido a la red: "busco ayuda con mi mudanza" es una emisión legítima y
# NO se intercepta; "ayuda" a secas sí pide el mapa de cómo hablarle al puente.
DISPARADORES_AYUDA = {
    "ayuda", "help", "menu", "menú", "comandos", "?", "/ayuda", "/help",
    "como funciona", "cómo funciona", "como te uso", "cómo te uso",
    "que hago", "qué hago", "que puedo hacer", "qué puedo hacer",
}


def es_confirmacion(texto: str) -> bool:
    return (texto or "").strip().lower() in CONFIRMACIONES


def pide_ayuda(texto: str) -> bool:
    """La palabra de orientación, sola: pide el mapa, no emite a la red. Un
    texto más largo que la contenga ('busco ayuda con...') es una intención y
    sigue su camino: la ayuda no secuestra la palabra propia."""
    return (texto or "").strip().lower().rstrip("!¡.") in DISPARADORES_AYUDA


def texto_ayuda(comandos_vivos: list | None = None) -> str:
    """El mapa de cómo hablarle a cualquier puente (mismo texto para Telegram,
    Discord o el próximo): qué es, cómo se emite, el acto sin botón, las
    resonancias, los patrones del común y la escalera de la llave. Si se le
    pasa la lengua viva del nodo, la muestra tal cual: el vocabulario no está
    fijo, brota del uso."""
    if comandos_vivos:
        listado = ", ".join(f"!{c}" for c in comandos_vivos[:8])
        linea_lengua = (f"Ahora mismo, la lengua viva de esta red incluye: "
                        f"{listado}. Y podés inventar el tuyo: si otros lo "
                        f"retoman, queda; si no, se olvida.")
    else:
        linea_lengua = ("Arrancá con !busco, !ofrezco, !organizo... o inventá "
                        "el tuyo: la lengua es de quien la habla, no un menú "
                        "fijo. Lo que nadie usa se olvida.")
    return (
        "🌿 *Cómo hablarme*\n\n"
        "Esto no es una app que te retiene: es una plaza para coordinarte con "
        "otra gente por lo que buscás, ofrecés u organizás. No hay perfil que "
        "te encasille ni algoritmo que te enganche. Lo que no se usa, se "
        "olvida, a propósito.\n\n"
        "*Cómo se emite.* Escribime en tus palabras lo que necesitás. Yo leo "
        "la intención y te muestro cómo la entendí; vos confirmás con *si* y "
        "recién ahí firmo y la emito con TU llave. Nada sale sin tu palabra: "
        "no hay botón de aceptar, el acto es siempre algo que vos decís.\n\n"
        f"*La lengua.* {linea_lengua}\n\n"
        "*Las resonancias.* Cuando emitís un !busco, te muestro lo que resuena "
        "en la red. Si nada resuena todavía, no te invento coincidencias: tu "
        "señal queda sembrada, esperando a quien la lea, aunque tarde.\n\n"
        "*Los patrones del común.* Si lo tuyo se parece a algo que la "
        "comunidad ya hace (un préstamo, un trueque, una asamblea), te lo "
        "ofrezco para jugarlo entero, paso a paso, confirmando cada emisión.\n\n"
        "*Tu identidad.* Tu llave es tuya; por ahora la custodio yo, pero con "
        "/llave te la llevás cuando quieras, sin perder nada.\n\n"
        "_Comandos:_ /start (empezar) · /ayuda (esto) · /llave (llevarte tu "
        "identidad).\n"
        "¿Querías pedir ayuda a la RED, no a mí? Escribilo entero, por "
        "ejemplo *busco ayuda con una mudanza*, y lo tomo como intención.")


def mensaje_propuesta_lectura(intencion: str, texto_limpio: str) -> str:
    """El mismo texto de propuesta para todo puente: propone la lectura y pide
    confirmación escrita. Sin botones, sin plantillas de respuesta."""
    return (f"Te leí así: !{intencion} {texto_limpio}\n\n"
            f"Si está bien, respondé \"si\" y lo emito firmado con tu llave. "
            f"Si no, escribilo de nuevo con tus palabras.")


import re

_COMANDO_PLATAFORMA = re.compile(r"^[a-z0-9_]{1,32}$")


def comandos_para_menu(lengua: dict, maximo: int = 10) -> list:
    """De la lengua viva del nodo (GET /espejo/lengua) al registro nativo de
    la plataforma: alta por masa, baja por decay (lo que no vuelve, se
    des-registra). Nada de esto filtra la entrada: texto libre siempre entra.

    Los menús de las plataformas son más pobres que la lengua (Telegram solo
    acepta a-z, 0-9 y guión bajo: rechaza !sueño por la ñ y tiraba abajo el
    registro ENTERO). El comando que el menú no puede mostrar sigue vivo en
    la lengua y sigue entrando por texto: el menú es comodidad, no gate."""
    filas = (lengua or {}).get("lengua", [])
    comandos = []
    for fila in filas:
        if len(comandos) >= maximo:
            break
        slug = (fila.get("comando") or "").strip().lstrip("!")
        if not slug or slug == "?" or not _COMANDO_PLATAFORMA.match(slug):
            continue
        comandos.append({
            "comando": slug,
            "descripcion": f"vivo en la red (masa {fila.get('masa', 0)})",
        })
    return comandos


async def sync_lengua(api_url: str, registrar, maximo: int = 10) -> int:
    """Trae la lengua viva y la registra en la plataforma vía el callable
    `registrar(comandos)`. Devuelve cuántos comandos quedaron listados."""
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as cliente:
        respuesta = await cliente.get(f"{api_url.rstrip('/')}/espejo/lengua")
        respuesta.raise_for_status()
        comandos = comandos_para_menu(respuesta.json(), maximo)
    await registrar(comandos)
    return len(comandos)


# --- La escalera: llevarse la llave del puente a la Mini App ---------------

def generar_codigo_exportacion(redis_client, private_key: str,
                               ttl_segundos: int = TTL_CODIGO_SEGUNDOS) -> str:
    """Un código de un solo uso y vida corta. Quien lo canjea se lleva la
    llave delegada: el puente deja de ser custodio único (escalón arriba)."""
    codigo = uuid.uuid4().hex
    redis_client.setex(f"{PREFIJO_CODIGO}{codigo}", ttl_segundos, private_key)
    return codigo


def canjear_codigo(redis_client, codigo: str) -> str | None:
    """Un solo canje: el código se destruye al leerse. Vencido o ya usado,
    no hay llave (y no queda registro de quién intentó)."""
    clave = f"{PREFIJO_CODIGO}{(codigo or '').strip()}"
    valor = redis_client.get(clave)
    if valor is None:
        return None
    redis_client.delete(clave)
    return valor.decode() if isinstance(valor, bytes) else valor


# --- Lectura de intención por resonancia (WP-31) -------------------------
# El puente no adivina por keywords: embebe la frase y la compara contra
# frases-prototipo de los verbos de la lengua. Si nada resuena, el deseo
# puro (sin comando) es una emisión legítima: se ofrece sembrar tal cual.

PROTOTIPOS_INTENCION = {
    "busco": [
        "busco algo que necesito",
        "necesito ayuda con algo",
        "solicito gente para una actividad",
        "ando buscando a alguien que sepa hacer algo",
        "me hace falta una cosa",
        "quiero conseguir algo",
    ],
    "ofrezco": [
        "ofrezco algo que tengo",
        "tengo algo para dar o prestar",
        "regalo una cosa que ya no uso",
        "encontre un objeto o un animal perdido y lo cuido hasta devolverlo",
        "doy en adopcion",
        "puedo ayudar con lo que se hacer",
        "doy clases o servicios",
    ],
    "organizo": [
        "organizo una juntada o actividad",
        "convoco a una reunion en el barrio",
        "armo un evento y aviso",
    ],
    "comparto": [
        "comparto un momento o un espacio con quien quiera sumarse",
        "abro las puertas de mi lugar para otros",
        "invito a compartir una experiencia",
    ],
    "permuto": [
        "cambio una cosa por otra",
        "intercambio lo mio por lo tuyo",
        "trueque de objetos o servicios",
    ],
}

UMBRAL_INTENCION = 0.60  # medido con tests/eval_intencion.py; se ajusta midiendo

_CACHE_VECTORES_PROTOTIPO: dict = {}


def _coseno(a, b):
    import numpy as np
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    na, nb = (va ** 2).sum() ** 0.5, (vb ** 2).sum() ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float((va * vb).sum() / (na * nb))


# --- Los patrones de coordinación en el puente (WP-32) ---------------------
# Si la frase de una persona resuena con un patrón vivo del acervo, el puente
# lo OFRECE: jugar el flujo entero (préstamo, trueque, asamblea) en vez de
# emitir a mano paso por paso. El patrón acelera, jamás saltea el acto: cada
# emisión del patrón se confirma y firma como siempre.

UMBRAL_PATRON = 0.65  # medido con tests/eval_patrones.py sobre los cinco
                      # primeros patrones reales publicados: centro de la
                      # meseta 13/13 del barrido (0.63-0.66), margen a ambos
                      # bordes; re-medir cuando el acervo crezca

_CACHE_VECTORES_PATRON: dict = {}


async def leer_patron(texto, embedder, patrones: list,
                      umbral: float = UMBRAL_PATRON) -> dict | None:
    """Compara la frase contra los patrones de coordinación PUBLICADOS del
    acervo (nombre + descripción; `patrones` es la lista de GET /formas ya
    filtrada por tipo). Devuelve {"forma_id", "nombre", "afinidad"} del que
    mejor resuena sobre el umbral, o None: sin resonancia no se ofrece nada,
    el silencio también acá es legítimo."""
    vivos = [p for p in (patrones or [])
             if p.get("tipo") == "patron_coordinacion"
             and p.get("estado", "publicada") == "publicada"]
    if not vivos:
        return None
    v_texto = await embedder(texto)
    mejor, afinidad = None, 0.0
    for patron in vivos:
        # La descripción del patrón son FRASES EJEMPLO en voz de usuario,
        # separadas por ";": se compara contra cada una y gana la mejor
        # (concatenarlas diluye; misma lección que los prototipos de
        # intención, medida con tests/eval_patrones.py).
        frases = [f.strip() for f in (patron.get("descripcion") or "").split(";")
                  if f.strip()]
        if not frases:
            continue
        for frase in frases:
            if frase not in _CACHE_VECTORES_PATRON:
                _CACHE_VECTORES_PATRON[frase] = await embedder(frase)
            score = _coseno(v_texto, _CACHE_VECTORES_PATRON[frase])
            if score > afinidad:
                mejor, afinidad = patron, score
    if mejor is None or afinidad < umbral:
        return None
    return {"forma_id": mejor.get("id"), "nombre": mejor.get("nombre"),
            "afinidad": afinidad}


async def leer_intencion(texto, embedder, umbral: float = UMBRAL_INTENCION,
                         prototipos: dict | None = None) -> dict:
    """Lee la intención de una frase natural por resonancia contra los
    prototipos de cada verbo. Devuelve {"comando": slug|None, "afinidad":
    float}. comando None significa deseo puro: emisión legítima sin verbo,
    jamás un rechazo. `embedder` es un async callable texto -> vector (el
    mismo del nodo: la semiótica del par liviano vive de este lado).

    Los vectores de los prototipos se calculan UNA vez y se cachean
    (módulo-nivel, lazy): solo la frase del usuario se embebe por mensaje."""
    protos = prototipos or PROTOTIPOS_INTENCION
    v_texto = await embedder(texto)
    mejor, afinidad = None, 0.0
    for slug, frases in protos.items():
        for frase in frases:
            if frase not in _CACHE_VECTORES_PROTOTIPO:
                _CACHE_VECTORES_PROTOTIPO[frase] = await embedder(frase)
            score = _coseno(v_texto, _CACHE_VECTORES_PROTOTIPO[frase])
            if score > afinidad:
                mejor, afinidad = slug, score
    if afinidad < umbral:
        return {"comando": None, "afinidad": afinidad}
    return {"comando": mejor, "afinidad": afinidad}
