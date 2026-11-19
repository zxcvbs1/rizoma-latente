"""
El banco de comportamiento del ofrecimiento de patrones (WP-32).

NO es parte de la batería: necesita Ollama vivo (el embedder real) y el nodo
vivo (los patrones PUBLICADOS del acervo son la referencia: el banco mide lo
que el puente ofrecería de verdad, no una copia). Corre
tests/fixtures/corpus_patrones.json contra `packages.puentes.kit.leer_patron`,
barre umbrales [0.55..0.75 paso 0.01] y reporta por umbral: patrones
correctos, silencios correctos (esperado null y calló) y errores (patrón
equivocado, patrón donde iba silencio, silencio donde iba patrón). Elige el
mejor umbral (máx correctos; a empate, el más alto) y da el veredicto:
ÚTIL solo con el corpus entero correcto en el umbral vigente del kit.

Uso:
    .venv/bin/python tests/eval_patrones.py
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import httpx

from packages.adapters.adapter import OllamaAdapter
from packages.puentes import kit

CORPUS = os.path.join(REPO, "tests", "fixtures", "corpus_patrones.json")
API = os.getenv("RIZOMA_API", "http://localhost:8000")
UMBRALES = [round(0.55 + 0.01 * i, 2) for i in range(21)]  # 0.55 .. 0.75


async def main():
    corpus = json.load(open(CORPUS))["casos"]
    formas = httpx.get(f"{API}/formas", timeout=10).json()["formas"]
    patrones = [f for f in formas if f["tipo"] == "patron_coordinacion"
                and f["estado"] == "publicada"]
    if not patrones:
        print("No hay patrones publicados en el nodo: nada que medir todavía.")
        sys.exit(1)
    print(f"{len(patrones)} patrones publicados; corpus de {len(corpus)} casos\n")

    ollama = OllamaAdapter()
    lecturas = []
    for caso in corpus:
        # umbral 0.0: siempre el mejor y su afinidad; el barrido va después
        crudo = await kit.leer_patron(caso["frase"], ollama.generate_embedding,
                                      patrones, umbral=0.0)
        lecturas.append((caso["frase"], caso["esperado"],
                         crudo["nombre"] if crudo else None,
                         crudo["afinidad"] if crudo else 0.0))

    mejor_umbral, mejor_correctos = None, -1
    for umbral in UMBRALES:
        correctos = errores = 0
        for _, esperado, mejor, afinidad in lecturas:
            got = mejor if afinidad >= umbral else None
            if got == esperado:
                correctos += 1
            else:
                errores += 1
        marca = ""
        if correctos >= mejor_correctos:
            mejor_umbral, mejor_correctos = umbral, correctos
            marca = "  <-"
        print(f"umbral {umbral:.2f}: {correctos}/{len(lecturas)} correctos, "
              f"{errores} errores{marca}")

    print(f"\nMejor umbral del barrido: {mejor_umbral} "
          f"({mejor_correctos}/{len(lecturas)})")
    print(f"Umbral vigente del kit: {kit.UMBRAL_PATRON}")

    fallas_vigente = [(f, e, m, a) for f, e, m, a in lecturas
                      if (m if a >= kit.UMBRAL_PATRON else None) != e]
    if fallas_vigente:
        print("\nFallas con el umbral vigente:")
        for frase, esperado, mejor, afinidad in fallas_vigente:
            got = mejor if afinidad >= kit.UMBRAL_PATRON else None
            print(f"  '{frase}' -> {got} ({afinidad:.2f}), esperado {esperado}")
        print("\nVeredicto: TODAVÍA NO")
        sys.exit(1)
    print("\nVeredicto: ÚTIL (corpus entero correcto con el umbral vigente)")


if __name__ == "__main__":
    asyncio.run(main())
