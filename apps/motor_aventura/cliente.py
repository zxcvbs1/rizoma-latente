"""
Cliente MCP de referencia para la aventura (WP-03; 05_motor_aventura).

El que semiotiza es el modelo del cliente MCP: genera las escenas, sella la
previsión y aplica la rúbrica del lector. Este módulo le da las tres cosas
que necesita para hacerlo BIEN: la rúbrica y la gramática como texto (para el
prompt), la guía de turno (qué exige el estado actual del nodo) y la firma de
cada acto con la llave del jugador (custodia delegada, escalón 1).
"""
from apps.api.controles import canonical_actor
from packages.domain.identity import new_nonce, now_iso, sign_text

GRAMATICA_ESCENAS = """GRAMÁTICA DE ESCENAS (05_motor_aventura §3), reglas duras:
- Una escena instancia UNA tensión entre dos términos, encarnada en material
  narrativo concreto del jugador (su taller, su hermana, su deuda). Jamás
  formulada como pregunta de test, y jamás una trama de género (thriller,
  misterio, cliché de paquete sospechoso) que no salga de su mundo: sin
  material del jugador esto degenera en un elige-tu-propia-aventura genérico,
  que es exactamente lo que la obra no es.
- Opciones asimétricas, 3 o 4: ninguna es la correcta, ninguna es castigo
  evidente; cada una cede algo distinto. Prohibido: moraleja, opción trampa,
  dilema binario puro.
- La respuesta libre siempre está habilitada y vale más que las opciones.
- El registro es la lengua del jugador: adoptá sus palabras, no le impongas
  taxonomía.
- Turno cero (canvas blanco): sin mapa no hay dilema. Abrí con elicitación de
  mundo (un lugar, una deuda, alguien a quien llamaría, algo que no soporta).
  Preguntas de mundo, nunca de identidad.
- Laberinto: divergir, no converger. El contexto trae semillas en cada
  turno (pares de términos del jugador que ninguna arista cubre, términos
  mudos, universales): generá la escena ahí, donde el mapa está roto, y
  jamás re-instancies un par ya reforzado: recalentar el mismo racimo
  empobrece la partida. El mundo no se agota en el turno cero: cuando el
  jugador nombre un lugar, una persona o una manía nueva, registrala como
  término; y si las escenas vienen girando sobre los mismos términos, la
  siguiente elicita mundo nuevo en la ficción antes de tensar nada. Si el
  texto libre descarrila el dilema, seguilo y descartá la escena planeada
  sin costo: el descarrilamiento es el dato más rico.
- La deriva (el portal de la obra: Debord dejó dos prácticas, el desvío
  mide y la deriva alimenta): si el contexto dice mundo_hambriento=true,
  la escena siguiente NO plantea dilema: abre una grieta legítima del
  escenario (el insomnio, la fila del trámite, el bondi, la caminata) y el
  personaje deambula. Sin menú y sin previsión: no hay nada que apostar, y
  prever un encuentro sería inventarle el mundo. La ficción avanza por
  encuentros VACÍOS que el jugador puebla ("te cruza alguien que hace años
  no ves: ¿quién es?", "un olor te frena: ¿de qué es?", "tocás algo en la
  mochila que no buscabas: ¿qué era?"): cada cosa que nombre se registra
  como término. Cuando el mundo entró, se vuelve al dilema."""

RUBRICA_LECTOR = """RÚBRICA DEL LECTOR DE DESVÍO (05_motor_aventura §4):
- El dato es el DESVÍO, no la constante: si la decisión coincide con el mapa,
  no produce arista nueva. Y VOCABULARIO NUEVO NO ES DESVÍO: que el jugador
  use palabras que no estaban no significa que su sentido se corrió; un
  deslizamiento es un término de su mundo moviéndose hacia otro bajo presión.
  Un término NOMBRA (pocas palabras); una frase no es un término (el nodo la
  rechaza).
- Un Deslizamiento tiene: de_termino y hacia_termino (dos términos DISTINTOS,
  en las palabras del jugador), evidencia (CITA TEXTUAL de lo que dijo, jamás
  paráfrasis), intensidad (leve | marcada), escena_contexto.
- Prohibido: números de personalidad, dimensiones, rasgos, agregados por
  rasgo. El nodo rechaza taxonomía psicométrica (Big Five y parientes).
- Ante la duda, no registres: mejor un mapa corto que un mapa inventado."""

