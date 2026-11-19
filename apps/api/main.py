from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from apps.api.security import SecurityService
from apps.api.schemas import (EmitRequest, LinkRequest, NodePatchRequest, SynapseAddressRequest,
                              ActorControlRequest, AventuraIniciarRequest, AventuraTerminosRequest,
                              AventuraPrediccionRequest, AventuraDecisionRequest, AventuraCerrarRequest)
from apps.api import controles
from apps.motor_aventura import motor as motor_aventura
from apps.motor_simulacion import motor as motor_simulacion
from packages.domain import frontera
from packages.domain.models import Partida, Corrida
from apps.api.schemas import (CorridaIniciarRequest, CorridaParticipanteRequest,
                              CorridaContextoRequest, CorridaActoRequest,
                              CorridaTensionesRequest, CorridaRespuestaRequest,
                              CorridaPresupuestoRequest, CorridaDelegadaRequest,
                              CorridaCerrarRequest,
                              InjertoRegistrarRequest,
                              VeredictoRequest, AdopcionRequest)
from apps.motor_simulacion import delegacion
from apps.motor_simulacion import relato as relato_mod
from apps.motor_simulacion.runtime_concordia import _concordia_instalada
from packages.domain.models import Injerto, PropuestaForma, Forma
from apps.acervo import acervo
from apps.acervo import galeria as galeria_mod
from apps.espejo import espejo as espejo_mod
from apps.worker import emergencia
from packages.domain.models import Pieza
from apps.espejo.pagina import PAGINA_ESPEJO
from fastapi.responses import HTMLResponse
from apps.api.schemas import (FormaProponerRequest, RevisionFormaRequest,
                              BifurcarFormaRequest, SinteticoRequest,
                              PersonajeRequest,
                              RubricaProponerRequest, TareaCrearRequest,
                              TareaResolverRequest)
from apps.worker import pool
from apps.motor_aventura import multiplayer
from apps.api.schemas import (SesionAbrirRequest, SesionEntrarRequest,
                              TurnoProponerRequest, TurnoValidarRequest)
from packages.domain.models import SesionMultiplayer
from packages.domain.database import get_db, init_db
from packages.domain.models import Node, Actor, Link, Synapse
from packages.adapters.adapter import OllamaAdapter
from packages.adapters.engine import RelevanceEngine
from apps.m2_handshake import gradiente
import uuid
import os
import json
import httpx
import asyncio
import datetime
from typing import Optional

app = FastAPI(title="Rizoma Latente API")
security = SecurityService()
ollama = OllamaAdapter()

@app.on_event("startup")
def startup():
    init_db()
    # WP-02: columnas del gradiente, idempotente (sin migración formal)
    from packages.domain.database import engine
    from sqlalchemy import text as sa_text
    with engine.begin() as conn:
        for ddl in (
            "ALTER TABLE synapses ADD COLUMN IF NOT EXISTS addressed_by VARCHAR(255)",
            "ALTER TABLE synapses ADD COLUMN IF NOT EXISTS addressed_at TIMESTAMPTZ",
            "ALTER TABLE synapses ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ",
        ):
            conn.execute(sa_text(ddl))

