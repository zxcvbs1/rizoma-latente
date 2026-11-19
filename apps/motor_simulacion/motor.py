"""
Motor de simulación, mitad NODO (WP-05/15/16; 06_motor_simulacion).

Cliente en el bucle: el cliente MCP del operador pone las mentes (roleplay de
agentes, Game Master, análisis semiótico); el nodo guarda lo que los
servidores hacen bien: estado material, rondas, presupuesto y VALIDADORES.
Reglas duras por construcción:

- INV-07: el doble se calibra con token firmado POR CORRIDA, vive solo en la
  memoria de la corrida y muere con ella. Las tablas no tienen columnas para
  dobles, tokens ni topologías: no hay de dónde regenerarlo.
- INV-17: todo contexto servido pasa el filtro de frontera (roles, jamás
  llaves); toda lectura devuelta se valida antes de tocar el estado.
- Sin token, degradación honesta: agente aleatorio en su lugar; jamás fallo
  silencioso, jamás proceder con la topología de quien no firmó.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import json

from apps.motor_simulacion.marcos import MARCOS, marco_valido, reglas_de
from packages.domain import frontera
from packages.domain.models import Corrida, Deslizamiento, Forma, Injerto, Tension

# contexto mínimo por operación (INV-17): nada fuera de esta lista sale al cliente
CAMPOS_CONTEXTO_RONDA = {"rol", "marco", "marco_reglas", "ronda", "inventario",
                         "disposiciones", "presupuesto_restante", "forma_origen"}

TOKEN_PREFIX = "doble:"  # canonical: rizoma.actor.patch|actor|ts|nonce|doble:<corrida_id>


class MotorSimError(Exception):
    pass


@dataclass
class MemoriaCorrida:
    """Todo lo reconstruible muere acá adentro (INV-07)."""
    inventario: dict = field(default_factory=dict)
    dobles: dict = field(default_factory=dict)        # rol -> {"disposiciones": [...]}
    sinteticos: dict = field(default_factory=dict)    # rol -> {"disposiciones", "forma_id"} (cantera, WP-20)
    llaves_por_rol: dict = field(default_factory=dict)  # SOLO consentimiento vivo; jamás cruza la frontera
    aleatorios: list = field(default_factory=list)    # roles estocásticos
    transcript: list = field(default_factory=list)    # efímero, muere al cierre
    lente_borrador: dict = field(default_factory=dict)  # lente propia sin publicar; muere con la corrida
    arco_turnos: int = 0         # turnos pedidos a la engine
    rondas_completadas: int = 0  # rondas que la engine terminó de verdad
    motivo_fin: str = ""         # por qué terminó la engine (honesto en el cierre)


_corridas: dict[str, MemoriaCorrida] = {}


def _uid() -> str:
    return uuid.uuid4().hex


def _ahora():
    return datetime.now(timezone.utc)


def token_action(corrida_id: str) -> str:
    return f"{TOKEN_PREFIX}{corrida_id}"


def _corrida_abierta(db, corrida_id: str) -> Corrida:
    corrida = db.query(Corrida).filter(Corrida.id == corrida_id).first()
    if not corrida or corrida.estado != "abierta":
        raise MotorSimError("corrida inexistente o cerrada")
    if corrida_id not in _corridas:
        _corridas[corrida_id] = MemoriaCorrida()
    return corrida


def iniciar_corrida(db, operador: str, marco: str, inventario: dict | None = None,
                    presupuesto_rondas: int = 12, lente_borrador: dict | None = None) -> Corrida:
    if lente_borrador:
        if not lente_borrador.get("nombre") or not lente_borrador.get("estresa"):
            raise MotorSimError("una lente borrador declara al menos nombre y estresa")
        frontera.validar_salida(lente_borrador)
        corrida = Corrida(id=_uid(), operador_llave=operador, marco=lente_borrador["nombre"],
                          estado="abierta", rondas=0, presupuesto_rondas=presupuesto_rondas)
        db.add(corrida)
        db.flush()
        memoria = MemoriaCorrida(inventario=dict(inventario or {}))
        memoria.lente_borrador = {
            "nombre": lente_borrador["nombre"], "estresa": lente_borrador["estresa"],
            "crisis_tipicas": lente_borrador.get("crisis_tipicas", []),
            "metricas": lente_borrador.get("metricas", []),
            "del_acervo": False, "borrador": True,
        }
        _corridas[corrida.id] = memoria
        return corrida

    if not marco_valido(marco, db):
        raise MotorSimError(
            f"marco desconocido: {marco}. Válidos: uno de los seis semilla "
            f"({', '.join(sorted(MARCOS))}) o una lente PUBLICADA del acervo. "
            "Para publicar la tuya: acervo_proponer_rubrica con tipo='lente' "
            "(no hace falta ninguna corrida), después acervo_consentir y "
            "acervo_publicar; recién ahí usá su nombre como marco acá. "
            "O probala primero sin publicar: corrida_iniciar con "
            "lente_borrador={nombre, estresa, ...}; el borrador muere con la "
            "corrida y publicás solo si te conforma.")
    marco_canonico = marco if marco in MARCOS else reglas_de(marco, db)["nombre"]
    corrida = Corrida(id=_uid(), operador_llave=operador, marco=marco_canonico,
                      estado="abierta", rondas=0, presupuesto_rondas=presupuesto_rondas)
    db.add(corrida)
    db.flush()
    _corridas[corrida.id] = MemoriaCorrida(inventario=dict(inventario or {}))
    return corrida


def calibrar_desde_topologia(db, llave: str) -> list:
    """Cada arista del mapa se vuelve una regla condicional de conducta
    (06 §3). Contexto mínimo: la regla, sin citas ni identidades."""
    disposiciones = []
    for d in db.query(Deslizamiento).all():
        if (d.jugador_llave or "").lower() == llave.lower():
            disposiciones.append(
                f"bajo tensión, su '{d.de_termino}' tiende a '{d.hacia_termino}'"
                + (f" (intensidad {d.intensidad})" if d.intensidad else ""))
    return disposiciones


def sumar_participante(db, corrida_id: str, rol: str, security=None,
                       token: dict | None = None) -> dict:
    """Gate de entrada (INV-07): token de partida firmado por la persona para
    ESTA corrida. Sin token: agente aleatorio. Token inválido: rechazo
    explícito (jamás proceder en silencio)."""
    _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    rol = (rol or "").strip()
    if not rol or frontera.contiene_identidades(rol):
        raise MotorSimError("el rol es un nombre de escena, jamás una identidad")

    if token is None:
        memoria.aleatorios.append(rol)
        return {"rol": rol, "calibrado": False, "poblacion": "aleatoria"}

    if security is None:
        raise MotorSimError("no puedo verificar el token sin servicio de firma")
    llave = token.get("actor_id") or ""
    msg = (f"rizoma.actor.patch|{llave}|{token.get('timestamp')}|"
           f"{token.get('nonce')}|{token_action(corrida_id)}")
    if not security.verify_eip191_signature(llave, token.get("signature", ""), msg):
        raise MotorSimError("token de partida inválido: la persona no firmó esta corrida")

    memoria.dobles[rol] = {"disposiciones": calibrar_desde_topologia(db, llave)}
    memoria.llaves_por_rol[rol] = llave
    return {"rol": rol, "calibrado": True, "poblacion": "doble"}


def contexto_ronda(db, corrida_id: str, rol: str) -> dict:
    """El contexto del turno para el cliente ejecutor. SIEMPRE cruza la
    frontera: roles y disposiciones, jamás llaves ni mapas completos."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    if corrida.rondas >= corrida.presupuesto_rondas:
        raise MotorSimError("presupuesto de rondas agotado: la corrida pide cierre limpio")
    bruto = {
        "rol": rol,
        "marco": corrida.marco,
        "marco_reglas": memoria.lente_borrador or reglas_de(corrida.marco, db),
        "ronda": corrida.rondas,
        "inventario": dict(memoria.inventario),
        "disposiciones": list((memoria.dobles.get(rol)
                               or memoria.sinteticos.get(rol, {})).get("disposiciones", [])),
        "forma_origen": memoria.sinteticos.get(rol, {}).get("forma_id"),
        "presupuesto_restante": corrida.presupuesto_rondas - corrida.rondas,
    }
    return frontera.filtrar_contexto(bruto, CAMPOS_CONTEXTO_RONDA)


