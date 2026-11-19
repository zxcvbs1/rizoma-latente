"""
El mundo-espejo (WP-09; 03_comunidad §7, INV-09).

Estructuralmente sin persona: la proyección se arma SOLO de formas publicadas
y agregados anónimos, y toda vista pasa la frontera antes de salir. Si algo
con identidad se coló a un store, el espejo se NIEGA a servirlo (fallo
cerrado y ruidoso), no lo filtra en silencio.

Solo lectura por construcción: este módulo no contiene una sola escritura
(el test lo verifica sobre el fuente). Nada de lo que se navega escribe
señales hacia resonancia, ranking ni notificaciones: no modulación.

Filtro de diseño de cada vista: ¿expone la maquinaria o expone a alguien?
"""
from apps.acervo import acervo
from apps.worker import alarmas
from packages.domain import frontera
from packages.domain.models import Forma, Node, Partida, Synapse


def _publicar(vista: dict) -> dict:
    frontera.validar_salida(vista)
    return vista


def vista_formas(db) -> dict:
    """Deambulación por el acervo: formas publicadas, conteos por tipo y el
    grafo de linaje (bifurcaciones) como enlaces laterales."""
    formas = acervo.listar_formas(db)
    por_tipo = {}
    for forma in formas:
        por_tipo[forma["tipo"]] = por_tipo.get(forma["tipo"], 0) + 1
    linaje = [{"de": f["linaje"], "a": f["id"]} for f in formas if f.get("linaje")]
    return _publicar({"formas": formas, "por_tipo": por_tipo, "linaje": linaje})


def vista_lengua(db) -> dict:
    """La doc viva de INV-15: los comandos de la lengua con su masa VIVA
    (WP-28: ComandoVivo, la fuente con olvido). Una lengua que no olvida se
    fosiliza: lo que nadie usa decae y sale del espejo, aunque el archivo lo
    recuerde. Agregado puro: ningún actor, ningún texto."""
    from packages.domain.models import ComandoVivo
    lengua = [
        {"comando": c.slug, "masa": round(float(c.mass or 0.0), 2)}
        for c in db.query(ComandoVivo).all() if (c.mass or 0) > 0]
    lengua.sort(key=lambda fila: -fila["masa"])
    return _publicar({"lengua": lengua})


def vista_epocas(db) -> dict:
    """Entrada por épocas: cuántas intenciones y cuántas formas por mes.
    Conteos, jamás contenidos."""
    epocas = {}
    for nodo in db.query(Node).all():
        mes = nodo.created_at.strftime("%Y-%m") if nodo.created_at else "?"
        fila = epocas.setdefault(mes, {"epoca": mes, "intenciones": 0, "formas": 0})
        fila["intenciones"] += 1
    for forma in db.query(Forma).all():
        mes = forma.created_at.strftime("%Y-%m") if forma.created_at else "?"
        fila = epocas.setdefault(mes, {"epoca": mes, "intenciones": 0, "formas": 0})
        fila["formas"] += 1
    return _publicar({"epocas": sorted(epocas.values(), key=lambda fila: fila["epoca"])})


def vista_alarmas(db) -> dict:
    """Las alarmas de salud (WP-11), públicas en el propio sistema: entran
    filas con llaves, salen agregados sin nadie. Jamás KPIs."""
    nodos_por_id = {n.id: n for n in db.query(Node).all()}
    surco = alarmas.senal_surco_riel(db.query(Synapse).all(), nodos_por_id)
    absorcion = alarmas.senal_absorcion(db.query(Partida).all())
    return _publicar({
        "surco_riel": surco,
        "absorcion": absorcion,
        "nota": "alarmas agregadas y anónimas; ningún motor las consume (INV-13/16)",
    })


def vista_salud(leer_contador) -> dict:
    """Las alarmas son públicas (INV-13/16): el espejo las muestra y jamás
    las consume para nada."""
    predicciones = leer_contador("prevision:global:predicciones")
    aciertos = leer_contador("prevision:global:aciertos")
    return _publicar({"prevision": {
        "predicciones": predicciones,
        "aciertos": aciertos,
        "tasa_acierto": round(aciertos / predicciones, 3) if predicciones else None,
        "lectura": ("si la previsión acierta cada vez más, la gente está saliendo "
                    "MÁS previsible y el juego cambió de familia"),
    }})
