# Rizoma Latente

Nodo de coordinación semántica distribuida. Recibe intenciones firmadas como
`!busco` y `!ofrezco`, las vectoriza y busca afinidades en un índice local.
Waku transporta las señales entre nodos; cada nodo conserva su propia lectura.
Los clientes proponen interpretaciones, el nodo valida y las personas confirman
los actos de coordinación.

## Componentes

- `apps/api/`: API FastAPI y servidor MCP para clientes y agentes.
- `apps/m1_ingestor/`: captura de señales Waku y verificación de firmas.
- `apps/m2_handshake/`: propuestas de sinapsis y vencimiento por inactividad.
- `apps/m3_sovereign/webapp/`: Mini App React/TypeScript y mensajería P2P.
- `apps/motor_aventura/` y `apps/motor_simulacion/`: partidas, corridas y
  razonamiento delegado al cliente, con integración Concordia.
- `apps/acervo/`, `apps/espejo/` y `apps/worker/`: formas compartidas, proyección
  pública, tareas en segundo plano y olvido de información.
- `apps/bot_telegram/` y `apps/bot_discord/`: puentes con firma delegada.
- `packages/`: modelos, identidad, adaptadores y validadores compartidos.
- `infra/`, `tests/` y `examples/`: despliegue, verificación y ejemplos de cliente.

## Levantar un nodo

Se necesitan Docker y Docker Compose. Desde la raíz:

```bash
cp .env.example .env
openssl rand -hex 24
```

Guardar el valor generado como `POSTGRES_PASSWORD` en `.env`. Luego:

```bash
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d --build db redis ollama waku api worker ingestor handshake-worker
curl http://localhost:8000/health
```

Ollama descarga `nomic-embed-text` al iniciar; la primera descarga puede tardar.
La API queda en `http://localhost:8000` y su documentación interactiva en
`http://localhost:8000/docs`. Postgres usa pgvector y PostGIS; Redis coordina
las tareas y controla nonces. El worker procesa embeddings y tareas Celery.

El segundo nodo es opcional (`db-rosario` y `api-rosario`, puerto 8001).
Para Telegram, completar `TELEGRAM_TOKEN` y levantar `bot-telegram` con el mismo
comando de Compose. Discord se ejecuta por separado con `discord.py` instalado.
Las imágenes de infraestructura conservan sus etiquetas del proyecto; este
Compose es para desarrollo y no configura TLS ni una exposición pública segura.

## Python, CLI y MCP

Python 3.12 es la versión usada por la imagen del nodo:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Para ejecutar Python fuera de Docker, completar `DATABASE_URL` en `.env` con la
misma contraseña de Postgres y cargar el entorno desde esa copia local:

```bash
set -a
. ./.env
set +a
python rizoma '!ofrezco semillas'
python -m apps.api.mcp_server
```

El CLI y los agentes crean su identidad en `user_keys.json`. El gateway usa
`GATEWAY_PRIVATE_KEY` si se configura; de lo contrario genera una identidad
propia y la conserva en ese keystore. `RIZOMA_KEYSTORE` cambia su ubicación.
Para conectar un cliente MCP, usar el Python del entorno y la ruta absoluta a
`apps/api/mcp_server.py`, pasando las variables del nodo al proceso.
`nodo.toml.example` sirve como referencia de opciones; comprobar en cada módulo
si una opción se lee desde el entorno o la configuración del runtime.

## Mini App

```bash
cd apps/m3_sovereign/webapp
npm ci
npm run dev
```

`npm run build` produce `dist/`. Para apuntar a otra API, crear un `.env.local`
en ese directorio con `VITE_API_URL=http://localhost:8000`. Las variables
`VITE_*` son públicas en el navegador: nunca poner secretos allí.

La Mini App conserva características de prototipo: el acceso por email deriva
una identidad de forma predecible, la sesión/importación de llaves usa
`localStorage` y las señales generales usan una clave de red pública incluida
en el cliente. Ese mecanismo no aporta confidencialidad a las señales públicas.
El chat directo tiene otro mecanismo de cifrado. No usar el acceso de prototipo
para custodiar fondos ni identidades sensibles.

## Verificación sin servicios

Los tests son scripts independientes que usan dobles y bases en memoria:

```bash
for t in tests/test_wp*.py tests/test_t*.py tests/test_delegacion_cola.py tests/test_modelo_delegado.py tests/test_runtime_escalones.py tests/test_runtime_concordia_real.py; do
  python "$t" || exit 1
done
python tests/eval_doctrina.py
```

Los scripts `step*`, las evaluaciones con embeddings y las pruebas Waku requieren
servicios o red y se ejecutan aparte. Los corpus de regresión son datos de
prueba; el caso de doctrina es sintético y no incluye una conversación personal.

## Firmas y frontera de datos

Cada emisión usa EIP-191 sobre el mensaje canónico
`rizoma.emit|{actor_id}|{timestamp}|{nonce}|{text}`. La identidad es una dirección
EIP-55. El nodo verifica firma, ventana temporal y nonce para rechazar replays.

| Salida | Tratamiento |
| --- | --- |
| `GET /search` | Intenciones públicas con actor, sin vectores ni campos privados. |
| `GET /synapses/{id}` | Estado de la propuesta y claves públicas para el cliente. |
| `POST /synapses/{id}/address` | Acto firmado que cambia el estado del vínculo. |
| `GET /actors/{id}/synapses` | Devuelve 403: el grafo de vínculos no es público. |
| `POST /actors/{id}/huella` | Acceso del dueño mediante firma. |
| `GET /formas` | Formas compartidas sin identidades personales. |
| `GET /espejo/*` | Proyección pública filtrada; se rechazan identidades. |
| `GET /piezas` y `GET /tareas` | Material público o anónimo validado al crearse. |
| Aventura, corridas y sesiones | Contexto mínimo por operación, con roles en lugar de identidades. |

Las validaciones están en `packages/domain/frontera.py`. Las intenciones
emitidas son públicas: no incluir datos personales o secretos en su texto.

## Material local y publicación

`_local/` conserva tesis, PDFs, bibliografía, notas, diseños, instrucciones de
agentes y versiones retiradas. Está excluido tanto de Git como del contexto de
Docker. `.env`, keystores, bases, logs y dependencias instaladas también están
ignorados. Los archivos necesarios para una instalación propia son el código,
los manifiestos y las plantillas `.example`, que no contienen credenciales.

Mover archivos y agregarlos a `.gitignore` no borra commits anteriores. El
historial original contiene documentación personal y metadatos de autor.
Para publicar únicamente esta versión del código sin ese historial, usar la
copia `_local/publicacion/rizoma-codigo.tar.gz`,
extraerla en otro directorio y crear allí un repositorio nuevo. El archivo no
incluye `.git`, datos locales ni dependencias instaladas. Si cambia el código,
hay que generar nuevamente esa copia antes de publicarla.

## Licencias

El software se mantiene bajo **AGPL-3.0-or-later**; texto completo en
[LICENSE](LICENSE). La documentación se mantiene bajo **CC-BY-SA-4.0**:
<https://creativecommons.org/licenses/by-sa/4.0/>.
