from sqlalchemy import Column, String, Float, DateTime, Enum, JSON, Integer, ForeignKey, Boolean, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector
from geoalchemy2 import Geography
import uuid
import datetime

class Base(DeclarativeBase):
    pass

class Actor(Base):
    __tablename__ = "actors"
    id = Column(String(255), primary_key=True)
    alias = Column(String, nullable=True)
    reputation = Column(Float, default=1.0) # Valor de influencia (0.1 a 10.0)
    geo_point = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    geo_level = Column(String, default="none")
    home_server = Column(String, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    payload = Column(JSONB, default={})

class Node(Base):
    __tablename__ = "nodes"
    id = Column(String, primary_key=True)
    state = Column(String, default="pending")
    text_raw = Column(String, nullable=False)
    text_normalized = Column(String, nullable=True)
    command_raw = Column(String, nullable=False)
    command_slug = Column(String, nullable=False, index=True)
    groups = Column(ARRAY(String), default=[])
    content_vector = Column(Vector(768), nullable=True)
    geo_point = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    geo_radius_km = Column(Integer, nullable=True)
    geo_level = Column(String, default="none")
    mass = Column(Float, default=1.0)
    search_hits = Column(Integer, default=0)
    link_confirmations = Column(Integer, default=0)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    actor_id = Column(String(255), index=True)
    server_id = Column(String, index=True)
    payload = Column(JSONB, default={})
    ttl_dias = Column(Integer, nullable=True)  # vida declarada por el emisor; None = el TTL global del nodo

class Link(Base):
    __tablename__ = "links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_a_id = Column(String, nullable=False, index=True)
    node_a_server = Column(String, nullable=False)
    node_b_id = Column(String, nullable=False, index=True)
    node_b_server = Column(String, nullable=False)
    confirmed = Column(Boolean, default=True)
    score = Column(Float, nullable=False)
    actor_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    payload = Column(JSONB, default={})

class ActionLog(Base):
    __tablename__ = "action_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, default="dry_run")
    action_type = Column(String, nullable=False)
    pattern_observed = Column(JSONB)
    agent_reasoning = Column(String)
    parameters_proposed = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    applied_at = Column(DateTime(timezone=True), nullable=True)

class SemanticRule(Base):
    __tablename__ = "semantic_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label = Column(String, unique=True, nullable=False)
    mass_multiplier = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class ComandoVivo(Base):
    """La gramática de las resonancias (WP-28): un comando existe porque se
    usa. Gana masa con cada emisión que lo porta y decae sin uso hasta
    olvidarse (desgramaticalización): la lengua viva de este nodo, sedimento
    del habla, jamás un diccionario impuesto."""
    __tablename__ = "comandos_vivos"
    slug = Column(String(64), primary_key=True)
    mass = Column(Float, default=1.0)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class SearchLog(Base):
    __tablename__ = "search_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text = Column(String, nullable=False)
    results_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Peer(Base):
    __tablename__ = "peers"
    url = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    reputation = Column(Float, default=1.0) # Comienza en 1.0
    is_blocked = Column(Boolean, default=False)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Synapse(Base):
    __tablename__ = "synapses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    origin_actor_id = Column(String(255), index=True)
    target_actor_id = Column(String(255), index=True)
    origin_node_id = Column(String, index=True)
    target_node_id = Column(String, index=True)
    similarity = Column(Float, nullable=False)
    # WP-02 (01_red §4): proposed -> addressed -> active | expired ("matched" = legado)
    status = Column(String, default="proposed")
    addressed_by = Column(String(255), nullable=True)
    addressed_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

# --- Escala sujeto: topología de deslizamientos (WP-03/14; 05_motor_aventura §1) ---
# Por construcción NO existen columnas para predicciones, marcador ni transcript:
# el mal alimento no tiene dónde persistirse (INV-04). Ids portables (hex), sin
# tipos exclusivos de Postgres, para que la auditoría corra también en tests.

class Partida(Base):
    __tablename__ = "partidas"
    id = Column(String(64), primary_key=True)
    jugador_llave = Column(String(255), index=True, nullable=False)
    estado = Column(String, default="abierta")  # abierta | cerrada
    marco = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

class TerminoMapa(Base):
    __tablename__ = "terminos_mapa"
    id = Column(String(64), primary_key=True)
    jugador_llave = Column(String(255), index=True, nullable=False)
    termino = Column(String, nullable=False)  # en la lengua del jugador, sin taxonomía
    origen_escena = Column(String, nullable=True)
    mass = Column(Float, default=1.0)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Deslizamiento(Base):
    __tablename__ = "deslizamientos"
    id = Column(String(64), primary_key=True)
    jugador_llave = Column(String(255), index=True, nullable=False)
    de_termino = Column(String, nullable=False)
    hacia_termino = Column(String, nullable=False)
    evidencia = Column(String, nullable=False)  # cita textual del jugador
    escena_contexto = Column(String, nullable=True)
    intensidad = Column(String, default="leve")  # leve | marcada
    mass = Column(Float, default=1.0)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

# --- Escala comunidad: corridas (WP-05/15/16; 06_motor_simulacion) ---
# Por construcción NO existen columnas para dobles, tokens, topologías de
# origen ni transcripts (INV-07): todo eso vive en memoria de corrida y muere
# con ella. Persisten la corrida (metadatos del operador) y las tensiones
# despersonalizadas (roles, jamás identidades).

class Corrida(Base):
    __tablename__ = "corridas"
    id = Column(String(64), primary_key=True)
    operador_llave = Column(String(255), index=True, nullable=False)
    marco = Column(String, nullable=False)  # declarado en todo output
    estado = Column(String, default="abierta")  # abierta | cerrada
    rondas = Column(Integer, default=0)
    presupuesto_rondas = Column(Integer, default=12)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

class Tension(Base):
    __tablename__ = "tensiones"
    id = Column(String(64), primary_key=True)
    corrida_id = Column(String(64), index=True, nullable=False)
    marco = Column(String, nullable=False)
    tipo = Column(String, nullable=False)
    roles = Column(String, nullable=False)      # roles involucrados, jamás identidades
    evidencia = Column(String, nullable=False)  # citas del transcript, POR ROL
    intensidad = Column(String, default="leve")
    ronda = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Injerto(Base):
    __tablename__ = "injertos"
    # La intervención cristalizada (06 §6). Despersonalizada por construcción:
    # nace de tensiones por ROL y jamás referencia llaves ni topologías.
    id = Column(String(64), primary_key=True)
    corrida_id = Column(String(64), index=True, nullable=False)
    marco = Column(String, nullable=False)
    nombre = Column(String, nullable=False)
    tension_que_ataca = Column(String, nullable=False)
    regla_logica = Column(String, nullable=False)
    flujo = Column(String, nullable=False)
    requisitos_materiales = Column(String, default="{}")  # JSON: menores o iguales al inventario
    pseudocodigo = Column(String, nullable=True)
    senales_alivio = Column(String, nullable=False)
    estado = Column(String, default="propuesto")  # propuesto | aprobado | necesita_ajustes | rechazado | adoptado | descartado
    evidencia_veredicto = Column(String, nullable=True)
    metricas_sin = Column(String, nullable=True)   # JSON agregado (permitido persistir)
    metricas_con = Column(String, nullable=True)
    guion = Column(String, nullable=True)          # JSON: la partida jugable exportada
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    decidido_at = Column(DateTime(timezone=True), nullable=True)

# --- El acervo de formas (WP-08; 03_comunidad §6, INV-08) ---
# Dos stores deliberadamente separados: PropuestaForma es REGISTRO DE
# GOBERNANZA (porta llaves de aportantes y firmas: jamás lo lee el espejo);
# Forma es el objeto del acervo: despersonalizado por construcción.

class PropuestaForma(Base):
    __tablename__ = "propuestas_forma"
    id = Column(String(64), primary_key=True)
    corrida_id = Column(String(64), index=True, nullable=True)  # null si es rúbrica a mano (WP-22)
    borrador = Column(String, nullable=False)        # JSON del borrador de forma
    n_comunidad = Column(Integer, nullable=False)
    aportantes = Column(String, default="[]")        # JSON: llaves de quienes pusieron carne
    firmas = Column(String, default="{}")            # JSON: llave -> fecha de sí
    regla = Column(String, nullable=False)            # regla de consentimiento vigente al proponer
    revision_humana_requerida = Column(Boolean, default=False)
    revision_humana_ok = Column(Boolean, default=False)
    estado = Column(String, default="juntando")       # juntando | publicada | vencida
    forma_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Forma(Base):
    __tablename__ = "formas"
    id = Column(String(64), primary_key=True)
    tipo = Column(String, nullable=False)             # tension_tipo | injerto | patron_coordinacion | rubrica | lente
    nombre = Column(String, nullable=False)
    descripcion = Column(String, nullable=False)
    cuerpo = Column(String, nullable=True)            # WP-22: texto declarativo de una rúbrica-forma (INV-18)
    contexto_material = Column(String, default="{}")  # JSON de RANGOS declarados, jamás cifras exactas
    marco = Column(String, nullable=False)
    procedencia = Column(String, nullable=False)      # comunidad anónima + fecha
    regla_consentimiento = Column(String, nullable=False)  # declarada en la forma (decisión jul 2026)
    licencia = Column(String, default="abierta")
    linaje = Column(String(64), nullable=True)        # forma madre si es bifurcación
    estado = Column(String, default="publicada")      # publicada | retirada
    retirada_motivo = Column(String, nullable=True)   # sin identidades ("revocación de un aportante")
    mass = Column(Float, default=1.0)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Pieza(Base):
    __tablename__ = "piezas"
    # Emergencia generativa (WP-19; 01_red §7/§7.1, INV-14): declaración
    # pública de andamiaje. Registrada, auditable, reversible, decae sin uso.
    id = Column(String(64), primary_key=True)
    tipo = Column(String, nullable=False)              # subindice | regla_enlace | lugar (lista blanca)
    justificacion = Column(String, nullable=False)     # agregados del surco, jamás identidades
    spec = Column(String, default="{}")                # JSON declarativo
    topic_derivado = Column(String, nullable=True)     # /rizoma/v2/idx/<h> | /rizoma/v2/lugar/<h>
    proponente_llave = Column(String(255), nullable=False)  # declaración pública firmada, como una intención
    estado = Column(String, default="candidata")       # candidata | activa | inactiva | revocada
    mass = Column(Float, default=0.0)                  # masa por USO real, jamás por proponerse
    ttl_dias = Column(Integer, default=30)
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

# --- El procomún semiótico: pool de cómputo (WP-23; 09_procomun §2.2, INV-18) ---
# Los clientes con fierro aportan cómputo sobre material YA anónimo. La
# validación es por RESULTADO (validadores locales), no por confianza en quien
# aporta. El peso de contribución prioriza pero decae, no se transfiere y no es
# ranking (INV-10, INV-03). No hay slashing: un aporte inválido no penaliza.

class TareaComun(Base):
    __tablename__ = "tareas_comun"
    id = Column(String(64), primary_key=True)
    tipo = Column(String, nullable=False)            # cristalizar | proponer_forma | densificar
    dominio = Column(String, nullable=False)
    material = Column(String, default="{}")          # JSON: SOLO agregados anónimos
    estado = Column(String, default="abierta")       # abierta | tomada | resuelta | vencida
    tomada_por = Column(String(255), nullable=True)
    resultado = Column(String, nullable=True)        # JSON de la propuesta validada
    ttl_dias = Column(Integer, default=7)
    tomada_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class PesoContribucion(Base):
    __tablename__ = "pesos_contribucion"
    id = Column(String(64), primary_key=True)
    llave = Column(String(255), index=True, nullable=False)
    dominio = Column(String, nullable=False)
    peso = Column(Float, default=0.0)                # prioriza; decae; NO transferible, NO ranking
    last_touched = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

# --- El procomún semiótico: multiplayer semiótico (WP-25; 09_procomun §2.4) ---
# Servidor autoritativo de ESTADO, jamás de sentido: el nodo mantiene turno,
# quién compone y quién participa, y NO interpreta. El cómputo neutral emerge de
# quota rotativa (sorteo de GM + rúbrica pública + validación cruzada). El
# contenido de la ficción es efímero y muere al cierre; solo persiste el metadato.

class SesionMultiplayer(Base):
    __tablename__ = "sesiones_multiplayer"
    id = Column(String(64), primary_key=True)
    convocante_llave = Column(String(255), nullable=False)
    rubrica_gm_id = Column(String(64), nullable=True)     # forma-rúbrica que arbitra
    participantes = Column(String, default="[]")          # JSON: [{llave, con_fierro}]
    estado = Column(String, default="abierta")            # abierta | activa | degradada | cerrada
    turno = Column(Integer, default=0)
    gm_actual = Column(String(255), nullable=True)
    gm_anterior = Column(String(255), nullable=True)
    escena_propuesta = Column(String, nullable=True)      # JSON efímero del turno en curso
    veredictos = Column(String, default="{}")             # JSON: {llave: bool}
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