@app.post("/emit", status_code=status.HTTP_202_ACCEPTED)
async def emit(req: EmitRequest, db: Session = Depends(get_db)):
    if not security.is_valid_timestamp(req.timestamp):
        raise HTTPException(status_code=401, detail="Timestamp expired or invalid")
    if not security.is_nonce_new(req.actor_id, req.nonce):
        raise HTTPException(status_code=401, detail="Nonce already used")
    msg = f"rizoma.emit|{req.actor_id}|{req.timestamp}|{req.nonce}|{req.text}"
    if not security.verify_eip191_signature(req.actor_id, req.signature, msg):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 1. Guardar localmente, VECTORIZADO si el embedder está (un nodo sin
    # ingestor, como un segundo nodo mínimo, tiene que poder buscar lo que
    # recibió directo; hallazgo del playtest federado, jul 2026). Si Ollama
    # no responde, queda sin vector y el barrido del worker lo completa.
    parsed = ollama.parse_emission(req.text)
    node_id = f"{parsed['command_slug']}-{uuid.uuid4().hex[:6]}"
    try:
        # El comando NO viaja en el vector (banco de resonancias, jul 2026):
        # dos "!busco" no se parecen por el gesto de buscar sino por su
        # contenido. Mismo criterio que el ingestor (clean_text) desde siempre:
        # esta asimetría era un bug solo del camino directo.
        vector = await ollama.generate_embedding(parsed.get('clean_text') or req.text)
    except Exception:
        vector = None
    # ACTIVA de nacimiento: la firma se verificó recién (INV-12 satisfecho acá
    # mismo). El ingestor no la duplica: el nonce ya quedó consumido y su
    # captura desde Waku rebota como replay. "pending" la dejaba invisible
    # para siempre en un nodo sin ingestor (hallazgo del playtest federado).
    new_node = Node(
        id=node_id, state="active", text_raw=req.text,
        command_raw=parsed['command_raw'], command_slug=parsed['command_slug'],
        groups=parsed['groups'], actor_id=req.actor_id, server_id="local-01",
        content_vector=vector
    )
    if req.ttl_dias is not None:
        new_node.ttl_dias = req.ttl_dias
    db.add(new_node)
    db.commit()

    # WP-28: la gramática es sedimento, no gate; una falla acá no bloquea
    # la emisión (se reporta, no se silencia).
    try:
        from apps.worker.gramatica import gramaticalizar
        gramaticalizar(db, parsed['command_slug'])
        db.commit()
    except Exception as exc:
        print(f"[!] Gramaticalización no disponible para {node_id}: {exc}")

    # 2. PROPAGAR AL OCÉANO (Waku)
    # Esto permite que el Ingestor Semántico lo capture y busque matches
    from packages.adapters.waku_adapter import WakuAdapter
    waku = WakuAdapter()
    event = {
        "protocol": "rizoma.v2",
        "action": "emit",
        "actor_id": req.actor_id,
        "timestamp": req.timestamp,
        "nonce": req.nonce,
        "payload": {"text": req.text},
        "signature": req.signature
    }
    await waku.broadcast(event)
    print(f"[WAKU] Intención {node_id} propagada al Océano. 🌊")

    try:
        from apps.worker.tasks import process_node_embedding
        process_node_embedding.delay(node_id)
    except Exception as exc:
        # el ingestor Waku procesa la emisión igual; el worker acá es opcional
        print(f"[!] Worker de embeddings no disponible: {exc}")
    return {"node_id": node_id, "state": "pending"}

# Piso honesto de resonancia (banco de resonancias, jul 2026): coseno puro
# mínimo para MOSTRAR una coincidencia. Elegido por doble barrido: el banco
# aislado (tests/eval_resonancias.py) dio meseta de F hasta 0.65, y el
# antagonista de punta a punta contra el nodo vivo
# (tests/eval_resonancias_e2e.py) mostró que a 0.65 una sonda imposible aún
# arrastraba una coincidencia forzada; a 0.66, 9/10 aciertos, cero falsos y
# el vacío honesto. Mejor huérfana honesta que falso resonante. Se reajusta
# midiendo, no a ojo. Config: nodo.toml [umbrales] resonancia_busqueda, o la
# variable de entorno.
UMBRAL_BUSQUEDA = float(os.getenv("RIZOMA_UMBRAL_BUSQUEDA", "0.66"))


deduplicar_resultados = RelevanceEngine.deduplicar_resultados


NOTA_SIN_RESONANCIA = ("nadie resuena con esto todavía: tu señal queda "
                       "sembrada, esperando a su intérprete (resonancia latente)")


@app.get("/search")
async def search(q: str, limit: int = 10, offset: int = 0, group: Optional[str] = None, db: Session = Depends(get_db)):
    # Simetría con la emisión: si la búsqueda trae un !comando, el vector se
    # calcula sobre el contenido (el comando no es materia semántica).
    parsed_q = ollama.parse_emission(q) if q.strip().startswith("!") else None
    query_vector = await ollama.generate_embedding(
        (parsed_q.get("clean_text") if parsed_q else None) or q)

    # 1. Búsqueda Local (el piso se aplica sobre el coseno puro, en el engine)
    db_results = RelevanceEngine.search_nodes(db, query_vector, limit, offset, group,
                                              umbral_semantico=UMBRAL_BUSQUEDA)
    local_results = []
    for row in db_results:
        node = row.Node
        local_results.append({
            "node": {
                "id": str(node.id), "state": str(node.state), "text_raw": str(node.text_raw),
                "command_slug": str(node.command_slug), "groups": list(node.groups) if node.groups else [],
                "mass": float(node.mass), "actor_id": str(node.actor_id),
                "created_at": node.created_at.isoformat() if node.created_at else None
            },
            "score": float(row.total_score),
            "afinidad": float(row.semantic_score),
            "server_origin": "local", "peer_url": None
        })

    # WP-10 (INV-11): el nodo sirve SOLO su lectura local. La federación la
    # arma el CLIENTE consultando N nodos y mergeando por su cuenta
    # (packages/adapters/federacion.py). El merge server-side ponderado por
    # reputación de peers quedó retirado: era una lectura coronada.
    all_results = deduplicar_resultados(
        sorted(local_results, key=lambda x: x["score"], reverse=True))

    from packages.domain.models import SearchLog
    db.add(SearchLog(query_text=q, results_count=len(all_results)))
    db.commit()
    respuesta = {"results": all_results[:limit], "umbral": UMBRAL_BUSQUEDA}
    if not all_results:
        respuesta["nota"] = NOTA_SIN_RESONANCIA
    frontera.validar_respuesta_publica(respuesta)  # T-02: ningún campo privado se filtra
    return respuesta

@app.post("/link", status_code=status.HTTP_201_CREATED)
async def create_link(req: LinkRequest, db: Session = Depends(get_db)):
    try:
        if not security.is_valid_timestamp(req.timestamp):
            raise HTTPException(status_code=401, detail="Timestamp expired")
        if not security.is_nonce_new(req.actor_id, req.nonce):
            raise HTTPException(status_code=401, detail="Nonce already used")
        msg = f"rizoma.link|{req.actor_id}|{req.timestamp}|{req.nonce}|{req.node_a}|{req.node_b}"
        if not security.verify_eip191_signature(req.actor_id, req.signature, msg):
            raise HTTPException(status_code=401, detail="Invalid signature")

        # El link puede ser local-local o local-federado
        node_a = db.query(Node).filter(Node.id == req.node_a).first()
        # Si node_b no es local, buscamos si algún peer lo conoce (simplificado para MVP)
        node_b = db.query(Node).filter(Node.id == req.node_b).first()
        
        if not node_a:
            raise HTTPException(status_code=404, detail="Node A not found")

        # 4. Obtener reputación del Actor
        actor = db.query(Actor).filter(Actor.id == req.actor_id).first()
        if not actor:
            # Si es la primera vez que lo vemos, le damos una reputación base baja
            actor = Actor(id=req.actor_id, reputation=0.5)
            db.add(actor)
            db.flush()

        # WP-10 (INV-11): el premio de reputación al peer quedó retirado: el
        # nodo no rankea nodos ajenos; la lista de nodos es del cliente.

        # 6. Calcular inyección de masa proporcional
        # Fórmula: delta = 0.5 * R_actor
        mass_boost = 0.5 * actor.reputation
        node_a.mass += mass_boost

        # 7. Crear Link
        new_link = Link(
            node_a_id=req.node_a, node_a_server="local",
            node_b_id=req.node_b, node_b_server="local" if node_b else "remote",
            actor_id=req.actor_id, score=1.0, confirmed=True
        )
        db.add(new_link)
        db.commit()
        return {"link_id": str(new_link.id), "node_a_mass": node_a.mass, "applied_boost": mass_boost}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/node/{id}")
async def update_node(id: str, req: NodePatchRequest, db: Session = Depends(get_db)):
    if not security.is_valid_timestamp(req.timestamp): raise HTTPException(status_code=401)
    msg = f"rizoma.node.patch|{req.actor_id}|{req.timestamp}|{req.nonce}|{id}|{req.action}"
    if not security.verify_eip191_signature(req.actor_id, req.signature, msg): raise HTTPException(status_code=401)
    node = db.query(Node).filter(Node.id == id).first()
    if not node or node.actor_id != req.actor_id: raise HTTPException(status_code=403)
    if req.action == "close": node.state = "closed"
    if req.action == "renew":
        from apps.worker.olvido import renovar_intencion
        renovar_intencion(node)
    db.commit()
    return {"id": id, "state": node.state}

@app.get("/actors/{actor_id}/synapses")
async def get_synapses(actor_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """DEPRECADO (T-02, INV-10): el grafo de vínculos de una persona no es
    público; leerlo es derivar su grafo social. La consulta del propio grafo va
    por la huella FIRMADA (POST /actors/{id}/huella, WP-04), donde el dueño
    prueba que es él."""
    raise HTTPException(
        status_code=403,
        detail=("el grafo de vínculos no es público (INV-10); usá "
                "POST /actors/{id}/huella firmado por el dueño"))


async def _get_synapses_retirado(actor_id, limit, db):
    from sqlalchemy import func
    from packages.domain.models import Synapse
    actor_id_lower = actor_id.lower()
    syns = db.query(Synapse).filter(
        (func.lower(Synapse.origin_actor_id) == actor_id_lower) |
        (func.lower(Synapse.target_actor_id) == actor_id_lower)
    ).order_by(Synapse.created_at.desc()).limit(limit).all()

    results = []
    for s in syns:
        node_a = db.query(Node).filter(Node.id == s.origin_node_id).first()
        node_b = db.query(Node).filter(Node.id == s.target_node_id).first()
        
        results.append({
            "synapse_id": str(s.id),
            "similarity": float(s.similarity),
            "status": str(s.status),
            "created_at": s.created_at.isoformat(),
            "origin": {
                "actor": str(s.origin_actor_id),
                "text": node_a.text_raw if node_a else "Contenido no disponible"
            },
            "target": {
                "actor": str(s.target_actor_id),
                "text": node_b.text_raw if node_b else "Contenido no disponible"
            }
        })
    return {"synapses": results}

@app.get("/synapses/{synapse_id}")
async def get_synapse(synapse_id: str, db: Session = Depends(get_db)):
    """Estado para la Mini App: el texto original del otro y un campo vacío.
    Acá no hay palabras, solo estados (01_red §4.2)."""
    try:
        sid = uuid.UUID(synapse_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Sinapsis inexistente")
    syn = db.query(Synapse).filter(Synapse.id == sid).first()
    if not syn:
        raise HTTPException(status_code=404, detail="Sinapsis inexistente")
    if gradiente.esta_vencida(syn.created_at, syn.status):
        syn.status = gradiente.EXPIRED
        db.commit()
    node_a = db.query(Node).filter(Node.id == syn.origin_node_id).first()
    node_b = db.query(Node).filter(Node.id == syn.target_node_id).first()

    def clave_publica(actor_id):
        actor = db.query(Actor).filter(Actor.id == actor_id).first()
        return (actor.payload or {}).get("public_key") if actor else None

    return {
        "synapse_id": str(syn.id),
        "status": gradiente.normalizar_estado(syn.status),
        "addressed_by": syn.addressed_by,
        "origin": {"actor": syn.origin_actor_id, "node": syn.origin_node_id,
                   "text": node_a.text_raw if node_a else None,
                   "public_key": clave_publica(syn.origin_actor_id)},
        "target": {"actor": syn.target_actor_id, "node": syn.target_node_id,
                   "text": node_b.text_raw if node_b else None,
                   "public_key": clave_publica(syn.target_actor_id)},
    }

@app.post("/synapses/{synapse_id}/address")
async def address_synapse(synapse_id: str, req: SynapseAddressRequest, db: Session = Depends(get_db)):
    """
    WP-02 (INV-01/02): registra el ACTO de dirigirse. La primera palabra viaja
    cifrada al topic derivado y nunca llega acá; este endpoint solo mueve el
    estado, con firma del contrato (rizoma.link). No existe "aceptar":
    existe dirigirse.
    """
    try:
        sid = uuid.UUID(synapse_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Sinapsis inexistente")
    syn = db.query(Synapse).filter(Synapse.id == sid).first()
    if not syn:
        raise HTTPException(status_code=404, detail="Sinapsis inexistente")

    if not security.is_valid_timestamp(req.timestamp):
        raise HTTPException(status_code=401, detail="Timestamp expired")
    if not security.is_nonce_new(req.actor_id, req.nonce):
        raise HTTPException(status_code=401, detail="Nonce already used")
    msg = gradiente.canonical_link(req.actor_id, req.timestamp, req.nonce,
                                   syn.origin_node_id, syn.target_node_id)
    if not security.verify_eip191_signature(req.actor_id, req.signature, msg):
        raise HTTPException(status_code=401, detail="Invalid signature")
    if not gradiente.es_parte(syn, req.actor_id):
        raise HTTPException(status_code=403, detail="No sos parte de esta sinapsis")

    if gradiente.esta_vencida(syn.created_at, syn.status):
        syn.status = gradiente.EXPIRED
        db.commit()
        raise HTTPException(status_code=410, detail="La propuesta expiró en silencio")

    try:
        nuevo, addressed_by = gradiente.transicionar(syn.status, syn.addressed_by, req.actor_id)
    except gradiente.TransicionInvalida as exc:
        raise HTTPException(status_code=exc.codigo, detail=exc.motivo)

    ahora = datetime.datetime.utcnow()
    syn.status = nuevo
    syn.addressed_by = addressed_by
    if nuevo == gradiente.ADDRESSED:
        syn.addressed_at = ahora
    if nuevo == gradiente.ACTIVE:
        syn.activated_at = ahora
    db.commit()

    # Notificación por el puente: al otro si addressed, a ambos si active.
    enlace = gradiente.enlace_sinapsis(syn.id, os.getenv("MINIAPP_URL", "http://localhost:5173"))
    partes = [p for p in (syn.origin_actor_id, syn.target_actor_id) if p]
    try:
        if nuevo == gradiente.ADDRESSED:
            for otro in [p for p in partes if p.lower() != req.actor_id.lower()]:
                security.redis.publish("telegram_outbound", json.dumps(
                    {"actor_id": otro, "text": gradiente.mensaje_addressed(enlace)}))
        elif nuevo == gradiente.ACTIVE:
            for parte in partes:
                security.redis.publish("telegram_outbound", json.dumps(
                    {"actor_id": parte, "text": gradiente.mensaje_active(enlace)}))
    except Exception as exc:
        print(f"[!] No se pudo notificar por el puente: {exc}")

    return {"synapse_id": str(syn.id), "status": nuevo}

def _verificar_control(req: ActorControlRequest, actor_path: str, action: str) -> str:
    """WP-04: solo el dueño de la llave, con firma del contrato."""
    actor = security.normalize_actor_id(req.actor_id)
    if not actor or actor.lower() != actor_path.lower():
        raise HTTPException(status_code=403, detail="Solo el dueño de la llave")
    if not security.is_valid_timestamp(req.timestamp):
        raise HTTPException(status_code=401, detail="Timestamp expired")
    if not security.is_nonce_new(actor, req.nonce):
        raise HTTPException(status_code=401, detail="Nonce already used")
    msg = controles.canonical_actor(actor, req.timestamp, req.nonce, action)
    if not security.verify_eip191_signature(actor, req.signature, msg):
        raise HTTPException(status_code=401, detail="Invalid signature")
    return actor

@app.post("/actors/{actor_id}/huella")
async def huella_actor(actor_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Ver y llevarse (INV-05, CU-T6): todo lo que la red sabe de la llave,
    exportable y legible. Nada más existe."""
    actor = _verificar_control(req, actor_id, "export")
    return controles.armar_huella(db, actor)

@app.post("/actors/{actor_id}/borrar")
async def borrar_actor(actor_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Borrar borra (INV-05): cascada real. Tras esto, ninguna búsqueda ni
    resonancia puede referenciar a la persona."""
    actor = _verificar_control(req, actor_id, "erase")
    contadores = controles.borrar_actor(db, actor)
    db.commit()
    controles.borrar_rastros_redis(security.redis, actor,
                                   datetime.datetime.utcnow().strftime("%Y%m%d"))
    return {"borrado": True, **contadores}

def _partida_del_actor(db, partida_id: str, actor: str):
    partida = db.query(Partida).filter(Partida.id == partida_id).first()
    if not partida:
        raise HTTPException(status_code=404, detail="Partida inexistente")
    if (partida.jugador_llave or "").lower() != actor.lower():
        raise HTTPException(status_code=403, detail="La partida es de otra llave")
    return partida

@app.post("/aventura/partidas", status_code=status.HTTP_201_CREATED)
async def aventura_iniciar(req: AventuraIniciarRequest, db: Session = Depends(get_db)):
    """WP-03/14: el nodo abre la partida; las escenas las genera el cliente."""
    actor = _verificar_control(req, req.actor_id, "aventura.iniciar")
    partida = motor_aventura.iniciar_partida(db, actor, req.marco)
    db.commit()
    return {"partida_id": partida.id, "estado": partida.estado}

@app.post("/aventura/partidas/{partida_id}/terminos")
async def aventura_terminos(partida_id: str, req: AventuraTerminosRequest, db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "aventura.terminos")
    _partida_del_actor(db, partida_id, actor)
    try:
        creados = motor_aventura.registrar_terminos(db, partida_id, req.terminos, req.origen_escena)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"terminos": creados}

@app.post("/aventura/partidas/{partida_id}/contexto")
async def aventura_contexto(partida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El nodo entrega SOLO el mapa propio y la memoria de esta partida (INV-17)."""
    actor = _verificar_control(req, req.actor_id, "aventura.contexto")
    _partida_del_actor(db, partida_id, actor)
    try:
        return motor_aventura.contexto_turno(db, partida_id)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/aventura/partidas/{partida_id}/prediccion")
async def aventura_prediccion(partida_id: str, req: AventuraPrediccionRequest, db: Session = Depends(get_db)):
    """La previsión se sella y NO se persiste (INV-04): vive en la memoria de
    partida y muere con ella. En el canvas blanco, la previsión calla (409)."""
    actor = _verificar_control(req, req.actor_id, "aventura.prediccion")
    _partida_del_actor(db, partida_id, actor)
    try:
        return motor_aventura.prever(db, partida_id, req.escena_id,
                                                req.opcion_prevista, req.razon)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/aventura/partidas/{partida_id}/decision")
async def aventura_decision(partida_id: str, req: AventuraDecisionRequest, db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "aventura.decision")
    _partida_del_actor(db, partida_id, actor)

    # Lector de doble vía (05 §4): la rúbrica es del cliente; la señal
    # vectorial es del nodo. Sin campo vectorial no se persiste a ciegas.
    if req.deslizamientos:
        try:
            limpios = [motor_aventura.validar_deslizamiento(c) for c in req.deslizamientos]
        except motor_aventura.MotorError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        piso = float(os.getenv("LECTOR_PISO_VECTORIAL", "0.15"))
        try:
            for limpio in limpios:
                vec_ev = await ollama.generate_embedding(limpio["evidencia"])
                vec_de = await ollama.generate_embedding(limpio["de_termino"])
                vec_ha = await ollama.generate_embedding(limpio["hacia_termino"])
                if not motor_aventura.validador_vectorial(vec_ev, vec_de, vec_ha, piso=piso):
                    raise HTTPException(
                        status_code=422,
                        detail=(f"lector doble vía: la evidencia no suena cerca de sus términos "
                                f"({limpio['de_termino']} -> {limpio['hacia_termino']})"))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503,
                                detail=f"el campo vectorial del nodo no está disponible: {exc}")

    try:
        resultado = motor_aventura.resolver_decision(
            db, partida_id, req.escena_id, req.eleccion, req.deslizamientos)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    # Único agregado permitido de la previsión (02_sujeto §3, alarma INV-13):
    # contador global, anónimo, sin ventana fina. Jamás por persona. El
    # acierto es CONFIRMACIÓN DE MAPA (solo refuerzo, sin arista nueva): si
    # la previsión acierta cada vez más, la gente está saliendo MÁS previsible
    # y el juego cambió de familia. Sin lectura no cuenta nadie.
    if resultado.get("prevision_sellada") and resultado.get("acierto_sistema") is not None:
        try:
            security.redis.incr("prevision:global:predicciones")
            if resultado.get("acierto_sistema"):
                security.redis.incr("prevision:global:aciertos")
        except Exception:
            pass
    # El puntaje trabaja EN SILENCIO (02_sujeto §3, corrección jul 2026): el
    # marcador y el acierto no viajan al cliente, así el GM no puede narrarlos
    # (exitismo fuera por construcción). Lo que el GM necesita queda: la
    # revelación (honestidad) y salir_del_mapa (dramaturgia).
    resultado.pop("marcador", None)
    resultado.pop("acierto_sistema", None)
    return resultado

@app.post("/aventura/partidas/{partida_id}/semillas")
async def aventura_semillas(partida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Fuentes de tensión: universales, términos mudos y pares que el mapa no
    cubre (divergir con criterio, no con intuición del cliente)."""
    actor = _verificar_control(req, req.actor_id, "aventura.semillas")
    _partida_del_actor(db, partida_id, actor)
    try:
        return motor_aventura.semillas(db, partida_id)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/aventura/partidas/{partida_id}/cerrar")
async def aventura_cerrar(partida_id: str, req: AventuraCerrarRequest, db: Session = Depends(get_db)):
    """Toda partida tiene final propio (INV-13); al cierre la memoria muere."""
    actor = _verificar_control(req, req.actor_id, "aventura.cerrar")
    _partida_del_actor(db, partida_id, actor)
    try:
        devolucion = motor_aventura.cerrar_partida(db, partida_id, req.lo_pide_el_jugador)
    except motor_aventura.MotorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return devolucion

def _corrida_del_operador(db, corrida_id: str, actor: str):
    corrida = db.query(Corrida).filter(Corrida.id == corrida_id).first()
    if not corrida:
        raise HTTPException(status_code=404, detail="Corrida inexistente")
    if (corrida.operador_llave or "").lower() != actor.lower():
        raise HTTPException(status_code=403, detail="La corrida es de otro operador")
    return corrida

def _sim(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except frontera.FronteraViolada as exc:
        # el incidente queda auditado a la vista (WP-15 / CU-T2)
        print(f"[FRONTERA] Bloqueado: {exc}")
        raise HTTPException(status_code=422, detail=f"frontera: {exc}")
    except motor_simulacion.MotorSimError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except acervo.AcervoError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.post("/corridas", status_code=status.HTTP_201_CREATED)
async def corrida_iniciar(req: CorridaIniciarRequest, db: Session = Depends(get_db)):
    """WP-16: el nodo guarda estado y validadores; las mentes las pone el
    cliente MCP del operador."""
    actor = _verificar_control(req, req.actor_id, "corrida.iniciar")
    corrida = _sim(motor_simulacion.iniciar_corrida, db, actor, req.marco,
                   req.inventario, req.presupuesto_rondas, req.lente_borrador)
    db.commit()
    respuesta = {"corrida_id": corrida.id, "marco": corrida.marco,
                 "token_action": motor_simulacion.token_action(corrida.id)}
    if req.lente_borrador:
        respuesta["lente"] = ("borrador (muere con la corrida; si te conforma, "
                              "publicala con acervo_proponer_rubrica tipo='lente')")
    return respuesta

@app.post("/corridas/{corrida_id}/participantes")
async def corrida_participante(corrida_id: str, req: CorridaParticipanteRequest,
                               db: Session = Depends(get_db)):
    """INV-07: con token firmado por la persona, doble calibrado; sin token,
    agente aleatorio; token inválido, rechazo explícito."""
    actor = _verificar_control(req, req.actor_id, "corrida.participante")
    _corrida_del_operador(db, corrida_id, actor)
    resultado = _sim(motor_simulacion.sumar_participante, db, corrida_id,
                     req.rol, security=security, token=req.token)
    db.commit()
    return resultado

@app.post("/corridas/{corrida_id}/sinteticos")
async def corrida_sintetico(corrida_id: str, req: SinteticoRequest, db: Session = Depends(get_db)):
    """WP-20: personaje sintético desde forma del acervo. Sin token porque no
    hay persona detrás; el sorteo de casting jamás escribe masa."""
    actor = _verificar_control(req, req.actor_id, "corrida.sintetico")
    _corrida_del_operador(db, corrida_id, actor)
    resultado = _sim(motor_simulacion.sumar_sintetico, db, corrida_id, req.rol, req.forma_id)
    db.commit()
    return resultado

@app.post("/corridas/{corrida_id}/personajes")
async def corrida_personaje(corrida_id: str, req: PersonajeRequest, db: Session = Depends(get_db)):
    """Personaje del entorno con disposiciones propias (no una persona, no una
    forma): el que hace que la simulación tenga agentes distintos."""
    actor = _verificar_control(req, req.actor_id, "corrida.personaje")
    _corrida_del_operador(db, corrida_id, actor)
    resultado = _sim(motor_simulacion.sumar_personaje, db, corrida_id, req.rol, req.disposiciones)
    db.commit()
    return resultado

@app.post("/corridas/{corrida_id}/contexto")
async def corrida_contexto(corrida_id: str, req: CorridaContextoRequest,
                           db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "corrida.contexto")
    _corrida_del_operador(db, corrida_id, actor)
    return _sim(motor_simulacion.contexto_ronda, db, corrida_id, req.rol)

@app.post("/corridas/{corrida_id}/acto")
async def corrida_acto(corrida_id: str, req: CorridaActoRequest,
                       db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "corrida.acto")
    _corrida_del_operador(db, corrida_id, actor)
    return _sim(motor_simulacion.acto_ronda, db, corrida_id, req.rol, req.acto)

@app.post("/corridas/{corrida_id}/ronda")
async def corrida_ronda(corrida_id: str, req: ActorControlRequest,
                        db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "corrida.ronda")
    _corrida_del_operador(db, corrida_id, actor)
    resultado = _sim(motor_simulacion.avanzar_ronda, db, corrida_id)
    db.commit()
    return resultado

@app.post("/corridas/{corrida_id}/tensiones")
async def corrida_tensiones(corrida_id: str, req: CorridaTensionesRequest,
                            db: Session = Depends(get_db)):
    """La lectura es del cliente; el nodo valida esquema y frontera antes de
    que toque el estado (el patrón entero en una línea)."""
    actor = _verificar_control(req, req.actor_id, "corrida.tensiones")
    _corrida_del_operador(db, corrida_id, actor)
    persistidas = _sim(motor_simulacion.leer_tensiones, db, corrida_id, req.tensiones)
    db.commit()
    return {"tensiones_persistidas": persistidas}

@app.post("/corridas/{corrida_id}/transcript")
async def corrida_transcript(corrida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El operador se lleva el transcript de SU corrida (roles, jamás llaves;
    ya pasó la frontera). El nodo no lo persiste: muere igual al cierre
    (INV-07). Es el patrón llevarse, para que el cliente lo guarde local."""
    actor = _verificar_control(req, req.actor_id, "corrida.transcript")
    _corrida_del_operador(db, corrida_id, actor)
    return _sim(motor_simulacion.transcript_de, db, corrida_id)

@app.post("/corridas/{corrida_id}/estado")
async def corrida_estado(corrida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El pulso de la corrida sin cerrarla: por qué ronda va, cuántos actos y
    tensiones lleva. Solo el operador."""
    actor = _verificar_control(req, req.actor_id, "corrida.estado")
    _corrida_del_operador(db, corrida_id, actor)
    return _sim(motor_simulacion.estado_de, db, corrida_id)

@app.post("/corridas/{corrida_id}/relato-html")
async def corrida_relato_html(corrida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El artefacto portátil de TU historia (HTML autocontenido, INV-07): el
    nodo lo renderiza, no lo hostea ni lo persiste. Se arma ANTES de cerrar
    (el transcript muere con la corrida, igual que corrida_transcript)."""
    actor = _verificar_control(req, req.actor_id, "corrida.relato_html")
    _corrida_del_operador(db, corrida_id, actor)
    return {"html": _sim(relato_mod.render_relato_html, corrida_id, db)}

@app.post("/corridas/{corrida_id}/cerrar")
async def corrida_cerrar(corrida_id: str, req: CorridaCerrarRequest,
                         db: Session = Depends(get_db)):
    """Muerte del doble (INV-07): el cierre destruye todo lo reconstruible."""
    actor = _verificar_control(req, req.actor_id, "corrida.cerrar")
    _corrida_del_operador(db, corrida_id, actor)
    resultado = _sim(motor_simulacion.cerrar_corrida, db, corrida_id, req.sin_cosecha)
    db.commit()
    return resultado

def _corrida_viva(db, corrida_id: str):
    corrida = db.query(Corrida).filter(Corrida.id == corrida_id).first()
    if not corrida:
        raise HTTPException(status_code=404, detail="Corrida inexistente")
    if corrida.estado == "cerrada":
        raise HTTPException(status_code=409, detail="La corrida está cerrada")
    return corrida

@app.post("/corridas/{corrida_id}/pedidos")
async def corrida_pedidos_delegados(corrida_id: str, req: ActorControlRequest,
                                    db: Session = Depends(get_db)):
    """La cola de razonamiento delegado (09 §2.6): pull, jamás push. Cualquier
    cliente firmado puede consultar (el pool es abierto, INV-12); NO exige ser
    el operador: al pool se entra sirviendo, no siendo dueño."""
    _verificar_control(req, req.actor_id, "corrida.pedidos")
    _corrida_viva(db, corrida_id)
    cola = delegacion.cola(corrida_id)
    if cola is None:
        return {"pedidos": [], "gradiente": None, "actos": []}
    return {"pedidos": cola.pedidos_pendientes(),
            "gradiente": {"estado": cola.estado,
                          "presupuesto_estimado": cola.presupuesto_estimado,
                          "comprometido": cola.comprometido},
            "actos": list(cola.actos)}

def _resolver_engine_delegada(engine_pedida: str, concordia_instalada: bool) -> str:
    """Concordia conduce por defecto (corrección jul 2026, 06 §2.1): "auto"
    corre Concordia si está instalada, si no degrada a la demo. "concordia" y
    "demo" fuerzan el escalón pedido (la validación de que "concordia" exija
    la librería es responsabilidad del caller, que necesita un 422 propio).
    Función pura para poder testearla sin servicios."""
    engine_pedida = (engine_pedida or "auto").lower()
    if engine_pedida not in ("auto", "concordia", "demo"):
        raise ValueError("engine inválida: auto | concordia | demo")
    if engine_pedida in ("concordia", "demo"):
        return engine_pedida
    return "concordia" if concordia_instalada else "demo"

@app.post("/corridas/{corrida_id}/delegada")
async def corrida_delegada_demo(corrida_id: str, req: CorridaDelegadaRequest,
                                db: Session = Depends(get_db)):
    """Lanza la engine HOSPEDADA en el nodo para la corrida (09 §2.6). Por
    defecto ("auto") conduce Concordia: turnos y memoria son código
    determinista del nodo, el razonamiento va delegado a la cola (el cliente
    presta la mente, en personaje) y exige corrida POBLADA. Si `gdm-concordia`
    no está instalada, "auto" degrada a la engine demo (un rol, sin memoria
    asociativa) y lo declara en la respuesta. `engine="concordia"` fuerza el
    escalón real (422 si falta la librería o si la corrida no está poblada);
    `engine="demo"` fuerza el fallback. Solo el operador de la corrida; con
    presupuesto_estimado > 0 la corrida nace propuesta y espera cobertura."""
    actor = _verificar_control(req, req.actor_id, "corrida.delegada")
    corrida = _corrida_del_operador(db, corrida_id, actor)
    _corrida_viva(db, corrida_id)
    concordia_instalada = _concordia_instalada()
    try:
        engine = _resolver_engine_delegada(req.engine, concordia_instalada)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if engine == "concordia" and not concordia_instalada:
        raise HTTPException(status_code=422,
            detail="gdm-concordia no está instalada en este nodo (pip install gdm-concordia==2.4.0)")
    # turnos<=0 (default) pide el arco entero: el presupuesto_rondas de la
    # corrida, no el turnos=3 heredado de la demo (corrección jul 2026).
    turnos_efectivos = req.turnos if req.turnos > 0 else corrida.presupuesto_rondas

    if engine == "concordia":
        cola = _sim(delegacion.lanzar_engine_concordia, db, corrida_id, turnos=req.turnos,
                   situacion=req.situacion, presupuesto_estimado=req.presupuesto_estimado,
                   liviano=req.liviano)
        return {"gradiente": cola.estado, "turnos": turnos_efectivos,
                "presupuesto_estimado": cola.presupuesto_estimado, "engine": "concordia"}

    cola = delegacion.lanzar_engine_demo(
        corrida_id, turnos=req.turnos, rol=req.rol, situacion=req.situacion,
        presupuesto_estimado=req.presupuesto_estimado, db=db)
    respuesta = {"gradiente": cola.estado, "turnos": turnos_efectivos,
                "presupuesto_estimado": cola.presupuesto_estimado, "engine": "demo"}
    if (req.engine or "auto").lower() == "auto" and not concordia_instalada:
        respuesta["nota_engine"] = (
            "Concordia no está instalada: corre la engine demo (un rol, sin "
            "memoria asociativa); para la conducción real instalá gdm-concordia "
            "en el contenedor")
    return respuesta

@app.post("/corridas/{corrida_id}/presupuesto")
async def corrida_presupuesto_delegado(corrida_id: str, req: CorridaPresupuestoRequest,
                                       db: Session = Depends(get_db)):
    """El consentimiento del umbral (09 §2.6): la llave compromete pedidos. La
    corrida cara pasa de propuesta a cubierta cuando la cobertura alcanza;
    declarar 0 es retirarse (antes de activarse, la cobertura puede caer)."""
    actor = _verificar_control(req, req.actor_id, "corrida.presupuesto")
    _corrida_viva(db, corrida_id)
    cola = delegacion.cola(corrida_id)
    if cola is None:
        raise HTTPException(status_code=404, detail="La corrida no tiene cola delegada")
    try:
        return cola.declarar_presupuesto(actor, req.pedidos)
    except delegacion.ColaCerrada:
        raise HTTPException(status_code=409, detail="La corrida está cerrada")

@app.post("/corridas/{corrida_id}/pedidos/{pedido_id}/respuesta")
async def corrida_respuesta_delegada(corrida_id: str, pedido_id: str,
                                     req: CorridaRespuestaRequest,
                                     db: Session = Depends(get_db)):
    """El cliente deposita su razonamiento. La frontera lo filtra ANTES de que
    toque la engine (INV-17); la firma cuenta para el contador agregado, pero
    la respuesta viaja sin procedencia (INV-04: el acto es del rol)."""
    actor = _verificar_control(req, req.actor_id, f"corrida.responder:{pedido_id}")
    _corrida_viva(db, corrida_id)
    cola = delegacion.cola(corrida_id)
    if cola is None:
        raise HTTPException(status_code=404, detail="La corrida no tiene cola delegada")
    # Una respuesta vacía no sirve un pedido: sin acto compuesto (text) ni
    # elección (idx), el cliente estaría vaciando la cola sin pensar, y el
    # relato saldría con actos en blanco (corrección jul 2026, del playtest
    # donde el subagente drenó 24 pedidos con texto vacío).
    if not (req.text or "").strip() and (req.idx is None or req.idx < 0):
        raise HTTPException(
            status_code=422,
            detail="respuesta vacía: un pedido de texto se sirve componiendo el "
                   "acto (text, 3 a 5 frases en personaje), uno de elección con idx. "
                   "Vaciar la cola sin componer no es servir la corrida.")
    _sim(frontera.validar_salida, {"respuesta": req.text or "", "idx": req.idx})
    servido = cola.responder(pedido_id, text=req.text, idx=req.idx, llave=actor)
    if not servido:
        raise HTTPException(status_code=409, detail="Pedido inexistente o ya servido")
    return {"servido": True, "servidos_total": cola.servidos}

def _injerto_del_operador(db, injerto_id: str, actor: str):
    injerto = db.query(Injerto).filter(Injerto.id == injerto_id).first()
    if not injerto:
        raise HTTPException(status_code=404, detail="Injerto inexistente")
    corrida = db.query(Corrida).filter(Corrida.id == injerto.corrida_id).first()
    if not corrida or (corrida.operador_llave or "").lower() != actor.lower():
        raise HTTPException(status_code=403, detail="El injerto es de otra corrida u operador")
    return injerto

@app.post("/corridas/{corrida_id}/premisas")
async def corrida_premisas(corrida_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Deducción dirigida desde la matriz material (06 §6)."""
    actor = _verificar_control(req, req.actor_id, "corrida.premisas")
    _corrida_del_operador(db, corrida_id, actor)
    return _sim(motor_simulacion.premisas, db, corrida_id)

@app.post("/corridas/{corrida_id}/injertos", status_code=status.HTTP_201_CREATED)
async def corrida_injerto(corrida_id: str, req: InjertoRegistrarRequest, db: Session = Depends(get_db)):
    """El cliente cristaliza; el nodo valida plantilla, frontera y REGLA DE ORO."""
    actor = _verificar_control(req, req.actor_id, "corrida.injerto")
    _corrida_del_operador(db, corrida_id, actor)
    injerto = _sim(motor_simulacion.registrar_injerto, db, corrida_id, req.spec)
    db.commit()
    return {"injerto_id": injerto.id, "estado": injerto.estado, "marco": injerto.marco}

@app.post("/injertos/{injerto_id}/veredicto")
async def injerto_veredicto(injerto_id: str, req: VeredictoRequest, db: Session = Depends(get_db)):
    """A/B del cliente; veredicto del catálogo con evidencia por ROLES."""
    actor = _verificar_control(req, req.actor_id, "injerto.veredicto")
    _injerto_del_operador(db, injerto_id, actor)
    injerto = _sim(motor_simulacion.validar_ab, db, injerto_id, req.veredicto,
                   req.evidencia, req.metricas_sin, req.metricas_con)
    db.commit()
    return {"injerto_id": injerto.id, "estado": injerto.estado}

@app.post("/injertos/{injerto_id}/exportar")
async def injerto_exportar(injerto_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """exportar_protocolo (WP-07): del injerto aprobado a la partida jugable."""
    actor = _verificar_control(req, req.actor_id, "injerto.exportar")
    _injerto_del_operador(db, injerto_id, actor)
    guion = _sim(motor_simulacion.exportar_protocolo, db, injerto_id)
    db.commit()
    return guion

@app.post("/injertos/{injerto_id}/adopcion")
async def injerto_adopcion(injerto_id: str, req: AdopcionRequest, db: Session = Depends(get_db)):
    """El residuo colectivo único de la partida comunitaria (05 §6.2)."""
    actor = _verificar_control(req, req.actor_id, "injerto.adopcion")
    _injerto_del_operador(db, injerto_id, actor)
    injerto = _sim(motor_simulacion.resolver_adopcion, db, injerto_id, req.decision)
    db.commit()
    return {"injerto_id": injerto.id, "estado": injerto.estado}

def _propuesta_del_operador(db, propuesta_id: str, actor: str):
    propuesta = db.query(PropuestaForma).filter(PropuestaForma.id == propuesta_id).first()
    if not propuesta:
        raise HTTPException(status_code=404, detail="Propuesta inexistente")
    if propuesta.corrida_id is None:
        # Rúbrica a mano (WP-22): el dueño es su aportante único (el
        # proponente). El guard viejo buscaba una corrida que no existe y
        # daba 403 siempre: el bug que rompía el flujo manual entero.
        aportantes = [a.lower() for a in json.loads(propuesta.aportantes or "[]")]
        if actor.lower() not in aportantes:
            raise HTTPException(status_code=403, detail="La propuesta es de otro proponente")
        return propuesta
    corrida = db.query(Corrida).filter(Corrida.id == propuesta.corrida_id).first()
    if not corrida or (corrida.operador_llave or "").lower() != actor.lower():
        raise HTTPException(status_code=403, detail="La propuesta es de otra corrida u operador")
    return propuesta

@app.post("/corridas/{corrida_id}/formas", status_code=status.HTTP_201_CREATED)
async def corrida_forma(corrida_id: str, req: FormaProponerRequest, db: Session = Depends(get_db)):
    """Abre el registro de gobernanza del acervo: pipeline (1)+(2) y captura
    de aportantes vivos. El consentimiento se junta después, firma a firma."""
    actor = _verificar_control(req, req.actor_id, "corrida.forma")
    _corrida_del_operador(db, corrida_id, actor)
    propuesta = _sim(acervo.proponer_forma, db, corrida_id, req.borrador, req.n_comunidad)
    db.commit()
    return {"propuesta_id": propuesta.id, "regla": propuesta.regla,
            "aportantes": len(json.loads(propuesta.aportantes)),
            "revision_humana_requerida": propuesta.revision_humana_requerida}

@app.post("/formas/propuestas/{propuesta_id}/consentir")
async def forma_consentir(propuesta_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El sí afirmativo de un aportante, firmado para ESTA propuesta.
    El silencio no se registra: simplemente vence."""
    actor = _verificar_control(req, req.actor_id, f"forma.consentir:{propuesta_id}")
    resultado = _sim(acervo.firmar_consentimiento, db, propuesta_id, actor)
    db.commit()
    return resultado

@app.post("/formas/propuestas/{propuesta_id}/revision")
async def forma_revision(propuesta_id: str, req: RevisionFormaRequest, db: Session = Depends(get_db)):
    """N-chico: la revisión humana obligatoria cuando la comunidad es chica."""
    actor = _verificar_control(req, req.actor_id, "forma.revision")
    _propuesta_del_operador(db, propuesta_id, actor)
    propuesta = _sim(acervo.revisar_humano, db, propuesta_id, req.aprobada)
    db.commit()
    return {"propuesta_id": propuesta.id, "revision_humana_ok": propuesta.revision_humana_ok}

@app.post("/formas/propuestas/{propuesta_id}/publicar")
async def forma_publicar(propuesta_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El cruce al acervo: solo con el piso entero cumplido."""
    actor = _verificar_control(req, req.actor_id, "forma.publicar")
    _propuesta_del_operador(db, propuesta_id, actor)
    forma = _sim(acervo.publicar_forma, db, propuesta_id)
    db.commit()
    return {"forma_id": forma.id, "estado": forma.estado,
            "regla_consentimiento": forma.regla_consentimiento}

@app.post("/formas/{forma_id}/revocar")
async def forma_revocar(forma_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Revocación individual del aportante: despublica con linaje marcado."""
    actor = _verificar_control(req, req.actor_id, f"forma.revocar:{forma_id}")
    forma = _sim(acervo.revocar_forma, db, forma_id, actor)
    db.commit()
    return {"forma_id": forma.id, "estado": forma.estado, "motivo": forma.retirada_motivo}

@app.post("/formas/{forma_id}/bifurcar", status_code=status.HTTP_201_CREATED)
async def forma_bifurcar(forma_id: str, req: BifurcarFormaRequest, db: Session = Depends(get_db)):
    """Tomarla, torcerla, volverla a publicar: con linaje. La madre gana masa."""
    _verificar_control(req, req.actor_id, f"forma.bifurcar:{forma_id}")
    hija = _sim(acervo.bifurcar_forma, db, forma_id, req.cambios)
    db.commit()
    return {"forma_id": hija.id, "linaje": hija.linaje}

@app.post("/formas/{forma_id}/retomar")
async def forma_retomar(forma_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Retoma explícita: la masa la escriben solo actos humanos."""
    _verificar_control(req, req.actor_id, f"forma.retomar:{forma_id}")
    forma = _sim(acervo.retomar_forma, db, forma_id)
    db.commit()
    return {"forma_id": forma.id, "masa": float(forma.mass)}

@app.post("/rubricas", status_code=status.HTTP_201_CREATED)
async def rubrica_proponer(req: RubricaProponerRequest, db: Session = Depends(get_db)):
    """WP-22: cualquiera propone una rúbrica-forma a mano (skill legible), no
    solo la emergencia. Se despersonaliza, se valida declarativa, y vive por
    adopción."""
    actor = _verificar_control(req, req.actor_id, "rubrica.proponer")
    propuesta = _sim(acervo.proponer_rubrica, db, req.borrador, actor, req.n_comunidad)
    db.commit()
    return {"propuesta_id": propuesta.id, "estado": propuesta.estado}

@app.get("/formas/{forma_id}/rubrica")
def rubrica_cargar(forma_id: str, db: Session = Depends(get_db)):
    """Sirve una rúbrica del común SIEMPRE envuelta como DATO/sugerencia, jamás
    como instrucción (INV-18/19). Cargarla es adoptarla; usarla es del cliente."""
    forma = db.query(Forma).filter(Forma.id == forma_id).first()
    if (not forma or forma.tipo not in ("rubrica", "lente", "patron_coordinacion")
            or forma.estado != "publicada"):
        raise HTTPException(status_code=404, detail="rúbrica inexistente o retirada")
    return acervo.envolver_rubrica(forma)

@app.get("/ruteo")
async def ruteo_lsh(q: str, radio: int = 1):
    """WP-24: el plan de índice distribuido para una búsqueda. Devuelve los
    content topics de bucket LSH que un cliente debe consultar (su bucket y el
    vecindario de Hamming). Un semi-nodo suscripto a esos buckets tiene los
    candidatos; el cliente mergea (federación, INV-11)."""
    from packages.adapters import lsh, semi_nodo
    vector = await ollama.generate_embedding(q)
    return {"topics": lsh.topics_de_consulta(vector, radio=radio),
            "publicacion": semi_nodo.registrar_intencion(vector),
            "nota": "índice por proximidad (LSH); recall aproximado (INV-11)"}

@app.get("/formas")
def formas_publicas(db: Session = Depends(get_db)):
    """La cara pública del acervo (semilla del espejo, WP-09): store sin
    identidades, navegable por cualquiera, sin cuenta."""
    return {"formas": acervo.listar_formas(db)}

@app.get("/surcos/confirmacion")
def surcos_confirmacion(db: Session = Depends(get_db)):
    """WP-32 (01_red §7): los pares de comandos que confirman juntos una y
    otra vez, como agregado anónimo de la lengua. De acá no nace ninguna
    pieza: nace el material para que un CLIENTE redacte un patrón de
    coordinación y el ciclo del acervo lo consienta. El nodo cuenta; el
    cliente redacta; los humanos confirman."""
    from apps.worker.emergencia import detectar_surcos_confirmacion
    return {"surcos": detectar_surcos_confirmacion(db),
            "nota": "agregado de la lengua, sin identidades; el patrón que "
                    "salga de acá se propone al acervo y vive por adopción"}

@app.get("/forja/material")
def forja_material_endpoint(db: Session = Depends(get_db)):
    """WP-33 (01_red §7.3): el material del inventor, agregado y anónimo:
    surcos de confirmación, búsquedas huérfanas, tensiones-tipo del acervo.
    El nodo cuenta; inventar es del cliente (con la rúbrica de la forja);
    decidir es de la comunidad."""
    from apps.acervo.forja import material_de_forja
    return material_de_forja(db)

@app.get("/vocabulario")
def vocabulario_vivo(db: Session = Depends(get_db)):
    """La lengua viva de este nodo (WP-28): los comandos que su comunidad usa,
    con su masa. Sedimento del habla, no diccionario: lo que no se usa se
    olvida. Comparar el vocabulario de dos nodos es ver dos territorios
    hablando distinto: divergencia como propiedad (INV-11)."""
    from packages.domain.models import ComandoVivo
    comandos = [
        {"comando": f"!{c.slug}", "masa": float(c.mass or 0.0)}
        for c in db.query(ComandoVivo).all() if (c.mass or 0) > 0]
    comandos.sort(key=lambda c: c["masa"], reverse=True)
    return {"vocabulario": comandos,
            "nota": "la gramática brota del uso y se olvida sin él; cualquiera "
                    "acuña un comando emitiendo con !palabra"}

@app.get("/acervo/galeria", response_class=HTMLResponse)
def acervo_galeria_pagina(db: Session = Depends(get_db)):
    """La galería del común (público, sin firma: GET /formas ya lo es):
    las formas publicadas con su linaje y su masa de adopción, en un HTML
    autocontenido. Lo colectivo que sobrevive al olvido, no las historias."""
    return galeria_mod.render_galeria_html(db)

def _espejo(vista_fn, *args):
    """El espejo falla CERRADO y ruidoso: si una identidad se coló al store,
    se niega a servir la vista entera (INV-09; CU-T1)."""
    try:
        return vista_fn(*args)
    except frontera.FronteraViolada as exc:
        print(f"[ESPEJO] Me niego a servir: {exc}")
        raise HTTPException(status_code=503,
                            detail="el espejo se niega: hay material con identidad en el store")

def _leer_contador(clave: str) -> int:
    try:
        valor = security.redis.get(clave)
        if valor is None:
            return 0
        return int(valor.decode() if isinstance(valor, bytes) else valor)
    except Exception:
        return 0

@app.get("/espejo", response_class=HTMLResponse)
def espejo_pagina():
    """El mundo-espejo: deambulación pública, sin cuenta, sin persona."""
    return PAGINA_ESPEJO

@app.get("/espejo/formas")
def espejo_formas(db: Session = Depends(get_db)):
    return _espejo(espejo_mod.vista_formas, db)

@app.get("/espejo/epocas")
def espejo_epocas(db: Session = Depends(get_db)):
    return _espejo(espejo_mod.vista_epocas, db)

@app.get("/espejo/lengua")
def espejo_lengua(db: Session = Depends(get_db)):
    return _espejo(espejo_mod.vista_lengua, db)

@app.get("/espejo/salud")
def espejo_salud():
    return _espejo(espejo_mod.vista_salud, _leer_contador)

@app.get("/espejo/alarmas")
def espejo_alarmas(db: Session = Depends(get_db)):
    return _espejo(espejo_mod.vista_alarmas, db)

@app.get("/piezas")
def piezas_publicas(db: Session = Depends(get_db)):
    """Registro público del andamiaje (INV-14): toda pieza con su
    justificación, auditable por cualquiera. Las declaraciones son públicas
    y firmadas, como las intenciones."""
    return {"piezas": [{
        "id": p.id, "tipo": p.tipo, "justificacion": p.justificacion,
        "spec": json.loads(p.spec or "{}"), "topic_derivado": p.topic_derivado,
        "proponente": p.proponente_llave, "estado": p.estado,
        "masa": float(p.mass or 0.0), "ttl_dias": p.ttl_dias,
    } for p in db.query(Pieza).all()]}

def _sim_emergencia(callable_, *args):
    try:
        return callable_(*args)
    except emergencia.EmergenciaError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.post("/piezas/{pieza_id}/adoptar")
async def pieza_adoptar(pieza_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    _verificar_control(req, req.actor_id, f"pieza.adoptar:{pieza_id}")
    pieza = _sim_emergencia(emergencia.adoptar_pieza, db, pieza_id)
    db.commit()
    return {"pieza_id": pieza.id, "estado": pieza.estado}

@app.post("/piezas/{pieza_id}/desadoptar")
async def pieza_desadoptar(pieza_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Reversibilidad sin autoridad: no adoptar nada no excluye a nadie."""
    _verificar_control(req, req.actor_id, f"pieza.desadoptar:{pieza_id}")
    pieza = _sim_emergencia(emergencia.des_adoptar_pieza, db, pieza_id)
    db.commit()
    return {"pieza_id": pieza.id, "estado": pieza.estado}

@app.post("/piezas/{pieza_id}/revocar")
async def pieza_revocar(pieza_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Revocación firmada del proponente."""
    actor = _verificar_control(req, req.actor_id, f"pieza.revocar:{pieza_id}")
    pieza = _sim_emergencia(emergencia.revocar_pieza, db, pieza_id, actor)
    db.commit()
    return {"pieza_id": pieza.id, "estado": pieza.estado}

def _pool(callable_, *args):
    try:
        return callable_(*args)
    except frontera.FronteraViolada as exc:
        raise HTTPException(status_code=422, detail=f"frontera: {exc}")
    except pool.PoolError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.post("/tareas", status_code=status.HTTP_201_CREATED)
async def tarea_crear(req: TareaCrearRequest, db: Session = Depends(get_db)):
    """WP-23: el nodo abre una tarea de cómputo sobre material anónimo. La
    frontera rechaza cualquier identidad antes de que la tarea exista."""
    _verificar_control(req, req.actor_id, "tarea.crear")
    tarea = _pool(pool.crear_tarea, db, req.tipo, req.dominio, req.material)
    db.commit()
    return {"tarea_id": tarea.id, "tipo": tarea.tipo, "dominio": tarea.dominio}

@app.get("/tareas")
def tareas_abiertas(db: Session = Depends(get_db)):
    """Las tareas que un cliente con fierro puede tomar. Solo material anónimo."""
    return {"tareas": pool.listar_abiertas(db)}

@app.post("/tareas/{tarea_id}/tomar")
async def tarea_tomar(tarea_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    actor = _verificar_control(req, req.actor_id, "tarea.tomar")
    resultado = _pool(pool.tomar_tarea, db, tarea_id, actor)
    db.commit()
    return resultado

@app.post("/tareas/{tarea_id}/resolver")
async def tarea_resolver(tarea_id: str, req: TareaResolverRequest, db: Session = Depends(get_db)):
    """El cliente devuelve su propuesta; se valida por resultado. Si pasa,
    acredita peso; si no, no penaliza (no hay slashing)."""
    actor = _verificar_control(req, req.actor_id, "tarea.resolver")
    resultado = _pool(pool.resolver_tarea, db, tarea_id, actor, req.propuesta)
    db.commit()
    return resultado

@app.post("/contribucion")
async def contribucion_propia(req: ActorControlRequest, db: Session = Depends(get_db)):
    """El peso de contribución del propio dueño (no hay ranking de actores)."""
    actor = _verificar_control(req, req.actor_id, "contribucion.ver")
    return {"llave": actor, "peso_total": pool.peso_de(db, actor),
            "nota": "prioriza tus tareas; decae; no es transferible ni ranking (INV-10)"}

def _mp(callable_, *args):
    try:
        return callable_(*args)
    except frontera.FronteraViolada as exc:
        raise HTTPException(status_code=422, detail=f"frontera: {exc}")
    except multiplayer.MultiplayerError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.post("/sesiones", status_code=status.HTTP_201_CREATED)
async def sesion_abrir(req: SesionAbrirRequest, db: Session = Depends(get_db)):
    """WP-25: un miembro convoca una escena de N jugadores. La rúbrica-forma
    pública es el GM común."""
    actor = _verificar_control(req, req.actor_id, "sesion.abrir")
    sesion = _mp(multiplayer.abrir_sesion, db, actor, req.rubrica_gm_id)
    db.commit()
    return {"sesion_id": sesion.id, "estado": sesion.estado}

@app.post("/sesiones/{sesion_id}/entrar")
async def sesion_entrar(sesion_id: str, req: SesionEntrarRequest, db: Session = Depends(get_db)):
    """Acto individual de entrada; con_fierro declara si el cliente puede componer."""
    actor = _verificar_control(req, req.actor_id, "sesion.entrar")
    resultado = _mp(multiplayer.entrar, db, sesion_id, actor, req.con_fierro)
    db.commit()
    return resultado

@app.post("/sesiones/{sesion_id}/sortear-gm")
async def sesion_sortear(sesion_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Sortea quién compone el turno (el neutralizador). Sin fierro, degrada."""
    _verificar_control(req, req.actor_id, "sesion.sortear")
    gm = _mp(multiplayer.sortear_gm, db, sesion_id)
    db.commit()
    return {"gm": gm}

@app.post("/sesiones/{sesion_id}/turno")
async def sesion_turno(sesion_id: str, req: TurnoProponerRequest, db: Session = Depends(get_db)):
    """El GM sorteado compone la escena; el nodo valida lo objetivo (frontera)."""
    actor = _verificar_control(req, req.actor_id, "sesion.turno")
    resultado = _mp(multiplayer.proponer_turno, db, sesion_id, actor, req.composicion)
    db.commit()
    return resultado

@app.post("/sesiones/{sesion_id}/validar")
async def sesion_validar(sesion_id: str, req: TurnoValidarRequest, db: Session = Depends(get_db)):
    """Validación cruzada: un par chequea el turno del GM."""
    actor = _verificar_control(req, req.actor_id, "sesion.validar")
    resultado = _mp(multiplayer.validar_turno, db, sesion_id, actor, req.acepta)
    db.commit()
    return resultado

@app.post("/sesiones/{sesion_id}/resolver")
async def sesion_resolver(sesion_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """Cuenta la validación cruzada; acepta o rechaza el turno y re-sortea GM."""
    _verificar_control(req, req.actor_id, "sesion.resolver")
    resultado = _mp(multiplayer.resolver_turno, db, sesion_id)
    db.commit()
    return resultado

@app.post("/sesiones/{sesion_id}/estado")
async def sesion_estado(sesion_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """El espejo de la sesión (historia, manual-GM, turno, pendiente): solo un
    participante lo ve. Componer sin mirar esto es componer a ciegas."""
    actor = _verificar_control(req, req.actor_id, "sesion.estado")
    sesion = _mp(multiplayer._sesion, db, sesion_id)
    if not any(p["llave"].lower() == actor.lower()
               for p in json.loads(sesion.participantes)):
        raise HTTPException(status_code=403, detail="Solo un participante ve el estado")
    return _mp(multiplayer.estado_sesion, db, sesion_id)

@app.post("/sesiones/{sesion_id}/puente")
async def sesion_puente(sesion_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """La puerta de salida a la emisión real (05 §6): ensayo, no realidad-sustituta."""
    _verificar_control(req, req.actor_id, "sesion.puente")
    return _mp(multiplayer.ofrecer_puente, db, sesion_id)

@app.post("/sesiones/{sesion_id}/cerrar")
async def sesion_cerrar(sesion_id: str, req: ActorControlRequest, db: Session = Depends(get_db)):
    """La ficción muere al cierre; solo persiste el metadato."""
    _verificar_control(req, req.actor_id, "sesion.cerrar")
    resultado = _mp(multiplayer.cerrar_sesion, db, sesion_id)
    db.commit()
    return resultado

@app.get("/salud/prevision")
def salud_prevision():
    """Alarma INV-13 (semilla de WP-11): agregado global ANÓNIMO de la
    previsión, visible en el propio sistema. Si la previsión acierta cada vez
    más, la gente está saliendo MÁS previsible y el juego cambió de familia.
    Es alarma, jamás KPI."""
    def _leer(clave):
        try:
            valor = security.redis.get(clave)
            if valor is None:
                return 0
            return int(valor.decode() if isinstance(valor, bytes) else valor)
        except Exception:
            return 0
    predicciones = _leer("prevision:global:predicciones")
    aciertos = _leer("prevision:global:aciertos")
    return {"predicciones": predicciones, "aciertos": aciertos,
            "tasa_acierto": round(aciertos / predicciones, 3) if predicciones else None,
            "nota": "agregado anónimo, sin ventana fina; alarma, jamás KPI (INV-13)"}

class CanjeRequest(BaseModel):
    codigo: str

@app.post("/puente/canjear-llave")
def canjear_llave(req: "CanjeRequest"):
    """WP-21 (escalera de custodia): la Mini App canjea el código de un solo
    uso que dio el bot y recibe la llave delegada, para custodiarla la persona.
    Sin código válido no hay llave, y el código se destruye al canjearse."""
    from packages.puentes import kit
    private_key = kit.canjear_codigo(security.redis, req.codigo)
    if not private_key:
        raise HTTPException(status_code=404, detail="código inválido, vencido o ya usado")
    return {"private_key": private_key}

@app.get("/health")
def health():
    return {"status": "alive", "version": "0.1.0", "model": "nomic-embed-text"}
