"""
El antagonista de doctrina (WP-30): mide cualquier explicación del
protocolo contra el canon servible (apps/api/brujula.py, guía
"resonancias") en vez de dejar que el prior de cada modelo confabule.

Dispara esto: un GM le puso cerebro al nodo tres veces explicando el ciclo
de la lengua y los injertos ("la IA del nodo procesa...", "la masa lo
convierte en estándar de facto", "el nodo procesa grandes volúmenes de
interacciones de la gente"). El catálogo de herejías
(tests/fixtures/herejias_doctrina.json) crece con cada confabulación
que aporte un playtest.

SIN servicios. Uso:
    .venv/bin/python tests/eval_doctrina.py                       # autoverificación
    .venv/bin/python tests/eval_doctrina.py archivo.txt [tema ...]  # evalúa un texto
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

FIXTURE = os.path.join(REPO, "tests", "fixtures", "herejias_doctrina.json")
CASO_REGRESION = os.path.join(REPO, "tests", "fixtures", "doctrina_incorrecta.txt")

NEGACIONES = ("no hay", "no existe", "sin ", "jamás")


def _cargar_catalogo() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _es_negacion(texto_norm: str, inicio: int) -> bool:
    """Mira los ~30 caracteres previos al match buscando una negación."""
    contexto = texto_norm[max(0, inicio - 30):inicio]
    return any(neg in contexto for neg in NEGACIONES)


def evaluar(texto: str, temas=None) -> dict:
    """Corre el catálogo de herejías y las verdades requeridas de los temas
    pedidos (o todos) sobre `texto`. Devuelve un reporte con veredicto."""
    catalogo = _cargar_catalogo()
    texto_norm = texto.lower()

    herejias_marcadas = []
    for herejia in catalogo["herejias"]:
        patron = herejia["patron"]
        for match in re.finditer(patron, texto_norm, flags=re.IGNORECASE | re.UNICODE):
            if herejia.get("solo_afirmativo") and _es_negacion(texto_norm, match.start()):
                continue
            inicio = max(0, match.start() - 40)
            fin = min(len(texto), match.end() + 40)
            herejias_marcadas.append({
                "id": herejia["id"],
                "correccion": herejia["correccion"],
                "evidencia": texto[inicio:fin],
            })
            break  # una entrada por herejía alcanza para el reporte

    verdades_requeridas = catalogo["verdades_requeridas"]
    temas_a_chequear = temas if temas else list(verdades_requeridas)
    verdades_faltantes = []
    for tema in temas_a_chequear:
        for verdad in verdades_requeridas.get(tema, []):
            if not any(clave.lower() in texto_norm for clave in verdad["claves"]):
                verdades_faltantes.append({
                    "tema": tema,
                    "id": verdad["id"],
                    "descripcion": verdad["descripcion"],
                })

    infiel = bool(herejias_marcadas) or len(verdades_faltantes) > 1
    return {
        "herejias": herejias_marcadas,
        "verdades_faltantes": verdades_faltantes,
        "veredicto": "INFIEL" if infiel else "FIEL",
    }


def _guias_del_canon() -> dict:
    from apps.api.brujula import guia_de
    familias = ("aventura", "corrida", "acervo", "sesion", "pool", "resonancias")
    return {familia: guia_de(familia)["guia"] for familia in familias}


def _autoverificar() -> bool:
    ok = True

    print("=== autoverificación: el canon propio da cero herejías ===")
    for familia, guia in _guias_del_canon().items():
        reporte = evaluar(guia)
        if reporte["herejias"]:
            ok = False
            ids = ", ".join(h["id"] for h in reporte["herejias"])
            print(f"FAIL  guia_de('{familia}'): herejías detectadas: {ids}")
        else:
            print(f"PASS  guia_de('{familia}'): cero herejías")

    print("\n=== autoverificación: el caso sintético da INFIEL ===")
    with open(CASO_REGRESION, encoding="utf-8") as fh:
        texto_caso = fh.read()
    reporte = evaluar(texto_caso)
    esperadas = {"nodo-con-cerebro", "masa-dispara-generacion", "nodo-procesa-personas"}
    encontradas = {h["id"] for h in reporte["herejias"]}
    print(f"veredicto: {reporte['veredicto']}")
    for h in reporte["herejias"]:
        print(f"  herejía: {h['id']}\n    evidencia: ...{h['evidencia']}...\n"
              f"    corrección: {h['correccion']}")
    if reporte["veredicto"] != "INFIEL" or not esperadas <= encontradas:
        ok = False
        faltan = esperadas - encontradas
        print(f"FAIL  caso sintético: veredicto={reporte['veredicto']}, faltan={faltan}")
    else:
        print(f"PASS  caso sintético: INFIEL con {sorted(esperadas)}")

    return ok


def _imprimir_reporte(reporte: dict) -> None:
    print(f"veredicto: {reporte['veredicto']}\n")
    if reporte["herejias"]:
        print("herejías detectadas:")
        for h in reporte["herejias"]:
            print(f"  - {h['id']}: ...{h['evidencia']}...")
            print(f"    corrección: {h['correccion']}")
    else:
        print("herejías detectadas: ninguna")
    if reporte["verdades_faltantes"]:
        print("\nverdades faltantes:")
        for v in reporte["verdades_faltantes"]:
            print(f"  - [{v['tema']}] {v['id']}: {v['descripcion']}")
    else:
        print("\nverdades faltantes: ninguna")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        ok = _autoverificar()
        return 0 if ok else 1

    archivo, temas = args[0], (args[1:] or None)
    with open(archivo, encoding="utf-8") as fh:
        texto = fh.read()
    reporte = evaluar(texto, temas=temas)
    _imprimir_reporte(reporte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