def acto_ronda(db, corrida_id: str, rol: str, acto: dict,
               registrar_transcript: bool = True) -> dict:
    """Validador de restricciones materiales (06 §2.1): un acto imposible se
    rechaza y el cliente replanifica; el acto imposible no toca el estado.
    registrar_transcript=False cuando el engine ya pobló el relato en memoria
    (evita el doble append)."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    frontera.validar_salida(acto)

    costo = acto.get("costo") or {}
    for recurso, cantidad in costo.items():
        if memoria.inventario.get(recurso, 0) < cantidad:
            raise MotorSimError(
                f"acto materialmente imposible: {recurso} insuficiente "
                f"({memoria.inventario.get(recurso, 0)} < {cantidad})")
    for recurso, cantidad in costo.items():
        memoria.inventario[recurso] -= cantidad

    if registrar_transcript:
        memoria.transcript.append((corrida.rondas, rol, acto.get("descripcion", "")))
    return {"rol": rol, "ronda": corrida.rondas, "inventario": dict(memoria.inventario)}


def transcript_de(db, corrida_id: str) -> dict:
    """El transcript vivo de la corrida (roles, ronda, descripción del acto).
    No persiste: es para que el dueño se lo lleve; muere al cierre (INV-07)."""
    _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    return {"corrida": corrida_id,
            "actos": [{"ronda": r, "rol": rol, "descripcion": desc}
                      for (r, rol, desc) in memoria.transcript],
            "rondas_completadas": memoria.rondas_completadas,
            "nota": "roles, jamás identidades; el nodo no guarda esto, muere al cerrar"}


def estado_de(db, corrida_id: str) -> dict:
    """El pulso de la corrida sin cerrarla: por qué ronda va, cuántos actos
    lleva, cuántas tensiones se leyeron. Para saber que está viva y por dónde,
    en vez de esperar a ciegas."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    poblacion = len(memoria.dobles) + len(memoria.sinteticos) + len(memoria.aleatorios)
    tensiones = db.query(Tension).filter(Tension.corrida_id == corrida_id).count()
    return {
        "corrida": corrida_id,
        "marco": corrida.marco,
        "poblacion": poblacion,
        "arco_turnos": memoria.arco_turnos,
        "rondas_completadas": memoria.rondas_completadas,
        "actos_hasta_ahora": len(memoria.transcript),
        "tensiones_leidas": tensiones,
        "motivo_fin": memoria.motivo_fin or "en curso",
    }


