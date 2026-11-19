from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.orm import Session
from packages.domain.models import Node, SemanticRule
import math

class RelevanceEngine:
    @staticmethod
    def search_nodes(db: Session, query_vector: list[float], limit: int = 10, offset: int = 0,
                     group: str = None, umbral_semantico: float = 0.0):
        """
        Implementa la fórmula de ranking evolucionada:
        score = (sem_sim * ln(mass + 1) * decay) * rule_multiplier

        umbral_semantico (jul 2026, del banco de resonancias): piso HONESTO
        sobre el coseno puro (sem_sim), no sobre el total inflado por masa o
        frescura. Por debajo, la coincidencia no se muestra: "nadie resuena
        todavía" es una respuesta legítima. El valor se ajusta corriendo
        tests/eval_resonancias.py, no a ojo.
        """
        
        # 1. Componentes Base (Semántica, Masa, Decay)
        semantic_score = (1 - Node.content_vector.cosine_distance(query_vector))
        # Ajustamos para que masa=1 resulte en multiplicador 1.0 (usando log natural de masa + 1)
        # pero escalando para que el impacto sea positivo desde el inicio
        mass_weight = func.log(Node.mass + 1) / func.log(2.0) 
        days_diff = func.extract('day', func.now() - Node.last_touched)
        freshness_weight = func.greatest(0.15, func.exp(-days_diff / 30.0))
        
        base_score = semantic_score * mass_weight * freshness_weight

        # 2. Aplicar Multiplicadores de Reglas Dinámicas
        # Buscamos si el nodo tiene algún tag que coincida con una regla activa
        # Para el MVP, usamos un subquery o una lógica de CASE
        # Simplificación: si el nodo tiene algún grupo que tiene regla, aplicamos el máximo multiplicador encontrado
        rule_subquery = (
            select(func.max(SemanticRule.mass_multiplier))
            .where(and_(
                SemanticRule.is_active == True,
                Node.groups.any(func.replace(SemanticRule.label, '#', ''))
            ))
            .scalar_subquery()
        )
        
        # Si no hay regla, el multiplicador es 1.0
        final_multiplier = func.coalesce(rule_subquery, 1.0)
        final_score = base_score * final_multiplier

        query = select(
            Node,
            final_score.label("total_score"),
            semantic_score.label("semantic_score")
        ).where(
            and_(
                Node.state == "active",
                Node.content_vector.isnot(None)
            )
        )

        if umbral_semantico > 0:
            query = query.where(semantic_score >= umbral_semantico)

        if group:
            query = query.where(Node.groups.any(group))

        # Ordenar por el score calculado y limitar
        query = query.order_by(text("total_score DESC")).offset(offset).limit(limit)

        return db.execute(query).all()

    @staticmethod
    def deduplicar_resultados(resultados: list) -> list:
        """El mismo texto emitido N veces es UNA resonancia, no tres renglones
        (el 'Busco miel' triplicado del playtest del puente, jul 2026).
        Conserva el primero (la lista ya llega ordenada por score desc)."""
        vistos, unicos = set(), []
        for r in resultados:
            clave = ((r.get("node") or {}).get("text_raw") or "").strip().lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            unicos.append(r)
        return unicos
