"""
El antagonista de punta a punta (jul 2026): corre las sondas del corpus
contra el NODO VIVO (/search), como si diez personas distintas buscaran
cosas cotidianas, y verifica el comportamiento que la spec promete:

- lo esperado aparece (la resonancia encuentra el contenido afín),
- lo prohibido NO aparece por encima del piso (sin coincidencias forzadas),
- una búsqueda sin afinidad real devuelve la nota de la señal sembrada.

Necesita el nodo vivo (localhost:8000) con el corpus sembrado
(tests/fixtures/corpus_resonancias.json vía /emit). No es parte de la
batería. Uso:
    .venv/bin/python tests/eval_resonancias_e2e.py
"""
import json
import os
import sys

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

API = os.getenv("RIZOMA_API_URL", "http://localhost:8000")
CORPUS = os.path.join(REPO, "tests", "fixtures", "corpus_resonancias.json")

SONDA_SIN_AFINIDAD = "busco repuestos para un submarino nuclear"


def correr():
    with open(CORPUS) as fh:
        corpus = json.load(fh)
    emisiones, sondas = corpus["emisiones"], corpus["sondas"]

    aciertos = falsos = huerfanas_esperadas = 0
    detalles = []
    with httpx.Client(timeout=30.0) as http:
        for sonda in sondas:
            r = http.get(f"{API}/search", params={"q": sonda["texto"], "limit": 3})
            datos = r.json()
            textos_top = [(res["node"]["text_raw"], res.get("afinidad", res["score"]))
                          for res in datos.get("results", [])]
            ids_top = [eid for eid, texto in emisiones.items()
                       if any(texto == t for t, _ in textos_top)]
            hallo = any(e in ids_top for e in sonda["esperados"])
            contamino = any(p in ids_top for p in sonda["prohibidos"])
            aciertos += hallo
            falsos += contamino
            marca = ("+" if hallo else "-") + ("!" if contamino else " ")
            detalles.append(f"  {sonda['id']} [{marca}] {sonda['texto'][:42]:42s} -> "
                            + (", ".join(f"{t[:34]}:{a:.2f}" for t, a in textos_top) or "(vacio + nota)"))

        # La sonda sin afinidad posible: tiene que volver vacía con la nota.
        r = http.get(f"{API}/search", params={"q": SONDA_SIN_AFINIDAD, "limit": 3})
        datos = r.json()
        sin_afinidad_ok = (not datos.get("results")) and "sembrada" in datos.get("nota", "")

    print(f"antagonista e2e contra {API} (umbral del nodo: {datos.get('umbral')})")
    print("\n".join(detalles))
    print(f"\n  aciertos: {aciertos}/10   falsos: {falsos}/10   "
          f"sonda-sin-afinidad honesta: {'SI' if sin_afinidad_ok else 'NO'}")
    exito = aciertos >= 9 and falsos == 0 and sin_afinidad_ok
    print(f"  veredicto: {'UTIL' if exito else 'TODAVIA NO'}")
    return 0 if exito else 1


if __name__ == "__main__":
    sys.exit(correr())