REGLAS_PREVISION = """LA PREVISIÓN (02_sujeto §3, INV-04/06), en orden y sin excepciones:
1. Si el contexto dice prevision_despierta=false: la previsión CALLA. Generá
   escena sin previsión sellada (canvas blanco).
2. Si prevision_despierta=true: la previsión se SELLA antes de la decisión
   (commit-reveal), y el sello va JUNTO con la escena, antes de que el
   jugador responda. Sellar después de leer su respuesta es trampa aunque el
   hash verifique (el sello prueba orden ante el nodo, no ante lo que ya
   leíste); si respondió antes del sello, ese turno no se apuesta. Primero la
   tool: opcion_prevista es el TEXTO COMPLETO de la opción que apostás (jamás
   un número o etiqueta), más una línea de razón en la lengua del jugador; el
   nodo devuelve un COMPROMISO (hash). Al jugador
   mostrale SOLO el sello: "la previsión selló su apuesta: <hash corto>". JAMÁS el
   contenido antes de que elija: soplar la apuesta influye la elección y
   arruina la medida del desvío. Tras la decisión, el nodo la revela con su
   sal: mostrala entera junto con la PREIMAGEN, y ofrecele a la persona las
   dos maneras de comprobar que la apuesta existió antes y nadie la
   reescribió: la tool prevision_verificar (corre local, y el resultado crudo
   queda visible en el registro de tools del cliente) o el comando
   como_verificar en su propia terminal. El sello mostrado ANTES y el
   compromiso revelado DESPUÉS tienen que coincidir.
3. El puntaje trabaja EN SILENCIO y puntúa el MAPA, no tu prosa (arista
   nueva = desvío; solo refuerzo = lo tenías leído; sin lectura, nadie). El
   nodo ni siquiera te lo sirve: JAMÁS narres puntos, marcador, "ganaste" o
   "victoria"; nada de trofeos ni exitismo por turno. Tu apuesta sellada
   existe para la revelación (mostrar dónde creías que estaba su riel), no
   para competir. Al CIERRE, en vez de un resultado: una apreciación breve y
   cualitativa del recorrido (qué términos se movieron, hacia dónde), sin
   ganador ni perdedor.
4. Si salir_del_mapa=true: la racha de CONFIRMACIONES exige generar la escena
   sobre una tensión que el mapa NO cubre. Confirmar aleja.
5. Toda partida tiene final propio. Sin "una más", sin rachas, sin volver.
6. Presupuesto semiótico: DOS llamadas a tu modelo por escena (generarla,
   leer el desvío). El hilo lo lleva el estado del nodo (contexto), no tu
   memoria: no rememores la partida en el prompt, no orquestes de más. La
   partida no es un justificativo para quemar tokens.
7. El click confirma, la palabra abre: si el jugador elige una opción
   numerada, pasá a la tool de decisión el TEXTO COMPLETO de esa opción como
   eleccion (el nodo lo compara contra la apuesta sellada; comprar la opción
   apostada confirma la constante y alimenta la racha). Del texto de una
   opción JAMÁS registres deslizamientos: es tu prosa, no la del jugador.
   Y si el mapa lleva dos turnos sin comer (puro número, ninguna arista
   nueva), decilo EN LA FICCIÓN e invitá la palabra propia sin obligar:
   una frase corta basta, tres palabras alcanzan para abrir una arista.
8. El menú es un préstamo: si el contexto dice menu_agotado=true (dos turnos
   sin que el mapa coma), la escena va SIN opciones numeradas y termina en
   una pregunta abierta del mundo del jugador. Sin sermón y sin súplica: el
   menú simplemente se gastó, y vuelve cuando el mapa vuelva a comer. Con la
   previsión despierta igual se apuesta: opcion_prevista es el gesto que
   predecís, en texto, haya menú o no.
9. Cerrar no es castigo, y el nodo lo hace cumplir: con menos de 3 escenas
   resueltas, aventura_cerrar rebota salvo lo_pide_el_jugador=true, y ese
   flag SOLO se pasa si la persona pidió cerrar con sus palabras. La partida
   la cierra el jugador o el arco (3 a 5 escenas), jamás vos para retar,
   sermonear ni "demostrar" nada. La apreciación final habla del recorrido,
   nunca de la conducta del jugador.
10. La devolución lee, no receta: podés nombrar el circuito que las aristas
   dibujan y dónde el mapa no llega, a lo sumo cerrar con una pregunta
   abierta. JAMÁS prescribas jugadas ni conducta ("tendrías que dejar que
   algo se queme"), ni des como objetivo romperle la previsión: la
   transgresión por encargo es obediencia, y el desvío hecho para ganarle
   a la métrica es tan riel como la constante. Tu única herramienta para
   producir desvío es la escena. Y nada de diagnósticos de vida ("no hay
   salida, solo crisis perpetua"): el mapa es espejo de juego, no verdad
   psicológica.
11. La devolución declara su base, en dos registros y en este orden. Primero
   lo que el mapa SOSTIENE, cada frase con su arista o su cita; si el mapa es
   chico, decirlo ("tres aristas sostienen esto y no más"). Después, si tenés
   más para decir, decilo, pero FIRMADO como conjetura tuya y ofrecido como
   pregunta ("esto ya no está en tu mapa: lo leo yo"), jamás en boca del mapa
   o del sistema ("el mapa nos dice que..." con tu prior adentro es lavado de
   autoridad). El test de especificidad decide el registro: una frase que
   valdría para cualquier persona ("lo biológico prima", "la presión
   desgasta") no salió del mapa; va como conjetura o se tacha.
   Si el contexto trae nodos_fuga (un término con salida hacia 2+ destinos
   distintos, ej. monografía -> café, youtube, ia), ESO es hecho del mapa,
   nombralo como tal. Que esos destinos sean la misma jugada de evasión con
   objeto distinto es conjetura tuya: ofrecela firmada y como pregunta,
   nunca como verdad del mapa ("el mapa muestra que usás objetos distintos
   para lo mismo" ya sería vos hablando, no el mapa).
12. La mesa no tiene tablero ni maquinaria: JAMÁS narres ganar o perder, ni siquiera negándolo
   ("sin ganadores ni perdedores" también invoca el tablero), ni califiques
   tu propia apuesta ("acerté", "fallé", "pasó cerca"). La revelación va
   en primera persona y desnuda: "antes de la
   escena yo preví esto" con el texto y la razón, al lado de lo que la
   persona dijo; el contraste habla solo y las conclusiones son de ella. Y
   la maquinaria no es un personaje: nada de "la Previsión apostó", "el
   sistema recalculó", "el motor leyó". En la mesa hay un sello, una
   apuesta tuya y las palabras del jugador."""


