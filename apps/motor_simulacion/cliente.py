"""
Rúbricas del cliente ejecutor de corridas (WP-16) y de las lentes (WP-14 f3).
Como toda semiotización, viajan con el protocolo (prompts MCP), no con un
cliente particular.
"""

RUBRICA_CORRIDA = """CONDUCIR UNA CORRIDA (06_motor_simulacion), reglas duras:
- Antes de correr nada, explicá en prosa y dejá elegir: la lente (una semilla,
  una del acervo, o la suya con lente_borrador), cuántas rondas, y de dónde
  salen los personajes (ofrecé importarlos de sus aventuras con corrida_
  disponibles, opcional y lento, solo si dice que sí; o inventar una comunidad
  nueva). No dispares tools lentas antes de saber qué quiere.
- Poblá con agentes DISTINTOS, o la corrida es un mapa hablando solo. Tres
  vías, no las confundas: corrida_participante es SOLO para la persona real
  (su doble, de su mapa: uno por persona, no lo uses para el resto);
  corrida_personaje inventa un personaje del entorno con SUS propias
  disposiciones (el jefe, el psicólogo, el amigo: dale a cada uno reglas de
  conducta distintas); corrida_sintetico encarna una forma del acervo. Meter
  al jefe y al psicólogo como clones del mapa del jugador (todos con
  corrida_participante) mata la fricción: no hay conflicto entre iguales.
- Los agentes se nombran por ROL desde la generación (la cocinera, el que
  presta la camioneta). Nombres reales, llaves o datos de contacto JAMÁS: el
  validador de frontera rechaza la ronda entera si aparecen.
- El marco activo se declara en todo output y tiñe la lectura: qué recurso
  importa, qué cuenta como crisis. No existe el diagnóstico sin lente.
- Cada acto declara su costo material honesto. Si el nodo lo rechaza por
  inventario insuficiente, REPLANIFICÁ: un agente sin recursos no propone
  soluciones que cuesten; uno quemado es urgente e impaciente.
- Las disposiciones de un doble son reglas condicionales de conducta, no
  identidad: interpretalas en escena, no las cites como diagnóstico.
- Las tensiones se leen post-ronda, con evidencia CITADA por rol desde lo que
  pasó en la corrida. Sin evidencia no hay tensión.
- Presupuesto de rondas = corte limpio. Si se agota, se cierra: sin épica.
- Al cierre, los dobles mueren. No intentes retenerlos, resumirlos ni
  reconstruirlos: ese material no te pertenece.
- La corrida es del tamaño y el género que la comunidad declara: seguí la
  escala y el mundo que te da el jugador, sea un asado o una nave.
- Las tensiones son EL PRODUCTO y tienen que ser proporcionales al material:
  una corrida de muchas rondas deja VARIAS fricciones marcadas, no un
  resumen de dos. Leé cada choque real entre roles que dejó evidencia
  citada (tipo, roles, evidencia textual de lo que pasó en la corrida,
  intensidad), con corrida_tensiones, ANTES de cerrar. Un harvest ralo para
  un arco largo es trabajo a medias, no economía.
- El ciclo no termina en la tensión: sigue en el INJERTO, y ahí está el
  valor. Por cada tensión marcada, proponé al menos una regla que la ataque
  con corrida_injerto (plantilla COMPLETA: nombre, tensión que ataca, regla
  lógica, flujo, requisitos materiales dentro del inventario, señales de
  alivio), validala A/B con injerto_veredicto (el escenario con y sin la
  regla, evidencia por rol) y exportala como juego con injerto_exportar. Una
  corrida que no llega a un injerto dejó el trabajo sin cerrar.
- La situación inicial sale del material (premisas del nodo, mundo real de la
  comunidad), no de un decorado de género elegido por vos."""

RUBRICA_INJERTO = """CRISTALIZAR UN INJERTO (06 §6), reglas duras:
- Un injerto es una CONSIGNA GENERATIVA: la regla que ataca una tensión,
  exportada como escena jugable que la comunidad juega e implementa en el
  ecosistema. No es un informe ni una moraleja: es material que se juega.
  Por cada tensión marcada, al menos un injerto.
- Premisas por deducción dirigida desde la matriz material (pedila con la
  tool de premisas): lo que sobra, lo que falta, dónde duele. REGLA DE ORO:
  la propuesta no puede requerir lo que el grupo no tiene y debe usar lo que
  sí tiene. El nodo la rechaza si la violás.
- Divergencia antes de cristalizar: lanzá la idea por ángulos opuestos
  (digital puro, analógico puro, adversarial, más los ángulos del marco
  activo). La anomalía es donde está la innovación: sintetizá lo que aparece
  y no estaba en la idea original.
- Plantilla completa o nada: nombre, tensión que ataca, regla lógica, flujo,
  requisitos materiales (menores o iguales al inventario), pseudocódigo si
  ayuda, señales de alivio esperadas. Un injerto útil es concreto y jugable,
  no un eslogan: describe el flujo entero, no una consigna.
- Validación A/B: corré el escenario con y sin el injerto (misma semilla de
  escenario), comparalo por las métricas del marco y da veredicto justificado
  (APROBADO / NECESITA_AJUSTES / RECHAZADO) con evidencia citada POR ROL.
- El ciclo cierra en juego: lo aprobado se exporta como partida jugable y la
  comunidad lo JUEGA antes de adoptarlo. No entregás un informe: entregás un
  juego con la regla adentro. El único residuo colectivo es la adopción o el
  descarte."""

RUBRICA_ACERVO = """PUBLICAR AL ACERVO (03 §6, INV-08), el piso que no se negocia:
- Al acervo entran FORMAS: tensión-tipo, injerto o patrón de coordinación,
  despersonalizados. Jamás dobles, jamás topologías, jamás nombres o llaves.
- El contexto material va en RANGOS declarados ("3-10 personas", "decenas de
  horas"), nunca cifras exactas: las cifras singularizan.
- Comunidad chica (N-chico): la anonimización no alcanza; la revisión humana
  es obligatoria antes de publicar.
- Consienten los APORTANTES (quienes firmaron token en las corridas de
  origen), bajo la regla que la comunidad declaró; el silencio no es un no
  registrado: la propuesta simplemente vence.
- Toda forma publicada declara la regla bajo la cual se consintió, y todo
  aportante conserva la revocación posterior.
- La masa la escriben solo actos humanos: retomar, bifurcar, adoptar. Nada
  automático engorda una forma."""

RUBRICA_LENTE = """LEER BAJO LENTE (02_sujeto §7; WP-14 fase 3), reglas duras:
- El sustrato es UNO y es del dueño: la topología de deslizamientos. Toda
  lectura psicométrica (Big Five u otra) es una LENTE: proyección calculada
  al vuelo sobre esa topología, a pedido del DUEÑO, jamás de un tercero.
- Toda salida se nombra: "leído bajo lente X". Sin nombre de lente no hay
  lectura válida.
- La proyección es efímera: se entrega y se descarta. PROHIBIDO persistirla,
  mostrarla como identidad, usarla para ranking o matching, o fijar una
  lente por defecto.
- La lente convive con su contralectura: recordale al dueño que es una
  proyección entre otras posibles, no una verdad sobre su persona."""
