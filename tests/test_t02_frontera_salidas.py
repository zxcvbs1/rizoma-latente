"""
T-02 · Frontera sobre los puntos de salida (INV-17, INV-10).

Las intenciones son públicas (llevan su actor_id, llave pública), pero jamás
sale material privado en una respuesta pública, ni el grafo de vínculos de un
tercero. Corre sin servicios:
    .venv/bin/python tests/test_t02_frontera_salidas.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from packages.domain import frontera

LLAVE = "0x" + "a1" * 20


def test_intencion_publica_pasa_con_su_llave():
    respuesta = {"results": [{"node": {"id": "ofrezco-1", "text_raw": "!ofrezco bici",
                                       "actor_id": LLAVE, "mass": 2.0}, "score": 0.9}]}
    frontera.validar_respuesta_publica(respuesta)  # no levanta: actor_id es público


def test_vector_nunca_sale():
    for veneno in ({"node": {"content_vector": [0.1, 0.2]}},
                   {"node": {"vector": [0.1]}},
                   {"embedding": [0.3]}):
        try:
            frontera.validar_respuesta_publica(veneno)
            assert False, f"un vector no sale en respuesta pública: {veneno}"
        except frontera.FronteraViolada:
            pass


def test_material_privado_nunca_sale():
    for clave in ("mapa", "topologia", "deslizamientos", "token_partida",
                  "private_key", "disposiciones", "prediccion", "marcador"):
        try:
            frontera.validar_respuesta_publica({"x": {clave: "algo"}})
            assert False, f"{clave} es privado, no sale público"
        except frontera.FronteraViolada:
            pass


def test_search_response_pasa_el_guardian():
    # la forma real de /search: sin vector, con actor_id público
    respuesta = {"results": [{
        "node": {"id": "busco-9", "state": "active", "text_raw": "!busco funda",
                 "command_slug": "busco", "groups": [], "mass": 1.0,
                 "actor_id": LLAVE, "created_at": "2026-07-09"},
        "score": 0.7, "server_origin": "local", "peer_url": None}]}
    frontera.validar_respuesta_publica(respuesta)


def test_grafo_de_vinculos_de_tercero_deprecado():
    fuente = open(os.path.join(REPO, "apps/api/main.py")).read()
    # el GET público del grafo de un actor devuelve 403 y apunta a la huella firmada
    assert 'status_code=403' in fuente and "el grafo de vínculos no es público" in fuente, \
        "consultar el grafo de vínculos de un tercero no puede ser público (INV-10)"


def test_alias_en_valor_no_cruza():
    """Corrección 2026-07-10 (playtest del procomún): el payload exacto que
    coló la frontera cuando solo miraba llaves 0x."""
    try:
        frontera.validar_salida({"vector": [0.1, 0.2], "identidad": "mcp:antigravity"})
        assert False, "identidad con alias, aunque el campo también sea 'identidad'"
    except frontera.FronteraViolada:
        pass


def test_alias_en_campo_inocente_no_cruza():
    try:
        frontera.validar_salida({"quien": "mcp:antigravity"})
        assert False, "el alias vive en el VALOR, el nombre del campo es inocente"
    except frontera.FronteraViolada:
        pass


def test_campo_de_identidad_no_cruza_aunque_el_valor_sea_inocuo():
    try:
        frontera.validar_salida({"autor": "cualquier cosa"})
        assert False, "el NOMBRE del campo ya declara identidad"
    except frontera.FronteraViolada:
        pass


def test_dos_puntos_con_espacio_no_es_alias():
    frontera.validar_salida({"evidencia": "lo dijo el jugador: que no llegaba"})


def test_inventario_documentado():
    inv = os.path.join(REPO, "README.md")
    assert os.path.exists(inv), "el inventario de puntos de salida queda documentado"
    texto = open(inv).read()
    for endpoint in ("/search", "/actors/{id}/synapses", "/espejo", "/formas"):
        assert endpoint in texto, f"el inventario cubre {endpoint}"


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
