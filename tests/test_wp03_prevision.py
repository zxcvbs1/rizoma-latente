"""
WP-03 · La previsión, mitad nodo (INV-04, INV-06) + WP-14 · sustrato Deslizamiento.

La previsión se sella antes y jamás se persiste; el marcador es invertido y
muere con la partida; la apuesta crece con los aciertos; lo único que queda
en los stores son términos y Deslizamientos, sin taxonomía. La auditoría
corre sobre una base real (sqlite en memoria).

Corre sin servicios:
    .venv/bin/python tests/test_wp03_prevision.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_aventura import motor
from packages.domain.models import Deslizamiento, Forma, Partida, TerminoMapa

JUGADOR = "0x" + "c4" * 20
OTRA = "0x" + "d5" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Partida.__table__, TerminoMapa.__table__, Deslizamiento.__table__,
                  Forma.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def partida_con_mapa(db, n=motor.MAPA_MINIMO_PREVISION, jugador=JUGADOR):
    partida = motor.iniciar_partida(db, jugador)
    for i in range(n):
        motor.resolver_decision(db, partida.id, f"semilla-{i}", "x", deslizamientos=[{
            "de_termino": f"termino-{i}", "hacia_termino": f"deriva-{i}",
            "evidencia": f"yo dije tal cosa {i}"}])
    return partida


def test_canvas_blanco_prevision_muda():
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.registrar_terminos(db, partida.id, ["mi taller", "mi hermana", "la deuda"])
    contexto = motor.contexto_turno(db, partida.id)
    # El conjunto vivo (masa > 0) ordena por masa/recencia, no por inserción
    # (_vivas): lo que importa acá es QUÉ se sirve, no en qué orden.
    assert set(contexto["terminos"]) == {"mi taller", "mi hermana", "la deuda"}
    assert not contexto["prevision_despierta"], "sin aristas no hay apuesta honesta"
    try:
        motor.prever(db, partida.id, "e1", "quedarse", "siempre elegís el lazo")
        assert False, "la previsión debe callar en el canvas blanco"
    except motor.MotorError:
        pass


def test_prevision_despierta_y_sella_sin_soplar():
    db = db_limpia()
    partida = partida_con_mapa(db)
    assert motor.contexto_turno(db, partida.id)["prevision_despierta"]
    sellada = motor.prever(db, partida.id, "e9", "se queda", "siempre elegís el lazo")
    assert sellada["sellada"] and len(sellada["compromiso"]) == 64, \
        "el sello devuelve un compromiso (hash), no la apuesta"
    plano = str(sellada)
    assert "se queda" not in plano and "lazo" not in plano, \
        "la previsión NO viaja legible antes de la decisión (no se sopla)"


def test_revelacion_verifica_el_compromiso():
    import hashlib
    db = db_limpia()
    partida = partida_con_mapa(db)
    sellada = motor.prever(db, partida.id, "e9b", "se queda", "siempre el lazo")
    resultado = motor.resolver_decision(db, partida.id, "e9b", "irse")
    rev = resultado["revelacion"]
    assert rev["opcion_prevista"] == "se queda" and rev["razon"] == "siempre el lazo"
    recomputado = hashlib.sha256(
        f"e9b|{rev['opcion_prevista']}|{rev['razon']}|{rev['sal']}".encode()).hexdigest()
    assert recomputado == sellada["compromiso"] == rev["compromiso"], \
        "cualquiera verifica que la apuesta existió antes y no se reescribió"
    assert hashlib.sha256(rev["preimagen"].encode()).hexdigest() == rev["compromiso"], \
        "la preimagen viene lista para pegar en cualquier sha256 (verificación de persona)"
    assert "sha256sum" in rev["como_verificar"], "el nodo entrega el comando exacto"


def test_comando_de_verificacion_se_pega_tal_cual():
    """El copy-paste de una persona real: el comando corre en bash TAL CUAL,
    incluso con comillas y caracteres raros en la razón."""
    import subprocess
    db = db_limpia()
    partida = partida_con_mapa(db)
    razon = "porque D'Andrea dijo \"nunca\" y $HOME no es un lugar"
    motor.prever(db, partida.id, "e9c", "se va", razon)
    rev = motor.resolver_decision(db, partida.id, "e9c", "quedarse")["revelacion"]
    salida = subprocess.run(["bash", "-c", rev["como_verificar"]],
                            capture_output=True, text=True, timeout=10)
    assert salida.returncode == 0, f"el comando pegado no corre: {salida.stderr}"
    assert salida.stdout.split()[0] == rev["compromiso"], \
        "lo que la persona ve al pegar es el compromiso, byte por byte"


def test_marcador_puntua_el_mapa_no_la_prosa():
    """Corrección jul 2026 (playtest): arista nueva = jugador; solo refuerzo =
    sistema; sin lectura = nadie. La prosa de la apuesta no compite."""
    db = db_limpia()
    partida = partida_con_mapa(db)
    # decisión que ABRE arista nueva: desvío, punto del jugador
    motor.prever(db, partida.id, "e10", "se queda", "siempre el lazo")
    resultado = motor.resolver_decision(db, partida.id, "e10", "me corto solo", deslizamientos=[{
        "de_termino": "el lazo", "hacia_termino": "el corte",
        "evidencia": "dije que me corto solo"}])
    assert resultado["acierto_sistema"] is False
    assert resultado["marcador"]["jugador"] == 1, "arista nueva = victoria del jugador (CU-S2)"
    # decisión que SOLO REFUERZA una arista existente: el sistema lo tenía leído
    motor.prever(db, partida.id, "e11", "va a repetir el lazo", "riel visible")
    resultado = motor.resolver_decision(db, partida.id, "e11", "otra vez lo mismo", deslizamientos=[{
        "de_termino": "termino-0", "hacia_termino": "deriva-0",
        "evidencia": "repito lo de siempre"}])
    assert resultado["acierto_sistema"] is True and resultado["aristas_reforzadas"] == 1
    assert resultado["marcador"]["sistema"] == 1
    # decisión SIN lectura: nadie puntúa
    motor.prever(db, partida.id, "e12", "va a dudar", "zona muda")
    resultado = motor.resolver_decision(db, partida.id, "e12", "paso")
    assert resultado["acierto_sistema"] is None
    assert resultado["marcador"] == {"jugador": 1, "sistema": 1}


def test_apuesta_creciente_por_confirmaciones():
    db = db_limpia()
    partida = partida_con_mapa(db)
    for i in range(motor.APUESTA_RACHA):
        motor.prever(db, partida.id, f"r{i}", "va a confirmar su mapa", "racha")
        resultado = motor.resolver_decision(db, partida.id, f"r{i}", "lo de siempre",
                                            deslizamientos=[{
            "de_termino": "termino-1", "hacia_termino": "deriva-1",
            "evidencia": f"otra vez igual {i}"}])
    assert resultado["salir_del_mapa"], \
        "confirmar aleja: la escena siguiente se busca fuera del mapa (CU-S3)"
    assert motor.contexto_turno(db, partida.id)["salir_del_mapa"]


def test_opcion_comprada_confirma():
    """El click confirma, la palabra abre: comprar la opción que la apuesta
    sellada tenía es confirmación del sistema, sin tocar el mapa."""
    db = db_limpia()
    partida = partida_con_mapa(db)
    opcion = "me quedo terminando la entrega"
    motor.prever(db, partida.id, "op1", opcion, "siempre termina lo que empieza")
    resultado = motor.resolver_decision(db, partida.id, "op1", "  ME QUEDO Terminando la entrega  ")
    assert resultado["acierto_sistema"] is True
    assert resultado["marcador"]["sistema"] == 1
    assert resultado["deslizamientos_persistidos"] == 0 and resultado["aristas_reforzadas"] == 0
    assert motor._memorias[partida.id].aciertos_seguidos == 1


def test_opcion_distinta_sin_lectura_no_puntua():
    db = db_limpia()
    partida = partida_con_mapa(db)
    motor.prever(db, partida.id, "op2", "me quedo terminando la entrega", "razón")
    resultado = motor.resolver_decision(db, partida.id, "op2", "me voy a caminar")
    assert resultado["acierto_sistema"] is None
    assert resultado["marcador"] == {"jugador": 0, "sistema": 0}


def test_racha_de_opciones_compradas_curva_el_laberinto():
    db = db_limpia()
    partida = partida_con_mapa(db)
    opcion = "vuelve a llamar a su hermana"
    for i in range(motor.APUESTA_RACHA):
        motor.prever(db, partida.id, f"oprc{i}", opcion, "racha de clicks")
        resultado = motor.resolver_decision(db, partida.id, f"oprc{i}", opcion)
    assert resultado["salir_del_mapa"], \
        "el jugador que solo compra opciones también curva el laberinto"


def test_cierre_destruye_todo_lo_efimero():
    db = db_limpia()
    partida = partida_con_mapa(db)
    motor.prever(db, partida.id, "e20", "se queda", "razón")
    devolucion = motor.cerrar_partida(db, partida.id)
    assert partida.id not in motor._memorias, "la memoria muere con la partida"
    assert len(devolucion["mapa"]) == motor.MAPA_MINIMO_PREVISION, \
        "la devolución es el mapa legible, con sus escenas de origen"
    assert devolucion["controles"] == ["ver", "llevarse", "borrar"]
    assert motor.auditar_mal_alimento(db) == [], "auditoría CU-T5: cero hallazgos"
    try:
        motor.resolver_decision(db, partida.id, "e21", "x")
        assert False, "sobre una partida cerrada no se opera"
    except motor.MotorError:
        pass


def test_cierre_temprano_rebota():
    """Cerrar no es castigo, por construcción: con menos de 3 escenas
    resueltas, cerrar_partida rechaza salvo lo_pide_el_jugador=True."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.resolver_decision(db, partida.id, "u1", "x")
    try:
        motor.cerrar_partida(db, partida.id)
        assert False, "una sola escena resuelta no alcanza el arco mínimo"
    except motor.MotorError as exc:
        assert "arco mínimo" in str(exc)
    devolucion = motor.cerrar_partida(db, partida.id, lo_pide_el_jugador=True)
    assert devolucion["controles"] == ["ver", "llevarse", "borrar"], \
        "con el pedido explícito del jugador, cierra igual"


