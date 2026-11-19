"""
La cola de razonamiento delegado (09_procomun §2.6; WP-23 segundo modo).

Cuando una engine hospedada en el nodo (el runtime Concordia) necesita que un
modelo piense, deposita un pedido en la cola de su corrida y bloquea. Los
clientes del pool la consultan por las tools MCP (`corrida_pedidos` /
`corrida_responder`) y sirven: pull, jamás push (INV-19). Una cola con un solo
consumidor es un pool válido; la descentralización no se activa, se puebla.

Contrato duro del tránsito (09 §2.6, §5): los pedidos portan el encuadre de la
corrida (transcript en potencia). Viven SOLO en memoria, mueren con la corrida
(`cerrar_corrida` cierra la cola), y ningún store tiene columnas capaces de
retenerlos: el pedido delegado no tiene modelo SQLAlchemy a propósito. La
auditoría de mal alimento (`auditar_transito`) verifica que ninguna cola
sobreviva a su corrida.

Identidad: el acto es del ROL. La cola cuenta cuántos pedidos sirvió cada llave
(contador agregado, en memoria, para el peso de contribución de 09 §4) pero
JAMÁS vincula una respuesta con la llave que la razonó (INV-04): la respuesta
se entrega a la engine sin procedencia.
"""
import threading
import uuid


class ColaCerrada(Exception):
    """La corrida murió mientras la engine esperaba: degradar o abortar."""


class GradienteIncompleto(Exception):
    """La corrida cara no está cubierta: la engine no puede pedir razonamiento
    todavía (09 §2.6). No es un error del pool, es el umbral trabajando."""


