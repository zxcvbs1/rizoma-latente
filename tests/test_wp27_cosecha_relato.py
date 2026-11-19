"""
WP-27 · Relato para llevarse, harvest denso, Concordia liviano, discovery y
galería del acervo (jul 2026, playtest cruzado Gemini/Antigravity).

Cubre: cerrar_corrida devuelve el relato entero + cosecha_rala; la rúbrica de
corrida exige densidad proporcional y el ciclo hasta el injerto, sin las
negaciones defensivas viejas; brujula sin "no_es"; el artefacto portátil
(render_relato_html) sin identidades; la galería del acervo renderiza formas
publicadas; corrida_disponibles arma las tres claves de discovery; el modo
liviano de Concordia mide menos llamadas que el pesado.

Corre sin servicios:
    .venv/bin/python tests/test_wp27_cosecha_relato.py
"""
import hashlib
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.acervo import acervo
from apps.acervo import galeria as galeria_mod
from apps.api import mcp_server
from apps.api.brujula import FAMILIAS, guia_de
from apps.motor_simulacion import cliente as sim_cliente
from apps.motor_simulacion import motor as sim
from apps.motor_simulacion import relato as relato_mod
from packages.domain import frontera
from packages.domain.models import Corrida, Deslizamiento, Forma, Injerto, Tension

OPERADOR = "0x" + "1a" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Tension.__table__, Injerto.__table__,
                  Deslizamiento.__table__, Forma.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def test_cerrar_devuelve_relato_completo():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado",
                                  inventario={"horas": 4}, presupuesto_rondas=3)
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    ctx = sim.contexto_ronda(db, corrida.id, "la que riega")
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})

    # corrió y no leyó tensiones: sin sin_cosecha=True el cierre rebota
    # (corrección jul 2026, cierre sin cosecha); acá probamos el relato, no el gate.
    cierre = sim.cerrar_corrida(db, corrida.id, sin_cosecha=True)
    assert cierre["relato"] == [
        {"ronda": 0, "rol": "la que riega", "descripcion": "reparte el agua"}]
    assert "nota_relato" in cierre, "con relato no vacío, la nota explica que es la cosecha del dueño"
    assert "INV-07" in cierre["nota_relato"] or "no lo retiene" in cierre["nota_relato"]


def test_cierre_sin_actos_no_trae_nota_de_relato():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["relato"] == []
    assert "nota_relato" not in cierre


def test_estado_de_muestra_el_pulso_sin_cerrar():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    memoria = sim._corridas[corrida.id]
    memoria.arco_turnos = 10
    memoria.rondas_completadas = 3
    sim.leer_tensiones(db, corrida.id, [
        {"tipo": "carga desigual", "roles": ["la que riega"], "evidencia": "'siempre yo'"}])
    estado = sim.estado_de(db, corrida.id)
    assert estado["poblacion"] == 1
    assert estado["arco_turnos"] == 10
    assert estado["rondas_completadas"] == 3
    assert estado["tensiones_leidas"] == 1
    assert estado["motivo_fin"] == "en curso"
    # No cerró la corrida: sigue abierta.
    assert sim._corrida_abierta(db, corrida.id).estado == "abierta"


def test_cosecha_rala_marca_pocas_tensiones_para_muchas_rondas():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    memoria = sim._corridas[corrida.id]
    memoria.rondas_completadas = 9  # arco largo

    # Una sola tensión leída para 9 rondas: ralo (9 // 3 = 3, 1 < 3).
    sim.leer_tensiones(db, corrida.id, [
        {"tipo": "carga desigual", "roles": ["la que riega"], "evidencia": "'siempre yo'"}])
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["cosecha_rala"] is True
    assert "nota_cosecha_rala" in cierre


def test_cosecha_proporcional_no_es_rala():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    memoria = sim._corridas[corrida.id]
    memoria.rondas_completadas = 6

    # Tres tensiones para 6 rondas: proporcional (6 // 3 = 2, 3 >= 2).
    for i in range(3):
        sim.leer_tensiones(db, corrida.id, [
            {"tipo": f"tensión-{i}", "roles": ["la que riega"], "evidencia": f"cita {i}"}])
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["cosecha_rala"] is False
    assert "nota_cosecha_rala" not in cierre