def test_arco_completo_cierra_sin_flag():
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    for i in range(motor.ARCO_MINIMO_ESCENAS):
        motor.resolver_decision(db, partida.id, f"arco-{i}", "x")
    devolucion = motor.cerrar_partida(db, partida.id)
    assert devolucion["controles"] == ["ver", "llevarse", "borrar"], \
        "con el arco cumplido, cierra sin necesitar el flag"


def test_auditoria_de_esquema():
    db = db_limpia()
    assert motor.auditar_mal_alimento(db) == [], \
        "ninguna tabla tiene columnas capaces de retener el mal alimento"


def test_taxonomia_rechazada():
    db = db_limpia()
    partida = partida_con_mapa(db)
    motor.prever(db, partida.id, "e30", "sigue igual", "razón")
    try:
        motor.resolver_decision(db, partida.id, "e30", "seguir", deslizamientos=[{
            "de_termino": "autonomía", "hacia_termino": "extraversión",
            "evidencia": "cita cualquiera"}])
        assert False, "la tipología no entra al mapa (WP-14)"
    except motor.MotorError:
        pass
    try:
        motor.registrar_terminos(db, partida.id, ["apertura"])
        assert False, "tampoco como término"
    except motor.MotorError:
        pass


def test_validador_vectorial():
    ev, de, hacia = [1.0, 0.1], [0.9, 0.2], [0.8, 0.3]
    assert motor.validador_vectorial(ev, de, hacia), "evidencia cerca de sus términos pasa"
    assert not motor.validador_vectorial([1.0, 0.0], [0.9, 0.1], [-1.0, 0.0]), \
        "evidencia lejos de un término no pasa"


