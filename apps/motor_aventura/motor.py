"""
Motor de aventura, mitad NODO (WP-03 previsión + WP-14 sustrato; 05_motor_aventura).

El motor es el par: el CLIENTE MCP del jugador semiotiza (genera escenas,
predice, aplica la rúbrica del lector); este módulo es el nodo: valida,
persiste lo único persistible (términos y Deslizamientos) y hace cumplir la
retención POR CONSTRUCCIÓN (INV-04): predicciones, marcador y memoria de
partida viven en memoria de proceso y mueren con la partida. Las tablas no
tienen columnas donde guardarlos.
"""
import hashlib
import math
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from packages.domain.models import Base, Deslizamiento, Forma, Partida, TerminoMapa

MAPA_MINIMO_PREVISION = 5   # nodo.toml [umbrales] mapa_minimo_prevision
APUESTA_RACHA = 3      # confirmaciones seguidas que curvan el laberinto fuera del mapa
MENU_AGOTADO_TURNOS = 2  # turnos sin palabra propia antes de que el menú se gaste
ARCO_MINIMO_ESCENAS = 3  # cerrar antes es solo del jugador, jamás del GM
VENTANA_MAPA = 40  # aristas/términos servidos al GM por turno (el archivo entero sigue en el mapa del dueño)

# Ninguna salida del motor contiene taxonomía psicométrica (05 §9, WP-14).
TAXONOMIA_PROHIBIDA = {
    "apertura", "responsabilidad", "extraversion", "extraversión", "amabilidad",
    "neuroticismo", "openness", "conscientiousness", "extraversion",
    "agreeableness", "neuroticism", "big five", "big5",
}

# Columnas que, si algún refactor las agregara, volverían persistible el mal
# alimento. La auditoría falla ante cualquiera de estos nombres.
COLUMNAS_PROHIBIDAS = {"prediccion", "predicciones", "marcador", "transcript",
                       "eleccion", "elecciones", "acierto", "aciertos",
                       "doble", "dobles", "token", "tokens", "topologia",
                       "disposiciones",
                       # el pedido delegado es tránsito, no dato (09 §2.6/§5):
                       "pedido", "pedidos", "prompt", "prompts"}


class MotorError(Exception):
    pass


@dataclass
class MemoriaPartida:
    """Todo lo efímero de una partida. Muere con ella; jamás toca un store."""
    predicciones: dict = field(default_factory=dict)   # escena_id -> (opcion, razon)
    marcador: dict = field(default_factory=lambda: {"jugador": 0, "sistema": 0})
    aciertos_seguidos: int = 0
    mundo: dict = field(default_factory=dict)          # continuidad narrativa efímera
    turnos_sin_comer: int = 0  # turnos seguidos sin palabra propia (el menú es un préstamo)
    escenas_resueltas: int = 0  # el arco de la partida (cerrar no es castigo)
    terminos_nuevos: int = 0  # términos que esta partida le sumó al mapa (hambre de mundo)


_memorias: dict[str, MemoriaPartida] = {}


def _uid() -> str:
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


def _aristas_de(db, jugador: str):
    return [d for d in db.query(Deslizamiento).all()
            if (d.jugador_llave or "").lower() == jugador.lower()]


def _terminos_de(db, jugador: str):
    return [t for t in db.query(TerminoMapa).all()
            if (t.jugador_llave or "").lower() == jugador.lower()]


