"""
WP-20 · La cantera generativa del acervo (03 §6, 05 §2.3, 06 §3.1;
CU-S10, CU-C8 y adversarios).

Se acumulan tensiones encarnables, no personas: el personaje es siempre
instancia efímera; lo colectivo es la forma. El sorteo lee masa y JAMÁS la
escribe. Corre sin servicios:
    .venv/bin/python tests/test_wp20_cantera.py
"""
import json
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_aventura import motor as aventura
from apps.motor_simulacion import motor as sim
from packages.domain import frontera
from packages.domain.models import (Corrida, Deslizamiento, Forma, Injerto, Partida,
                                    Tension, TerminoMapa)

OPERADOR = "0x" + "0a" * 20
JUGADOR = "0x" + "c4" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (Corrida.__table__, Tension.__table__, Forma.__table__,
                  Partida.__table__, TerminoMapa.__table__, Deslizamiento.__table__,
                  Injerto.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def forma(db, fid, nombre, masa=1.0, estado="publicada", tipo="tension_tipo"):
    fila = Forma(id=fid, tipo=tipo, nombre=nombre,
                 descripcion=f"descripción de {nombre}", contexto_material="{}",
                 marco="cuidado", procedencia="comunidad anónima, 2026-07-08",
                 regla_consentimiento="unanimidad", estado=estado, mass=masa)
    db.add(fila)
    db.flush()
    return fila


def test_sorteo_lee_masa_y_jamas_la_escribe():
    db = db_limpia()
    pesada = forma(db, "f-pesada", "la que todos retoman", masa=50.0)
    liviana = forma(db, "f-liviana", "la recién nacida", masa=0.0)
    forma(db, "f-retirada", "la revocada", estado="retirada")

    rng = random.Random(7)
    elegidas = sim.sortear_formas(db, n=60, fraccion_uniforme=0.3, rng=rng)
    ids = [f.id for f in elegidas]
    assert "f-retirada" not in ids, "la retirada no entra al casting"
    assert ids.count("f-pesada") > ids.count("f-liviana"), "la masa pondera"
    assert ids.count("f-liviana") > 0, \
        "la fracción uniforme le da lugar a lo nuevo (divergir, no converger)"
    assert float(pesada.mass) == 50.0 and float(liviana.mass) == 0.0, \
        "el sorteo automático JAMÁS escribe masa (decisión jul 2026)"


def test_sintetico_desde_forma_y_solo_desde_forma():
    db = db_limpia()
    fila = forma(db, "f-1", "el filtro que desaparece humanos")
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado", {"horas": 3})
    resultado = sim.sumar_sintetico(db, corrida.id, "la que filtra", "f-1")
    assert resultado["poblacion"] == "sintetica" and resultado["forma_origen"] == "f-1"

    contexto = sim.contexto_ronda(db, corrida.id, "la que filtra")
    assert contexto["forma_origen"] == "f-1", "declara su forma de origen (CU-C8)"
    assert any("el filtro que desaparece humanos" in d for d in contexto["disposiciones"])
    assert not frontera.contiene_identidades(json.dumps(contexto))

    for forma_id in ("no-existe", "0x" + "9" * 40):
        try:
            sim.sumar_sintetico(db, corrida.id, "rol-x", forma_id)
            assert False, "el constructor solo acepta ids de forma del acervo"
        except sim.MotorSimError:
            pass
    try:
        sim.sumar_sintetico(db, corrida.id, "rol-y", "f-retirada-x")
        assert False
    except sim.MotorSimError:
        pass
    retirada = forma(db, "f-r", "retirada", estado="retirada")
    try:
        sim.sumar_sintetico(db, corrida.id, "rol-z", retirada.id)
        assert False, "una forma retirada no se encarna"
    except sim.MotorSimError:
        pass


def test_sintetico_muere_al_cierre_y_lee_tensiones():
    db = db_limpia()
    forma(db, "f-1", "tensión-tipo del común")
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado")
    sim.sumar_sintetico(db, corrida.id, "rol-sintetico", "f-1")
    sim.acto_ronda(db, corrida.id, "rol-sintetico", {"descripcion": "actúa en escena", "costo": {}})
    persistidas = sim.leer_tensiones(db, corrida.id, [{
        "tipo": "prueba", "roles": ["rol-sintetico"],
        "evidencia": "rol-sintetico: 'lo dijo en escena'"}])
    assert persistidas == 1, "los roles sintéticos existen para el analizador"
    sim.cerrar_corrida(db, corrida.id)
    assert corrida.id not in sim._corridas, \
        "el sintético muere al cierre como todo agente"
    assert sim.auditar_corridas(db) == []


def test_personaje_puebla_con_disposiciones_propias_no_del_jugador():
    """corrida_personaje (el hueco del playtest de capitalismo de vigilancia):
    el jefe o el psicólogo se puebla con SUS disposiciones, jamás con las del
    mapa del jugador."""
    db = db_limpia()
    corrida = sim.iniciar_corrida(db, OPERADOR, "cuidado", {"horas": 3})
    resultado = sim.sumar_personaje(db, corrida.id, "el jefe", [
        "bajo presión exige resultados sin mirar el costo humano",
        "premia la obediencia, no la iniciativa"])
    assert resultado["poblacion"] == "personaje"
    assert resultado["disposiciones"] == [
        "bajo presión exige resultados sin mirar el costo humano",
        "premia la obediencia, no la iniciativa"]

    contexto = sim.contexto_ronda(db, corrida.id, "el jefe")
    assert any("bajo presión exige resultados" in d for d in contexto["disposiciones"])
    assert not frontera.contiene_identidades(json.dumps(contexto))

    try:
        sim.sumar_personaje(db, corrida.id, "rol-vacio", [])
        assert False, "sin disposiciones es un títere sin lógica propia"
    except sim.MotorSimError:
        pass
    try:
        sim.sumar_personaje(db, corrida.id, "rol-vacio2", ["   ", ""])
        assert False, "disposiciones solo con espacios tampoco cuenta"
    except sim.MotorSimError:
        pass
    try:
        sim.sumar_personaje(db, corrida.id, "0x" + "9" * 40, ["algo"])
        assert False, "una identidad en el rol rebota"
    except sim.MotorSimError:
        pass


def test_semillas_del_comun_en_la_aventura():
    db = db_limpia()
    forma(db, "f-1", "la tensión del filtro")
    forma(db, "f-2", "un injerto", tipo="injerto")
    partida = aventura.iniciar_partida(db, JUGADOR)
    aventura.registrar_terminos(db, partida.id, ["mi taller"])
    semillas = aventura.semillas(db, partida.id)
    assert semillas["del_comun"] == [{"forma_id": "f-1", "nombre": "la tensión del filtro"}], \
        "solo tensiones-tipo publicadas entran como semilla del común (05 §2.3)"


def test_jugar_no_escribe_al_acervo():
    db = db_limpia()
    fila = forma(db, "f-1", "la tensión del filtro", masa=2.0)
    partida = aventura.iniciar_partida(db, JUGADOR)
    aventura.semillas(db, partida.id)
    aventura.resolver_decision(db, partida.id, "escena-del-comun", "x", deslizamientos=[{
        "de_termino": "esperar", "hacia_termino": "abrir",
        "evidencia": "dije que abro yo"}])
    aventura.cerrar_partida(db, partida.id, lo_pide_el_jugador=True)
    assert float(fila.mass) == 2.0, \
        "publicar es acto de comunidad, jamás efecto del juego (05 §2.3)"


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
