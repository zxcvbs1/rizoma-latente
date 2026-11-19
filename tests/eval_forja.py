"""
El evaluador antagonista de la forja (WP-33): el filtro que hace seguro
generar barato. Cada candidato a andamiaje (dict con nombre, descripcion,
cuerpo, que_necesita) pasa por:

1. Los validadores del acervo que ya existen: es_declarativa (sin órdenes al
   sistema) y patron_sin_castigo (sin castigo ni automatismo).
2. El catálogo de venenos propio de la forja: plata, ranking, centro
   permanente, app obligatoria, retención de historial.
3. El catálogo de herejías de doctrina (tests/eval_doctrina.py): el invento
   que le pone cerebro al nodo o centro a la red también rebota.
4. La regla de oro de los injertos: el candidato DECLARA qué necesita
   (campo que_necesita); sin declaración honesta no hay patrón.

Veredicto por candidato: FORJABLE | RECHAZADO (con motivos).

Corre SIN servicios (es texto contra texto). La regresión completa:
    .venv/bin/python tests/eval_forja.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from apps.acervo import acervo
from tests.eval_doctrina import evaluar as evaluar_doctrina

CORPUS = os.path.join(REPO, "tests", "fixtures", "inventos_envenenados.json")

# Venenos propios de la forja: las recapturas que un invento "útil" mete de
# contrabando. Regex sobre el candidato entero (nombre+descripcion+cuerpo).
VENENOS_FORJA = {
    "plata": re.compile(
        r"token|cr[eé]dito[s]? (que|en|canjeable)|se canjea|moneda|"
        r"puntos? canjeable|acredita un token", re.IGNORECASE),
    "ranking": re.compile(
        r"ranking|puntaje|score|los m[aá]s confiables|tabla de posiciones",
        re.IGNORECASE),
    "centro": re.compile(
        r"administrador central|autoridad central|permanente que (recibe|"
        r"decide|aprueba)|aprueba cada|decide cu[aá]les publican",
        re.IGNORECASE),
    "app-obligatoria": re.compile(
        r"obligatorio usar|app obligatoria|aplicaci[oó]n oficial|"
        r"quien no la instala no puede|solo por la aplicaci[oó]n",
        re.IGNORECASE),
    "retencion": re.compile(
        r"registro permanente|historial completo de cada persona|"
        r"se guarda para siempre|no se borra", re.IGNORECASE),
}


def evaluar_candidato(candidato: dict) -> dict:
    """El filtro completo sobre un candidato de la forja. Devuelve
    {"veredicto": "FORJABLE"|"RECHAZADO", "motivos": [...]}. Los motivos
    nombran el veneno, no reescriben el candidato: corregir es del inventor."""
    motivos = []
    texto = " ".join(str(candidato.get(campo, "")) for campo in
                     ("nombre", "descripcion", "cuerpo"))
    cuerpo = candidato.get("cuerpo") or ""

    if not cuerpo.strip():
        motivos.append("sin cuerpo: un patrón sin pasos no es un patrón")
    if not (candidato.get("que_necesita") or "").strip():
        motivos.append("regla de oro: no declara qué necesita para funcionar")
    if cuerpo.strip() and not acervo.es_declarativa(cuerpo):
        motivos.append("imperativo: intenta ordenar acciones al sistema (INV-18/19)")
    if cuerpo.strip() and not acervo.patron_sin_castigo(cuerpo):
        motivos.append("castigo o automatismo (INV-12/INV-01)")
    for veneno, patron in VENENOS_FORJA.items():
        if patron.search(texto):
            motivos.append(f"veneno de forja: {veneno}")
    reporte = evaluar_doctrina(texto)
    for herejia in reporte["herejias"]:
        motivos.append(f"herejía de doctrina: {herejia['id']}")

    return {"veredicto": "RECHAZADO" if motivos else "FORJABLE",
            "motivos": motivos}


def correr_regresion() -> bool:
    """El corpus envenenado entero debe rebotar, cada uno por su veneno; el
    candidato sano debe pasar. Devuelve True si la regresión está en verde."""
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    verde = True
    for caso in corpus["envenenados"]:
        resultado = evaluar_candidato(caso["candidato"])
        ok = resultado["veredicto"] == "RECHAZADO"
        verde &= ok
        marca = "OK " if ok else "MAL"
        print(f"{marca} [{caso['veneno']:16}] {caso['candidato']['nombre']:38} "
              f"-> {resultado['veredicto']} {resultado['motivos']}")
    sano = evaluar_candidato(corpus["sano"])
    ok = sano["veredicto"] == "FORJABLE"
    verde &= ok
    print(f"{'OK ' if ok else 'MAL'} [sano            ] "
          f"{corpus['sano']['nombre']:38} -> {sano['veredicto']} {sano['motivos']}")
    return verde


if __name__ == "__main__":
    if correr_regresion():
        print("\nRegresión de la forja: en verde (todo veneno rebota, lo sano pasa)")
        sys.exit(0)
    print("\nRegresión de la forja: HAY AGUJEROS")
    sys.exit(1)
