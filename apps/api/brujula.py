"""
La brújula del nodo: el nombre REAL de cada familia de tools y su sentido.
Existe porque tres sesiones frías de un GM inventaron taxonomías sobre
prefijos opacos ("Mesa de Paz", "Mercados de Predicción"): todo vacío
semiótico lo llena el prior del modelo, y el prior viene empapado del
lenguaje de mercado. Acá no queda vacío.
"""

FAMILIAS = {
    "aventura_*": {
        "nombre": "La aventura (escala sujeto)",
        "que_es": ("el ciclo del sujeto: escenas desde el mundo del jugador, "
                   "mapa de deslizamientos, previsión sellada, deriva. El GM "
                   "conduce con la rúbrica (tool aventura_rubrica)"),
    },
    "sesion_*": {
        "nombre": "La sesión compartida (WP-25)",
        "que_es": ("ficción a varias voces con estado en el nodo: GM sorteado "
                   "y rotativo, validación cruzada, la ficción muere al cierre"),
    },
    "corrida_*": {
        "nombre": "La corrida (escala comunidad)",
        "que_es": ("una comunidad simulándose bajo una lente declarada: se "
                   "puebla con roles (dobles/sintéticos), Concordia conduce "
                   "por defecto, el producto son tensiones leídas e injertos "
                   "validados y jugados"),
    },
    "acervo_*": {
        "nombre": "El acervo (el común semiótico)",
        "que_es": ("formas despersonalizadas del común: tensiones-tipo, "
                   "rúbricas, lentes. Se proponen, se consienten, viven por "
                   "adopción y decaen sin uso, como la lengua"),
    },
    "pool_*": {
        "nombre": "El pool de cómputo del común (WP-23)",
        "que_es": ("tareas semióticas sobre material YA anónimo; quien tiene "
                   "fierro dona cómputo y gana peso que decae y no se "
                   "transfiere"),
    },
    "mapa_*": {
        "nombre": "Los controles del dueño (INV-05)",
        "que_es": "ver, llevarse o borrar TU mapa; nada oculto, todo tuyo",
    },
    "prevision_* / broadcast / buscar_federado": {
        "nombre": "Verificación y red",
        "que_es": ("verificar sellos localmente; emitir intenciones firmadas; "
                   "buscar en la federación mostrando divergencia sin "
                   "resolverla"),
    },
}

FAMILIAS["aventura_*"]["guia"] = "nodo_guia('aventura')"
FAMILIAS["sesion_*"]["guia"] = "nodo_guia('sesion')"
FAMILIAS["corrida_*"]["guia"] = "nodo_guia('corrida')"
FAMILIAS["acervo_*"]["guia"] = "nodo_guia('acervo')"
FAMILIAS["pool_*"]["guia"] = "nodo_guia('pool')"
FAMILIAS["prevision_* / broadcast / buscar_federado"]["guia"] = "nodo_guia('resonancias')"