class BuzonEnMemoria:
    """El buzón del transporte en memoria (mismo protocolo que el de archivos
    de modelo_delegado.py: pedido -> el cliente responde -> respuesta).

    Gradiente (09 §2.6): con `presupuesto_estimado` > 0 la cola nace `propuesta`
    y NO acepta pedidos hasta que los presupuestos declarados la cubren
    (`cubierta`); el primer pedido depositado la vuelve `activa`. Con 0 (corrida
    barata) nace `activa` directo. La garantía es física: la engine no puede
    pedir razonamiento a una corrida sin cobertura."""

    def __init__(self, presupuesto_estimado: int = 0):
        self._cond = threading.Condition()
        self._pedidos = {}     # rid -> pedido (dict)
        self._respuestas = {}  # rid -> respuesta (dict)
        self._cerrado = False
        self.servidos = 0                  # contador agregado (persistible)
        self._servidos_por_llave = {}      # solo memoria; se cosecha al cierre (09 §4)
        self.presupuesto_estimado = max(0, int(presupuesto_estimado))
        self._presupuestos = {}            # llave -> pedidos comprometidos (solo memoria)
        self._estado = "activa" if self.presupuesto_estimado == 0 else "propuesta"
        self.actos = []                    # lo producido por la engine (muere con la cola)

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def comprometido(self) -> int:
        with self._cond:
            return sum(self._presupuestos.values())

    def declarar_presupuesto(self, llave: str, pedidos: int) -> dict:
        """El consentimiento del umbral: la llave compromete cuántos pedidos
        presta. Declarar de nuevo REEMPLAZA (bajar a 0 es retirarse); si la
        cobertura cae antes de activarse, la corrida vuelve a `propuesta`.
        Una vez activa, el retiro no la frena: degrada por timeouts."""
        with self._cond:
            if self._cerrado:
                raise ColaCerrada("la cola está cerrada; la corrida murió")
            llave = (llave or "").lower()
            if pedidos <= 0:
                self._presupuestos.pop(llave, None)
            else:
                self._presupuestos[llave] = int(pedidos)
            if self._estado != "activa":
                cubierta = sum(self._presupuestos.values()) >= self.presupuesto_estimado
                self._estado = "cubierta" if cubierta else "propuesta"
            self._cond.notify_all()
            return {"estado": self._estado,
                    "presupuesto_estimado": self.presupuesto_estimado,
                    "comprometido": sum(self._presupuestos.values())}

    def depositar_pedido(self, pedido: dict) -> str:
        with self._cond:
            if self._cerrado:
                raise ColaCerrada("la cola está cerrada; la corrida murió")
            if self._estado == "propuesta":
                raise GradienteIncompleto(
                    f"corrida sin cobertura: {sum(self._presupuestos.values())}"
                    f"/{self.presupuesto_estimado} pedidos comprometidos")
            self._estado = "activa"
            rid = pedido.get("id") or uuid.uuid4().hex[:12]
            pedido["id"] = rid
            self._pedidos[rid] = pedido
            self._cond.notify_all()
            return rid

    def pedidos_pendientes(self) -> list:
        with self._cond:
            return [dict(p) for rid, p in sorted(self._pedidos.items())
                    if rid not in self._respuestas]

    def responder(self, rid: str, *, text=None, idx=None, llave: str = "") -> bool:
        """El cliente deposita su razonamiento. La respuesta NO guarda la llave:
        el contador agregado es el único rastro (y muere con la cola)."""
        with self._cond:
            if self._cerrado or rid not in self._pedidos or rid in self._respuestas:
                return False
            respuesta = {"id": rid}
            if text is not None:
                respuesta["text"] = text
            if idx is not None:
                respuesta["idx"] = idx
            self._respuestas[rid] = respuesta
            self.servidos += 1
            if llave:
                clave = llave.lower()
                self._servidos_por_llave[clave] = self._servidos_por_llave.get(clave, 0) + 1
            self._cond.notify_all()
            return True

    def esperar_respuesta(self, rid: str, timeout_s: float) -> dict:
        """La engine bloquea acá. Si la cola se cierra mientras espera, la
        espera termina con ColaCerrada (la corrida murió, INV-07)."""
        with self._cond:
            resto = timeout_s
            while rid not in self._respuestas:
                if self._cerrado:
                    raise ColaCerrada("la corrida cerró mientras la engine esperaba")
                if resto <= 0:
                    raise TimeoutError(f"el pool no respondió el pedido {rid}")
                import time
                inicio = time.monotonic()
                self._cond.wait(timeout=min(resto, 1.0))
                resto -= time.monotonic() - inicio
            return dict(self._respuestas[rid])

    def cerrar(self) -> dict:
        """Muerte del tránsito: borra pedidos, respuestas y presupuestos, y
        despierta a los que esperan. Devuelve la COSECHA (llave -> pedidos
        servidos), lo único que puede salir vivo: un contador agregado para el
        peso de contribución (09 §4), jamás contenido."""
        with self._cond:
            cosecha = dict(self._servidos_por_llave)
            self._cerrado = True
            self._pedidos.clear()
            self._respuestas.clear()
            self._servidos_por_llave.clear()
            self._presupuestos.clear()
            self.actos.clear()
            self._cond.notify_all()
            return cosecha

    @property
    def cerrado(self) -> bool:
        return self._cerrado

    @property
    def vacio(self) -> bool:
        with self._cond:
            return not self._pedidos and not self._respuestas


# --- Registro por corrida (memoria del proceso del nodo) ---

_colas: dict = {}


def abrir_cola(corrida_id: str, presupuesto_estimado: int = 0) -> BuzonEnMemoria:
    if corrida_id not in _colas or _colas[corrida_id].cerrado:
        _colas[corrida_id] = BuzonEnMemoria(presupuesto_estimado)
    return _colas[corrida_id]


def cola(corrida_id: str):
    return _colas.get(corrida_id)


def cerrar_cola(corrida_id: str) -> dict:
    """Cierra y devuelve la cosecha (llave -> servidos) para acreditar peso."""
    buzon = _colas.pop(corrida_id, None)
    return buzon.cerrar() if buzon is not None else {}


