"""
Tareas del worker. `nightly_decay` es el olvido estructural (WP-12, INV-03);
`process_node_embedding` vectoriza los nodos que entran por la API.
"""
import asyncio
from datetime import datetime, timezone

from apps.worker.celery_app import celery_app
from packages.domain.database import SessionLocal
from packages.domain.models import Node
from packages.adapters.adapter import OllamaAdapter
from apps.worker import olvido


@celery_app.task
def nightly_decay():
    """El olvido corre por scheduler, sin acción de nadie (INV-03)."""
    db = SessionLocal()
    try:
        contadores = olvido.barrer(db, datetime.now(timezone.utc))
        db.commit()
        print(f"[OLVIDO] {contadores}")
        return contadores
    except Exception as exc:
        db.rollback()
        print(f"[!] Error en el barrido de olvido: {exc}")
        raise
    finally:
        db.close()


@celery_app.task
def process_node_embedding(node_id: str):
    """Vectoriza un nodo pendiente con el embedder local del nodo (INV-17)."""
    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.id == node_id).first()
        if not node:
            return {"node_id": node_id, "estado": "inexistente"}
        ollama = OllamaAdapter()
        texto = node.text_normalized or node.text_raw
        node.content_vector = asyncio.run(ollama.generate_embedding(texto))
        node.state = "active"
        db.commit()
        return {"node_id": node_id, "estado": "active"}
    except Exception as exc:
        db.rollback()
        print(f"[!] Error vectorizando {node_id}: {exc}")
        raise
    finally:
        db.close()


@celery_app.task
def ciclo_emergencia():
    """El agente reactivo (INV-14): surcos -> propuestas de pieza. Corre por
    scheduler si el operador lo agenda; jamás actúa fuera de la lista blanca."""
    from apps.worker import emergencia as em
    from packages.domain.identity import KeyStore

    db = SessionLocal()
    try:
        address, _ = KeyStore().get_or_create("agente:emergencia")
        propuestas = em.ciclo_emergencia(db, proponente=address)
        db.commit()
        print(f"[EMERGENCIA] {len(propuestas)} piezas propuestas")
        return {"propuestas": [p.id for p in propuestas]}
    except Exception as exc:
        db.rollback()
        print(f"[!] Error en el ciclo de emergencia: {exc}")
        raise
    finally:
        db.close()