def test_frontera_el_mapa_de_otro_jamas():
    db = db_limpia()
    partida_a = motor.iniciar_partida(db, JUGADOR)
    motor.registrar_terminos(db, partida_a.id, ["mi taller"])
    partida_b = motor.iniciar_partida(db, OTRA)
    motor.registrar_terminos(db, partida_b.id, ["su huerta"])
    contexto_a = motor.contexto_turno(db, partida_a.id)
    assert contexto_a["terminos"] == ["mi taller"], \
        "el contexto sirve SOLO el mapa propio (INV-17)"


def test_contexto_turno_trae_semillas():
    """Las semillas viajan en el contexto (corrección jul 2026, playtest de
    la saturación): el cliente no las pide aparte, la escena se genera donde
    el mapa está roto."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.registrar_terminos(db, partida.id, ["el taller", "la deuda", "mi hermana"])
    motor.resolver_decision(db, partida.id, "s1", "x", deslizamientos=[{
        "de_termino": "el taller", "hacia_termino": "la deuda",
        "evidencia": "el taller se me llenó de deuda"}])
    contexto = motor.contexto_turno(db, partida.id)
    semillas = contexto["semillas"]
    assert set(semillas.keys()) == {"universales", "terminos_mudos",
                                     "pares_no_cubiertos", "del_comun", "nodos_fuga"}
    assert semillas["pares_no_cubiertos"], \
        "con 3 términos y 1 arista, algún par queda sin cobertura"
    assert "el taller / mi hermana" in semillas["pares_no_cubiertos"] \
        or "mi hermana / el taller" in semillas["pares_no_cubiertos"]


def test_borrado_en_cascada_de_topologia():
    from apps.api import controles

    class DBParcial:
        """El sqlite mínimo solo tiene las tablas de la aventura (las de red
        usan tipos de Postgres); para el resto responde vacío."""

        def __init__(self, session):
            self.session = session

        def query(self, modelo):
            if modelo in (Partida, TerminoMapa, Deslizamiento):
                return self.session.query(modelo)

            class Vacia:
                def all(self):
                    return []

                def first(self):
                    return None

            return Vacia()

        def delete(self, obj):
            self.session.delete(obj)

    sesion = db_limpia()
    partida = partida_con_mapa(sesion)
    db = DBParcial(sesion)
    contadores = controles.borrar_actor(db, JUGADOR)
    sesion.commit()
    assert contadores["topologia"] == motor.MAPA_MINIMO_PREVISION
    assert contadores["partidas"] == 1
    assert partida.id not in motor._memorias
    huella = controles.armar_huella(db, JUGADOR)
    assert huella["topologia"]["deslizamientos"] == [] and huella["partidas"] == [], \
        "tras borrar, nada puede referenciar a la persona (INV-05)"


def test_refuerzo_no_duplica():
    db = db_limpia()
    partida = partida_con_mapa(db, n=4)  # previsión aún muda: sin gate
    r = motor.resolver_decision(db, partida.id, "rep-1", "x", deslizamientos=[{
        "de_termino": "termino-0", "hacia_termino": "deriva-0",
        "evidencia": "lo repitió igual que antes"}])
    assert r["aristas_reforzadas"] == 1 and r["deslizamientos_persistidos"] == 0, \
        "la arista repetida refuerza, no duplica (05 §4)"
    mismos = [d for d in db.query(Deslizamiento).all() if d.de_termino == "termino-0"]
    assert len(mismos) == 1 and float(mismos[0].mass) == 2.0


def test_prevision_despierta_exige_prevision_sellada():
    db = db_limpia()
    partida = partida_con_mapa(db)  # 5 aristas: previsión despierta
    try:
        motor.resolver_decision(db, partida.id, "sin-sello", "x")
        assert False, "INV-06 por construcción: sin previsión sellada no hay decisión"
    except motor.MotorError as exc:
        assert "INV-06" in str(exc)


def test_semillas():
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.registrar_terminos(db, partida.id, ["mi taller", "la deuda"])
    s = motor.semillas(db, partida.id)
    assert "autonomía / lazo" in s["universales"]
    assert "mi taller" in s["terminos_mudos"], "términos nombrados que nunca deslizaron"
    # _vivas ordena por masa/recencia, no por inserción: el par puede salir
    # en cualquiera de los dos sentidos.
    assert "mi taller / la deuda" in s["pares_no_cubiertos"] \
        or "la deuda / mi taller" in s["pares_no_cubiertos"], "pares que el mapa no cubre"
    assert s["salir_del_mapa"] is False


def test_apuesta_con_etiqueta_rechazada():
    db = db_limpia()
    partida = partida_con_mapa(db)
    try:
        motor.prever(db, partida.id, "e40", "1", "va a abrir la caja")
        assert False, "la apuesta se sella con texto, no con una etiqueta"
    except motor.MotorError:
        pass


def test_apuesta_snake_case_o_una_sola_palabra_rechazada():
    """Corrección 2026-07-10 (playtest Gemini): la apuesta-etiqueta que
    colaba el validador de tres caracteres ("negacion_rotunda", "huir")."""
    db = db_limpia()
    partida = partida_con_mapa(db)
    for etiqueta in ("negacion_rotunda", "huir"):
        try:
            motor.prever(db, partida.id, "e41", etiqueta, "va a abrir la caja")
            assert False, f"'{etiqueta}' es etiqueta, no el texto de una opción"
        except motor.MotorError:
            pass
    sellada = motor.prever(db, partida.id, "e41", "le corto y no atiendo más",
                                      "va a abrir la caja")
    assert sellada["sellada"], "el texto real de una opción (dos palabras o más) sella bien"


def test_frase_no_es_termino():
    """Contaminación cartográfica (playtest Gemini, jul 2026): fragmentos de
    oración registrados como nodos del mapa. Un término NOMBRA, no narra."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.registrar_terminos(db, partida.id, ["el desorden", "mi taller"])  # nombran: pasan
    try:
        motor.registrar_terminos(db, partida.id, ["la meto adentro y la guardo"])
        assert False, "una frase no es un término"
    except motor.MotorError:
        pass
    try:
        motor.resolver_decision(db, partida.id, "e1", "x", deslizamientos=[{
            "de_termino": "el desorden",
            "hacia_termino": "mira si voy a caer en hacerme cargo",
            "evidencia": "cita textual cualquiera"}])
        assert False, "una frase tampoco entra como punta de arista"
    except motor.MotorError:
        pass


