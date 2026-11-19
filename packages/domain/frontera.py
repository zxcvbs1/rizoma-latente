"""
Frontera de datos (WP-15, INV-17).

Todo contexto que el nodo sirve a un cliente que semiotiza pasa por acá, y
toda lectura que un cliente devuelve también: pseudonimización (roles, jamás
llaves ni nombres), contexto mínimo por operación, y fallo CERRADO: ante una
identidad donde no corresponde, la operación no ocurre y el incidente queda
a la vista del caller.
"""
import re

PATRON_LLAVE = re.compile(r"0x[a-fA-F0-9]{40}")

# Alias del protocolo: identidad legible tipo:nombre (mcp:antigravity,
# jugador:ejemplo). El nombre pegado a los dos puntos, sin espacio: "el
# jugador: que no llegaba" no es un alias.
PATRON_ALIAS = re.compile(r"\b(?:mcp|jugador|operador):\S+")

# Un campo cuyo NOMBRE declara identidad no cruza, valga lo que valga.
CLAVES_IDENTIDAD = ("identidad", "autor", "actor_id", "agent_id", "llave", "firma", "signature")


class FronteraViolada(Exception):
    """Una llave o identidad intentó cruzar donde solo pasan roles."""


def contiene_identidades(texto) -> bool:
    return bool(PATRON_LLAVE.search(texto or "") or PATRON_ALIAS.search(texto or ""))


def _recorrer(obj, camino=""):
    if isinstance(obj, str):
        if contiene_identidades(obj):
            raise FronteraViolada(f"llave detectada en {camino or 'raíz'}")
    elif isinstance(obj, dict):
        for clave, valor in obj.items():
            if str(clave).lower() in CLAVES_IDENTIDAD:
                raise FronteraViolada(f"campo de identidad en {camino}.{clave}")
            if contiene_identidades(str(clave)):
                raise FronteraViolada(f"llave detectada en clave {camino}.{clave}")
            _recorrer(valor, f"{camino}.{clave}" if camino else str(clave))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _recorrer(item, f"{camino}[{i}]")


def filtrar_contexto(contexto: dict, campos_permitidos) -> dict:
    """Contexto mínimo por operación: solo los campos que el turno exige, y
    ninguno puede portar identidades."""
    limpio = {campo: contexto[campo] for campo in campos_permitidos if campo in contexto}
    _recorrer(limpio)
    return limpio


def validar_salida(obj) -> None:
    """Nada de lo que un cliente devuelve se persiste sin pasar por acá: una
    lectura con llaves o nombres de actor no toca el estado."""
    _recorrer(obj)


# Material que JAMÁS sale en una respuesta pública, aunque la intención sea
# pública y lleve su actor_id (llave pública). Frontera de SALIDA (T-02, INV-17).
CLAVES_PRIVADAS = ("content_vector", "vector", "embedding", "topologia", "topología",
                   "mapa", "deslizamiento", "token", "private_key", "privatekey",
                   "disposiciones", "prediccion", "predicción", "marcador")


def validar_respuesta_publica(obj) -> None:
    """Las intenciones son públicas y llevan su actor_id, así que acá NO se
    rechazan llaves; pero jamás se filtra material privado (vectores, mapas,
    topologías, tokens, predicciones) por un campo que se haya colado."""
    _recorrer_publico(obj)


def _recorrer_publico(obj, camino="") -> None:
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            bajo = str(clave).lower()
            if any(p in bajo for p in CLAVES_PRIVADAS):
                raise FronteraViolada(f"campo privado en respuesta pública: {camino}.{clave}")
            _recorrer_publico(valor, f"{camino}.{clave}" if camino else str(clave))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _recorrer_publico(item, f"{camino}[{i}]")
