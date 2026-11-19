"""
Modelo DELEGADO por MCP: el escalón que hace que Concordia (o cualquier engine
que pida un `language_model`) razone con el modelo del CLIENTE, no con una API
directa (06_motor_simulacion §2.1; WP-16).

La idea (probada en terreno con sesiones de Gemini Code / Codex): no se conecta
Concordia a un LLM por clave de API; se parcha su interfaz de modelo para que
cada `sample_text`/`sample_choice` DELEGUE el razonamiento al cliente MCP. La
librería llama a `sample_text` desde adentro de su bucle; el método deja el
prompt en un buzón y BLOQUEA; el cliente (el LLM que orquesta la sesión) toma el
pedido, razona y devuelve; la librería sigue. Así la inteligencia queda en el
BORDE (el cliente), no en el centro ni en un servicio remoto: es exactamente el
patrón de Rizoma ("el cliente propone, el validador filtra").

El buzón admite dos transportes con el mismo protocolo (pedido -> el cliente
responde -> respuesta): un directorio de archivos (multi-proceso, para correr y
testear sin red) o un `BuzonEnMemoria` (delegacion.py), que es el que sirven
las tools MCP del nodo (`corrida_pedidos` / `corrida_responder`, 09 §2.6).

Invariantes (INV-17/11): la frontera envuelve las DOS direcciones. Ni identidades
entran al prompt que se delega, ni identidades salen en la respuesta que vuelve
al estado. La memoria muere con la corrida (INV-07): el buzón es efímero.
"""
import json
import os
import time
import uuid
from pathlib import Path

from packages.domain import frontera

try:
    from concordia.language_model import language_model as _lm
    _Base = _lm.LanguageModel
except Exception:  # la librería es opcional; sin ella el modelo igual sirve por duck-typing
    _Base = object


class DelegacionExpirada(Exception):
    """El cliente no respondió el pedido delegado dentro del plazo."""


def _es_buzon_objeto(buzon) -> bool:
    return hasattr(buzon, "depositar_pedido")


def pedidos_pendientes(buzon):
    """Pedidos sin respuesta, en orden. Lo usa el cliente (o un responder de
    test) para saber qué razonar. Acepta ambos transportes."""
    if _es_buzon_objeto(buzon):
        return buzon.pedidos_pendientes()
    buzon = Path(buzon)
    pend = []
    for req in sorted(buzon.glob("req_*.json")):
        rid = req.stem[len("req_"):]
        if not (buzon / f"resp_{rid}.json").exists():
            pend.append(json.loads(req.read_text()))
    return pend


def responder(buzon, rid: str, *, text: str = None, idx: int = None) -> None:
    """El cliente deposita su razonamiento. Acepta ambos transportes; en
    archivos la escritura es atómica (tmp + rename)."""
    if _es_buzon_objeto(buzon):
        buzon.responder(rid, text=text, idx=idx)
        return
    buzon = Path(buzon)
    payload = {"id": rid}
    if text is not None:
        payload["text"] = text
    if idx is not None:
        payload["idx"] = idx
    tmp = buzon / f".resp_{rid}.tmp"
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, buzon / f"resp_{rid}.json")


class ModeloDelegadoMCP(_Base):
    """language_model de Concordia cuyo razonamiento lo sirve el cliente MCP por
    un buzón. No hay LLM local ni clave de API: el modelo es el cliente."""

    def __init__(self, buzon, timeout_s: float = 900.0, poll_s: float = 0.2):
        if _es_buzon_objeto(buzon):
            self._buzon = buzon          # BuzonEnMemoria (delegacion.py)
        else:
            self._buzon = Path(buzon)    # directorio de archivos
            self._buzon.mkdir(parents=True, exist_ok=True)
        self._timeout = timeout_s
        self._poll = poll_s

    def _nuevo_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _pedir(self, req: dict) -> dict:
        if _es_buzon_objeto(self._buzon):
            rid = self._buzon.depositar_pedido(req)
            try:
                return self._buzon.esperar_respuesta(rid, self._timeout)
            except TimeoutError as exc:
                raise DelegacionExpirada(str(exc))
        rid = self._nuevo_id()
        req["id"] = rid
        tmp = self._buzon / f".req_{rid}.tmp"
        tmp.write_text(json.dumps(req))
        os.replace(tmp, self._buzon / f"req_{rid}.json")
        resp = self._buzon / f"resp_{rid}.json"
        limite = time.time() + self._timeout
        while not resp.exists():
            if time.time() > limite:
                raise DelegacionExpirada(f"el cliente no respondió el pedido {rid}")
            time.sleep(self._poll)
        return json.loads(resp.read_text())

    def sample_text(self, prompt, *, max_tokens=5000, terminators=(), temperature=1.0,
                    top_p=0.95, top_k=64, timeout=60, seed=None) -> str:
        frontera.validar_salida({"prompt": prompt})  # ni identidades se delegan
        resp = self._pedir({"kind": "text", "prompt": prompt,
                            "terminators": list(terminators), "max_tokens": max_tokens})
        text = resp.get("text", "")
        frontera.validar_salida({"salida": text})  # ni identidades vuelven al estado
        return text

    def sample_choice(self, prompt, responses, *, seed=None):
        responses = list(responses)
        frontera.validar_salida({"prompt": prompt, "responses": responses})
        resp = self._pedir({"kind": "choice", "prompt": prompt, "responses": responses})
        idx = int(resp.get("idx", 0))
        idx = max(0, min(idx, len(responses) - 1))
        return idx, responses[idx], {}
