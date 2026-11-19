"""
WP-25 · Multiplayer semiótico, el árbitro que emerge (09_procomun §2.4;
INV-11/10/18/19/17).

Servidor autoritativo de estado (no de sentido); GM sorteado que rota; validación
cruzada que tumba un turno; la ficción muere al cierre; el puente consentido
siempre disponible; degradación sin fierro.

Corre sin servicios:
    .venv/bin/python tests/test_wp25_multiplayer.py
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.motor_aventura import multiplayer as mp
from packages.domain import frontera
from packages.domain.models import Forma, PesoContribucion, SesionMultiplayer

A = "0x" + "a1" * 20
B = "0x" + "b2" * 20
C = "0x" + "c3" * 20
LLAVE = "0x" + "dd" * 20


def db_limpia():
    engine = create_engine("sqlite://")
    for tabla in (SesionMultiplayer.__table__, Forma.__table__, PesoContribucion.__table__):
        tabla.create(engine)
    return sessionmaker(bind=engine)()


def sesion_tres(db):
    s = mp.abrir_sesion(db, A)  # convocante con fierro
    mp.entrar(db, s.id, B, con_fierro=True)
    mp.entrar(db, s.id, C, con_fierro=False)  # jugador sin fierro
    return s


def test_entrada_es_acto_individual():
    db = db_limpia()
    s = mp.abrir_sesion(db, A)
    import json
    assert len(json.loads(s.participantes)) == 1, "solo el convocante al abrir"
    mp.entrar(db, s.id, B, con_fierro=True)
    mp.entrar(db, s.id, B, con_fierro=True)  # idempotente
    assert len(json.loads(mp._sesion(db, s.id).participantes)) == 2


def test_gm_rota_nadie_arbitra_solo():
    db = db_limpia()
    s = sesion_tres(db)
    rng = random.Random(1)
    vistos = set()
    for _ in range(12):
        s.gm_anterior = s.gm_actual
        gm = mp.sortear_gm(db, s.id, rng=rng)
        vistos.add(gm)
        assert gm != s.gm_anterior or len(mp._con_fierro(s)) == 1, \
            "no repite GM consecutivo si hay más de uno con fierro"
    assert vistos == {A, B}, "el GM rota entre los que tienen fierro; el sin-fierro nunca compone"


def test_solo_el_gm_compone_y_pasa_frontera():
    db = db_limpia()
    s = sesion_tres(db)
    mp.sortear_gm(db, s.id, rng=random.Random(0))
    gm = mp._sesion(db, s.id).gm_actual
    otro = B if gm == A else A
    try:
        mp.proponer_turno(db, s.id, otro, {"texto": "escena mía"})
        assert False, "solo el GM sorteado compone el turno"
    except mp.MultiplayerError:
        pass
    try:
        mp.proponer_turno(db, s.id, gm, {"texto": f"la maneja {LLAVE}"})
        assert False, "una composición con identidad la bloquea la frontera"
    except frontera.FronteraViolada:
        pass


def test_validacion_cruzada_tumba_el_turno():
    db = db_limpia()
    s = sesion_tres(db)
    mp.sortear_gm(db, s.id, rng=random.Random(0))
    gm = mp._sesion(db, s.id).gm_actual
    pares = [p for p in (A, B, C) if p != gm]
    mp.proponer_turno(db, s.id, gm, {"texto": "una escena"})
    mp.validar_turno(db, s.id, pares[0], acepta=True)
    mp.validar_turno(db, s.id, pares[1], acepta=False)  # un rechazo
    r = mp.resolver_turno(db, s.id)
    assert r["aceptado"] is False and "cruzada" in r["motivo"]
    assert mp._sesion(db, s.id).turno == 0, "un turno rechazado no avanza"


def test_turno_aceptado_avanza_y_acredita():
    db = db_limpia()
    s = sesion_tres(db)
    mp.sortear_gm(db, s.id, rng=random.Random(0))
    gm = mp._sesion(db, s.id).gm_actual
    pares = [p for p in (A, B, C) if p != gm]
    mp.proponer_turno(db, s.id, gm, {"texto": "una escena que va"})
    for par in pares:
        mp.validar_turno(db, s.id, par, acepta=True)
    r = mp.resolver_turno(db, s.id)
    assert r["aceptado"] is True and mp._sesion(db, s.id).turno == 1
    from apps.worker import pool
    assert pool.peso_de(db, gm, "multiplayer") == 1.0, "componer un turno aporta al común"


def test_gm_no_valida_su_turno():
    db = db_limpia()
    s = sesion_tres(db)
    mp.sortear_gm(db, s.id, rng=random.Random(0))
    gm = mp._sesion(db, s.id).gm_actual
    mp.proponer_turno(db, s.id, gm, {"texto": "escena"})
    try:
        mp.validar_turno(db, s.id, gm, acepta=True)
        assert False, "el GM no valida su propio turno"
    except mp.MultiplayerError:
        pass


def test_degradacion_sin_fierro():
    db = db_limpia()
    s = SesionMultiplayer(id=mp._uid(), convocante_llave=C,
                          participantes='[{"llave": "%s", "con_fierro": false}]' % C,
                          estado="abierta", turno=0)
    db.add(s)
    db.flush()
    mp._sesiones[s.id] = []
    gm = mp.sortear_gm(db, s.id)
    assert gm is None and mp._sesion(db, s.id).estado == "degradada", \
        "sin cliente con fierro, degrada al camino asincrónico"


def test_puente_siempre_disponible():
    db = db_limpia()
    s = sesion_tres(db)
    r = mp.ofrecer_puente(db, s.id)
    assert r["puente_disponible"] is True and "real" in r["nota"]


def test_ficcion_muere_al_cierre():
    db = db_limpia()
    s = sesion_tres(db)
    mp.sortear_gm(db, s.id, rng=random.Random(0))
    gm = mp._sesion(db, s.id).gm_actual
    mp.proponer_turno(db, s.id, gm, {"texto": "algo que se dijo"})
    mp.cerrar_sesion(db, s.id)
    cerrada = mp._sesion(db, s.id)
    assert cerrada.estado == "cerrada" and cerrada.escena_propuesta is None
    assert s.id not in mp._sesiones, "la historia efímera murió"
    assert mp.auditar_sesiones(db) == [], "ninguna ficción viva en sesión cerrada"
    try:
        mp.proponer_turno(db, s.id, gm, {"texto": "x"})
        assert False, "sobre una sesión cerrada no se compone"
    except mp.MultiplayerError:
        pass


def test_rubrica_gm_debe_ser_forma_rubrica():
    db = db_limpia()
    try:
        mp.abrir_sesion(db, A, rubrica_gm_id="no-existe")
        assert False, "la rúbrica del GM debe ser una forma-rúbrica publicada"
    except mp.MultiplayerError:
        pass
    forma = Forma(id="r1", tipo="rubrica", nombre="gm", descripcion="d",
                  cuerpo="mirá la tensión", marco="general",
                  procedencia="anónima", regla_consentimiento="unanimidad",
                  estado="publicada", mass=1.0)
    db.add(forma)
    db.flush()
    s = mp.abrir_sesion(db, A, rubrica_gm_id="r1")
    assert s.rubrica_gm_id == "r1"


def test_estado_sesion_es_el_espejo():
    """estado_sesion: el compositor mira, no compone a ciegas. Con rúbrica
    publicada, dos participantes, GM sorteado y turno compuesto, el espejo
    trae manual (cuerpo de la rúbrica), gm_actual, escena_propuesta pendiente
    y, tras resolver, la historia con la escena aceptada."""
    db = db_limpia()
    forma = Forma(id="r-gm", tipo="rubrica", nombre="gm-comun",
                  descripcion="d", cuerpo="mirá la tensión material antes de narrar",
                  marco="general", procedencia="anónima",
                  regla_consentimiento="unanimidad", estado="publicada", mass=1.0)
    db.add(forma)
    db.flush()
    s = mp.abrir_sesion(db, A, rubrica_gm_id="r-gm")
    mp.entrar(db, s.id, B, con_fierro=True)

    estado0 = mp.estado_sesion(db, s.id)
    assert estado0["manual"]["cuerpo"] == "mirá la tensión material antes de narrar"
    assert set(estado0["participantes"]) == {A, B}
    assert estado0["historia"] == []
    assert estado0["escena_propuesta"] is None

    gm = mp.sortear_gm(db, s.id, rng=random.Random(0))
    mp.proponer_turno(db, s.id, gm, {"texto": "la escena que propone el GM"})
    estado1 = mp.estado_sesion(db, s.id)
    assert estado1["gm_actual"] == gm
    assert estado1["escena_propuesta"]["texto"] == "la escena que propone el GM"

    otro = B if gm == A else A
    mp.validar_turno(db, s.id, otro, acepta=True)
    r = mp.resolver_turno(db, s.id)
    assert r["aceptado"] is True

    estado2 = mp.estado_sesion(db, s.id)
    assert estado2["historia"] == [{"texto": "la escena que propone el GM"}]
    assert estado2["escena_propuesta"] is None, "el turno resuelto ya no está pendiente"


def test_sesion_huerfana_se_cierra():
    db = db_limpia()
    s = sesion_tres(db)
    s.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    assert mp.cerrar_sesion_huerfana(s) and s.estado == "cerrada"


def test_brujula_nombra_las_siete_familias_sin_vacio():
    from apps.api.brujula import FAMILIAS
    esperadas = {"aventura_*", "sesion_*", "corrida_*", "acervo_*", "pool_*",
                "mapa_*", "prevision_* / broadcast / buscar_federado"}
    assert set(FAMILIAS.keys()) == esperadas, "las siete familias, ni una menos"
    for familia, datos in FAMILIAS.items():
        assert {"nombre", "que_es"} <= set(datos.keys()), familia
        assert "no_es" not in datos, \
            f"{familia}: las cosas se definen por lo que son, no por negación"
        texto_vinculante = f"{datos['nombre']} {datos['que_es']}".lower()
        assert "mercado de predicción" not in texto_vinculante, \
            f"{familia}: el nombre inventado no puede colarse como válido"
        assert "mesa de partes" not in texto_vinculante, \
            f"{familia}: el nombre inventado no puede colarse como válido"


def test_guia_de_sirve_la_dinamica_completa_de_cada_familia():
    from apps.api.brujula import FAMILIAS, guia_de

    for familia in ("aventura", "corrida", "acervo", "sesion", "pool"):
        resultado = guia_de(familia)
        assert resultado["familia"] == familia
        assert resultado["guia"].strip(), f"{familia}: guía vacía"

    corrida = guia_de("corrida")["guia"]
    assert "corrida_tensiones" in corrida, \
        "la guía de corrida tiene que nombrar la tool del producto"
    assert "EN PERSONAJE" in corrida

    desconocida = guia_de("no-existe")
    assert "error" in desconocida
    assert set(desconocida["familias"]) == {"aventura", "corrida", "acervo",
                                             "sesion", "pool", "resonancias"}

    con_guia = {"aventura_*", "sesion_*", "corrida_*", "acervo_*", "pool_*",
                "prevision_* / broadcast / buscar_federado"}
    sin_guia = {"mapa_*"}
    for familia in con_guia:
        assert "guia" in FAMILIAS[familia], f"{familia}: le falta la clave guia"
    for familia in sin_guia:
        assert "guia" not in FAMILIAS[familia], f"{familia}: no debería tener guia"


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
