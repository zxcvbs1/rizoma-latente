"""
Federación desde el cliente (WP-10; 01_red §8, INV-11).

El nodo no federa: sirve su lectura local y nada más. El CLIENTE consulta N
nodos (su lista propia, compartible como texto plano), mergea LOCALMENTE y
decide su propia lectura. Sin registro central de nodos: este módulo no toca
ninguna base; su única fuente es la lista que el cliente trae.

La divergencia entre nodos no se resuelve: se muestra. Que dos embedders lean
distinto la misma intención es una propiedad, no un bug.
"""
import asyncio

import httpx


def parse_lista_nodos(texto: str) -> list:
    """La lista de nodos viaja como texto plano (comas o líneas), compartible
    por cualquier canal. Deduplica y normaliza."""
    urls = []
    for cruda in (texto or "").replace("\n", ",").split(","):
        url = cruda.strip().rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls


def mergear(respuestas: dict, limite: int = 10) -> dict:
    """Merge LOCAL de las respuestas {url: {"results": [...]}}: agrupa por id
    de intención conservando TODAS las lecturas (cada nodo leyó con su propio
    embedder), y ordena por la mejor lectura de cada una."""
    por_id = {}
    for nodo, cuerpo in respuestas.items():
        for item in (cuerpo or {}).get("results", []):
            intencion = item.get("node") or {}
            iid = intencion.get("id") or f"{nodo}:{len(por_id)}"
            entrada = por_id.setdefault(iid, {"intencion": intencion, "lecturas": []})
            entrada["lecturas"].append({"nodo": nodo, "score": item.get("score")})

    resultados = []
    for entrada in por_id.values():
        entrada["lecturas"].sort(key=lambda lectura: -(lectura["score"] or 0.0))
        entrada["mejor_score"] = entrada["lecturas"][0]["score"]
        entrada["divergencia"] = len(entrada["lecturas"]) > 1
        resultados.append(entrada)
    resultados.sort(key=lambda entrada: -(entrada["mejor_score"] or 0.0))
    return {"resultados": resultados[:limite]}


async def consultar_nodos(urls: list, q: str, limite: int = 10, fetch=None) -> dict:
    """Consulta todos los nodos de la lista en paralelo. Un nodo caído no
    voltea la lectura: simplemente no participa de ella."""
    async def _fetch_httpx(url):
        async with httpx.AsyncClient(timeout=5.0) as cliente:
            respuesta = await cliente.get(f"{url}/search", params={"q": q, "limit": limite})
            respuesta.raise_for_status()
            return respuesta.json()

    fetch = fetch or _fetch_httpx
    resultados = await asyncio.gather(*(fetch(url) for url in urls), return_exceptions=True)

    respuestas, respondieron, caidos = {}, [], []
    for url, resultado in zip(urls, resultados):
        if isinstance(resultado, Exception):
            caidos.append(url)
        else:
            respuestas[url] = resultado
            respondieron.append(url)

    merged = mergear(respuestas, limite)
    merged["nodos_consultados"] = list(urls)
    merged["nodos_respondieron"] = respondieron
    merged["nodos_caidos"] = caidos
    merged["nota"] = ("cada score es la lectura del embedder de SU nodo; "
                      "la divergencia es una propiedad, no un bug (INV-11)")
    return merged
