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
cp .env.example .env          # rellena HF_API_KEY_ID y HF_API_KEY_SECRET
uv run hf-studio create-key claude-code   # muestra la clave hfs_… una sola vez
uv run hf-studio create-key codex
uv run hf-studio serve        # http://127.0.0.1:8787  ·  docs interactivas en /docs
```

Otros comandos: `hf-studio list-keys`, `hf-studio revoke-key NOMBRE`, `hf-studio sync-catalog`.

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

Herramientas: `find_models`, `get_model`, `upload_media`, `estimate_cost`, `generate`, `get_generation`
(con espera), `list_generations`, `cancel_generation`, `download_outputs`. El MCP no conoce las credenciales
de Higgsfield, solo su propia clave `hfs_…`.

## API REST

Todas las rutas `/v1` requieren `Authorization: Bearer hfs_…`.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/v1/models?capability=&output=&q=` | Catálogo filtrable (lista de capacidades incluida) |
| GET | `/v1/models/{id}` | `input_schema`, notas de uso, enlace a docs |
| POST | `/v1/uploads` (multipart `file`) | Sube jpg/png/webp/gif/mp4/wav → URL pública |
| POST | `/v1/estimate` `{model, input}` | Costo en créditos/USD |
| POST | `/v1/generations` `{model, input}` | Encola; 202 nuevo, 200 si se deduplicó. Header `Idempotency-Key` |
| GET | `/v1/generations/{id}?wait=60` | Estado; espera hasta N s a que sea terminal |
| GET | `/v1/generations` | Historial del cliente |
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