def test_cerrar_sin_cosecha_rebota():
    """Corrección jul 2026 (el gate en el momento correcto, del playtest que
    cerró apenas terminaron los turnos): una corrida que corrió y no leyó ni
    una tensión no se puede cerrar sin declarar sin_cosecha=True."""
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    try:
        sim.cerrar_corrida(db, corrida.id)
        assert False, "corrió y no leyó tensiones: el cierre tiene que rebotar"
    except sim.MotorSimError as exc:
        assert "cosecha" in str(exc)
    # sigue abierta: el rebote no tocó el estado
    assert sim._corrida_abierta(db, corrida.id).estado == "abierta"

    cierre = sim.cerrar_corrida(db, corrida.id, sin_cosecha=True)
    assert cierre["corrida"] == corrida.id, "con sin_cosecha=True el cierre sí procede"


def test_cerrar_con_tension_leida_no_exige_sin_cosecha():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    sim.leer_tensiones(db, corrida.id, [
        {"tipo": "carga desigual", "roles": ["la que riega"], "evidencia": "'siempre yo'"}])
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["corrida"] == corrida.id, "con una tensión depositada, cierra sin flag"


def test_injertos_sin_veredicto_declara_nota():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "bienes_comunes",
                                  inventario={"salon": 1})
    sim.sumar_participante(db, corrida.id, "el que presta la llave", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "el que presta la llave",
                   {"descripcion": "abre el salon", "costo": {}})
    sim.leer_tensiones(db, corrida.id, [{
        "tipo": "acceso desigual al salon", "roles": ["el que presta la llave"],
        "evidencia": "el que presta la llave: 'si no estoy yo, no se abre'"}])
    sim.registrar_injerto(db, corrida.id, {
        "nombre": "llave compartida rotativa",
        "tension_que_ataca": "acceso desigual al salon",
        "regla_logica": "la llave rota semanalmente entre tres personas listadas a la vista",
        "flujo": "cada domingo pasa a la siguiente; la lista vive pegada en el salon",
        "requisitos_materiales": {"salon": 1},
        "senales_alivio": "nadie espera en la puerta; abre gente distinta cada semana",
    })
    cierre = sim.cerrar_corrida(db, corrida.id)
    assert cierre["injertos_sin_veredicto"] >= 1
    assert "nota_veredicto" in cierre
    assert "injerto_veredicto" in cierre["nota_veredicto"]


def test_rubrica_corrida_exige_densidad_y_el_ciclo_del_injerto():
    texto = sim_cliente.RUBRICA_CORRIDA
    assert "proporcional" in texto or "proporcionales" in texto
    assert "corrida_injerto" in texto and "injerto_veredicto" in texto
    assert "no llega a un injerto" in texto or "dejó el trabajo sin cerrar" in texto
    # Las negaciones defensivas viejas no sobreviven (principio: se definen por lo que son).
    for prohibido in ("distopía", "gig economy", "cyberpunk", "gusanos corporativos"):
        assert prohibido not in texto, f"'{prohibido}' es una negación defensiva vieja"
    assert "tamaño y el género que la comunidad declara" in texto


def test_rubrica_injerto_exige_extension_no_eslogan():
    assert "no un eslogan" in sim_cliente.RUBRICA_INJERTO


def test_rubrica_corrida_distingue_las_tres_vias_de_poblar():
    texto = sim_cliente.RUBRICA_CORRIDA
    assert "corrida_personaje" in texto
    assert "mapa hablando solo" in texto


def test_rubrica_injerto_encuadra_consigna_generativa():
    assert "consigna generativa" in sim_cliente.RUBRICA_INJERTO.lower()


def test_brujula_familias_y_guia_sin_negaciones_defensivas():
    for datos in FAMILIAS.values():
        assert "no_es" not in datos
    for familia in ("aventura", "corrida", "acervo", "sesion", "pool"):
        cuerpo = guia_de(familia)["guia"].lower()
        for frase in ("no es mediación", "nada paga nada", "gig economy",
                      "mercado de nada", "no es un mercado"):
            assert frase not in cuerpo, f"{familia}: '{frase}' es una negación defensiva vieja"


