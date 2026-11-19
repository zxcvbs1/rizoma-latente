"""
La forja (WP-33; 01_red §7.3): el inventor antagonista de andamiaje.

La invención no brota de una estadística: un QR, una llave rotativa o un
banco de herramientas no salen del conteo de un surco sino de un MODELO
leyendo la fricción con una rúbrica que le enseñe a inventar. Este módulo
sirve las dos mitades del lado nodo: el material (fricciones agregadas,
jamás identidades) y la rúbrica (la gramática generativa de la invención,
semiotización del cliente servida como prompt, INV-17).

El nodo jamás inventa: cuenta y valida. Inventar es del cliente. Decidir
es de la comunidad, por adopción y decaimiento.
"""
import json

from packages.domain.models import Forma

RUBRICA_FORJA = """LA FORJA: cómo inventar andamiaje de coordinación desde una fricción.

Sos el inventor. El nodo contó la fricción y va a validar lo que produzcas;
la comunidad va a decidir por adopción. Tu trabajo es el del medio: leer una
fricción real o simulada y proponer infraestructura de coordinación que la
alivie, pensando fuera de lo obvio. Generá barato, que el filtro es duro.

1. LAS FUENTES DE FRICCIÓN (de dónde partir, nunca de la nada):
- Surcos de confirmación: pares de comandos que confirman juntos una y otra
  vez (el nodo los sirve agregados). La comunidad ya repite un flujo a mano.
- Tensiones de corridas: para eso EXISTEN las corridas, buscar por lo lúdico
  las fricciones de una comunidad antes de que estallen. Una tensión leída
  con evidencia es una fricción con pedigrí.
- Tensiones-tipo del acervo: fricciones que otras comunidades destilaron.
- Búsquedas huérfanas: lo que la gente pide y nadie responde.
- La fricción traída a mano: quien forja puede declarar la suya, con sus
  palabras. Vale igual: entra al mismo filtro y a la misma adopción.

2. LA PALETA (los materiales con los que se compone, no hay otros):
- Comandos nuevos de la lengua (!palabra: cualquiera acuña, el uso decide).
- Expectativas declaradas (quien presta declara la devolución; quien convoca
  declara el ritmo). Se dicen, no se imponen; lo incumplido decae.
- Lugares de coordinación (un topic de grupo para lo que necesita casa).
- Subíndices y reglas de enlace (puntos de encuentro y ligaduras declarativas).
- Patrones del acervo (flujos enteros en prosa, paso a paso).
- Realizaciones cliente-lado: lo que el cliente de cada quien puede fabricar
  LOCALMENTE leyendo el patrón (un QR con los datos del evento, un
  recordatorio, un calendario, un mapa propio). Siempre marcadas como del
  cliente: son ayudantes opcionales, jamás requisito para participar.

3. LOS MOVIMIENTOS INVENTIVOS (probá varios antes de conformarte):
- Rotar la custodia: lo que uno solo sostiene (la llave, el acta, la
  convocatoria) pasa a turnar entre personas listadas a la vista.
- Invertir quién sostiene: si el que pide carga con el peso, probá que
  cargue el que ofrece, o el que pasó por lo mismo la vez anterior.
- Declarar lo escaso: lo que genera conflicto por opaco (el tiempo, el
  cupo, la zona) se dice en la señal, con palabras propias, y deja de
  negociarse a oscuras.
- Volver ritmo lo que era carga: lo que agota como tarea puntual (convocar,
  registrar, recordar) puede vivir como ciclo declarado que se renueva.
- Mutualizar el riesgo: lo que asusta de a uno (prestar, hospedar, cuidar)
  puede repartirse entre varios que declaran juntos.
- Degradar con gracia: todo lo que propongas tiene que funcionar peor pero
  funcionar cuando falte gente, fierro o ganas. Si sin la pieza nueva el
  flujo muere, la pieza es un centro disfrazado.

4. LAS TRADICIONES DE DONDE ROBAR (siglos de autogestión ya inventaron):
minga y tequio (trabajo colectivo convocado, cada quien trae lo suyo), ayni
(reciprocidad diferida sin cuenta exacta), olla popular (la comida como
lugar y no como producto), biblioteca de cosas (el objeto circula, la
custodia rota), banco de tiempo (horas por horas, sin precio), fondo
rotatorio o pasanaku (el pozo que gira por turnos), y las sindicales: bolsa
de trabajo (el pedido y el oficio se encuentran sin patrón), fondo de
huelga (mutualizar el riesgo de parar), apoyo mutuo como doctrina. No
copies el nombre: traducí el mecanismo a la paleta.

5. LAS REGLAS DURAS (el filtro que viene después no perdona):
- Prosa declarativa: pasos y expectativas, jamás órdenes al sistema.
- Sin plata: ni token, ni crédito, ni puntaje canjeable. La reciprocidad se
  declara y se recuerda, no se contabiliza.
- Sin castigo: lo incumplido decae en silencio. Nada baja la masa de nadie.
- Sin centro: ningún rol permanente, ningún aprobador fijo, ninguna app
  obligatoria. Los roles rotan o no existen.
- Sin automatismo: cada emisión la confirma y firma una persona.
- Sin retención: nada del patrón acumula historial de personas.
- Regla de oro: declarar QUÉ NECESITA el patrón para funcionar (gente,
  cosas, ritmo). No exigir lo que una comunidad chica no tiene.

6. LA SALIDA (el formato de cada candidato):
Producí 2 o 3 candidatos DIVERGENTES por fricción, jamás uno solo: la
convergencia prematura es el enemigo. Que al menos uno sea raro. Cada uno:
- nombre: corto y propio.
- descripcion: VOZ DE USUARIO, frases ejemplo separadas por ";" (es lo que
  resuena en el puente; la taxonomía no resuena).
- cuerpo: los pasos del flujo, en prosa declarativa.
- que_necesita: la regla de oro, dicha honesta.
- realizacion_cliente: opcional, qué podría fabricar localmente un cliente
  capaz (el QR, el recordatorio); marcada como opcional y local.

7. EL CIERRE LÚDICO (antes de adoptar, jugar):
Un candidato que pasó el filtro puede probarse JUGANDO antes de tocar la
vida: corrida con lente_borrador que incluya la regla nueva, o injerto
exportado como partida. La comunidad lo juega y recién ahí decide su
adopción. Lo que empezó como juego vuelve a ser juego antes de ser regla.
El candidato que nadie juega ni retoma, decae: también eso es un veredicto."""


def material_de_forja(db) -> dict:
    """El material del inventor, todo agregado y sin identidades: surcos de
    confirmación, búsquedas huérfanas y tensiones-tipo del acervo. La
    fricción traída a mano no necesita al nodo: se declara al forjar."""
    from apps.worker.emergencia import (detectar_surcos,
                                        detectar_surcos_confirmacion)
    tensiones = [
        {"nombre": f.nombre, "descripcion": f.descripcion, "marco": f.marco}
        for f in db.query(Forma).all()
        if f.tipo == "tension_tipo" and f.estado == "publicada"]
    return {
        "surcos_confirmacion": detectar_surcos_confirmacion(db),
        "busquedas_huerfanas": detectar_surcos(db),
        "tensiones_tipo": tensiones,
        "nota": ("agregados anónimos: el nodo cuenta, vos inventás, la "
                 "comunidad decide. Si la fricción la traés vos, declarala "
                 "con tus palabras: entra al mismo filtro."),
    }