def test_menu_es_un_prestamo():
    """El menú es un préstamo (corrección jul 2026, segunda del playtest a
    puro número): dos turnos seguidos sin palabra propia gastan el menú
    (menu_agotado); el mapa comiendo lo repone. Fase canvas: sin previsión, sin
    apuestas, para aislar el mecanismo del resto del ciclo."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    assert motor.contexto_turno(db, partida.id)["menu_agotado"] is False, \
        "recién abierta, el menú está intacto"
    motor.resolver_decision(db, partida.id, "m1", "x")
    assert motor.contexto_turno(db, partida.id)["menu_agotado"] is False, \
        "un solo turno sin comer no gasta el menú"
    motor.resolver_decision(db, partida.id, "m2", "x")
    assert motor.contexto_turno(db, partida.id)["menu_agotado"] is True, \
        "dos turnos seguidos sin palabra propia gastan el menú"
    motor.resolver_decision(db, partida.id, "m3", "x", deslizamientos=[{
        "de_termino": "termino-x", "hacia_termino": "deriva-x",
        "evidencia": "cita textual cualquiera"}])
    assert motor.contexto_turno(db, partida.id)["menu_agotado"] is False, \
        "el mapa comiendo repone el menú"


def test_mundo_hambriento_por_partida_seca():
    """La deriva (05 §2): dos escenas resueltas sin ningún término nuevo y el
    contexto declara mundo_hambriento; un término nuevo lo sacia."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.resolver_decision(db, partida.id, "e1", "x")
    motor.resolver_decision(db, partida.id, "e2", "x")
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is True, \
        "dos escenas sin término nuevo declaran hambre de mundo"
    motor.registrar_terminos(db, partida.id, ["un lugar nuevo"])
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is False, \
        "un término nuevo sacia el hambre"