def avanzar_ronda(db, corrida_id: str) -> dict:
    corrida = _corrida_abierta(db, corrida_id)
    corrida.rondas += 1
    db.flush()
    agotado = corrida.rondas >= corrida.presupuesto_rondas
    return {"ronda": corrida.rondas, "presupuesto_agotado": agotado}


def leer_tensiones(db, corrida_id: str, tensiones: list) -> int:
    """El análisis es del cliente (post-ronda); el nodo valida esquema y
    frontera, y persiste SOLO tensiones despersonalizadas con marco declarado."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    if not any((desc or "").strip() for _, _, desc in memoria.transcript):
        raise MotorSimError(
            "no se leen tensiones de una corrida sin actos CON CONTENIDO: la "
            "evidencia cita lo que pasó EN la corrida (su transcript), no una "
            "narración externa. Si serviste la cola con respuestas vacías, no "
            "compusiste nada: componé los actos (corrida_responder con text) y "
            "recién después leé.")
    roles_conocidos = set(memoria.dobles) | set(memoria.aleatorios) | set(memoria.sinteticos)
    persistidas = 0
    for cruda in tensiones or []:
        frontera.validar_salida(cruda)
        tipo = (cruda.get("tipo") or "").strip()
        roles = [r.strip() for r in (cruda.get("roles") or []) if r and r.strip()]
        evidencia = (cruda.get("evidencia") or "").strip()
        intensidad = cruda.get("intensidad") or "leve"
        if not tipo or not roles or not evidencia:
            raise MotorSimError("una tensión exige tipo, roles y evidencia por rol")
        for rol in roles:
            if roles_conocidos and rol not in roles_conocidos:
                raise MotorSimError(f"rol desconocido en la lectura: {rol}")
        db.add(Tension(id=_uid(), corrida_id=corrida.id, marco=corrida.marco,
                       tipo=tipo, roles=",".join(roles), evidencia=evidencia,
                       intensidad=intensidad, ronda=corrida.rondas))
        persistidas += 1
    db.flush()
    return persistidas


COSECHA_DENSA_RATIO = 3  # una corrida sana deja ~1 tensión leída cada 3 rondas


def cerrar_corrida(db, corrida_id: str, sin_cosecha: bool = False) -> dict:
    """Muerte del doble (INV-07): al cierre se destruye todo estado capaz de
    reconstruirlo (dobles, tokens vivos, transcript), pero ANTES de morir la
    respuesta se lleva el relato completo (roles, ronda, acto): es la cosecha
    del dueño, no la retiene el nodo. La respuesta declara la cosecha:
    población, tensiones, relato y pedidos servidos; cosecha_vacia marca la
    corrida que no produjo conocimiento (corrección jul 2026, del playtest
    del SimCity) y cosecha_rala marca la que produjo poco para lo que corrió
    (corrección jul 2026, del playtest cruzado Gemini/Antigravity). El cierre
    sin cosecha rebota (corrección jul 2026, del playtest que cerró apenas
    terminaron los turnos): una corrida que CORRIÓ (hay actos con contenido)
    y no depositó ni una tensión no se puede cerrar salvo sin_cosecha=true
    explícito; el aviso post-mortem llegaba tarde, el gate llega mientras
    todavía se puede cosechar."""
    corrida = _corrida_abierta(db, corrida_id)
    mem = _corridas.get(corrida_id)
    corrio = bool(mem and any((d or "").strip() for _, _, d in mem.transcript))
    tensiones = [t for t in db.query(Tension).all() if t.corrida_id == corrida_id]
    if corrio and len(tensiones) == 0 and not sin_cosecha:
        raise MotorSimError(
            "la corrida corrió y no leíste ni una tensión: cerrar ahora es "
            "tirar la cosecha. Leé primero (corrida_tensiones, con evidencia "
            "citada del relato) y proponé al menos un injerto si una tensión "
            "lo merece (corrida_injerto). Si de verdad querés descartar la "
            "corrida sin cosechar, repetí con sin_cosecha=true: esa "
            "declaración queda visible en el registro de tools.")
    corrida.estado = "cerrada"
    corrida.closed_at = _ahora()
    poblacion = (len(mem.dobles) + len(mem.sinteticos) + len(mem.aleatorios)) if mem else 0
    arco = mem.arco_turnos if mem else 0
    rondas_ok = mem.rondas_completadas if mem else 0
    motivo = mem.motivo_fin if mem else ""
    relato = [{"ronda": r, "rol": rol, "descripcion": desc}
              for (r, rol, desc) in (mem.transcript if mem else [])]
    _corridas.pop(corrida_id, None)
    # El tránsito delegado muere con la corrida (09 §2.6): sin cola sobreviviente.
    # La cosecha (llave -> pedidos servidos) es lo único que sale vivo, y se
    # acredita al peso de contribución (09 §4): reputación por hacer, sin
    # vincular jamás contenido con llave.
    from apps.motor_simulacion import delegacion
    from apps.worker import pool as pool_comun
    cosecha = delegacion.cerrar_cola(corrida_id)
    for llave, servidos in cosecha.items():
        pool_comun.acreditar_peso(db, llave, "corridas", delta=float(servidos))
    db.flush()
    injertos = db.query(Injerto).filter(Injerto.corrida_id == corrida_id).count()
    injertos_sin_veredicto = db.query(Injerto).filter(
        Injerto.corrida_id == corrida_id, Injerto.estado == "propuesto").count()
    cosecha_vacia = (poblacion == 0 and len(tensiones) == 0
                     and not (cosecha and sum(cosecha.values()) > 0))
    cosecha_rala = (rondas_ok >= 4 and len(tensiones) < max(2, rondas_ok // COSECHA_DENSA_RATIO))
    sin_injertos = (len(tensiones) > 0 and injertos == 0)
    respuesta = {
        "corrida": corrida.id,
        "marco": corrida.marco,
        "rondas": corrida.rondas,
        "tensiones": [{"tipo": t.tipo, "roles": t.roles.split(","),
                       "evidencia": t.evidencia, "intensidad": t.intensidad,
                       "marco": t.marco} for t in tensiones],
        "relato": relato,
        "poblacion": poblacion,
        "pedidos_delegados_servidos": sum(cosecha.values()) if cosecha else 0,
        "cosecha_vacia": cosecha_vacia,
        "cosecha_rala": cosecha_rala,
        "injertos_propuestos": injertos,
        "injertos_sin_veredicto": injertos_sin_veredicto,
        "sin_injertos": sin_injertos,
        "nota_cosecha": (
            "esta corrida no pobló roles, no leyó tensiones ni sirvió pedidos "
            "delegados: no produjo conocimiento. Una corrida es un ensayo "
            "POBLADO (dobles o sintéticos) cuyo producto son las tensiones "
            "leídas; sin eso, mover inventario es narrar un juego de fichas."
            if cosecha_vacia
            else "cosecha registrada"),
        "arco": {"turnos_pedidos": arco, "rondas_completadas": rondas_ok,
                 "motivo_fin": motivo or "sin engine lanzada"},
    }
    if sin_injertos:
        respuesta["nota_sin_injertos"] = (
            "leíste tensiones pero no propusiste soluciones: una tensión sin "
            "injerto es diagnóstico sin remedio. El ciclo cierra en el injerto "
            "(corrida_injerto), que se valida A/B (injerto_veredicto) y se "
            "exporta como JUEGO jugable (injerto_exportar): esa es la solución "
            "como consigna generativa que la comunidad implementa.")
    if cosecha_rala:
        respuesta["nota_cosecha_rala"] = (
            "leíste pocas tensiones para las rondas que corriste: una corrida "
            "larga deja varias fricciones marcadas, no dos. Releé el relato y "
            "depositá las que quedaron sin leer con corrida_tensiones antes de "
            "cerrar.")
    if injertos_sin_veredicto:
        respuesta["nota_veredicto"] = (
            "hay injertos propuestos sin veredicto A/B depositado: un "
            "APROBADO narrado en el chat no existe para el nodo; corré el "
            "escenario B y depositá con injerto_veredicto.")
    if relato:
        respuesta["nota_relato"] = (
            "el relato completo va en esta respuesta: guardalo local si lo "
            "querés (el nodo no lo retiene, INV-07). Tus tensiones e injertos "
            "son la cosecha durable.")
    if arco and rondas_ok < arco and motivo != "arco completo":
        respuesta["arco"]["nota"] = (
            f"arco incompleto: se completaron {rondas_ok} de {arco} rondas "
            f"pedidas ({motivo}); no narres el arco entero, narrá lo que se "
            "corrió de verdad.")
    if len(tensiones) > 0:
        respuesta["siguiente_paso"] = (
            "estas tensiones son materia prima de soluciones: en una corrida "
            "del mismo marco, corrida_injerto propone la REGLA que ataca la "
            "tensión, injerto_veredicto la valida A/B (el escenario con y sin "
            "la regla), injerto_exportar la vuelve juego para que la comunidad "
            "la juegue antes de adoptarla")
    return respuesta


def sortear_formas(db, n: int = 1, fraccion_uniforme: float = 0.3, rng=None) -> list:
    """Casting de la cantera (03 §6, WP-20): pondera por masa PERO mezcla una
    fracción uniforme entre formas vivas (divergir, no converger), y JAMÁS
    escribe masa: la masa la dan solo retomas humanas."""
    import random
    rng = rng or random.Random()
    vivas = [f for f in db.query(Forma).all() if f.estado == "publicada"]
    if not vivas:
        return []
    elegidas = []
    for _ in range(n):
        if rng.random() < fraccion_uniforme:
            elegidas.append(rng.choice(vivas))
        else:
            pesos = [max(float(f.mass or 0.0), 0.05) for f in vivas]
            elegidas.append(rng.choices(vivas, weights=pesos, k=1)[0])
    return elegidas


def sumar_sintetico(db, corrida_id: str, rol: str, forma_id: str) -> dict:
    """Personaje sintético (06 §3.1): instanciado DESDE una forma del acervo,
    jamás desde personas. Sin token porque no hay nadie detrás; muere al
    cierre como todo agente. El constructor SOLO acepta ids de forma."""
    _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    rol = (rol or "").strip()
    if not rol or frontera.contiene_identidades(rol):
        raise MotorSimError("el rol es un nombre de escena, jamás una identidad")
    forma = db.query(Forma).filter(Forma.id == forma_id).first()
    if not forma:
        raise MotorSimError("el constructor solo acepta ids de forma del acervo")
    if forma.estado != "publicada":
        raise MotorSimError("una forma retirada no se encarna")
    memoria.sinteticos[rol] = {
        "disposiciones": [
            f"porta la tensión-tipo '{forma.nombre}': {forma.descripcion}",
            f"leída bajo el marco {forma.marco}",
        ],
        "forma_id": forma.id,
    }
    return {"rol": rol, "calibrado": False, "poblacion": "sintetica",
            "forma_origen": forma.id}


def sumar_personaje(db, corrida_id: str, rol: str, disposiciones) -> dict:
    """Personaje del entorno inventado para ESTA corrida, con SUS propias
    disposiciones (reglas condicionales de conducta), no las de una persona ni
    las de una forma del acervo. Muere al cierre como todo agente. Es lo que
    hace que la simulación tenga agentes DISTINTOS y no un solo mapa hablando
    solo."""
    _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    rol = (rol or "").strip()
    if not rol or frontera.contiene_identidades(rol):
        raise MotorSimError("el rol es un nombre de escena, jamás una identidad")
    disp = [d.strip() for d in (disposiciones or []) if d and d.strip()]
    if not disp:
        raise MotorSimError(
            "un personaje se define por sus disposiciones (reglas de conducta): "
            "no puede ir vacío, o es un títere sin lógica propia")
    frontera.validar_salida({"disposiciones": disp})
    memoria.sinteticos[rol] = {"disposiciones": disp, "forma_id": None}
    return {"rol": rol, "poblacion": "personaje", "disposiciones": disp}


VEREDICTOS = {"APROBADO", "NECESITA_AJUSTES", "RECHAZADO"}


def premisas(db, corrida_id: str) -> dict:
    """Deducción dirigida desde la matriz material (06 §6): lo que sobra, lo
    que falta, dónde duele. El razonamiento es del cliente; esto es el dato."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    tensiones = [t for t in db.query(Tension).all() if t.corrida_id == corrida_id]
    return {
        "marco": corrida.marco,
        "sobra": {r: c for r, c in memoria.inventario.items() if c > 0},
        "falta": sorted(r for r, c in memoria.inventario.items() if c <= 0),
        "duele": [{"tipo": t.tipo, "roles": t.roles.split(","),
                   "intensidad": t.intensidad} for t in tensiones],
        "regla_de_oro": ("la propuesta no puede requerir lo que el grupo no tiene "
                         "y debe usar lo que sí tiene"),
    }


