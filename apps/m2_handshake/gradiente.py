"""
Handshake por gradiente (WP-02, INV-01/02; 01_red §4).

Estados de la sinapsis: proposed -> addressed -> active | expired.

El acto mínimo es la primera palabra propia dirigida al otro, escrita en la
Mini App sobre un campo vacío. La palabra JAMÁS pasa por el servidor: viaja
cifrada al topic derivado (01_red §4.2). Acá solo se registra la TRANSICIÓN,
firmada según el contrato (rizoma.link). No existe botón de aceptar. No
existe el "no": la propuesta sin dirigirse expira en silencio, sin registro
de rechazo ni costo social.
"""
from datetime import datetime, timedelta, timezone

PROPOSED = "proposed"
ADDRESSED = "addressed"
ACTIVE = "active"
EXPIRED = "expired"
LEGACY_PROPOSED = "matched"  # estado histórico pre-WP-02

TTL_DIAS_DEFAULT = 7  # nodo.toml [ttl_dias] propuesta


class TransicionInvalida(Exception):
    def __init__(self, motivo: str, codigo: int = 409):
        self.motivo = motivo
        self.codigo = codigo
        super().__init__(motivo)


def canonical_link(actor_id: str, timestamp: str, nonce: str, node_a: str, node_b: str) -> str:
    # contracts/security.md: rizoma.link|{actor_id}|{timestamp}|{nonce}|{node_a}|{node_b}
    return f"rizoma.link|{actor_id}|{timestamp}|{nonce}|{node_a}|{node_b}"


def normalizar_estado(status: str) -> str:
    return PROPOSED if status == LEGACY_PROPOSED else status


def es_parte(synapse, actor_id: str) -> bool:
    actor = (actor_id or "").lower()
    return actor in (
        (synapse.origin_actor_id or "").lower(),
        (synapse.target_actor_id or "").lower(),
    )


def transicionar(estado_actual: str, addressed_by: str | None, actor_id: str):
    """
    El acto es el mismo para ambos: dirigirse. El orden decide el efecto:
    el primero abre (addressed), el segundo confirma (active). Devuelve
    (nuevo_estado, addressed_by).
    """
    estado = normalizar_estado(estado_actual)
    if estado == EXPIRED:
        raise TransicionInvalida("la propuesta expiró en silencio", 410)
    if estado == ACTIVE:
        raise TransicionInvalida("el vínculo ya está activo", 409)
    if estado == PROPOSED:
        return ADDRESSED, actor_id
    if estado == ADDRESSED:
        if addressed_by and addressed_by.lower() == actor_id.lower():
            raise TransicionInvalida("ya te dirigiste; falta la palabra del otro", 409)
        return ACTIVE, addressed_by
    raise TransicionInvalida(f"estado desconocido: {estado_actual}", 500)


def esta_vencida(created_at, estado: str, ttl_dias: int = TTL_DIAS_DEFAULT, ahora=None) -> bool:
    """Propuestas y addressed sin respuesta decaen por TTL; active jamás por esta vía."""
    if normalizar_estado(estado) not in (PROPOSED, ADDRESSED):
        return False
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    ahora = ahora or datetime.now(timezone.utc)
    return (ahora - created_at) > timedelta(days=ttl_dias)


# --- Notificaciones del puente (sin botón, con el texto original) ---------

def enlace_sinapsis(synapse_id, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/#/sinapsis/{synapse_id}"


def mensaje_propuesta(texto_original_del_otro: str, enlace: str) -> str:
    """
    La propuesta lleva el TEXTO ORIGINAL del otro (jamás un resumen del
    sistema) y un enlace que abre un campo vacío. Sin botones, sin plantillas
    de respuesta rápida (INV-02).
    """
    return (
        "🌊 *Resonancia*\n\n"
        f"Alguien emitió: \"{texto_original_del_otro}\"\n\n"
        "Si querés, escribile tu primera palabra (el enlace abre un campo vacío):\n"
        f"{enlace}\n\n"
        "Si no decís nada, esto expira solo y no queda registro."
    )


def mensaje_addressed(enlace: str) -> str:
    return (
        "✍️ Te escribieron una primera palabra sobre una resonancia tuya.\n"
        f"Leela y, si querés, respondé la tuya acá: {enlace}"
    )


def mensaje_active(enlace: str) -> str:
    return (
        "🔗 Vínculo activo: ambos se dirigieron. La conversación sigue en el canal cifrado:\n"
        f"{enlace}"
    )
