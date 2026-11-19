"""
El banco de comportamiento del lector de intención del puente (WP-31).

NO es parte de la batería: necesita Ollama vivo (el embedder real del nodo).
Corre tests/fixtures/corpus_intencion.json (frases naturales con el comando
esperado; null = deseo puro) contra `packages.puentes.kit.leer_intencion` con
el embedder real, barre umbrales [0.50..0.75 paso 0.05] y reporta por umbral:
comando_correcto (esperado no-null y acertado), deseo_correcto (esperado null
y devolvió None), errores (comando equivocado, o comando donde iba deseo, o
deseo donde iba comando). Elige el mejor umbral (máx correctos totales; a
empate, el más alto) y lo imprime.

Uso:
    .venv/bin/python tests/eval_intencion.py
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from packages.adapters.adapter import OllamaAdapter
from packages.puentes import kit

CORPUS = os.path.join(REPO, "tests", "fixtures", "corpus_intencion.json")
UMBRALES = [round(0.50 + 0.05 * i, 2) for i in range(6)]  # 0.50 .. 0.75


async def leer_crudo(adaptador, texto: str) -> dict:
    """Lee sin piso (umbral 0.0): devuelve siempre el mejor prototipo y su
    afinidad, cacheando los vectores de los prototipos. Los umbrales del
    barrido se aplican después, en Python puro, sin re-embeber nada."""
    return await kit.leer_intencion(texto, adaptador.generate_embedding, umbral=0.0)


def clasificar(mejor: str | None, afinidad: float, umbral: float):
    return mejor if afinidad >= umbral else None


async def main():
    with open(CORPUS) as fh:
        corpus = json.load(fh)
    casos = corpus["casos"]
    adaptador = OllamaAdapter()

    print(f"corpus: {len(casos)} casos; umbrales {UMBRALES}\n")

    lecturas = []
    for caso in casos:
        cruda = await leer_crudo(adaptador, caso["texto"])
        lecturas.append((caso, cruda["comando"], cruda["afinidad"]))
        print(f"  {caso['texto'][:50]:50s} esperado={str(caso['esperado']):8s} "
              f"mejor={str(cruda['comando']):8s} afinidad={cruda['afinidad']:.3f}")

    print(f"\n  {'umbral':>8s} {'comando_ok':>11s} {'deseo_ok':>9s} {'errores':>8s} {'total_ok':>9s}")
    mejor_umbral = None
    tabla = []
    for u in UMBRALES:
        comando_ok = deseo_ok = errores = 0
        detalle_errores = []
        for caso, mejor, afinidad in lecturas:
            leido = clasificar(mejor, afinidad, u)
            esperado = caso["esperado"]
            if esperado is None:
                if leido is None:
                    deseo_ok += 1
                else:
                    errores += 1
                    detalle_errores.append(f"'{caso['texto']}': esperaba deseo puro, leyó {leido}")
            else:
                if leido == esperado:
                    comando_ok += 1
                else:
                    errores += 1
                    detalle_errores.append(f"'{caso['texto']}': esperaba {esperado}, leyó {leido}")
        total_ok = comando_ok + deseo_ok
        tabla.append((u, comando_ok, deseo_ok, errores, total_ok, detalle_errores))
        print(f"  {u:>8.2f} {comando_ok:>11d} {deseo_ok:>9d} {errores:>8d} {total_ok:>9d}")
        if mejor_umbral is None or total_ok > mejor_umbral[4] or \
           (total_ok == mejor_umbral[4] and u > mejor_umbral[0]):
            mejor_umbral = (u, comando_ok, deseo_ok, errores, total_ok, detalle_errores)

    print(f"\nmejor umbral: {mejor_umbral[0]:.2f} "
          f"(comando_ok={mejor_umbral[1]}, deseo_ok={mejor_umbral[2]}, "
          f"errores={mejor_umbral[3]}, total_ok={mejor_umbral[4]}/{len(casos)})")
    if mejor_umbral[5]:
        print("errores en el mejor umbral:")
        for e in mejor_umbral[5]:
            print(f"  - {e}")

    if mejor_umbral[0] != kit.UMBRAL_INTENCION:
        print(f"\nUMBRAL_INTENCION vigente en kit.py: {kit.UMBRAL_INTENCION} "
              f"difiere del medido ({mejor_umbral[0]:.2f}): actualizar.")
    else:
        print(f"\nUMBRAL_INTENCION vigente ({kit.UMBRAL_INTENCION}) coincide con el medido.")


if __name__ == "__main__":
    asyncio.run(main())