def registrar_injerto(db, corrida_id: str, spec: dict) -> Injerto:
    """El cliente cristaliza; el nodo valida la plantilla, la frontera y la
    REGLA DE ORO contra el inventario real. Lo imposible no se registra."""
    corrida = _corrida_abierta(db, corrida_id)
    memoria = _corridas[corrida_id]
    frontera.validar_salida(spec)

    obligatorios = ("nombre", "tension_que_ataca", "regla_logica", "flujo", "senales_alivio")
    for campo in obligatorios:
        if not (spec.get(campo) or "").strip():
            raise MotorSimError(f"la plantilla del injerto exige {campo}")

    requisitos = spec.get("requisitos_materiales") or {}
    for recurso, cantidad in requisitos.items():
        disponible = memoria.inventario.get(recurso)
        if disponible is None:
            raise MotorSimError(
                f"regla de oro: el injerto requiere '{recurso}' y el grupo no lo tiene")
        if cantidad > disponible:
            raise MotorSimError(
                f"regla de oro: '{recurso}' insuficiente ({disponible} < {cantidad})")

    injerto = Injerto(id=_uid(), corrida_id=corrida.id, marco=corrida.marco,
                      nombre=spec["nombre"].strip(),
                      tension_que_ataca=spec["tension_que_ataca"].strip(),
                      regla_logica=spec["regla_logica"].strip(),
                      flujo=spec["flujo"].strip(),
                      requisitos_materiales=json.dumps(requisitos),
                      pseudocodigo=spec.get("pseudocodigo"),
                      senales_alivio=spec["senales_alivio"].strip(),
                      estado="propuesto")
    db.add(injerto)
    db.flush()
    return injerto


