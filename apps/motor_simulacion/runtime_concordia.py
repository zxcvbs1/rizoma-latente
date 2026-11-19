"""
Escalón Concordia: la engine CENTRALIZADA de simulación, como runtime opcional
(06_motor_simulacion §2.1; WP-16). Para COMPARAR con el cliente-en-el-bucle
distribuido bajo la misma interfaz (runtime.py).

Concordia (Google DeepMind) orquesta agentes generativos en UN proceso: cada
agente tiene memoria asociativa y plan, y un Game Master compone la escena. Su
ventaja frente al motor distribuido es la gestión de memoria: recupera solo los
recuerdos relevantes por turno (prompts más cortos, menos tokens, menos
latencia), en vez de reconstruir la mente entera cada ronda. Su costo: es
centralizado (un proceso, un modelo) y pesado.

Verificado contra `gdm-concordia==2.4.0` (pin en nodo.toml). El mapeo de este
adaptador a la API real está probado en tests/test_runtime_concordia_real.py y
CORRE acá con el embedder local del nodo: la mecánica ejecuta de verdad. Lo que
falta para una corrida con CONTENIDO no es el mapeo sino el modelo: sin un LLM
que Concordia pueda llamar como función (`sample_text`), la generación sale
vacía. En este entorno el único modelo local es el embedder (nomic-embed-text),
que no genera; un LLM exige una clave de API + red, o un modelo local de
generación. Sin eso, `disponible()` es False y el operador degrada al runtime
cliente-en-el-bucle.

Modo RICO por defecto (corrección jul 2026 del playtest de capitalismo de
vigilancia: el modo liviano que había quedado por defecto perdía la memoria
asociativa y el autor notó la pérdida de precisión). El default usa el
prefab entity.basic entero (memoria asociativa + plan + estado, 4 llamadas
por acto): más preciso, pero con humano-en-el-loop cada round-trip de
sample_text son ~18s, así que un arco largo TARDA (avisale a la persona y
sugerí servir en un subagente de fondo). Modo LIVIANO (`liviano=True`,
opt-in): produce el acto con UNA sola llamada (rol + disposiciones +
situación/último acto, sin memoria ni plan): Concordia SIGUE conduciendo
turnos y orden (código determinista del nodo), lo que baja es cuántas veces
se pide razonamiento al modelo por acto; más rápido, más chato. Usalo cuando
priorices velocidad sobre precisión.

Reglas duras que este adaptador impone sobre Concordia (INV-07/17/11):
- Los agentes se construyen desde DISPOSICIONES (reglas de conducta), jamás
  desde topologías ni identidades: el contexto ya viene pseudonimizado por rol.
- La memoria asociativa usa el embedder LOCAL del nodo (nomic-embed-text), no un
  servicio remoto (INV-11).
- La interfaz de modelo de la librería va envuelta por el filtro de frontera, en
  `sample_text` Y en `sample_choice`: nada con identidades entra al prompt, nada
  con identidades sale al estado.
- La memoria muere con la corrida: prohibido persistir checkpoints (INV-07).
"""
import importlib.util
import os

from packages.domain import frontera


DISPOSICIONES_MAX = 8  # con un mapa grande, tantas reglas por prompt lo inflan sin sumar


def _concordia_instalada() -> bool:
    return importlib.util.find_spec("concordia") is not None