def _aware(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _vivas(filas):
    """Solo lo que el olvido no apagó (masa > 0), del más pesado al más
    reciente. El conjunto de TRABAJO que se sirve al GM: el archivo completo
    sigue entero en el mapa del dueño (mapa_ver, huella, devolución)."""
    vivas = [f for f in filas if (f.mass or 0) > 0]
    vivas.sort(key=lambda f: ((f.mass or 0), _aware(f.last_touched) or _aware(f.created_at)
                              or datetime.min.replace(tzinfo=timezone.utc)),
               reverse=True)
    return vivas[:VENTANA_MAPA]


def iniciar_partida(db, jugador: str, marco: str | None = None) -> Partida:
    partida = Partida(id=_uid(), jugador_llave=jugador, estado="abierta", marco=marco)
    db.add(partida)
    db.flush()
    _memorias[partida.id] = MemoriaPartida()
    return partida


def _partida_abierta(db, partida_id: str) -> Partida:
    partida = db.query(Partida).filter(Partida.id == partida_id).first()
    if not partida or partida.estado != "abierta":
        raise MotorError("partida inexistente o cerrada")
    if partida_id not in _memorias:
        _memorias[partida_id] = MemoriaPartida()
    return partida


def registrar_terminos(db, partida_id: str, terminos, origen_escena: str | None = None):
    """Canvas blanco (05 §2.1): los términos entran con las palabras del
    jugador, sin normalizar a taxonomía alguna."""
    partida = _partida_abierta(db, partida_id)
    memoria = _memorias[partida_id]
    existentes = {t.termino.lower() for t in _terminos_de(db, partida.jugador_llave)}
    creados = []
    for termino in terminos or []:
        termino = (termino or "").strip()
        if not termino:
            continue
        if termino.lower() in TAXONOMIA_PROHIBIDA:
            raise MotorError(f"taxonomía psicométrica rechazada: {termino}")
        # Un término NOMBRA algo del mundo del jugador ("el desorden", "mi
        # taller"); una frase entera es contaminación cartográfica (playtest
        # jul 2026: el mapa se llenó de fragmentos de oración).
        if len(termino.split()) > 5:
            raise MotorError(
                f"un término nombra algo en pocas palabras, no es una frase: {termino!r}")
        db.add(TerminoMapa(id=_uid(), jugador_llave=partida.jugador_llave,
                           termino=termino, origen_escena=origen_escena))
        creados.append(termino)
        if termino.lower() not in existentes:
            memoria.terminos_nuevos += 1
            existentes.add(termino.lower())
    db.flush()
    return creados


def contexto_turno(db, partida_id: str) -> dict:
    """Lo único que el nodo entrega al cliente: el mapa PROPIO del jugador y la
    memoria de ESTA partida (INV-17). El mapa de un tercero, jamás."""
    partida = _partida_abierta(db, partida_id)
    memoria = _memorias[partida_id]
    # El mapa COMPLETO manda en los umbrales (INV-06: tiene que contar igual
    # que el gate de resolver_decision, o el juego se traba); lo que se SIRVE
    # al GM es el conjunto de trabajo, vivo y acotado por ventana (masa > 0).
    aristas = _aristas_de(db, partida.jugador_llave)
    aristas_vivas = _vivas(aristas)
    # El mapa dice dónde está roto (05 §2): las semillas viajan en cada
    # turno para que la escena no recaliente pares ya reforzados.
    sem = semillas(db, partida_id)
    return {
        "jugador": partida.jugador_llave,
        "marco": partida.marco,
        "terminos": [t.termino for t in _vivas(_terminos_de(db, partida.jugador_llave))],
        "aristas": [{"de": d.de_termino, "hacia": d.hacia_termino,
                     "evidencia": d.evidencia, "escena": d.escena_contexto}
                    for d in aristas_vivas],
        "prevision_despierta": len(aristas) >= MAPA_MINIMO_PREVISION,
        "salir_del_mapa": memoria.aciertos_seguidos >= APUESTA_RACHA,
        # El marcador NO se sirve (corrección jul 2026): puntúa en silencio,
        # solo alimenta la racha que curva el laberinto. Narrarlo por turno
        # era exitismo superfluo; lo que el GM necesita es salir_del_mapa.
        # El menú es un préstamo: con turnos sin palabra propia, la escena
        # siguiente va SIN opciones numeradas (pregunta abierta). No es
        # sanción: comprar el menú consume el menú; vuelve cuando el mapa come.
        "menu_agotado": memoria.turnos_sin_comer >= MENU_AGOTADO_TURNOS,
        "semillas": {k: sem[k] for k in
                     ("universales", "terminos_mudos", "pares_no_cubiertos", "del_comun",
                      "nodos_fuga")},
        # Hambre de mundo (la deriva, 05 §2): sin términos nuevos el mapa
        # solo recombina su propio racimo; la escena siguiente abre
        # territorio en vez de tensar lo ya escrito.
        "mundo_hambriento": (
            (memoria.escenas_resueltas >= 2 and memoria.terminos_nuevos == 0)
            or (memoria.escenas_resueltas == 0 and memoria.terminos_nuevos == 0
                and len(aristas) >= MAPA_MINIMO_PREVISION)),
        "mundo": dict(memoria.mundo),
    }


def prever(db, partida_id: str, escena_id: str, opcion_prevista: str, razon: str) -> dict:
    """La previsión (INV-04/06): la previsión se SELLA antes de la decisión
    (commit-reveal). El nodo es el escribano: guarda la apuesta en la memoria
    de partida y devuelve SOLO el compromiso (hash + fórmula). Mostrarla
    legible antes de elegir soplaría la respuesta e invalidaría la métrica
    del desvío (el jugador contradiría gratis). Se revela ENTERA al resolver
    la decisión, con la sal, para que cualquiera verifique que la apuesta
    existió antes y no se reescribió. En el canvas blanco la previsión calla."""
    partida = _partida_abierta(db, partida_id)
    if len(_aristas_de(db, partida.jugador_llave)) < MAPA_MINIMO_PREVISION:
        raise MotorError("la previsión calla en el canvas blanco (mapa bajo el umbral)")
    # La apuesta es TEXTO (la formulación de la opción), jamás una etiqueta:
    # "1" no se puede comparar semánticamente con una respuesta libre.
    texto_apuesta = (opcion_prevista or "").strip()
    if len(texto_apuesta) < 3 or "_" in texto_apuesta or len(texto_apuesta.split()) < 2:
        raise MotorError("la apuesta se sella con el texto de la opción, no una etiqueta")
    memoria = _memorias[partida_id]
    sal = secrets.token_hex(8)
    compromiso = hashlib.sha256(
        f"{escena_id}|{opcion_prevista}|{razon}|{sal}".encode()).hexdigest()
    memoria.predicciones[escena_id] = (opcion_prevista, razon, sal, compromiso)
    return {"compromiso": compromiso,
            "formula": "sha256(escena_id|opcion_prevista|razon|sal)",
            "sellada": True}


def validar_deslizamiento(payload: dict) -> dict:
    """Validador de esquema del nodo: términos del jugador, evidencia como cita
    textual, sin taxonomía. Devuelve el deslizamiento limpio o levanta."""
    de = (payload.get("de_termino") or "").strip()
    hacia = (payload.get("hacia_termino") or "").strip()
    evidencia = (payload.get("evidencia") or "").strip()
    intensidad = payload.get("intensidad") or "leve"
    if not de or not hacia or de.lower() == hacia.lower():
        raise MotorError("un deslizamiento exige dos términos distintos")
    if len(evidencia) < 3:
        raise MotorError("sin cita textual no hay evidencia")
    if intensidad not in ("leve", "marcada"):
        raise MotorError("intensidad inválida")
    for termino in (de, hacia):
        if termino.lower() in TAXONOMIA_PROHIBIDA:
            raise MotorError(f"taxonomía psicométrica rechazada: {termino}")
        if len(termino.split()) > 5:
            raise MotorError(
                f"un término nombra algo en pocas palabras, no es una frase: {termino!r}")
    return {"de_termino": de, "hacia_termino": hacia, "evidencia": evidencia,
            "intensidad": intensidad, "escena_contexto": payload.get("escena_contexto")}


def _coseno(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def validador_vectorial(vec_evidencia, vec_de, vec_hacia, piso: float = 0.15) -> bool:
    """Señal vectorial local (05 §4): la evidencia tiene que sonar cerca de los
    DOS términos del deslizamiento; si no, la lectura del cliente no pasa."""
    return (_coseno(vec_evidencia, vec_de) >= piso
            and _coseno(vec_evidencia, vec_hacia) >= piso)


def _norma_opcion(texto: str) -> str:
    """Comparación de opción comprada contra apuesta sellada: minúsculas y
    espacios colapsados, nada más (el GM escribió los dos textos)."""
    return " ".join((texto or "").lower().split())


def resolver_decision(db, partida_id: str, escena_id: str, eleccion: str,
                      deslizamientos=None, vectores=None) -> dict:
    """Cierre de turno. Marcador invertido (INV-06): abrir arista nueva es
    victoria del jugador; confirmar el mapa sube la apuesta y curva el
    laberinto fuera de él. Lo ÚNICO que persiste son los Deslizamientos.

    Puntaje por MAPA (corrección jul 2026, del playtest de Gabriel): comparar
    prosas resultó fútil (toda respuesta comparte el vocabulario de su escena;
    dos gestos opuestos daban ~0.7 de coseno). El árbitro es el mapa mismo,
    que ya valida con cita y campo vectorial: si la decisión ABRE una arista
    nueva, el jugador se desvió (punto suyo); si SOLO REFUERZA aristas que ya
    existían, el sistema lo tenía leído (punto del sistema); sin lectura, no
    puntúa nadie. La apuesta sellada conserva sus dos roles reales: honestidad
    (commit-reveal verificable) y dramaturgia (mostrar dónde creía el sistema
    que estaba el riel).

    Cuarta corrección (el click confirma): si la elección coincide con la
    opción apostada, confirmación del sistema sin tocar el mapa; el jugador
    de números no congela el juego, lo empuja fuera del mapa."""
    partida = _partida_abierta(db, partida_id)
    memoria = _memorias[partida_id]
    aristas_previas = _aristas_de(db, partida.jugador_llave)

    # INV-06 por construcción: con la previsión despierta, la decisión sin
    # previsión sellada ANTES para esta escena no existe.
    if len(aristas_previas) >= MAPA_MINIMO_PREVISION and escena_id not in memoria.predicciones:
        raise MotorError("el mapa ya alcanza para preverte: no hay decisión sin previsión sellada antes (INV-06)")

    resultado = {"prevision_sellada": False, "acierto_sistema": None,
                 "deslizamientos_persistidos": 0, "aristas_reforzadas": 0,
                 "salir_del_mapa": False}

    if escena_id in memoria.predicciones:
        opcion_prevista, razon, sal, compromiso = memoria.predicciones.pop(escena_id)
        resultado["prevision_sellada"] = True
        # Revelación (commit-reveal): el NODO devuelve lo que selló, con la
        # sal, para que el jugador verifique el compromiso mostrado antes.
        preimagen = f"{escena_id}|{opcion_prevista}|{razon}|{sal}"
        # La verificación tiene que ser de UNA persona, no de un programador:
        # comando listo para pegar TAL CUAL (shlex.quote: ninguna comilla ni
        # carácter raro de la razón lo rompe), con la nota aparte.
        import shlex
        resultado["revelacion"] = {
            "opcion_prevista": opcion_prevista, "razon": razon, "sal": sal,
            "compromiso": compromiso,
            "preimagen": preimagen,
            "como_verificar": f"printf %s {shlex.quote(preimagen)} | sha256sum",
            "nota": ("pegá el comando en tu terminal: el resultado debe coincidir "
                     "con el compromiso que viste ANTES de elegir; o pedile al "
                     "cliente la tool prevision_verificar (corre local)")}

    for crudo in deslizamientos or []:
        limpio = validar_deslizamiento(crudo)
        if vectores is not None:
            vecs = vectores(limpio)
            if not validador_vectorial(*vecs):
                raise MotorError("la evidencia no suena cerca de sus términos")
        # El dato es el desvío, no la constante: la arista repetida refuerza,
        # no duplica (05 §4).
        existente = next(
            (d for d in _aristas_de(db, partida.jugador_llave)
             if d.de_termino.lower() == limpio["de_termino"].lower()
             and d.hacia_termino.lower() == limpio["hacia_termino"].lower()),
            None)
        if existente:
            existente.mass = float(existente.mass or 0.0) + 1.0
            existente.last_touched = _ahora()
            resultado["aristas_reforzadas"] += 1
        else:
            db.add(Deslizamiento(id=_uid(), jugador_llave=partida.jugador_llave, **limpio))
            resultado["deslizamientos_persistidos"] += 1
    db.flush()

    memoria.escenas_resueltas += 1

    # El menú es un préstamo (corrección jul 2026, segunda del playtest a puro
    # número): un turno sin palabra propia gasta menú; el mapa comiendo lo repone.
    if resultado["deslizamientos_persistidos"] or resultado["aristas_reforzadas"]:
        memoria.turnos_sin_comer = 0
    else:
        memoria.turnos_sin_comer += 1

    # El puntaje sale del MAPA, no de la prosa (y solo con apuesta sellada):
    # arista nueva = desvío (jugador); solo refuerzo = confirmación (sistema);
    # sin lectura = nadie. La racha de confirmaciones curva el laberinto.
    if resultado["prevision_sellada"]:
        if resultado["deslizamientos_persistidos"] > 0:
            resultado["acierto_sistema"] = False
            memoria.marcador["jugador"] += 1
            memoria.aciertos_seguidos = 0
        elif resultado["aristas_reforzadas"] > 0:
            resultado["acierto_sistema"] = True
            memoria.marcador["sistema"] += 1
            memoria.aciertos_seguidos += 1
        elif _norma_opcion(eleccion) == _norma_opcion(opcion_prevista):
            # El click confirma, la palabra abre (corrección jul 2026, del
            # playtest a puro número): comprar la opción apostada es la
            # constante confirmada. No toca el mapa (ese texto es del GM,
            # no del jugador): solo alimenta la racha que curva el laberinto.
            resultado["acierto_sistema"] = True
            memoria.marcador["sistema"] += 1
            memoria.aciertos_seguidos += 1
        # sin lectura y sin opción comprada: acierto_sistema queda None

    resultado["salir_del_mapa"] = memoria.aciertos_seguidos >= APUESTA_RACHA
    resultado["marcador"] = dict(memoria.marcador)
    return resultado


SEMILLAS_UNIVERSALES = [("autonomía", "lazo"), ("cuidado", "control"), ("verdad", "lealtad")]


def semillas(db, partida_id: str) -> dict:
    """Fuentes de tensión para el cliente (05 §2): las universales, los
    términos nombrados que nunca deslizaron, y los pares del propio mapa que
    ninguna arista cubre. Divergir con criterio: buscar donde el mapa se
    rompe, no donde se confirma."""
    partida = _partida_abierta(db, partida_id)
    memoria = _memorias[partida_id]
    # Las semillas se buscan en el conjunto que vive (masa > 0, acotado por
    # ventana): generar la próxima escena dentro del mapa apagado no tiene
    # sentido de juego.
    terminos = [t.termino for t in _vivas(_terminos_de(db, partida.jugador_llave))]
    aristas = _vivas(_aristas_de(db, partida.jugador_llave))
    conectados = {(a.de_termino.lower(), a.hacia_termino.lower()) for a in aristas}
    con_salida = {a.de_termino.lower() for a in aristas}
    mudos = [t for t in terminos if t.lower() not in con_salida][:5]
    pares = []
    for i, a in enumerate(terminos):
        for b in terminos[i + 1:]:
            if ((a.lower(), b.lower()) not in conectados
                    and (b.lower(), a.lower()) not in conectados):
                pares.append(f"{a} / {b}")
    # Tercera fuente (05 §2.3, WP-20): tensiones-tipo del acervo común,
    # para encarnar en el material del jugador. Solo ids y nombres: el
    # linaje de forma es efímero y jamás se persiste en la partida.
    del_comun = [{"forma_id": f.id, "nombre": f.nombre}
                 for f in db.query(Forma).all()
                 if f.estado == "publicada" and f.tipo == "tension_tipo"][:5]
    # Nodos de fuga (corrección jul 2026, del playtest "la ia como atajo"):
    # un término de origen con 2+ destinos distintos es un HECHO del grafo
    # (grado de salida), no una interpretación. Si son la misma jugada de
    # evasión con objeto distinto es conjetura del lector, no del mapa.
    salidas_por_origen: dict[str, set[str]] = {}
    for a in aristas:
        origen = a.de_termino
        salidas_por_origen.setdefault(origen.lower(), set()).add(a.hacia_termino)
    nodos_fuga = [
        {"termino": next(a.de_termino for a in aristas if a.de_termino.lower() == origen_lower),
         "destinos": sorted(destinos)}
        for origen_lower, destinos in salidas_por_origen.items() if len(destinos) >= 2
    ][:5]
    return {
        "universales": [f"{x} / {y}" for x, y in SEMILLAS_UNIVERSALES],
        "terminos_mudos": mudos,
        "pares_no_cubiertos": pares[:5],
        "del_comun": del_comun,
        "salir_del_mapa": memoria.aciertos_seguidos >= APUESTA_RACHA,
        "nodos_fuga": nodos_fuga,
    }


def cerrar_partida(db, partida_id: str, lo_pide_el_jugador: bool = False) -> dict:
    """Toda partida tiene final propio (INV-13). Al cierre, la memoria muere:
    predicciones, marcador y mundo desaparecen. La devolución es el mapa
    legible, con los tres controles a un gesto (INV-05, vía WP-04). Con menos
    de 3 escenas resueltas, el cierre exige lo_pide_el_jugador=true (INV-13
    intacto: la persona siempre puede irse; las partidas abandonadas mueren
    solas por decay)."""
    partida = _partida_abierta(db, partida_id)

    # Cerrar no es castigo (corrección jul 2026, del playtest a puro número):
    # con la partida recién empezada, el cierre es SOLO del jugador. El GM que
    # pasa el flag sin que la persona lo haya pedido miente en un argumento
    # que queda visible en el registro de tools (mismo límite honesto que el
    # sello: el nodo no ve el chat, pero fuerza la afirmación explícita).
    memoria_previa = _memorias.get(partida_id)
    resueltas = memoria_previa.escenas_resueltas if memoria_previa else 0
    if resueltas < ARCO_MINIMO_ESCENAS and not lo_pide_el_jugador:
        raise MotorError(
            "la partida recién empieza (arco mínimo de 3 escenas): cerrar antes "
            "es solo del jugador; si la persona lo pidió con sus palabras, "
            "repetí con lo_pide_el_jugador=true")

    partida.estado = "cerrada"
    partida.closed_at = _ahora()
    _memorias.pop(partida_id, None)
    db.flush()
    aristas = _aristas_de(db, partida.jugador_llave)
    return {
        "partida": partida.id,
        "mapa": [{"de": d.de_termino, "hacia": d.hacia_termino,
                  "evidencia": d.evidencia, "escena": d.escena_contexto}
                 for d in aristas],
        "controles": ["ver", "llevarse", "borrar"],
    }


def auditar_mal_alimento(db) -> list:
    """CU-T5 en miniatura, para CI: nada de la lista prohibida puede existir.
    (a) Ninguna tabla tiene columnas capaces de retener predicciones, marcador
    o transcript; (b) ninguna partida cerrada conserva memoria viva; (c) ningún
    tránsito delegado sobrevive a su corrida (09 §2.6)."""
    hallazgos = []
    for tabla in Base.metadata.tables.values():
        for columna in tabla.columns:
            if columna.name.lower() in COLUMNAS_PROHIBIDAS:
                hallazgos.append(f"columna prohibida: {tabla.name}.{columna.name}")
    for partida in db.query(Partida).all():
        if partida.estado == "cerrada" and partida.id in _memorias:
            hallazgos.append(f"memoria viva de partida cerrada: {partida.id}")
    from apps.motor_simulacion import delegacion
    hallazgos.extend(delegacion.auditar_transito(db))
    return hallazgos