def test_mundo_hambriento_en_partida_nueva_sobre_mapa_denso():
    """Partida nueva sobre un mapa ya denso (mismo jugador, otra partida): el
    hambre se declara desde la escena cero, sin esperar a que se agote."""
    db = db_limpia()
    partida_con_mapa(db)  # deja >= MAPA_MINIMO_PREVISION aristas para JUGADOR
    partida = motor.iniciar_partida(db, JUGADOR)
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is True, \
        "mapa denso + cero términos nuevos: hambre desde la escena cero"
    motor.registrar_terminos(db, partida.id, ["un término que nunca estuvo"])
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is False, \
        "un término nuevo sacia el hambre también en mapa denso"


def test_contexto_sirve_solo_lo_vivo():
    """El conjunto de trabajo servido al GM es lo que el olvido no apagó
    (masa > 0); el archivo completo (_aristas_de) sigue intacto: es del
    dueño, no se toca."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    vivas = []
    for i in range(3):
        arista = Deslizamiento(id=f"viva-{i}", jugador_llave=JUGADOR,
                               de_termino=f"vivo-{i}", hacia_termino=f"destino-{i}",
                               evidencia=f"cita {i}", mass=1.0)
        db.add(arista)
        vivas.append(arista)
    apagadas = []
    for i in range(2):
        arista = Deslizamiento(id=f"muerta-{i}", jugador_llave=JUGADOR,
                               de_termino=f"muerto-{i}", hacia_termino=f"fin-{i}",
                               evidencia=f"cita apagada {i}", mass=0.0)
        db.add(arista)
        apagadas.append(arista)
    db.flush()

    servido = motor.contexto_turno(db, partida.id)["aristas"]
    servidos_de = {a["de"] for a in servido}
    assert servidos_de == {f"vivo-{i}" for i in range(3)}, \
        "solo lo vivo (masa > 0) se sirve en el conjunto de trabajo"
    for i in range(2):
        assert f"muerto-{i}" not in servidos_de, "lo apagado por decay no viaja al GM"

    completo = motor._aristas_de(db, JUGADOR)
    assert len(completo) == 5, \
        "el archivo completo del dueño sigue entero: el filtro no lo tocó"


def test_ventana_acota_lo_servido():
    """Con más aristas vivas que VENTANA_MAPA, el contexto sirve a lo sumo la
    ventana, y son las de mayor masa."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    total = motor.VENTANA_MAPA + 10
    for i in range(total):
        db.add(Deslizamiento(id=f"vent-{i}", jugador_llave=JUGADOR,
                             de_termino=f"vt-{i}", hacia_termino=f"vd-{i}",
                             evidencia=f"cita {i}", mass=float(i + 1)))
    db.flush()

    servido = motor.contexto_turno(db, partida.id)["aristas"]
    assert len(servido) == motor.VENTANA_MAPA, \
        "lo servido no excede la ventana aunque el mapa vivo sea más grande"
    servidos_de = {a["de"] for a in servido}
    top = {f"vt-{i}" for i in range(10, total)}  # las de mayor masa (i+1 más alto)
    assert servidos_de == top, "la ventana se llena con las de mayor masa"

    completo = motor._aristas_de(db, JUGADOR)
    assert len(completo) == total, "el archivo del dueño no se acota"


