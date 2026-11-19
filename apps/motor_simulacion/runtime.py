"""
El puerto del runtime de corrida (06_motor_simulacion §2.1, escalón; WP-16).

Una corrida necesita alguien que semiotice: produzca los actos de los agentes
desde su contexto, y lea las tensiones del transcript. QUIÉN lo hace es un
escalón de la escalera de soberanía de modelo, y todos hablan la MISMA interfaz
(este puerto), así que enchufar uno u otro no cambia el resto del sistema:

- `RuntimeClienteMCP`: el modo por defecto (cliente-en-el-bucle). No produce
  local: el cliente MCP externo del operador semiotiza vía tools, con su modelo.
  Es la engine DISTRIBUIDA (cada mente es un cliente; nadie orquesta al centro).
- `RuntimeConcordia`: escalón opcional (runtime_concordia.py). Hospeda la corrida
  en la librería Concordia con el modelo del operador. Es una engine
  CENTRALIZADA (un proceso orquesta a los agentes), local a ese operador.
- `RuntimeStub`: runtime determinista, sin modelo, para tests y demos.

Reglas que TODO runtime respeta (INV-07/17): recibe contexto pseudonimizado (sin
identidades), sus salidas pasan los validadores del nodo antes de tocar el
estado, y su memoria muere con la corrida (jamás persiste checkpoints).
"""
from typing import Protocol, runtime_checkable

from packages.domain import frontera


@runtime_checkable
class RuntimeCorrida(Protocol):
    """El contrato del escalón. Un runtime produce actos y lee tensiones; el
    nodo mantiene el estado y valida. El runtime no ve identidades ni persiste."""

    nombre: str

    def disponible(self) -> bool:
        """¿Está el runtime listo para correr? (una librería instalada, un
        modelo configurado). Si no, el operador degrada a otro escalón."""
        ...

    def producir_acto(self, contexto_ronda: dict) -> dict:
        """Dado el contexto pseudonimizado de un turno, produce el acto del
        agente (descripcion + costo). El nodo lo valida contra el inventario."""
        ...

    def analizar_tensiones(self, transcript: list, marco: str) -> list:
        """Del transcript de la corrida, produce tensiones por ROL con evidencia
        citada. El nodo las valida (frontera, esquema) antes de persistir."""
        ...


class RuntimeStub:
    """Runtime determinista sin modelo: para tests y demos aleatorias. Produce
    un acto material posible y una tensión mínima. No hay latencia de tokens
    porque no hay LLM: útil para comparar la MECÁNICA sin el costo del modelo."""

    nombre = "stub"

    def disponible(self) -> bool:
        return True

    def producir_acto(self, contexto_ronda: dict) -> dict:
        inventario = contexto_ronda.get("inventario", {})
        recurso = next((r for r, c in inventario.items() if c > 0), None)
        rol = contexto_ronda.get("rol", "agente")
        return {"descripcion": f"{rol} usa lo que hay",
                "costo": {recurso: 1} if recurso else {}}

    def analizar_tensiones(self, transcript: list, marco: str) -> list:
        roles = sorted({t[1] for t in transcript if len(t) > 1}) if transcript else []
        if len(roles) < 2:
            return []
        return [{"tipo": "coordinación pendiente", "roles": roles[:2],
                 "evidencia": f"{roles[0]}: 'esto no se está resolviendo solo'"}]


class RuntimeClienteMCP:
    """El modo por defecto: el cliente MCP externo semiotiza. Este runtime no
    produce nada localmente; señala que el bucle espera al cliente (la engine
    distribuida). Existe para que el puerto sea uniforme."""

    nombre = "cliente_mcp"

    def disponible(self) -> bool:
        return True

    def producir_acto(self, contexto_ronda: dict) -> dict:
        raise RuntimeExterno("el acto lo produce el cliente MCP vía tools (bucle distribuido)")

    def analizar_tensiones(self, transcript: list, marco: str) -> list:
        raise RuntimeExterno("las tensiones las lee el cliente MCP vía tools")


class RuntimeExterno(Exception):
    """El runtime delega en el cliente externo: no hay producción local."""


def validar_salida_runtime(obj) -> None:
    """Todo lo que un runtime produce pasa la frontera antes de tocar el estado
    (INV-17), igual que lo que devuelve un cliente MCP."""
    frontera.validar_salida(obj)


def crear_runtime(nombre: str = "cliente_mcp"):
    """Selección por config (nodo.toml [modelos] runtime_corridas). Sin nombre o
    'cliente_mcp' = engine distribuida por defecto; 'stub' = demo; 'concordia' =
    escalón local (requiere la librería)."""
    nombre = (nombre or "cliente_mcp").strip().lower()
    if nombre in ("", "cliente_mcp", "mcp"):
        return RuntimeClienteMCP()
    if nombre == "stub":
        return RuntimeStub()
    if nombre == "concordia":
        from apps.motor_simulacion.runtime_concordia import RuntimeConcordia
        return RuntimeConcordia()
    raise ValueError(f"runtime desconocido: {nombre} (cliente_mcp | stub | concordia)")
