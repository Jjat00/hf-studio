# HF Studio

Tu propio «Higgsfield»: una API sobre la [API de Higgsfield](https://docs.higgsfield.ai) que usan tus agentes
(Claude Code, Codex) por MCP o REST, y que servirá también de backend para una UI propia.

- **82 endpoints** (66 de video, 15 de imagen y 1 de referencias personalizadas) con su JSON Schema, sacados de la documentación oficial (`hf-studio sync-catalog`).
- **Texto a video, imagen a video, imagen inicial y final, video(s) de referencia, edición y extensión de video, transferencia de movimiento, texto a imagen.** Busca por capacidad y no por marca.
- Los trabajos son **asíncronos y persistentes**, cada uno pertenece a un cliente y otro cliente no puede verlo.
- Validación antes de gastar créditos, deduplicación, `Idempotency-Key`, cola local según la concurrencia de la cuenta, sondeo con backoff, webhooks opcionales y copia local de las salidas (Higgsfield solo las garantiza 7 días).

## Puesta en marcha

```bash
uv sync
cp .env.example .env          # pega tu clave de Higgsfield en HF_API_KEY
uv run hf-studio check-credentials        # valida la clave sin gastar créditos
uv run hf-studio create-key claude-code   # muestra la clave hfs_… una sola vez
uv run hf-studio create-key codex
uv run hf-studio serve        # http://127.0.0.1:8787  ·  docs interactivas en /docs
```

Otros comandos: `hf-studio list-keys`, `hf-studio revoke-key NOMBRE`, `hf-studio sync-catalog`.

## Arranque rápido

```bash
./dev.sh     # valida la clave, arranca la API en :8787 y la UI en :3000
```

## UI web (`web/`)

Next.js 16 con el look de Higgsfield: Inter con eje óptico (hace de Inter Display), Space Grotesk 700 en mayúsculas para titulares, superficies «cool» `#131416` y lima `#d1fe17`. Los valores se midieron en higgsfield.ai el 2026-09-24. El logo, el nombre y las ilustraciones son propios: las imágenes se generaron con la herramienta de imágenes de Codex.

```bash
uv run hf-studio create-key web-ui
cp web/.env.example web/.env.local    # HF_STUDIO_URL y HF_STUDIO_TOKEN=hfs_…
uv run hf-studio serve &              # API en :8787
cd web && pnpm install && pnpm dev    # UI en :3000
```

- **Páginas:** Explore, Video (Create Video: Text, Start & End, References · Edit Video: Edit, Extend, Objects swap · Motion Control), Image, Use cases, Presets, Library, Models y MCP.
- **Use cases** (`/use-cases`, datos en `web/src/lib/use-cases.ts`): 12 casos con mini tutorial por pasos en la UI y con el MCP, la petición exacta para el agente, prompts de ejemplo y costo orientativo en vivo. `?case=<slug>` abre uno; «Use in studio» abre el estudio con `?prompt=` precargado.
- **Formularios:** se generan desde el `input_schema` de cada modelo, así que cualquiera de los 82 endpoints funciona sin código específico.
- **Proxy:** el navegador solo habla con `/api/studio/*`, un proxy en el servidor de Next que añade la clave `hfs_…`. La clave nunca llega al cliente.

## Conectar agentes (MCP)

Claude Code:

```bash
claude mcp add hf-studio --scope user \
  -e HF_STUDIO_URL=http://127.0.0.1:8787 -e HF_STUDIO_TOKEN=hfs_… \
  -- uv run --directory ~/projects/hf-studio hf-studio mcp
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.hf-studio]
command = "uv"
args = ["run", "--directory", "/home/jjat00/projects/hf-studio", "hf-studio", "mcp"]
env = { HF_STUDIO_URL = "http://127.0.0.1:8787", HF_STUDIO_TOKEN = "hfs_…" }
```

Herramientas (15): `find_models`, `get_model`, `recommend_models`, `upload_media`, `estimate_cost`,
`generate`, `generate_batch`, `get_generation`, `wait_generations`, `list_generations`,
`cancel_generation`, `download_outputs`, `list_presets`, `run_preset` y `save_preset`. Las que gastan
créditos se cotizan primero (`dry_run`), y el servidor MCP pide a los agentes que muestren el costo antes de generar. El MCP no conoce las credenciales
de Higgsfield, solo su propia clave `hfs_…`.

## API REST

Todas las rutas `/v1` requieren `Authorization: Bearer hfs_…`.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/v1/models?capability=&output=&q=` | Catálogo filtrable (lista de capacidades incluida) |
| GET | `/v1/models/{id}` | `input_schema`, notas de uso, enlace a docs |
| POST | `/v1/uploads` (multipart `file`) | Sube jpg/png/webp/gif/mp4/wav → URL pública |
| POST | `/v1/estimate` `{model, input, hints}` | Costo antes de generar: exacto, aproximado por fórmula o pendiente de medios |
| POST | `/v1/generations` `{model, input}` | Encola; 202 nuevo, 200 si se deduplicó. Header `Idempotency-Key` |
| GET | `/v1/generations/{id}?wait=60` | Estado; espera hasta N s a que sea terminal |
| GET | `/v1/generations?ids=a,b&wait=60` | Historial, o espera a que terminen varias |
| POST | `/v1/generations/batch` | Varias generaciones; `dry_run` devuelve el costo por ítem y el total |
| GET | `/v1/recommend?task=…` | Modelos sugeridos para una tarea (es/en) con su costo |
| GET/POST/DELETE | `/v1/presets` | Recetas de serie y propias; `POST /v1/presets/{slug}/run` (con `dry_run`) |
| POST | `/v1/presets/from-generation/{id}` | Guardar una generación como preset |
| POST | `/v1/generations/{id}/cancel` | Solo en `pending`/`queued` |
| GET | `/v1/generations/{id}/files/{name}` | Copia local de la salida |

Estados: `pending` (cola local) → `submitting` → `queued` → `in_progress` → `completed` | `failed` | `nsfw` |
`canceled` | `timed_out`. Cada respuesta incluye `stage` legible, `terminal`, `elapsed_seconds` y
`correlation_id` (para soporte de Higgsfield).

Ejemplo, video entre dos imágenes:

```bash
curl -X POST localhost:8787/v1/generations -H "Authorization: Bearer $HFS" -H 'Content-Type: application/json' \
  -d '{"model":"bytedance/seedance-2.0/image-to-video",
       "input":{"image_url":"https://…/inicio.png","end_image_url":"https://…/final.png",
                "prompt":"slow dolly-in","duration":5}}'