def test_arista_decaida_se_revive_al_reforzar():
    """Una arista con masa cero (apagada por decay) cuyo par vuelve a
    deslizar en resolver_decision NO crea una arista nueva: revive la
    existente (le suma masa). La búsqueda de refuerzo sigue viendo el mapa
    completo, no solo lo vivo."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    apagada = Deslizamiento(id="decaida-1", jugador_llave=JUGADOR,
                            de_termino="el taller", hacia_termino="la deuda",
                            evidencia="cita vieja", mass=0.0)
    db.add(apagada)
    db.flush()
    assert apagada not in motor._vivas(motor._aristas_de(db, JUGADOR)), \
        "de partida, la arista apagada no está en el conjunto vivo"

    resultado = motor.resolver_decision(db, partida.id, "revive-1", "x", deslizamientos=[{
        "de_termino": "el taller", "hacia_termino": "la deuda",
        "evidencia": "el taller me debe otra vez"}])
    assert resultado["deslizamientos_persistidos"] == 0, \
        "no se crea una arista nueva: se revive la que ya existía"
    assert resultado["aristas_reforzadas"] == 1

    mismos = [d for d in db.query(Deslizamiento).all() if d.de_termino == "el taller"]
    assert len(mismos) == 1, "sigue habiendo una sola arista para el par (05 §4)"
    assert float(mismos[0].mass) == 1.0, "la masa vuelve a subir: el olvido se revierte con el uso"


def test_termino_repetido_no_sacia_el_hambre():
    """Registrar un término que YA existía en el mapa del jugador no cuenta
    como territorio nuevo (playtest jul 2026): el hambre sigue en pie."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    db.add(TerminoMapa(id="ya-existia", jugador_llave=JUGADOR, termino="café",
                       origen_escena=None))
    db.flush()
    motor.resolver_decision(db, partida.id, "e1", "x")
    motor.resolver_decision(db, partida.id, "e2", "x")
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is True
    motor.registrar_terminos(db, partida.id, ["café"])  # ya estaba en el mapa
    assert motor._memorias[partida.id].terminos_nuevos == 0, \
        "un término repetido no suma al conteo de territorio nuevo"
    assert motor.contexto_turno(db, partida.id)["mundo_hambriento"] is True, \
        "repetir un término no sacia el hambre"