def test_render_relato_html_sin_identidades():
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, corrida.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})

    html = relato_mod.render_relato_html(corrida.id, db)
    assert html.strip() and "<html" in html
    assert "la que riega" in html and "reparte el agua" in html
    assert not frontera.contiene_identidades(html), "solo roles, jamás llaves (frontera)"


def test_relato_html_vacio_declara_el_vacio():
    """Corrección jul 2026 (el playtest del GM que se narró la historia a sí
    mismo sin servir la cola): una corrida sin actos tiene que decirlo en el
    documento mismo, bien visible, no en una nota al pie."""
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, corrida.id, "la que riega", security=None, token=None)

    html_vacio = relato_mod.render_relato_html(corrida.id, db)
    assert "no registró ningún acto" in html_vacio

    otra = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_participante(db, otra.id, "la que riega", security=None, token=None)
    sim.acto_ronda(db, otra.id, "la que riega", {"descripcion": "reparte el agua", "costo": {}})
    html_con_actos = relato_mod.render_relato_html(otra.id, db)
    assert "no registró ningún acto" not in html_con_actos


def test_galeria_renderiza_formas_publicadas():
    db = db_limpia()
    db.add(Forma(id="forma-uno", tipo="tension_tipo", nombre="La carga que no rota",
                 descripcion="quien más presente está termina cargando todo",
                 contexto_material="{}", marco="cuidado",
                 procedencia="comunidad anónima, 2026-07-01",
                 regla_consentimiento="unanimidad", licencia="abierta",
                 estado="publicada", mass=2.0))
    db.add(Forma(id="forma-retirada", tipo="tension_tipo", nombre="Retirada",
                 descripcion="no debería aparecer", contexto_material="{}",
                 marco="cuidado", procedencia="x", regla_consentimiento="unanimidad",
                 licencia="abierta", estado="retirada"))
    db.flush()

    html = galeria_mod.render_galeria_html(db)
    assert "La carga que no rota" in html
    assert "Retirada" not in html, "solo formas publicadas, no retiradas"
    assert "<html" in html


def test_galeria_vacia_no_rompe():
    db = db_limpia()
    html = galeria_mod.render_galeria_html(db)
    assert "acervo todavía está vacío" in html


def test_corrida_disponibles_encuentra_la_llave_con_mapa():
    huella_rica = {"topologia": {
        "terminos": ["el desorden", "mi taller"],
        "deslizamientos": [{"de": "cuidar", "hacia": "controlar",
                            "evidencia": "'lo hago yo, mejor'", "intensidad": "marcada"}],
    }}
    huella_vacia = {"topologia": {"terminos": [], "deslizamientos": []}}
    formas = {"formas": [{"id": "f-1", "nombre": "La carga que no rota", "tipo": "tension_tipo"}]}
    # Varias identidades del keystore: solo la que tiene mapa aparece.
    resultado = mcp_server.armar_disponibles(
        [("jugador:zxcvbs", huella_vacia), ("jugador:gabriel", huella_rica)], formas)
    assert set(resultado) == {"tus_mapas", "sinteticos_del_comun", "nota", "para_arrancar"}
    assert "lente_borrador" in resultado["para_arrancar"]["1_marco"]
    assert "turnos" in resultado["para_arrancar"]["2_turnos"]
    assert len(resultado["tus_mapas"]) == 1  # la vacía no aparece
    mapa = resultado["tus_mapas"][0]
    assert mapa["jugador_scope"] == "jugador:gabriel"
    assert [p["termino"] for p in mapa["personajes"]] == ["el desorden", "mi taller"]
    assert mapa["tensiones"][0]["de"] == "cuidar"
    assert "jugador:gabriel" in mapa["meterte_como_doble"]
    assert "jugador:gabriel" in resultado["nota"]
    assert resultado["sinteticos_del_comun"] == [
        {"id": "f-1", "nombre": "La carga que no rota", "tipo": "tension_tipo"}]


def _embedder_determinista(texto: str):
    import numpy as np
    h = hashlib.sha256(texto.encode()).digest()
    return np.frombuffer((h * 24)[:768 * 4], dtype=np.float32).copy()