def _turnos_del_presupuesto(corrida_id: str, db=None) -> int:
    """turnos<=0 pide el arco ENTERO de la corrida: su presupuesto_rondas
    (corrección jul 2026: el turnos=3 de antes era un resabio de la demo,
    no una decisión sobre el arco). Si no viene sesión (la engine demo no
    la exige por diseño), abre una propia solo para esta lectura puntual."""
    from packages.domain.models import Corrida
    sesion_propia = db is None
    if sesion_propia:
        from packages.domain.database import SessionLocal
        db = SessionLocal()
    try:
        corrida = db.query(Corrida).filter(Corrida.id == corrida_id).first()
        return corrida.presupuesto_rondas if corrida else 12
    finally:
        if sesion_propia:
            db.close()


def lanzar_engine_demo(corrida_id: str, turnos: int = 0,
                       rol: str = "la-que-riega",
                       situacion: str = "El pozo comunitario está casi seco.",
                       presupuesto_estimado: int = 0,
                       timeout_s: float = 600.0, db=None) -> BuzonEnMemoria:
    """Engine DEMO hospedada en el nodo: prueba la cola de punta a punta SIN
    Concordia (el contenedor no la trae; es opcional). Por turno compone un
    prompt corto (rol + situación + último acto) y BLOQUEA esperando que el
    pool razone. turnos<=0 (default) usa el presupuesto_rondas de la corrida
    (el arco entero); pasá `db` si ya tenés una sesión abierta (el endpoint
    la reusa), si no la demo abre una propia solo para esa lectura. Con
    presupuesto_estimado > 0 respeta el gradiente: espera la cobertura antes
    de poder depositar. Los actos viven en la cola y mueren con ella
    (tránsito efímero). La frontera envuelve ambas direcciones
    (ModeloDelegadoMCP). El corte de pared TOTAL ya no es fijo: se computa
    sobre turnos * timeout_s, así el corte real de un run vivo lo decide el
    per-pedido (DelegacionExpirada), no un reloj de pared ciego; el cierre
    honesto (arco_turnos/rondas_completadas/motivo_fin) queda en la memoria
    de la corrida si existe (la demo también corre sin corrida seedeada, en
    pruebas del buzón solo)."""
    import time
    if turnos <= 0:
        turnos = _turnos_del_presupuesto(corrida_id, db)
    buzon = abrir_cola(corrida_id, presupuesto_estimado)
    from apps.motor_simulacion.modelo_delegado import ModeloDelegadoMCP, DelegacionExpirada
    modelo = ModeloDelegadoMCP(buzon, timeout_s=timeout_s)

    from apps.motor_simulacion import motor as motor_sim
    memoria = motor_sim._corridas.get(corrida_id)
    if memoria is not None:
        memoria.arco_turnos = turnos
        memoria.rondas_completadas = 0
        memoria.motivo_fin = ""

    def bucle():
        historial = situacion
        limite_total = time.monotonic() + turnos * timeout_s
        for t in range(turnos):
            while True:  # el gradiente puede frenar el arranque: esperar cobertura
                try:
                    acto = modelo.sample_text(
                        f"Turno {t + 1} de {turnos}. Rol: {rol}. Situación: {historial}\n"
                        f"¿Qué hace {rol} este turno? Tercera persona, SOLO roles.")
                    break
                except GradienteIncompleto:
                    if time.monotonic() > limite_total:
                        if memoria is not None:
                            memoria.motivo_fin = "presupuesto de tiempo agotado esperando cobertura"
                        return
                    time.sleep(0.5)
                except DelegacionExpirada:
                    if memoria is not None:
                        memoria.motivo_fin = ("un pedido no fue respondido a tiempo "
                                              "(el cliente dejó de prestar la mente)")
                    return
                except ColaCerrada:
                    if memoria is not None:
                        memoria.motivo_fin = "la corrida se cerró durante la ejecución"
                    return
            with buzon._cond:
                if buzon.cerrado:
                    if memoria is not None:
                        memoria.motivo_fin = "la corrida se cerró durante la ejecución"
                    return
                buzon.actos.append(acto)
            historial = f"{historial} Luego: {acto[:160]}"
            if memoria is not None:
                memoria.rondas_completadas += 1
            if time.monotonic() > limite_total:
                if memoria is not None:
                    memoria.motivo_fin = "presupuesto de tiempo agotado"
                return
        if memoria is not None:
            memoria.motivo_fin = "arco completo"

    threading.Thread(target=bucle, daemon=True).start()
    return buzon