class RuntimeConcordia:
    nombre = "concordia"

    def __init__(self, modelo=None, embedder=None, liviano: bool = True):
        # El modelo y el embedder los inyecta el operador; el embedder por
        # defecto es el local del nodo (INV-11). `liviano` (default True,
        # corrección jul 2026, de medir la lentitud con Gemini a mano): el
        # modo liviano hace UNA llamada por acto CON la historia del arco en
        # el prompt (rápido y coherente); es la única forma viable si la mente
        # es un humano sirviendo cada pedido (~18s por round-trip). liviano=
        # False es el modo rico: memoria asociativa + plan de Concordia (4
        # llamadas por acto), que ahora SÍ persiste el agente entre actos (el
        # bug era que lo reconstruía vacío cada vez); más fino pero
        # insoportablemente lento con un humano a mano, para engines
        # automáticas rápidas. Concordia conduce turnos y orden en los dos.
        self._modelo = modelo
        self._embedder = embedder
        self.liviano = liviano
        self._agentes = {}  # rol -> agente Concordia, persiste en el run para que su memoria acumule
        self._version_pin = os.getenv("RIZOMA_CONCORDIA_PIN", "")

    @classmethod
    def con_delegacion(cls, buzon, embedder=None, liviano: bool = True, **kw):
        """El escalón recomendado: Concordia con el razonamiento DELEGADO al
        cliente MCP por un buzón (modelo_delegado.py). Sin clave de API ni LLM
        local: el modelo es el cliente. Es la vía que hace que un cliente MCP
        pueda ser la engine de Concordia (WP-16). liviano=True por defecto:
        una llamada por acto con la historia del arco (viable con un humano a
        mano); liviano=False es el rico, 4 llamadas, para engines automáticas."""
        from apps.motor_simulacion.modelo_delegado import ModeloDelegadoMCP
        return cls(modelo=ModeloDelegadoMCP(buzon, **kw), embedder=embedder, liviano=liviano)

    def disponible(self) -> bool:
        return _concordia_instalada() and self._modelo is not None

    def describir(self) -> dict:
        """Comparación honesta sin correr: qué aporta y qué exige, frente al
        runtime distribuido."""
        return {
            "engine": "centralizada (un proceso orquesta a los agentes)",
            "ventaja": ("gestión de memoria asociativa: recupera lo relevante por "
                        "turno, prompts más cortos, menos tokens y menos latencia"),
            "costo": "librería pesada + un LLM; centralizado y local a un operador",
            "frente_al_distribuido": ("el runtime distribuido (cliente-en-el-bucle) "
                                      "reparte el cómputo entre MCPs y no orquesta al "
                                      "centro; Concordia no coordina humanos reales, "
                                      "simula dobles en un proceso"),
            "requiere": "pip install gdm-concordia + un modelo; pin de versión",
            "instalada": _concordia_instalada(),
            "genera": self._modelo is not None,  # sin modelo, la mecánica corre pero no hay contenido
        }

    def _envolver_modelo(self):
        """El language_model de Concordia, envuelto por la frontera: cada prompt
        de entrada y cada salida pasan `validar_salida` (ni identidades ni
        material privado cruzan la interfaz de modelo, INV-17). Se envuelven los
        DOS métodos de la interfaz real (2.4.0): `sample_text` y `sample_choice`."""
        if self._modelo is None:
            raise ConcordiaNoDisponible("falta el modelo (language_model) del operador")

        modelo = self._modelo

        class _ModeloConFrontera:
            def sample_text(self, prompt, **kw):
                frontera.validar_salida({"prompt": prompt})  # ni identidades entran
                salida = modelo.sample_text(prompt, **kw)
                frontera.validar_salida({"salida": salida})  # ni identidades salen
                return salida

            def sample_choice(self, prompt, responses, **kw):
                frontera.validar_salida({"prompt": prompt, "responses": list(responses)})
                return modelo.sample_choice(prompt, responses, **kw)

        return _ModeloConFrontera()

    def _construir_memoria(self):
        """La memoria asociativa de Concordia con NUESTRO embedder local (INV-11).
        Sin embedder inyectado, el operador debe pasar el del nodo."""
        if self._embedder is None:
            raise ConcordiaNoDisponible("falta el embedder local del nodo (INV-11)")
        if not _concordia_instalada():
            raise ConcordiaNoDisponible("gdm-concordia no está instalada")
        from concordia.associative_memory import basic_associative_memory
        return basic_associative_memory.AssociativeMemoryBank(sentence_embedder=self._embedder)

    def _construir_agente(self, rol: str, disposiciones, marco_reglas=None):
        """Un rol se vuelve un agente Concordia desde sus disposiciones (reglas
        condicionales de conducta), jamás desde una topología o una identidad.
        Mapeo verificado contra la 2.4.0: prefab `entity.basic` + memoria con
        embedder local + modelo envuelto por la frontera. El agente se
        construye UNA vez por rol (persiste en el run): si hay lente, entra en
        su identidad desde el arranque (corrección jul 2026: la lente viaja al
        pedido, no solo al prompt por turno)."""
        frontera.validar_salida({"rol": rol, "disposiciones": disposiciones})
        if not _concordia_instalada():
            raise ConcordiaNoDisponible("gdm-concordia no está instalada")
        from concordia.prefabs.entity import basic as entity_basic
        meta = disposiciones if isinstance(disposiciones, str) else "; ".join(
            list(disposiciones)[:DISPOSICIONES_MAX])
        if marco_reglas and (marco_reglas.get("estresa") or marco_reglas.get("nombre")):
            description = (f"rol de una corrida de Rizoma bajo la lente "
                           f"{marco_reglas.get('nombre', '')}: {marco_reglas.get('estresa', '')}")
        else:
            description = "rol de una corrida de Rizoma, desde disposiciones (sin identidad)"
        prefab = entity_basic.Entity(
            description=description,
            params={"name": rol, "goal": meta},
        )
        return prefab.build(model=self._envolver_modelo(), memory_bank=self._construir_memoria())

    def producir_acto(self, contexto_ronda: dict) -> dict:
        if not self.disponible():
            raise ConcordiaNoDisponible(
                "Concordia no está disponible; el operador degrada a runtime cliente_mcp")
        rol = contexto_ronda.get("rol", "agente")
        disposiciones = contexto_ronda.get("disposiciones", "")
        situacion = contexto_ronda.get("situacion")
        historial = contexto_ronda.get("historial")
        marco_reglas = contexto_ronda.get("marco_reglas")
        inventario = contexto_ronda.get("inventario")
        if situacion:
            frontera.validar_salida({"situacion": situacion})
        if self.liviano:
            return self._producir_acto_liviano(rol, disposiciones, situacion, historial,
                                               marco_reglas=marco_reglas, inventario=inventario)
        from concordia.typing import entity as entity_lib
        # El agente persiste por rol durante el run para que su memoria
        # asociativa ACUMULE (el bug era reconstruirlo vacío en cada acto).
        agente = self._agentes.get(rol)
        if agente is None:
            agente = self._construir_agente(rol, disposiciones, marco_reglas=marco_reglas)
            self._agentes[rol] = agente
        if situacion:
            agente.observe(situacion)
        acto = agente.act(entity_lib.free_action_spec(
            call_to_action=f"¿Qué hace {rol} este turno?"))
        frontera.validar_salida({"acto": acto})  # nada con identidad toca el estado
        # El costo lo mapean los validadores del nodo contra el inventario: el
        # runtime solo semiotiza, no decide legitimidad (INV-19).
        return {"descripcion": acto, "costo": {}}

    def _producir_acto_liviano(self, rol: str, disposiciones, situacion, historial=None,
                               marco_reglas=None, inventario=None) -> dict:
        """Modo por defecto: UNA llamada a sample_text, con la HISTORIA del
        arco en el prompt (los actos previos) para que cada acto tenga
        continuidad sin las 4 llamadas del rico. Rápido y coherente: el único
        lever contra la latencia del cliente a mano es hacer menos requests.
        Pasa por la MISMA frontera de entrada y salida (INV-17). Corrección
        jul 2026 (diagnóstico de corridas chatas): la lente (marco_reglas) y
        el inventario viajan en el prompt, y se pide una ESCENA, no una línea:
        una corrida ciega de lente producía actos chatos aunque la lente
        fuera riquísima."""
        frontera.validar_salida({"rol": rol, "disposiciones": disposiciones})
        disp = disposiciones if isinstance(disposiciones, str) else "; ".join(
            list(disposiciones)[:DISPOSICIONES_MAX])
        lineas = []
        if marco_reglas and (marco_reglas.get("estresa") or marco_reglas.get("nombre")):
            crisis = "; ".join(marco_reglas.get("crisis_tipicas", []))
            lineas.append(f"La lente que tiñe esta corrida: {marco_reglas.get('nombre', '')}. "
                          f"Lo que estresa: {marco_reglas.get('estresa', '')}."
                          + (f" Crisis típicas: {crisis}." if crisis else ""))
        lineas.append(f"Situación semilla: {situacion or 'sin situación previa'}.")
        if historial:
            recientes = "\n".join(f"- {h}" for h in list(historial)[-6:])
            lineas.append(f"Lo que viene pasando:\n{recientes}")
        if inventario:
            lineas.append("Lo material a mano: " + ", ".join(
                f"{k}={v}" for k, v in list(inventario.items())[:8]) + ".")
        lineas.append(f"Rol: {rol}. Sus disposiciones: {disp or 'ninguna declarada'}.")
        lineas.append(
            f"Componé la ESCENA de {rol} en este turno: 3 a 5 frases, tercera "
            "persona, SOLO roles. Un gesto concreto con su detalle material, qué "
            "cambia en la situación, y algo que quede en juego para el próximo "
            "turno. Bajo la lente declarada: que la escena la encarne, no que la "
            "cite. Nada de resúmenes ni una sola línea: es una escena, no un log.")
        prompt = "\n".join(lineas)
        acto = self._envolver_modelo().sample_text(prompt)
        frontera.validar_salida({"acto": acto})
        return {"descripcion": acto, "costo": {}}

    def analizar_tensiones(self, transcript: list, marco: str) -> list:
        """Decisión híbrida (06 §2.1, jul 2026): las tensiones las lee SIEMPRE
        el cliente-en-el-bucle, aun cuando los actos corren en Concordia. La
        orquestación de la escena puede centralizarse; la lectura del desvío
        no, porque lo interpretativo vive en el borde. Declina por diseño, no
        por falta: la misma señal que el runtime distribuido."""
        from apps.motor_simulacion.runtime import RuntimeExterno
        raise RuntimeExterno(
            "las tensiones las lee el cliente MCP vía tools (híbrido por diseño)")


class ConcordiaNoDisponible(Exception):
    """La librería o el modelo faltan: degradar al runtime cliente-en-el-bucle."""