def test_modo_liviano_usa_menos_llamadas_que_el_pesado():
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia, _concordia_instalada
    if not _concordia_instalada():
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return

    llamadas = {"pesado": 0, "liviano": 0}

    class ModeloContador:
        def __init__(self, clave):
            self.clave = clave

        def sample_text(self, prompt, **kw):
            llamadas[self.clave] += 1
            return "hace algo con calma"

        def sample_choice(self, prompt, responses, **kw):
            return 0, responses[0], {}

    contexto = {"rol": "la-que-riega", "disposiciones": "reparte antes de acumular",
               "situacion": "El pozo está casi seco."}

    pesado = RuntimeConcordia(modelo=ModeloContador("pesado"),
                              embedder=_embedder_determinista, liviano=False)
    pesado.producir_acto(contexto)

    liviano = RuntimeConcordia(modelo=ModeloContador("liviano"),
                               embedder=_embedder_determinista, liviano=True)
    acto = liviano.producir_acto(contexto)

    assert llamadas["liviano"] < llamadas["pesado"], \
        f"liviano ({llamadas['liviano']}) tiene que llamar menos que el pesado ({llamadas['pesado']})"
    assert llamadas["liviano"] == 1, "el modo liviano es UNA sola llamada por acto"
    assert acto["costo"] == {} and isinstance(acto["descripcion"], str)
    print(f"  medido: pesado={llamadas['pesado']} llamadas/acto, liviano={llamadas['liviano']}")


def test_runtime_concordia_default_es_liviano_con_memoria():
    """Corrección jul 2026 (de medir la lentitud con Gemini a mano): rico son
    4 llamadas por acto, insoportable con un humano sirviendo; el liviano
    ahora lleva la historia del arco en el prompt (rápido Y coherente) y
    vuelve a ser el default."""
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia
    r = RuntimeConcordia(modelo=object())
    assert r.liviano is True, "liviano con memoria es el default: una llamada por acto"


def test_con_delegacion_sin_pasar_liviano_queda_liviano():
    from apps.motor_simulacion.delegacion import BuzonEnMemoria
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia

    runtime = RuntimeConcordia.con_delegacion(BuzonEnMemoria(), embedder=_embedder_determinista)
    assert runtime.liviano is True, "con_delegacion sin liviano explícito también es liviano"


def test_liviano_lleva_la_historia_del_arco_al_prompt():
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia, DISPOSICIONES_MAX
    prompts = []

    class ModeloCaptura:
        def sample_text(self, prompt, **kw):
            prompts.append(prompt)
            return "el rol hace algo concreto"

        def sample_choice(self, prompt, responses, **kw):
            return 0, responses[0], {}

    rt = RuntimeConcordia(modelo=ModeloCaptura(), embedder=_embedder_determinista, liviano=True)
    dispo = [f"regla{i}" for i in range(17)]
    rt.producir_acto({"rol": "protagonista", "disposiciones": dispo,
                      "situacion": "la oficina a la mañana",
                      "historial": ["jefe: exige el informe", "psicologo: ofrece una pausa"]})
    p = prompts[-1]
    assert "exige el informe" in p and "ofrece una pausa" in p, "la historia del arco viaja en el prompt"
    assert p.count("regla") <= DISPOSICIONES_MAX, "las disposiciones se capan"


def test_rico_persiste_el_agente_entre_actos():
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia, _concordia_instalada
    if not _concordia_instalada():
        print("  SKIP: gdm-concordia no instalada (dependencia opcional)")
        return

    class Modelo:
        def sample_text(self, prompt, **kw):
            return "hace algo"

        def sample_choice(self, prompt, responses, **kw):
            return 0, responses[0], {}

    rt = RuntimeConcordia(modelo=Modelo(), embedder=_embedder_determinista, liviano=False)
    rt.producir_acto({"rol": "el jefe", "disposiciones": ["exige"], "situacion": "mañana"})
    id1 = id(rt._agentes["el jefe"])
    rt.producir_acto({"rol": "el jefe", "disposiciones": ["exige"], "situacion": "mediodía"})
    assert id(rt._agentes["el jefe"]) == id1, "el rico reusa el MISMO agente (memoria persiste)"
    assert len(rt._agentes) == 1, "un solo agente cacheado para el rol"


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
