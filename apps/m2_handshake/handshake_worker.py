"""
Worker del handshake por gradiente (WP-02, INV-01/02).

Reemplaza al worker de Matrix: ya no se crea ninguna sala de antemano ni se
manda enlace de "entrar a hablar". La propuesta lleva el texto ORIGINAL del
otro y un enlace a la Mini App que abre un campo vacío; los estados los mueve
la API (/synapses/{id}/address) con el acto firmado. Lo no dirigido decae en
silencio.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import redis

# Asegurar que el path incluya la raíz
sys.path.append(os.getcwd())

from apps.m2_handshake import gradiente
from packages.domain.database import SessionLocal
from packages.domain.models import Node, Synapse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("handshake_worker")

MINIAPP_URL = os.getenv("MINIAPP_URL", "http://localhost:5173")
TTL_DIAS = int(os.getenv("HANDSHAKE_TTL_DIAS", str(gradiente.TTL_DIAS_DEFAULT)))
SWEEP_SECONDS = 300


def notificar(r, actor_id, texto):
    r.publish("telegram_outbound", json.dumps({"actor_id": actor_id, "text": texto}))


def proponer(r, synapse_id):
    """La propuesta: texto original de la intención del otro + campo vacío."""
    db = SessionLocal()
    try:
        syn = db.query(Synapse).filter(Synapse.id == synapse_id).first()
        if not syn:
            return
        node_origin = db.query(Node).filter(Node.id == syn.origin_node_id).first()
        node_target = db.query(Node).filter(Node.id == syn.target_node_id).first()
        enlace = gradiente.enlace_sinapsis(syn.id, MINIAPP_URL)
        if node_target:
            notificar(r, syn.origin_actor_id,
                      gradiente.mensaje_propuesta(node_target.text_raw, enlace))
        if node_origin:
            notificar(r, syn.target_actor_id,
                      gradiente.mensaje_propuesta(node_origin.text_raw, enlace))
        logger.info(f"[PROPUESTA] Sinapsis {syn.id}: texto original a ambas partes, sin botón.")
    finally:
        db.close()


def barrer_vencidas():
    """El silencio que decae: sin notificación, sin registro de rechazo (INV-02/03)."""
    db = SessionLocal()
    try:
        limite = datetime.now(timezone.utc) - timedelta(days=TTL_DIAS)
        vencidas = db.query(Synapse).filter(
            Synapse.status.in_([gradiente.PROPOSED, gradiente.ADDRESSED,
                                gradiente.LEGACY_PROPOSED]),
            Synapse.created_at < limite,
        ).all()
        for syn in vencidas:
            syn.status = gradiente.EXPIRED
        if vencidas:
            db.commit()
            logger.info(f"[EXPIRY] {len(vencidas)} propuestas decaen en silencio.")
    finally:
        db.close()


def run():
    redis_url = os.getenv("REDIS_URL", "redis://rizoma-redis:6379/0")
    r = redis.from_url(redis_url)
    pubsub = r.pubsub()
    pubsub.subscribe("rizoma.v2.global")
    logger.info("[*] Handshake por gradiente (WP-02): proposed -> addressed -> active | expired.")

    ultima_barrida = 0.0
    while True:
        try:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                event = json.loads(message["data"])
                if event.get("action_type") == "match_found":
                    params = event.get("payload", {}).get("parameters", {})
                    synapse_id = params.get("synapse_id")
                    if synapse_id:
                        proponer(r, synapse_id)
            if time.time() - ultima_barrida > SWEEP_SECONDS:
                barrer_vencidas()
                ultima_barrida = time.time()
        except Exception as exc:
            logger.error(f"[!] Error en el loop del gradiente: {exc}")
            time.sleep(1)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("\n[*] Handshake Worker detenido.")