def _injerto(db, injerto_id: str) -> Injerto:
    injerto = db.query(Injerto).filter(Injerto.id == injerto_id).first()
    if not injerto:
        raise MotorSimError("injerto inexistente")
    return injerto


def validar_ab(db, injerto_id: str, veredicto: str, evidencia: str,
               metricas_sin: dict | None = None, metricas_con: dict | None = None) -> Injerto:
    """El A/B lo corre el cliente (misma semilla, con y sin injerto); el nodo
    exige veredicto del catálogo, evidencia por ROLES y guarda solo agregados."""
    injerto = _injerto(db, injerto_id)
    if veredicto not in VEREDICTOS:
        raise MotorSimError(f"veredicto inválido: {veredicto} (catálogo: {sorted(VEREDICTOS)})")
    if not (evidencia or "").strip():
        raise MotorSimError("sin evidencia no hay veredicto")
    frontera.validar_salida({"evidencia": evidencia, "sin": metricas_sin, "con": metricas_con})
    injerto.estado = veredicto.lower()
    injerto.evidencia_veredicto = evidencia.strip()
    injerto.metricas_sin = json.dumps(metricas_sin or {})
    injerto.metricas_con = json.dumps(metricas_con or {})
    db.flush()
    return injerto


def exportar_protocolo(db, injerto_id: str) -> dict:
    """Del injerto APROBADO a la partida jugable (06 §6): el ciclo cierra en
    juego. La mecánica de N jugadores es la partida comunitaria (05 §6.2)."""
    injerto = _injerto(db, injerto_id)
    if injerto.estado != "aprobado":
        raise MotorSimError(f"solo se exporta lo aprobado (estado: {injerto.estado})")
    tensiones = [t for t in db.query(Tension).all() if t.corrida_id == injerto.corrida_id]
    roles = sorted({rol for t in tensiones for rol in t.roles.split(",") if rol}) or ["participante"]
    guion = {
        "titulo": f"La regla en juego: {injerto.nombre}",
        "marco": injerto.marco,
        "tension_que_ataca": injerto.tension_que_ataca,
        "reglas": [injerto.regla_logica],
        "flujo": injerto.flujo,
        "requisitos_materiales": json.loads(injerto.requisitos_materiales or "{}"),
        "roles": roles,
        "escena_apertura": (
            f"Escena cooperativa breve: el grupo enfrenta '{injerto.tension_que_ataca}' "
            f"bajo el marco {injerto.marco}, jugando con la regla nueva: "
            f"{injerto.regla_logica}. Cada rol decide desde su lugar; el texto libre vale más."),
        "condicion_de_cierre": injerto.senales_alivio,
        "nota": ("la comunidad lo juega antes de adoptarlo (05 §6.2): entrar es acto "
                 "individual; el único residuo colectivo es la adopción o el descarte"),
    }
    frontera.validar_salida(guion)
    injerto.guion = json.dumps(guion)
    db.flush()
    return guion


def resolver_adopcion(db, injerto_id: str, decision: str) -> Injerto:
    """El residuo colectivo único de la partida comunitaria (05 §6.2)."""
    injerto = _injerto(db, injerto_id)
    if decision not in ("adoptado", "descartado"):
        raise MotorSimError("la decisión es adoptado o descartado")
    if injerto.estado != "aprobado":
        raise MotorSimError("solo se adopta o descarta lo aprobado y jugado")
    injerto.estado = decision
    injerto.decidido_at = _ahora()
    db.flush()
    return injerto


def auditar_corridas(db) -> list:
    """Complemento de auditar_mal_alimento para la escala comunidad: ninguna
    corrida cerrada conserva memoria viva (dobles, tokens, transcript)."""
    hallazgos = []
    for corrida in db.query(Corrida).all():
        if corrida.estado == "cerrada" and corrida.id in _corridas:
            hallazgos.append(f"memoria viva de corrida cerrada: {corrida.id}")
    return hallazgos