def _embedder_local():
    """Wrapper mínimo sobre el embedder LOCAL del nodo (nomic-embed-text vía
    Ollama, `packages/adapters/adapter.py`) para cumplir el contrato síncrono
    que pide la memoria asociativa de Concordia (texto -> vector), INV-11:
    nada de servicios remotos, el mismo embedder que ya usa el resto del nodo."""
    import asyncio

    import numpy as np

    from packages.adapters.adapter import OllamaAdapter

    adaptador = OllamaAdapter()

    def embed(texto: str):
        vector = asyncio.run(adaptador.generate_embedding(texto))
        return np.array(vector, dtype=np.float32)

    return embed


def lanzar_engine_concordia(db, corrida_id: str, turnos: int = 0,
                            situacion: str = "",
                            presupuesto_estimado: int = 0,
                            timeout_s: float = 1800.0,
                            liviano: bool = True) -> BuzonEnMemoria:
    """Engine POR DEFECTO (corrección jul 2026, del playtest del SimCity):
    Concordia orquesta turnos y memoria EN EL NODO (conducción determinista,
    el cliente no puede inventar mecánica) y el razonamiento va delegado a la
    cola (el cliente presta la mente, en personaje). turnos<=0 (default) usa
    el presupuesto_rondas de la corrida (el arco entero, no el resabio de
    turnos=3 de la demo). Exige POBLACIÓN: los agentes se construyen desde
    los roles de la corrida (dobles/sintéticos); una corrida despoblada no
    tiene de dónde armar agentes y rebota.

    Corrección jul 2026 (primer playtest de una corrida larga): el corte de
    pared ya no es un timeout TOTAL fijo (600s) que mutilaba un arco largo en
    silencio cuando el humano tardaba en contestar. El per-pedido sube a un
    default generoso (30 min: un humano puede tardar) y el corte de pared
    total se calcula sobre el tamaño real del arco (turnos * roles *
    timeout_s), así jamás corta un run que progresa; el que termina un run
    muerto es el per-pedido (DelegacionExpirada). El cierre declara
    honestamente cuántas rondas se completaron (memoria.rondas_completadas)
    de las pedidas (memoria.arco_turnos) y por qué terminó
    (memoria.motivo_fin), para que el GM no narre un arco que no corrió.

    `liviano` (default False, corrección jul 2026 del playtest de capitalismo
    de vigilancia: el modo liviano perdía precisión y el autor lo notó). El
    modo RICO (memoria asociativa + plan de Concordia) es el default, más
    preciso; un arco largo con un humano sirviendo a mano TARDA (avisale a la
    persona y sugerí servir en un subagente de fondo, ver corrida_estado para
    el pulso). liviano=True: una sola llamada a sample_text por acto en vez
    de las 4 del prefab entity.basic entero (memoria + plan + estado); con un
    humano sirviendo cada pedido (~18s por round-trip) baja la espera casi
    4x, pero sale más chato. Usalo cuando priorices velocidad sobre precisión."""
    import time

    from apps.motor_simulacion import motor as motor_sim
    from apps.motor_simulacion.modelo_delegado import DelegacionExpirada
    from apps.motor_simulacion.runtime_concordia import RuntimeConcordia

    corrida = motor_sim._corrida_abierta(db, corrida_id)  # valida la corrida y siembra la memoria
    if turnos <= 0:
        turnos = corrida.presupuesto_rondas
    memoria = motor_sim._corridas[corrida_id]  # misma referencia: el hilo escribe acá, no en una copia
    roles = {}
    roles.update({rol: d for rol, d in memoria.dobles.items()})
    roles.update({rol: d for rol, d in memoria.sinteticos.items()})
    if not roles:
        raise motor_sim.MotorSimError(
            "la corrida no tiene población: sumá dobles (token firmado) o "
            "sintéticos (corrida_sintetico) antes de lanzar la engine (una "
            "corrida despoblada es un SimCity)")

    # La lente: se computa UNA vez para todo el arco (corrección jul 2026, del
    # diagnóstico de corridas chatas: el contexto delegado no llevaba
    # marco_reglas y la premisa teórica jamás llegaba al pedido).
    from apps.motor_simulacion.marcos import reglas_de
    reglas = memoria.lente_borrador or reglas_de(corrida.marco, db)
    lente = {"nombre": reglas.get("nombre", corrida.marco),
             "estresa": reglas.get("estresa", ""),
             "crisis_tipicas": list(reglas.get("crisis_tipicas", []))[:4]}

    buzon = abrir_cola(corrida_id, presupuesto_estimado)
    runtime = RuntimeConcordia.con_delegacion(buzon, embedder=_embedder_local(),
                                              timeout_s=timeout_s, liviano=liviano)

    memoria.arco_turnos = turnos
    memoria.rondas_completadas = 0
    memoria.motivo_fin = ""

    def bucle():
        historial_actos = []  # continuidad del arco para el modo liviano
        limite_total = time.monotonic() + turnos * max(1, len(roles)) * timeout_s
        for ronda_num in range(1, turnos + 1):
            for rol, disposiciones in list(roles.items()):
                contexto = {"rol": rol,
                           "disposiciones": disposiciones.get("disposiciones", []),
                           "situacion": situacion,  # la semilla; la continuidad la da historial
                           "historial": list(historial_actos),
                           "marco_reglas": lente,
                           "inventario": dict(memoria.inventario)}
                while True:  # el gradiente puede frenar el arranque: esperar cobertura
                    try:
                        acto = runtime.producir_acto(contexto)
                        break
                    except GradienteIncompleto:
                        if time.monotonic() > limite_total:
                            memoria.motivo_fin = "presupuesto de tiempo agotado esperando cobertura"
                            return
                        time.sleep(0.5)
                    except DelegacionExpirada:
                        memoria.motivo_fin = ("un pedido no fue respondido a tiempo "
                                              "(el cliente dejó de prestar la mente)")
                        return
                    except ColaCerrada:
                        memoria.motivo_fin = "la corrida se cerró durante la ejecución"
                        return
                with buzon._cond:
                    if buzon.cerrado:
                        memoria.motivo_fin = "la corrida se cerró durante la ejecución"
                        return
                    buzon.actos.append(acto)
                # El relato vive en memoria (efímero, muere al cierre INV-07) y
                # se puebla DIRECTO acá: es el mismo proceso, confiable. Jamás
                # dependas de la DB para esto (un fallo silencioso de sesión
                # dejaba el relato vacío aunque los actos existieran).
                memoria.transcript.append(
                    (ronda_num, rol, acto.get("descripcion", "")))
                # Historia del arco para que el liviano tenga continuidad.
                historial_actos.append(f"{rol}: {acto.get('descripcion', '')[:200]}")
                # El costo material, si el acto lo declara, se descuenta aparte
                # (una sesión propia del hilo); que falle no pierde el relato.
                if acto.get("costo"):
                    try:
                        from packages.domain.database import SessionLocal
                        db_hilo = SessionLocal()
                        try:
                            motor_sim.acto_ronda(db_hilo, corrida_id, rol, acto,
                                                 registrar_transcript=False)
                            db_hilo.commit()
                        finally:
                            db_hilo.close()
                    except Exception:
                        pass
                if time.monotonic() > limite_total:
                    memoria.motivo_fin = "presupuesto de tiempo agotado"
                    return
            memoria.rondas_completadas += 1
        memoria.motivo_fin = "arco completo"

    threading.Thread(target=bucle, daemon=True).start()
    return buzon


def auditar_transito(db) -> list:
    """Para la auditoría de mal alimento: ninguna cola sobrevive a su corrida.
    Una cola cuya corrida está cerrada (o no existe) es un hallazgo."""
    from packages.domain.models import Corrida
    hallazgos = []
    for corrida_id, buzon in list(_colas.items()):
        corrida = db.query(Corrida).filter(Corrida.id == corrida_id).first()
        if corrida is None or corrida.estado == "cerrada":
            hallazgos.append(f"transito delegado vivo de corrida muerta: {corrida_id}")
    return hallazgos
