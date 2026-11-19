"""
El banco de comportamiento de resonancias (jul 2026).

NO es parte de la batería: necesita Ollama vivo (el embedder real del nodo).
Mide la FUNCIÓN de resonancia (embedding + similitud + umbral) aislada de la
infra: sin DB, cosenos en numpy. Corre el corpus de usos cotidianos
(tests/fixtures/corpus_resonancias.json) en varios modos de vectorización y
barre umbrales, para ajustar el módulo midiendo en vez de a ojo probando por
Telegram.

Modos:
  crudo           el texto tal cual (con el !comando adentro): lo que /emit hacía
  limpio          clean_text de parse_emission (el comando fuera del vector)
  limpio_prefijos limpio + prefijos de tarea de nomic-embed-text
                  (search_document: / search_query:), el uso recomendado del
                  modelo para retrieval

Uso:
    .venv/bin/python tests/eval_resonancias.py
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import numpy as np

from packages.adapters.adapter import OllamaAdapter

CORPUS = os.path.join(REPO, "tests", "fixtures", "corpus_resonancias.json")
UMBRALES = [round(0.30 + 0.05 * i, 2) for i in range(11)]  # 0.30 .. 0.80
TOP_K = 3


def _coseno(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


async def _vector(adaptador, texto: str) -> np.ndarray:
    v = await adaptador.generate_embedding(texto)
    return np.array(v, dtype=np.float32)


def _limpio(adaptador, texto: str) -> str:
    parsed = adaptador.parse_emission(texto)
    return parsed.get("clean_text") or texto


async def preparar(adaptador, emisiones: dict, sondas: list, modo: str):
    """Devuelve (vectores_emisiones, vectores_sondas) para el modo dado."""
    vecs_e, vecs_s = {}, {}
    for eid, texto in emisiones.items():
        if modo == "crudo":
            t = texto
        elif modo == "limpio":
            t = _limpio(adaptador, texto)
        else:  # limpio_prefijos
            t = "search_document: " + _limpio(adaptador, texto)
        vecs_e[eid] = await _vector(adaptador, t)
    for sonda in sondas:
        texto = sonda["texto"]
        if modo == "limpio_prefijos":
            t = "search_query: " + texto
        else:
            t = texto
        vecs_s[sonda["id"]] = await _vector(adaptador, t)
    return vecs_e, vecs_s


def evaluar(emisiones, sondas, vecs_e, vecs_s):
    """Para cada sonda: top K con scores. Devuelve la lista de rankings."""
    rankings = {}
    for sonda in sondas:
        vs = vecs_s[sonda["id"]]
        scores = sorted(((eid, _coseno(vs, ve)) for eid, ve in vecs_e.items()),
                        key=lambda par: -par[1])
        rankings[sonda["id"]] = scores[:TOP_K]
    return rankings


def metricas(sondas, rankings, umbral):
    aciertos = falsos = huerfanas = 0
    for sonda in sondas:
        top = [(eid, s) for eid, s in rankings[sonda["id"]] if s >= umbral]
        if not top:
            huerfanas += 1
            continue
        ids_top = [eid for eid, _ in top]
        if any(e in ids_top for e in sonda["esperados"]):
            aciertos += 1
        if any(p in ids_top for p in sonda["prohibidos"]):
            falsos += 1
    return aciertos, falsos, huerfanas


async def main():
    with open(CORPUS) as fh:
        corpus = json.load(fh)
    emisiones, sondas = corpus["emisiones"], corpus["sondas"]
    adaptador = OllamaAdapter()

    print(f"corpus: {len(emisiones)} emisiones, {len(sondas)} sondas; top_k={TOP_K}\n")
    resultados_modo = {}
    for modo in ("crudo", "limpio", "limpio_prefijos"):
        vecs_e, vecs_s = await preparar(adaptador, emisiones, sondas, modo)
        rankings = evaluar(emisiones, sondas, vecs_e, vecs_s)
        resultados_modo[modo] = rankings
        print(f"=== modo {modo} ===")
        for sonda in sondas:
            top = ", ".join(f"{eid}:{s:.2f}" for eid, s in rankings[sonda["id"]])
            marca_esp = "+" if any(
                e in [x for x, _ in rankings[sonda["id"]]] for e in sonda["esperados"]) else "-"
            marca_pro = "!" if any(
                p in [x for x, _ in rankings[sonda["id"]]] for p in sonda["prohibidos"]) else " "
            print(f"  {sonda['id']} [{marca_esp}{marca_pro}] {sonda['texto'][:44]:44s} -> {top}")
        print(f"  {'umbral':>8s} {'aciertos':>9s} {'falsos':>7s} {'huerfanas':>10s} {'F':>4s}")
        mejor = None
        for u in UMBRALES:
            a, f, h = metricas(sondas, rankings, u)
            fscore = a - f
            marca = ""
            if mejor is None or fscore > mejor[1] or (fscore == mejor[1] and u > mejor[0]):
                mejor = (u, fscore)
            print(f"  {u:>8.2f} {a:>9d} {f:>7d} {h:>10d} {fscore:>4d}")
        print(f"  mejor umbral del modo: {mejor[0]:.2f} (F={mejor[1]})\n")

    print("El modo y umbral ganadores se eligen por F (aciertos - falsos); a igual F, "
          "umbral más alto (mejor huérfana honesta que falso resonante).")


if __name__ == "__main__":
    asyncio.run(main())
