from apps.worker.celery_app import celery_app
from packages.domain.database import SessionLocal
from packages.domain.models import Node, ActionLog, SemanticRule

# ... (dentro del archivo)

@celery_app.task(name="apps.worker.tasks.apply_pending_actions")
def apply_pending_actions():
    """
    Toma propuestas de la bitácora y las materializa en el sistema.
    """
    db = SessionLocal()
    try:
        # 1. Buscar observaciones de clústeres no aplicadas
        logs = db.query(ActionLog).filter(ActionLog.status == "dry_run").all()
        
        applied_count = 0
        for log in logs:
            props = log.parameters_proposed
            label = props.get("proposed_label")
            multiplier = props.get("mass_multiplier", 1.0)
            
            if not label: continue
            
            # 2. Crear o actualizar la regla semántica
            rule = db.query(SemanticRule).filter(SemanticRule.label == label).first()
            if not rule:
                rule = SemanticRule(label=label, mass_multiplier=multiplier)
                db.add(rule)
            
            # 3. Marcar nodos del clúster con la nueva etiqueta para que la regla les afecte
            node_ids = log.pattern_observed.get("node_ids", [])
            if node_ids:
                clean_label = label.replace('#', '')
                # Usamos una forma más compatible de manejar arrays en SQLAlchemy/Postgres
                for nid in node_ids:
                    node = db.query(Node).filter(Node.id == nid).first()
                    if node:
                        current_groups = list(node.groups) if node.groups else []
                        if clean_label not in current_groups:
                            current_groups.append(clean_label)
                            node.groups = current_groups
            
            # 4. Marcar log como aplicado
            log.status = "applied"
            log.applied_at = datetime.datetime.utcnow()
            applied_count += 1
            
        db.commit()
        return f"Applied {applied_count} generative actions."
    finally:
        db.close()
from packages.adapters.adapter import OllamaAdapter
import datetime
from sqlalchemy import update, func, select
import json
import asyncio

ollama = OllamaAdapter()

from packages.domain.models import Node, ActionLog, SemanticRule, SearchLog, Actor

# ... (dentro del archivo)

from apps.worker.broadcaster import NetworkBroadcaster

broadcaster = NetworkBroadcaster()

@celery_app.task(name="apps.worker.tasks.run_observer_cycle")
def run_observer_cycle():
    """
    Analiza el corpus y emite señales de curación a la red global.
    """
    db = SessionLocal()
    try:
        # --- 1. Detección de Clústeres ---
        nodes = db.query(Node).filter(Node.state == "active", Node.content_vector.isnot(None)).all()
        if len(nodes) >= 2:
            reasoning = "Se observa una comunidad emergente interesada en agricultura urbana."
            params = {"proposed_label": "#cultivo-urbano", "mass_multiplier": 1.2}
            
            # Emitir señal a la RED
            broadcaster.broadcast_signal("cluster_detected", reasoning, params)
            
            # Registrar en DB local (ya existente)
            new_log = ActionLog(
                action_type="cluster_detected",
                pattern_observed={"node_ids": [n.id for n in nodes]},
                agent_reasoning=reasoning,
                parameters_proposed=params
            )
            db.add(new_log)

        # --- 2. Detección de Escasez ---
        all_logs = db.query(SearchLog.query_text).filter(SearchLog.results_count == 0).all()
        counts = {}
        for log in all_logs:
            counts[log.query_text] = counts.get(log.query_text, 0) + 1
            
        for text, count in counts.items():
            if count >= 3:
                reasoning = f"Se detecta alta demanda de '{text}' sin oferta disponible."
                params = {"signal": "low_supply", "target": text}
                
                # Emitir señal a la RED
                broadcaster.broadcast_signal("scarcity_detected", reasoning, params)
                
                scarcity_log = ActionLog(
                    action_type="scarcity_detected",
                    pattern_observed={"query": text, "hits": count},
                    agent_reasoning=reasoning,
                    parameters_proposed=params
                )
                db.add(scarcity_log)

        db.commit()
        return "Observer cycle completed and signals broadcasted."
    finally:
        db.close()

@celery_app.task(name="apps.worker.tasks.process_node_embedding", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_node_embedding(node_id: str):
    """
    Genera el embedding para un nodo y lo activa.
    """
    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.id == node_id).first()
        if not node: return f"Node {node_id} not found"

        parsed = ollama.parse_emission(node.text_raw)
        loop = asyncio.get_event_loop()
        vector = loop.run_until_complete(ollama.generate_embedding(parsed["clean_text"]))

        node.content_vector = vector
        node.text_normalized = parsed["clean_text"]
        node.state = "active"
        node.last_touched = datetime.datetime.utcnow()
        
        db.commit()
        return f"Node {node_id} activated"
    finally:
        db.close()

@celery_app.task(name="apps.worker.tasks.apply_semantic_antiquity")
def apply_semantic_antiquity():
    """
    Premia a los actores cuyos nodos han sobrevivido y mantenido masa.
    """
    db = SessionLocal()
    try:
        # Simplificamos: Cualquier nodo activo con masa > 0.5
        stable_nodes = db.query(Node).filter(Node.state == "active", Node.mass > 0.5).all()
        print(f"DEBUG: Encontrados {len(stable_nodes)} nodos para maduración.")

        rewarded_actors = 0
        for node in stable_nodes:
            actor = db.query(Actor).filter(Actor.id == node.actor_id).first()
            if actor:
                old_rep = actor.reputation
                actor.reputation = float(actor.reputation) + 0.1
                print(f"DEBUG: Actor {actor.id} madura de {old_rep} a {actor.reputation}")
                rewarded_actors += 1
        
        db.commit()
        return f"Maduración aplicada a {rewarded_actors} actores."
    finally:
        db.close()

@celery_app.task(name="apps.worker.tasks.nightly_decay")
def nightly_decay():
    """
    Aplica decaimiento de masa diario.
    """
    db = SessionLocal()
    try:
        decay_factor = 0.967
        db.execute(update(Node).where(Node.state == "active").values(mass=Node.mass * decay_factor))
        db.commit()
        return "Decay applied"
    finally:
        db.close()

@celery_app.task(name="apps.worker.tasks.forgetful_protocol_cleanup")
def forgetful_protocol_cleanup():
    """
    Implementa el 'Protocolo Olvidadizo': Borra el texto original y el vector
    de nodos cerrados hace más de 30 días para proteger la privacidad,
    manteniendo intacta la reputación del actor.
    """
    db = SessionLocal()
    try:
        limit_date = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        
        # Seleccionamos nodos cerrados cuya fecha de cierre superó el límite
        # y que aún no han sido anonimizados.
        nodes_to_clear = db.query(Node).filter(
            Node.state == "closed",
            Node.closed_at < limit_date,
            Node.text_raw != "[CONTENIDO ELIMINADO POR PRIVACIDAD]"
        ).all()
        
        cleared_count = 0
        for node in nodes_to_clear:
            node.text_raw = "[CONTENIDO ELIMINADO POR PRIVACIDAD]"
            node.text_normalized = None
            node.content_vector = None # Ya no es buscable semánticamente
            cleared_count += 1
            
        db.commit()
        return f"Protocolo Olvidadizo: {cleared_count} nodos anonimizados exitosamente."
    finally:
        db.close()
