from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SignedBase(BaseModel):
    actor_id: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    timestamp: str
    nonce: str
    signature: str

class GeoInput(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_km: Optional[int] = None
    level: str = "none"

class EmitRequest(SignedBase):
    text: str = Field(..., min_length=3, max_length=1000)
    geo: Optional[GeoInput] = None
    # vida declarada de ESTA señal (WP-28); None = TTL global del nodo (INV-03)
    ttl_dias: Optional[int] = Field(None, ge=1, le=365)

class LinkRequest(SignedBase):
    node_a: str
    node_b: str

class NodePatchRequest(SignedBase):
    action: str # "close" o "renew"

class ActorControlRequest(SignedBase):
    """Controles del perfil (WP-04, INV-05): el dueño firma export o erase."""
    pass

class AventuraCerrarRequest(ActorControlRequest):
    """Cierre de partida: bajo el arco mínimo, solo a pedido del jugador."""
    lo_pide_el_jugador: bool = False

class CorridaCerrarRequest(ActorControlRequest):
    """sin_cosecha=true declara explícito el descarte sin leer tensiones."""
    sin_cosecha: bool = False

class SynapseAddressRequest(SignedBase):
    """El acto de dirigirse (WP-02). La palabra NO viaja acá: solo la firma
    del acto (rizoma.link sobre los dos nodos de la sinapsis)."""
    pass

class AventuraIniciarRequest(SignedBase):
    marco: Optional[str] = None

class AventuraTerminosRequest(SignedBase):
    terminos: List[str]
    origen_escena: Optional[str] = None

class AventuraPrediccionRequest(SignedBase):
    escena_id: str
    opcion_prevista: str
    razon: str

class AventuraDecisionRequest(SignedBase):
    escena_id: str
    eleccion: str
    deslizamientos: List[dict] = []

class CorridaIniciarRequest(SignedBase):
    marco: str
    inventario: dict = {}
    presupuesto_rondas: int = 12
    lente_borrador: Optional[dict] = None

class CorridaRespuestaRequest(SignedBase):
    """El razonamiento delegado que un cliente del pool devuelve (09 §2.6).
    La firma prueba quién sirve (contador agregado); la respuesta NO la guarda."""
    text: Optional[str] = None
    idx: Optional[int] = None

class CorridaPresupuestoRequest(SignedBase):
    """El consentimiento del umbral (09 §2.6): cuántos pedidos compromete esta
    llave para la corrida. Declarar de nuevo reemplaza; 0 es retirarse."""
    pedidos: int = Field(..., ge=0)

class CorridaDelegadaRequest(SignedBase):
    """Lanza la engine hospedada en el nodo (09 §2.6): deposita pedidos de
    razonamiento y espera al pool. Solo el operador de la corrida. `engine`:
    "auto" (default, Concordia si está instalada y la corrida está poblada;
    si no, degrada a la demo y lo declara), "concordia" (fuerza el escalón
    real) o "demo" (fuerza el fallback). turnos=0 (default) usa el
    presupuesto_rondas de la corrida (el arco entero); un número > 0 pide
    ese tramo corto deliberado."""
    turnos: int = Field(0, ge=0, le=100)
    presupuesto_estimado: int = Field(0, ge=0)
    rol: str = "la-que-riega"
    situacion: str = "El pozo comunitario está casi seco."
    engine: str = "auto"
    liviano: bool = True

class CorridaParticipanteRequest(SignedBase):
    rol: str
    token: Optional[dict] = None  # firmado por la persona para ESTA corrida (INV-07)

class CorridaContextoRequest(SignedBase):
    rol: str

class CorridaActoRequest(SignedBase):
    rol: str
    acto: dict

class CorridaTensionesRequest(SignedBase):
    tensiones: List[dict]

class InjertoRegistrarRequest(SignedBase):
    spec: dict

class VeredictoRequest(SignedBase):
    veredicto: str
    evidencia: str
    metricas_sin: dict = {}
    metricas_con: dict = {}

class AdopcionRequest(SignedBase):
    decision: str  # adoptado | descartado

class FormaProponerRequest(SignedBase):
    borrador: dict
    n_comunidad: int

class RevisionFormaRequest(SignedBase):
    aprobada: bool

class BifurcarFormaRequest(SignedBase):
    cambios: dict = {}

class SinteticoRequest(SignedBase):
    rol: str
    forma_id: str

class PersonajeRequest(SignedBase):
    rol: str
    disposiciones: list[str]

class RubricaProponerRequest(SignedBase):
    borrador: dict
    n_comunidad: Optional[int] = None

class TareaCrearRequest(SignedBase):
    tipo: str
    dominio: str
    material: dict = {}

class TareaResolverRequest(SignedBase):
    propuesta: dict

class SesionAbrirRequest(SignedBase):
    rubrica_gm_id: Optional[str] = None

class SesionEntrarRequest(SignedBase):
    con_fierro: bool = False

class TurnoProponerRequest(SignedBase):
    composicion: dict

class TurnoValidarRequest(SignedBase):
    acepta: bool

class NodeSchema(BaseModel):
    id: str
    state: str
    text_raw: str
    command_slug: str
    groups: List[str]
    mass: float
    actor_id: str
    created_at: Optional[str]

class SearchResultSchema(BaseModel):
    node: NodeSchema
    score: float
    server_origin: str

class SearchResponseSchema(BaseModel):
    results: List[SearchResultSchema]