```

## Decisiones

- **REST directo (httpx) en lugar del SDK**: el POST de generación no admite idempotencia, así que tras un
  timeout ambiguo **no se reintenta** (el trabajo queda `failed/submission_ambiguous`). El SDK reintenta
  y sondea por su cuenta; aquí ese ciclo lo gobierna el worker con estado en BD.
- **Concurrencia**: Higgsfield responde 400 al llegar al límite y no envía `Retry-After`. Los trabajos esperan en
  `pending` y se envían cuando hay cupo (`HF_MAX_CONCURRENCY`).
- **Webhooks**: sin firma documentada. El webhook solo dispara una consulta autenticada al endpoint de estado
  (no se confía en su payload). Cada trabajo lleva un token propio en la URL. El sondeo sigue como respaldo.
- **Worker en proceso**: un solo proceso basta. El reclamo atómico (`pending → submitting`) evita dobles envíos
  si se levantan varios. Un reinicio a mitad de envío marca el trabajo como ambiguo en vez de repetirlo.

## Desarrollo

```bash
uv run pytest            # Higgsfield simulado con httpx.MockTransport: no gasta créditos
uv run ruff check src tests
```

## Skills de producción de Higgsfield (TouchDesigner, Blender…)

No pasan por la API de generación: son integraciones locales que se usan con el MCP de Higgsfield
(`claude.ai Higgsfield`) más un servidor MCP local por programa. `/use-touchdesigner` está instalado
en Windows (`%USERPROFILE%\.higgsfield\touch-designer-mcp-client`) y registrado como
`higgsfield-use-touch-designer` en Claude Code y en Codex. Usa el Node de Windows porque WSL está en
modo NAT y TouchDesigner escucha en el `127.0.0.1:9981` de Windows.