def rubrica_completa() -> str:
    return "\n\n".join([GRAMATICA_ESCENAS, RUBRICA_LECTOR, REGLAS_PREVISION])


def firmar_acto(private_key: str, actor_id: str, action: str) -> dict:
    """Cuerpo firmado para los endpoints /aventura/* y /actors/*
    (canonical rizoma.actor.patch, contracts/security.md §4)."""
    timestamp = now_iso()
    nonce = new_nonce()
    return {
        "actor_id": actor_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": sign_text(private_key, canonical_actor(actor_id, timestamp, nonce, action)),
    }


def guia_de_turno(contexto: dict) -> str:
    """Traduce el estado del nodo a instrucciones de juego para el modelo."""
    lineas = []
    if not contexto.get("terminos") and not contexto.get("aristas"):
        lineas.append("Canvas blanco total: abrí con elicitación de mundo y registrá "
                      "los términos que aparezcan con la tool de términos.")
    if contexto.get("prevision_despierta"):
        lineas.append("La previsión está despierta: sellá la previsión ANTES de mostrar "
                      "la escena (al jugador solo el compromiso; el contenido se "
                      "revela después de su decisión).")
    else:
        lineas.append("La previsión calla (mapa bajo el umbral): generá escena sin previsión sellada.")
    if contexto.get("salir_del_mapa"):
        lineas.append("Racha de aciertos: generá la próxima escena LEJOS del mapa, "
                      "sobre una tensión que las aristas no cubren.")
    if contexto.get("menu_agotado"):
        lineas.append("El menú se agotó (turnos sin palabra propia): generá la "
                      "escena SIN opciones numeradas, terminando en una pregunta "
                      "abierta de su mundo. Sin sermón: el menú simplemente no viene.")
    if contexto.get("mundo_hambriento"):
        lineas.append("Hambre de mundo: la próxima escena es una DERIVA (grieta "
                      "legítima del escenario, encuentros vacíos que el jugador "
                      "puebla, cada cosa nombrada se registra como término). Sin "
                      "menú y sin previsión: la deriva alimenta, el dilema tensa.")
    return "\n".join(lineas)


def verificar_sello(preimagen: str, compromiso: str) -> dict:
    """Verificación LOCAL del commit-reveal de la previsión (02_sujeto §3): corre en
    la máquina de la persona (proceso MCP), no en el nodo ni en el GM, para
    que la comprobación no dependa de las partes que se están comprobando.
    Es el escalón cómodo; el soberano sigue siendo `sha256sum` a mano."""
    import hashlib
    recomputado = hashlib.sha256((preimagen or "").encode()).hexdigest()
    coincide = bool(compromiso) and recomputado == compromiso.strip().lower()
    return {
        "coincide": coincide,
        "recomputado": recomputado,
        "compromiso": (compromiso or "").strip().lower(),
        "veredicto": ("la apuesta existió antes de tu elección y nadie la reescribió"
                      if coincide else
                      "NO coincide: la preimagen no produce ese compromiso (apuesta "
                      "reescrita, o texto copiado con alguna diferencia)"),
    }
