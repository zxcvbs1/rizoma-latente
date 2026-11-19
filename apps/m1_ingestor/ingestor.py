import redis
import json
import os
import sys
import asyncio

# Asegurar que el path incluya la raíz
sys.path.append(os.getcwd())

from apps.api.security import SecurityService
from packages.domain.database import SessionLocal
from packages.domain.models import Node, Actor, Synapse
from packages.adapters.adapter import OllamaAdapter
import uuid
from datetime import datetime

from packages.adapters.waku_adapter import WakuAdapter
from apps.worker.broadcaster import NetworkBroadcaster
import time

class NetworkIngestor:
    def __init__(self):
        self.waku = WakuAdapter()
        self.security = SecurityService()
        self.ollama = OllamaAdapter()
        self.broadcaster = NetworkBroadcaster()
        self.seen_messages = set() # Memoria de corto plazo para duplicados
        print(f"[*] Gateway Semántico iniciado. Escuchando Waku: {self.waku.content_topic}")

    async def listen_forever(self):
        print(f"[*] Smart Listener activado. Bebiendo del Océano de Datos...")
        while True:
            try:
                # 1. Recuperar mensajes del Océano (Waku)
                events = await self.waku.get_messages()
                
                # Filtrar solo mensajes realmente nuevos
                new_events = [e for e in events if str(e) not in self.seen_messages]
                
                if new_events:
                    print(f"[*] Capturadas {len(new_events)} intenciones NUEVAS...")
                    for event in new_events:
                        await self.process_event(event)
                        self.seen_messages.add(str(event))
                
            except Exception as e:
                print(f"[!] Error en ciclo de escucha: {e}")
            
            # Pausa de respiración del Océano
            await asyncio.sleep(5)

    async def process_event(self, event):
        """Procesa un evento individual del Océano."""
        print(f"[DEBUG] Evento crudo recibido: {json.dumps(event, indent=2)}")
        try:
            if event.get("protocol") != "rizoma.v2": 
                print(f"[!] Protocolo incorrecto: {event.get('protocol')}")
                return

            action = event.get("action")
            actor_id = event.get("actor_id")
            nonce = event.get("nonce")
            timestamp = event.get("timestamp")
            payload = event.get("payload", {})

            # WP-01 (INV-12): ninguna emisión sin firma verificada entra al
            # índice. Sin actores de confianza, sin bypasses de desarrollo.
            if action == "emit":
                text = payload.get("text")
                if not text:
                    print(f"[RECHAZO] Emisión sin texto de {actor_id}")
                    return

                normalized = self.security.normalize_actor_id(actor_id)
                if not normalized:
                    print(f"[RECHAZO] actor_id inválido (se exige dirección EIP-55): {actor_id}")
                    return
                actor_id = normalized

                if not event.get("signature"):
                    print(f"[RECHAZO] Emisión sin firma de {actor_id}")
                    return
                if not timestamp or not nonce:
                    print(f"[RECHAZO] Emisión sin timestamp o nonce de {actor_id}")
                    return
                if not self.security.is_valid_timestamp(timestamp):
                    print(f"[RECHAZO] Timestamp fuera de la ventana de {self.security.max_age_minutes} min ({actor_id})")
                    return
                if not self.security.is_nonce_new(actor_id, nonce):
                    print(f"[RECHAZO] Replay detectado: nonce repetido de {actor_id}")
                    return

                msg = f"rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}"
                if not self.security.verify_eip191_signature(actor_id, event["signature"], msg):
                    print(f"[RECHAZO] Firma inválida para {actor_id}")
                    return

                allowed, reason = self.security.check_rate_limit(actor_id)
                if not allowed:
                    print(f"[RECHAZO] {reason} ({actor_id})")
                    return

                print(f"[+] Emisión verificada. Ingestando intención de {actor_id[:10]}...")
                public_key = self.security.recover_public_key(event["signature"], msg)
                await self.ingest_with_profile(actor_id, text, public_key=public_key)
            
            elif action == "signal":
                # Las señales de red coordinan a los Gateways
                print(f"[*] Señal de red recibida de {actor_id[:10]}")

        except Exception as e:
            print(f"[!] Error procesando evento: {e}")

    async def ingest_with_profile(self, actor_id, text, public_key=None):
        """Guarda la intención y genera su vector semántico."""
        print(f"[*] Iniciando ingesta para {actor_id}...")
        db = SessionLocal()
        try:
            # 4. Asegurar existencia del Actor
            print(f"[*] Buscando/Creando Actor {actor_id}...")
            actor = db.query(Actor).filter(Actor.id == actor_id).first()
            if not actor:
                print(f"[*] Nuevo Actor detectado: {actor_id}. Creando perfil...")
                actor = Actor(id=actor_id, reputation=0.5)
                db.add(actor)
                db.flush()
                print(f"[OK] Actor {actor_id} creado.")
            # La firma hace pública la clave; se registra para que la Mini App
            # cifre la primera palabra al topic derivado (01_red §4.2).
            if public_key and (actor.payload or {}).get("public_key") != public_key:
                actor.payload = {**(actor.payload or {}), "public_key": public_key}

            # 5. Parsear e Indexar
            print(f"[*] Parseando texto: '{text}'")
            parsed = self.ollama.parse_emission(text)
            print(f"[*] Parseo exitoso: {parsed['command_slug']}")
            
            node_id = f"{parsed['command_slug']}-{uuid.uuid4().hex[:6]}"
            
            # Generar vector semántico (Asíncrono real)
            print(f"[*] Generando vector semántico...")
            vector = await self.ollama.generate_embedding(parsed['clean_text'])
            print(f"[OK] Vector generado ({len(vector)} dimensiones).")
            
            # WP-24: los topics de bucket LSH donde esta intención se anuncia
            # (uno por tabla). Un semi-nodo suscripto a esos buckets la indexa.
            from packages.adapters import semi_nodo as _sn
            buckets = _sn.registrar_intencion(vector)

            new_node = Node(
                id=node_id,
                state="active",
                text_raw=text,
                command_raw=parsed['command_raw'],
                command_slug=parsed['command_slug'],
                groups=parsed['groups'],
                content_vector=vector,
                actor_id=actor_id,
                server_id="network-ingested",
                payload={"lsh_buckets": buckets},
            )
            db.add(new_node)
            db.flush()

            # WP-28: la gramática es sedimento, no gate; una falla acá no
            # bloquea la ingesta (se reporta, no se silencia).
            try:
                from apps.worker.gramatica import gramaticalizar
                gramaticalizar(db, parsed['command_slug'])
            except Exception as exc:
                print(f"[!] Gramaticalización no disponible para {node_id}: {exc}")

            print(f"[OK] Nodo {node_id} indexado ({len(buckets)} buckets LSH).")

            # 6. ENCUENTRO SEMÁNTICO (Real-time Match)
            self.find_matches_and_handshake(db, new_node)
            
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[!] Error en ingesta: {e}")
        finally:
            db.close()

    def find_matches_and_handshake(self, db, new_node):
        """Busca resonancias semánticas en la base de datos local."""
        from sqlalchemy import text as sa_text
        
        target_slug = "busco" if new_node.command_slug == "ofrezco" else "ofrezco"
        
        # Consulta pgvector (similitud de coseno)
        query = sa_text("""
            SELECT id, actor_id, COALESCE(1.0 - (content_vector <=> :vec), 0.0) as similarity 
            FROM nodes 
            WHERE command_slug = :slug AND state = 'active' AND id != :current_id
            ORDER BY similarity DESC LIMIT 1
        """)
        
        # Convertir vector a formato Postgres
        vec_str = "[" + ",".join(map(str, new_node.content_vector)) + "]"
        
        result = db.execute(query, {
            "vec": vec_str, 
            "slug": target_slug,
            "current_id": new_node.id
        }).fetchone()

        if result and result.similarity is not None and result.similarity > 0.7:
            match_id, target_actor, similarity = result.id, result.actor_id, result.similarity
            print(f"\n[MATCH] ✨ RESONANCIA DETECTADA ({similarity:.2f})")
            print(f"        Original: {new_node.text_raw}")
            print(f"        Match: {match_id} (de {target_actor[:10]}...)")
            
            # Persistir la sinapsis en base de datos
            new_syn = Synapse(
                origin_actor_id=new_node.actor_id,
                target_actor_id=target_actor,
                origin_node_id=new_node.id,
                target_node_id=match_id,
                similarity=float(similarity),
                status="proposed"  # WP-02: el gradiente arranca acá
            )
            db.add(new_syn)
            db.flush()
            
            # Emitir señal de red global (Vía Redis/Waku)
            self.broadcaster.broadcast_signal(
                action_type="match_found",
                agent_reasoning=f"Resonancia semántica ({similarity:.2f}) entre intenciones.",
                parameters={
                    "synapse_id": str(new_syn.id),
                    "origin_actor": new_node.actor_id,
                    "target_actor": target_actor,
                    "similarity": float(similarity),
                    "context": new_node.text_raw[:50]
                }
            )
            print(f"[GATEWAY] Sinapsis {new_syn.id} persistida y señal emitida. 📡✨\n")

if __name__ == "__main__":
    ingestor = NetworkIngestor()
    asyncio.run(ingestor.listen_forever())