def guia_de(familia: str) -> dict:
    """La guía COMPLETA de conducción de un módulo, servida como dato. El
    nombre pelado de una tool no documenta nada: esta es la dinámica entera,
    en orden, con lo que produce cada paso."""
    from apps.motor_simulacion import cliente as sim_cliente
    from apps.motor_aventura import cliente as av_cliente
    guias = {
        "aventura": av_cliente.rubrica_completa(),
        "corrida": (
            "EL CICLO COMPLETO DE UNA CORRIDA, en orden:\n"
            "0. PRIMERO EXPLICÁ Y PREGUNTÁ, en prosa, sin correr tools todavía "
            "(no dispares nada lento antes de saber qué quiere): una corrida se "
            "arma con tres decisiones suyas. (a) La lente: una semilla "
            "(bienes_comunes, cuidado, decrecimiento, colonialidad, capitales, "
            "economia_social), una publicada del acervo, o LA SUYA PROPIA "
            "(lente_borrador). (b) Cuántas rondas. (c) Los personajes: puede "
            "IMPORTARLOS de sus aventuras (ofrecele mostrarle qué hay con "
            "corrida_disponibles, pero SOLO si dice que sí: es opcional y "
            "tarda) o inventar una comunidad nueva. Presentá las tres y dejá "
            "que elija; recién ahí actuás.\n"
            "1. corrida_iniciar (marco semilla, lente publicada o lente_borrador).\n"
            "2. POBLAR con agentes DISTINTOS, tres vías (no las confundas): "
            "corrida_participante te mete a VOS como tu doble (tu propia llave "
            "por defecto; si corrés el MCP vos mismo sos operador y jugador a "
            "la vez, no hace falta scope aparte; jugador_scope solo si juega "
            "OTRA persona real), SOLO para personas reales, uno por persona; "
            "corrida_personaje inventa un personaje del entorno con SUS "
            "propias disposiciones (el jefe, el psicólogo, el amigo: cada uno "
            "con reglas de conducta distintas, jamás un clon tuyo); "
            "corrida_sintetico suma formas del acervo. Sin población no hay "
            "sociedad y la engine rebota; poblar el entorno entero con "
            "corrida_participante clona tu mapa y mata la fricción.\n"
            "3. corrida_premisas: la matriz material (lo que sobra, falta, duele).\n"
            "4. corrida_delegada: Concordia conduce (turnos=0 usa el arco entero); "
            "vos servís los pedidos con corrida_pedidos/corrida_responder, EN "
            "PERSONAJE, tercera persona, solo roles.\n"
            "5. corrida_tensiones: EL PRODUCTO. La lectura post-ronda con "
            "evidencia citada por rol. Sin esto la corrida no produjo nada.\n"
            "6. El ciclo de soluciones: corrida_injerto (la regla que ataca una "
            "tensión), injerto_veredicto (A/B), injerto_exportar (se vuelve "
            "juego), injerto_adopcion (el único residuo colectivo).\n"
            "7. corrida_cerrar: los dobles mueren; la cosecha se declara.\n\n"
            + sim_cliente.RUBRICA_CORRIDA + "\n\n" + sim_cliente.RUBRICA_INJERTO),
        "acervo": (
            "EL ACERVO, flujos:\n"
            "- Rúbrica o lente A MANO: acervo_proponer_rubrica -> "
            "acervo_consentir (tu propio sí; firma automática del keystore, "
            "jamás un script) -> acervo_publicar. Vive por adopción, decae "
            "sin uso.\n"
            "- Forma nacida de una corrida: acervo_proponer (con corrida "
            "abierta) -> consienten LOS APORTANTES (quienes pusieron carne) "
            "-> revisión humana si la comunidad es chica -> acervo_publicar.\n"
            "- Sobre lo publicado: acervo_cargar_rubrica (usar), "
            "acervo_bifurcar (torcer con linaje), acervo_retomar (mantener "
            "viva), acervo_revocar (despublicar sin decir quién).\n\n"
            + sim_cliente.RUBRICA_ACERVO),
        "sesion": (
            "LA SESIÓN COMPARTIDA (WP-25), en orden: sesion_abrir (opcional "
            "rúbrica-forma pública como GM común) -> sesion_entrar (cada uno, "
            "con_fierro si su cliente compone) -> sesion_sortear_gm (rotativo, "
            "no repite) -> sesion_estado (mirá lo dicho hasta ahora y el "
            "manual antes de componer: componer a ciegas no vale) -> "
            "sesion_componer (el sorteado propone el turno) -> sesion_validar "
            "(todos; un rechazo tumba) -> sesion_resolver (el turno entra al "
            "estado) -> repetir -> sesion_cerrar (la ficción muere; solo "
            "sobrevive el puente consentido). Es ensayo colectivo efímero. "
            "Para TESTEAR a varias voces desde una sola máquina: todas las "
            "sesion_* aceptan como='jugador:ana' / 'jugador:beto' (un scope "
            "de keystore por jugador de prueba); cada scope es una llave "
            "distinta y el sorteo y la validación cruzada funcionan de "
            "verdad, no simulados."),
        "pool": (
            "EL POOL DE CÓMPUTO (WP-23): pool_tareas (ver las abiertas) -> "
            "pool_tomar (reservarla) -> pool_resolver (tu propuesta se valida "
            "POR RESULTADO; si pasa, acredita peso que decae y no se "
            "transfiere; si no, sin castigo). Solo material ya anónimo: la "
            "frontera rechaza cualquier identidad."),
        "resonancias": (
            "CÓMO FUNCIONA LA RESONANCIA Y LA LENGUA (canon; citá esto, no lo "
            "reinventes):\n"
            "1. Una intención se emite FIRMADA (sin firma no entra al índice) y "
            "queda como sedimento con TTL renovable: la señal espera a su "
            "intérprete, semanas si hace falta (resonancia latente).\n"
            "2. La resonancia es una lectura LOCAL: cada nodo vectoriza con su "
            "embedder (el comando no viaja en el vector: se mide contenido, no el "
            "gesto de buscar) y sirve solo su lectura. La federación la arma el "
            "cliente consultando N nodos; la divergencia entre nodos se muestra, "
            "jamás se resuelve desde un centro. El emparejamiento ES esa lectura "
            "local: no existe otra instancia.\n"
            "3. La búsqueda tiene piso honesto (medido con el banco de "
            "comportamiento, no a ojo): por debajo del umbral no se fuerzan "
            "coincidencias; 'tu señal queda sembrada, esperando' es una respuesta "
            "legítima.\n"
            "4. La lengua vive por uso: cualquiera acuña un comando emitiendo con "
            "!palabra; cada emisión que lo porta le suma masa; sin uso decae y se "
            "olvida (el nodo sirve su vocabulario vivo en GET /vocabulario). La "
            "masa solo MIDE uso y decae: toda formalización de un patrón es un "
            "acto humano posterior (proponer, consentir, adoptar). El menú de un "
            "puente es comodidad, no gate.\n"
            "5. Del sentido a la regla, TODO acto humano y del cliente: si una "
            "comunidad quiere formalizar un patrón, un CLIENTE cristaliza el "
            "injerto (el nodo JAMÁS lo redacta: no tiene cerebro; valida plantilla, "
            "frontera y regla de oro), se valida A/B, se exporta como juego, la "
            "comunidad lo juega y decide su adopción: ese es el único residuo "
            "colectivo. El patrón cardinal, siempre: el cliente propone, el "
            "validador filtra, el humano confirma."),
    }
    if familia not in guias:
        return {"error": f"familia desconocida: {familia}",
                "familias": sorted(guias)}
    return {"familia": familia, "guia": guias[familia]}