def test_nodos_fuga_por_grado_de_salida():
    """Nodos de fuga (corrección jul 2026, playtest "la misma evasión con
    objeto distinto"): un término con salida hacia 2+ destinos distintos es
    hecho del grafo (grado de salida), no clustering. Un término con una
    sola salida no es nodo de fuga."""
    db = db_limpia()
    partida = motor.iniciar_partida(db, JUGADOR)
    motor.resolver_decision(db, partida.id, "e1", "x", deslizamientos=[{
        "de_termino": "monografia", "hacia_termino": "cafe",
        "evidencia": "en vez de escribir me hice un cafe"}])
    motor.resolver_decision(db, partida.id, "e2", "x", deslizamientos=[{
        "de_termino": "monografia", "hacia_termino": "youtube",
        "evidencia": "termine viendo youtube"}])
    motor.resolver_decision(db, partida.id, "e3", "x", deslizamientos=[{
        "de_termino": "monografia", "hacia_termino": "ia",
        "evidencia": "agarro todos los apuntes y los paso por ia"}])
    motor.resolver_decision(db, partida.id, "e4", "x", deslizamientos=[{
        "de_termino": "el gimnasio", "hacia_termino": "la excusa",
        "evidencia": "una sola salida no es nodo de fuga"}])
    s = motor.semillas(db, partida.id)
    fuga = {f["termino"]: f["destinos"] for f in s["nodos_fuga"]}
    assert "monografia" in fuga, "3 destinos distintos: hecho del grafo"
    assert fuga["monografia"] == ["cafe", "ia", "youtube"], \
        "los 3 destinos, sin duplicados, ordenados"
    assert "el gimnasio" not in fuga, "una sola salida no es nodo de fuga"
    contexto = motor.contexto_turno(db, partida.id)
    assert "nodos_fuga" in contexto["semillas"]


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests OK")
    sys.exit(1 if failures else 0)
