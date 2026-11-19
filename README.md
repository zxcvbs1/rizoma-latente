# Rizoma Latente

Rizoma Latente es un proyecto experimental de coordinación semántica distribuida.
Permite expresar búsquedas y ofrecimientos, encontrar afinidades entre ellos y
construir vínculos de colaboración. Cada nodo mantiene su propio índice: las
coincidencias dependen de su lectura local de las intenciones publicadas.

El proyecto reúne una API, un servidor MCP para clientes de IA, una Mini App web
y puentes de mensajería. Incluye también motores de aventura y simulación para
explorar situaciones colectivas y proponer formas de organización compartidas.

## Contenido

- [Propuesta y conceptos](#qué-propone-el-proyecto)
- [Módulos y funcionalidades](#módulos-y-funcionalidades)
- [Conexión entre módulos](#cómo-se-conectan)
- [Ejecutar un nodo](#ejecutar-un-nodo)
- [Mini App](#mini-app)
- [CLI y clientes MCP](#cli-y-clientes-mcp)
- [Pruebas](#pruebas)
- [Datos y estado de desarrollo](#datos-y-estado-de-desarrollo)

## Qué propone el proyecto

Rizoma trabaja sobre tres escalas que pueden usarse por separado o combinarse:

- **Red:** hacer circular intenciones y encontrar personas cuyas búsquedas,
  ofrecimientos o propuestas puedan coordinarse.
- **Sujeto:** explorar decisiones mediante una aventura y construir un mapa
  propio de relaciones entre palabras, situaciones y elecciones.
- **Comunidad:** ensayar situaciones colectivas, leer sus tensiones y probar
  reglas de organización antes de adoptarlas.

La idea que las conecta es que una coordinación puede empezar como una frase,
ponerse a prueba en una situación y convertirse en una forma que otras
comunidades puedan reutilizar. El nodo aporta transporte, memoria operativa,
búsqueda y validación. Los clientes de IA componen escenas, interpretan
situaciones y proponen alternativas; las personas deciden qué emitir, compartir
o adoptar. El cliente propone, el nodo valida y las personas confirman.

Por ejemplo, una huerta comunitaria puede publicar que ofrece semillas y busca
herramientas. Las resonancias ayudan a abrir vínculos entre participantes. Si
aparece un problema de reparto del riego, una corrida permite ensayar roles,
recursos y reglas distintas. Una regla que el grupo considera útil puede
probarse como injerto y proponerse al acervo, con el consentimiento requerido,
para que otra comunidad la adapte a su contexto.

## Vocabulario básico

| Concepto | Qué significa |
| --- | --- |
| **Intención** | Una expresión pública de búsqueda, ofrecimiento, convocatoria u otro gesto, con o sin un comando como `!busco`. |
| **Resonancia** | Una afinidad semántica calculada por un nodo entre una consulta o intención y otras señales. |
| **Sinapsis** | Una propuesta de vínculo que avanza cuando sus participantes se dirigen la palabra. |
| **Mapa** | Relaciones entre términos y decisiones construidas durante las aventuras de una persona. |
| **Corrida** | Un ensayo de una comunidad con roles, recursos, rondas y una lente de lectura declarada. |
| **Doble** | Una representación temporal de disposiciones de un participante, autorizada para una corrida concreta. |
| **Lente** | Un marco explícito para leer una situación, por ejemplo desde el cuidado o la gestión de bienes comunes. |
| **Injerto** | Una modificación de las reglas o la organización que se propone para intervenir sobre una tensión. |
| **Forma** | Un material reutilizable del acervo: una tensión-tipo, una lente, una rúbrica o un patrón de coordinación. |
| **Rúbrica** | Un conjunto legible de criterios con los que un cliente compone o evalúa una propuesta. |
| **Masa** | Un peso asociado al uso o la retoma de una señal, comando o forma; pierde vigencia por inactividad. |

## Módulos y funcionalidades

### API y servidor MCP · `apps/api/`

Es la entrada al estado y a las operaciones del nodo. La API HTTP de FastAPI
permite emitir y buscar intenciones, gestionar sinapsis, conducir partidas y
corridas, publicar formas y participar en tareas de cómputo compartido.

`main.py` expone las rutas; `schemas.py` define los cuerpos de las solicitudes;
`security.py` verifica firmas, timestamps y nonces. Los controles de acceso de
cada operación se completan en sus rutas y módulos de dominio.

El servidor de `mcp_server.py` presenta estas operaciones a clientes de IA como
herramientas, recursos y prompts. Un mismo cliente puede actuar como emisor,
conductor de una aventura, operador de una corrida o colaborador del pool.
Las guías de `brujula.py`, accesibles mediante `nodo_brujula` y `nodo_guia`,
explican el orden y el sentido de cada familia de operaciones.

Sirve para construir distintos clientes sobre el mismo protocolo: el modelo
que redacta una escena o interpreta una tensión puede estar fuera del nodo,
mientras el nodo verifica los actos y mantiene el estado compartido.

### Ingestor semántico · `apps/m1_ingestor/`

Recibe las señales que circulan por Waku y las incorpora al índice local.
Comprueba el protocolo, la firma del emisor, la vigencia temporal, el nonce y
los límites de emisión antes de procesar una intención.

Su recorrido principal es:

1. Separar el comando, las etiquetas y el contenido del mensaje.
2. Obtener el embedding del contenido mediante Ollama.
3. Guardar la intención y su vector en PostgreSQL.
4. Registrar los buckets de proximidad y el uso del comando.
5. Buscar una intención complementaria y, si supera el umbral, proponer una
   sinapsis y notificar el encuentro mediante Redis.

Es la conexión entre el transporte distribuido y la lectura de cada nodo.
La búsqueda aplica un umbral de similitud: puede devolver un resultado vacío
cuando ninguna señal lo supera. El cliente puede consultar varios nodos y
comparar sus lecturas, en lugar de obtener un resultado único de toda la red.
En el emparejamiento automático actual, la complementariedad se concentra en
`!busco` y `!ofrezco`; el vocabulario de emisión y la búsqueda son más amplios.

### Handshake y sinapsis · `apps/m2_handshake/`

Gestiona el paso de una coincidencia calculada a un vínculo entre personas.
`gradiente.py` define las transiciones y `handshake_worker.py` envía las
notificaciones y revisa las propuestas que vencen.

La sinapsis empieza como `proposed`. La primera palabra dirigida por una de
las partes la lleva a `addressed`; la respuesta de la otra la vuelve `active`.
Si no hay continuidad dentro del plazo, pasa a `expired`.

La propuesta muestra el texto original de la otra intención y abre un campo
vacío para escribir. El contenido de esa palabra se envía por el canal del
cliente; la API registra el acto firmado que cambia el estado. Así, la
resonancia ofrece una posibilidad de coordinación y sus participantes
construyen el vínculo mediante sus propios actos.

### Mini App y mensajería · `apps/m3_sovereign/`

Es el cliente web en React y TypeScript, ubicado en `webapp/`. Reúne una vista
de señales, una bandeja de conversaciones, contactos y esquemas declarativos
para representar distintos tipos de intención.

`src/lib/rizoma.ts` contiene la conexión con Waku, la consulta y publicación de
señales, el cierre de intenciones y las funciones de mensajería. Incluye
cifrado de mensajes directos mediante un secreto derivado entre claves de los
participantes y soporte de lectura y envío con claves de grupo.

`SinapsisView.tsx` muestra una propuesta, permite escribir la primera palabra
y registra su transición firmada. `ImportarView.tsx` canjea un código de un
solo uso del puente para importar la identidad que este custodiaba.

Sirve como superficie de interacción para quien participa desde el navegador.
Su implementación sigue siendo experimental: tiene datos de demostración,
estadísticas simuladas y acciones de interfaz pendientes de completar.

### Puentes de Telegram y Discord · `apps/bot_telegram/`, `apps/bot_discord/`

Permiten participar desde una plataforma de mensajería. El puente conserva
una clave delegada por usuario y firma las emisiones con esa identidad. La
lógica reutilizable está en `packages/puentes/kit.py`.

El puente de Telegram puede leer una frase natural y compararla con prototipos
semánticos de los comandos. Antes de emitir, devuelve su interpretación para
que la persona la confirme o la reescriba. También ofrece ayuda sobre la lengua
viva del nodo, sugiere patrones del acervo y entrega con `/llave` un código
para trasladar la custodia de la identidad a la Mini App.

El puente de Discord reutiliza el contrato de confirmación y firma delegada
con un adaptador más pequeño. Se ejecuta por separado y requiere `discord.py`.
Las prestaciones de lectura semántica y ayuda de ambos puentes no son idénticas.

### Motor de aventura · `apps/motor_aventura/`

Es la escala individual del proyecto: una partida en la que las escenas y las
decisiones permiten explorar relaciones entre los términos del propio jugador.
El cliente MCP conduce la ficción con las rúbricas de `cliente.py`; `motor.py`
valida las operaciones y administra lo que puede conservarse.

Sus funciones principales son registrar términos, entregar contexto de turno,
sellar una previsión antes de la elección y resolver la decisión. La previsión
usa un compromiso criptográfico: primero se muestra un hash y después se revela
lo previsto, de modo que no pueda ajustarse retrospectivamente a la respuesta.

Los **deslizamientos** son relaciones entre términos apoyadas en evidencia de
la decisión. El motor verifica su esquema y puede contrastar la proximidad
semántica de esa evidencia. El mapa resultante sirve para conducir nuevas
escenas y, con una autorización específica, aportar disposiciones a una corrida.

Las previsiones, el marcador y la memoria narrativa de la partida son efímeros.
Los términos y deslizamientos constituyen el material persistente del mapa.
Los controles permiten consultarlo, exportarlo y borrarlo.

#### Sesiones compartidas y jams · `multiplayer.py`

Extiende el ensayo a varias voces. En las sesiones por turnos, el nodo mantiene
participantes y estado, sortea quién compone la siguiente escena y recibe la
validación de sus pares. La composición rota entre quienes declaran capacidad
para hacerla; una propuesta rechazada se descarta.

El mismo módulo incluye funciones para jams con ediciones propuestas en
paralelo y validación por edición. La API y las herramientas MCP exponen el
flujo de sesiones por turnos; las funciones de jam están en el módulo Python.
Al cerrar una sesión se destruye su historia efímera y queda su metadato.

### Motor de simulación comunitaria · `apps/motor_simulacion/`

Permite ensayar una comunidad bajo restricciones materiales: quiénes
participan, qué recursos existen, qué cuesta cada acción y durante cuántas
rondas se desarrolla la situación. Sirve para observar tensiones y probar
cambios organizativos antes de llevarlos a una práctica compartida.

La lectura se hace bajo una **lente declarada**. `marcos.py` incluye semillas
como bienes comunes, cuidado, decrecimiento, colonialidad, capitales y economía
social; también admite lentes publicadas en el acervo o un borrador propio.

La población puede combinar tres fuentes:

- Participantes reales que autorizan un doble para esa corrida mediante un
  token firmado. Sin autorización se utiliza un agente aleatorio; un token
  inválido se rechaza.
- Personajes inventados para el ensayo, con disposiciones distintas.
- Agentes sintéticos construidos desde formas del acervo.

`motor.py` valida los actos contra el inventario, avanza las rondas y recibe
lecturas de tensiones con evidencia por roles. Un acto materialmente imposible
se rechaza antes de modificar el estado.

El ciclo de intervención es: leer una tensión, proponer un injerto, presentar
su comparación A/B, exportar la propuesta aprobada como partida y registrar la
decisión de adopción. El nodo valida la estructura, las restricciones y el
veredicto; la composición y la evaluación semántica corresponden al cliente.

`runtime.py` ofrece una interfaz común para la conducción externa, las pruebas
sin modelo y Concordia. En las corridas delegadas, la opción automática elige
Concordia cuando está instalada: organiza turnos y memoria en el nodo, mientras `delegacion.py` deja
pedidos de razonamiento en una cola que los clientes atienden mediante MCP.
Si Concordia no está disponible, esa opción usa una engine de demostración y
lo declara en la respuesta.

La corrida mantiene un relato por roles que el dueño puede consultar y
exportar como HTML mediante `relato.py`. Al cierre se destruyen dobles, tokens,
colas y transcript en memoria; sobreviven los resultados permitidos, como las
tensiones y las decisiones sobre injertos.

### Acervo, galería y forja · `apps/acervo/`

El acervo permite que una experiencia produzca materiales reutilizables por
otras comunidades. Una forma puede ser una tensión-tipo, una lente de lectura,
una rúbrica o un patrón que describa un procedimiento de coordinación.

`acervo.py` implementa el recorrido de publicación: propuesta,
despersonalización, consentimiento de los aportantes y revisión humana cuando
el tamaño de la comunidad lo requiere. La regla de consentimiento puede
configurarse; por defecto exige unanimidad. Los aportantes conservan la
posibilidad de revocar una publicación.

Una forma publicada puede retomarse o bifurcarse conservando su linaje. Su masa
crece por actos de reutilización y pierde vigencia cuando deja de usarse.
`galeria.py` presenta las formas publicadas en una página navegable.

`forja.py` aporta el material y la rúbrica para inventar nuevas formas de
coordinación: reúne búsquedas sin respuesta, pares de comandos que se confirman
repetidamente y tensiones-tipo publicadas. El cliente interpreta esa fricción y
redacta candidatos; el nodo valida lo que se propone y la comunidad decide su
uso. Las formas se sirven como datos declarativos y pasan controles contra
instrucciones ejecutables, acciones automáticas o patrones punitivos.

### Mundo-espejo · `apps/espejo/`

Es una vista pública y de solo lectura de lo que el nodo puede mostrar de su
vida colectiva. Permite recorrer formas y bifurcaciones, consultar el
vocabulario vivo, ver conteos por época y observar señales agregadas de salud.

La página se sirve en `/espejo` y sus vistas de datos en `/espejo/*`. Usa formas
publicadas y agregados; las salidas pasan por validadores de identidad. Si un
contenido incumple esa frontera, la vista lo rechaza.

Sirve para hacer legible la actividad común sin ofrecer el mapa privado ni el
grafo de vínculos de una persona como una vista pública.

### Tareas, olvido, lengua y cómputo compartido · `apps/worker/`

Reúne servicios que sostienen el funcionamiento del nodo:

- **`tasks.py` y `celery_app.py`:** ejecución de tareas en segundo plano,
  generación de embeddings y configuración de la programación periódica.
- **`olvido.py`:** vencimiento de intenciones y propuestas, pérdida de peso por
  inactividad y cierre de estados huérfanos. Mantiene acotada la vigencia de
  señales, mapas, formas y contribuciones.
- **`gramatica.py`:** registro del uso de comandos. El vocabulario se construye
  con las emisiones de la comunidad y los comandos sin uso pierden vigencia.
- **`emergencia.py`:** detección de insistencias agregadas y propuestas de piezas
  de una lista acotada: subíndices, reglas de enlace y lugares de coordinación.
  Las piezas tienen justificación, adopción, revocación y decaimiento.
- **`alarmas.py`:** señales agregadas sobre diversidad de coordinaciones y
  duración de partidas. Se muestran para su interpretación; el módulo no
  modifica automáticamente el comportamiento de los motores.
- **`pool.py`:** tareas abiertas sobre material despersonalizado. Un cliente
  puede reservar una, procesarla con su modelo y devolver una propuesta que
  se valida por resultado. La contribución reconocida pierde peso por
  inactividad y no es transferible.
- **`broadcaster.py`:** firma y publicación de señales operativas del gateway.

El worker procesa tareas cuando se ejecuta Celery. La programación diaria del
olvido requiere además un proceso **Celery Beat**; ese proceso no se inicia con
el servicio `worker` del Compose básico. El ciclo de emergencia también debe
invocarse o programarse expresamente.

### Identidad, datos y adaptadores · `packages/`

Son las piezas compartidas por los módulos anteriores:

| Paquete | Para qué sirve y qué contiene |
| --- | --- |
| `domain/identity.py` | Creación y custodia local de identidades, firma de textos y construcción de emisiones canónicas. |
| `domain/models.py`, `database.py` | Modelos SQLAlchemy, conexión y persistencia en PostgreSQL con pgvector y PostGIS. |
| `domain/frontera.py` | Validación de identidades y campos privados, y selección del contexto permitido para cada operación. |
| `adapters/adapter.py` | Acceso a Ollama, parseo de emisiones y generación de embeddings. |
| `adapters/engine.py` | Búsqueda local por similitud semántica, umbral mínimo, ponderación y deduplicación. |
| `adapters/waku_adapter.py` | Publicación y recuperación de señales mediante la API de un nodo Waku. |
| `adapters/federacion.py` | Consulta de varios nodos desde el cliente y combinación de respuestas conservando sus distintas lecturas. |
| `adapters/lsh.py`, `semi_nodo.py` | Agrupación aproximada de vectores por proximidad y selección de los semi-nodos que declaran servir esos grupos. |
| `puentes/kit.py` | Confirmación de emisiones, lectura de intención, ayuda, sugerencia de patrones y traslado de custodia para los puentes. |

La federación usa una lista de nodos elegida por el cliente. La divergencia
entre sus lecturas se muestra conservando el origen y el score de cada una.
Si un nodo no responde, se conservan las respuestas de los demás. La búsqueda
por semi-nodos agrega un enrutamiento aproximado por similitud; sus resultados dependen de la
cobertura declarada y los parámetros del índice.

`packages/m5_reputation/` conserva tareas experimentales de observación y
curación, con lógica de ejemplo. No está incluido entre los módulos que carga
el worker actual; no constituye un observador generativo completo.

## Cómo se conectan

El recorrido básico de una señal es:

```text
CLI o puente → firma → Waku → ingestor → índice local → resonancia
                                                        ↓
Mini App ← notificación del handshake ← propuesta de sinapsis
```

La API también permite emitir directamente y consultar el índice. Los clientes
MCP utilizan la API y el transporte para conducir los otros recorridos:

```text
aventura → mapa propio → doble autorizado para una corrida
                               ↓
                    roles + recursos + lente
                               ↓
                  tensiones → injerto → ensayo
                               ↓
                  adopción / propuesta al acervo
                               ↓
                formas que otros pueden retomar
```

Estas conexiones requieren actos de sus participantes: importar un mapa,
publicar una forma o adoptar una regla son operaciones explícitas. Cada
recorrido puede utilizarse sin completar los demás.


## Ejecutar un nodo

Requiere Docker y Docker Compose. Desde la raíz del repositorio:

```bash
cp .env.example .env
openssl rand -hex 24
```

Copiar el valor generado en `POSTGRES_PASSWORD` dentro de `.env` y levantar los
servicios:

```bash
docker compose --env-file .env -f infra/docker/docker-compose.yml \
  up -d --build api worker ingestor handshake-worker
```

Compose inicia también PostgreSQL, Redis, Ollama y Waku. En el primer arranque,
Ollama descarga el modelo de embeddings `nomic-embed-text`.

```bash
curl http://localhost:8000/health
```

La API queda disponible en `http://localhost:8000`. El detalle de sus endpoints
y esquemas se puede consultar en `http://localhost:8000/docs`.

Para usar el puente de Telegram, completar `TELEGRAM_TOKEN` en `.env` y ejecutar:

```bash
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d bot-telegram
```

## Mini App

Con Node.js 22.12 o posterior:

```bash
cd apps/m3_sovereign/webapp
npm ci
npm run dev
```

Abrir la dirección que muestra Vite en la terminal. La Mini App usa
`http://localhost:8000` como API por defecto. Para cambiarla, crear `.env.local`
en el directorio de la Mini App y definir `VITE_API_URL`.

`npm run build` genera la versión de distribución.

## CLI y clientes MCP

Para ejecutar las herramientas Python fuera de Docker, crear un entorno con
Python 3.12 e instalar las dependencias:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Completar `DATABASE_URL` en `.env` con la contraseña elegida para PostgreSQL.
Con el nodo en ejecución, cargar la configuración y emitir una intención:

```bash
set -a
. ./.env
set +a
python rizoma '!ofrezco semillas para una huerta'
```

El servidor MCP se inicia con `python -m apps.api.mcp_server`. Para conectarlo a
un cliente, usar el Python del entorno virtual, la ruta absoluta a
`apps/api/mcp_server.py` y las variables de entorno del nodo. Las herramientas
`nodo_brujula` y `nodo_guia` explican las operaciones disponibles.

## Infraestructura y organización del código

`infra/docker/` contiene las imágenes y la definición de servicios. PostgreSQL
almacena el índice y el estado persistente; pgvector permite comparar embeddings
y PostGIS aporta los tipos espaciales del modelo. Redis transporta eventos
internos, respalda controles temporales y funciona como broker de Celery.
Ollama calcula embeddings y Waku transporta las señales entre participantes.

El Compose incluye un segundo nodo (`db-rosario`, `api-rosario`, puerto 8001)
para ensayar lecturas con bases independientes. La federación desde el cliente
puede consultar ambos mediante `RIZOMA_NODOS`.

`examples/` muestra integraciones desde clientes. `tests/` reúne las pruebas de
los módulos, los recorridos completos con dobles en memoria y los corpus de
evaluación de resonancia, intención, patrones y forja. `nodo.toml.example`
reúne opciones de referencia; las variables que lee cada proceso se documentan
en `.env.example` y en sus módulos.

## Pruebas

Con el entorno Python activo, ejecutar la batería que usa dobles y bases en
memoria, sin servicios externos:

```bash
for t in tests/test_wp*.py tests/test_t*.py \
  tests/test_delegacion_cola.py tests/test_modelo_delegado.py \
  tests/test_runtime_escalones.py tests/test_runtime_concordia_real.py; do
  python "$t" || exit 1
done
python tests/eval_doctrina.py
```

Las pruebas de integración con Waku y las evaluaciones con embeddings requieren
los servicios correspondientes.

## Datos y estado de desarrollo

Las intenciones emitidas son públicas. La firma EIP-191 vincula cada emisión
con una dirección EIP-55; los timestamps y nonces permiten rechazar eventos
vencidos o repetidos. El texto de una emisión no debe contener secretos.

La API ofrece controles firmados para consultar, exportar y borrar la huella
del dueño en ese nodo. El borrado local no retira por sí mismo copias que hayan
circulado por la red. Las previsiones de aventura, los dobles y las colas de
corridas viven en memoria de proceso: se destruyen al cierre y también se
pierden si el proceso se reinicia.

Los validadores de `packages/domain/frontera.py` controlan los campos y las
identidades que puede servir cada operación; estas comprobaciones no sustituyen
la revisión humana del contenido cuando una publicación pueda identificar a
alguien por su contexto.

| Endpoint | Alcance |
| --- | --- |
| `/search` | Búsqueda de intenciones públicas, sin exponer sus vectores. |
| `/actors/{id}/synapses` | Consulta pública deshabilitada; devuelve 403. |
| `/formas` | Formas compartidas en el acervo. |
| `/espejo/*` | Proyección pública con filtros de identidad. |

El despliegue incluido está orientado al desarrollo y no configura TLS. La
Mini App deriva una identidad de forma predecible en el acceso por email y
almacena las llaves importadas en el navegador. Las señales generales usan una
clave pública del protocolo, distinta del mecanismo de los mensajes directos;
ese cifrado general no las vuelve confidenciales. La custodia de identidad y
la integración entre clientes requieren trabajo adicional antes de un uso con
datos sensibles. Las variables `VITE_*` se incorporan al cliente y son públicas.

## Licencias

Código bajo **AGPL-3.0-or-later**: ver [LICENSE](LICENSE).
Documentación bajo **CC-BY-SA-4.0**:
<https://creativecommons.org/licenses/by-sa/4.0/>.
