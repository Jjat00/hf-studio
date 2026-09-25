# HF Studio

Tu propio estudio de video, imagen y audio con IA sobre la [API de Higgsfield](https://docs.higgsfield.ai) y la de
[ElevenLabs](https://elevenlabs.io/docs): una **API** y un **servidor MCP** para que tus agentes (Claude Code, Codex,
Claude Desktop, ChatGPT…) generen por ti, y una **interfaz web** para hacerlo a mano. Todo comparte la misma
biblioteca.

*Your own AI video, image and audio studio on top of the Higgsfield and ElevenLabs APIs: a REST API, an MCP server for
agents and a web UI (Spanish by default, English available).*

![Estudio de video](docs/img/estudio-video.png)

## Qué incluye

- **82 endpoints de Higgsfield** (66 de video, 15 de imagen y 1 de referencias personalizadas), cada uno con su JSON
  Schema sacado de la documentación oficial (`hf-studio sync-catalog`).
- **Todas las capacidades de video e imagen:** texto a video, imagen a video, fotograma inicial y final, videos de
  referencia, edición y extensión de video, transferencia de movimiento, cambio de objetos (Genjutsu), texto a imagen
  y edición de imagen. Se busca por capacidad, no por marca.
- **Audio con ElevenLabs (opcional):** cambio de voz en un tramo de un video, con efectos de terror (grave, monstruo,
  fantasma), texto a voz, efectos de sonido, música y aislamiento de voz.
- **Conservar el audio original** en las ediciones de video: HF Studio le pone al resultado el sonido del video de
  entrada (gratis, con ffmpeg), útil cuando el modelo lo devuelve mudo.
- **El costo siempre se ve antes de generar.** En la UI aparece junto al botón. Por MCP y API, generar exige una
  cotización previa de esa misma petición, de un solo uso.
- **Trabajos asíncronos y persistentes:** validación antes de gastar créditos, deduplicación, `Idempotency-Key`, cola
  local según la concurrencia de la cuenta, sondeo con backoff, webhooks opcionales y copia local de las salidas
  (Higgsfield solo las guarda 7 días).
- **Biblioteca** en cuadrícula masonry con todo lo generado desde la UI y desde los agentes (con su origen), filtros por
  tipo y una página de detalle por resultado con su configuración completa (modelo, prompt, parámetros, archivos de
  entrada y JSON).
- **Presets** (recetas con variables), **lotes** con cotización total, **recomendador** de modelos en lenguaje
  natural (es/en) y **12 casos de uso** con tutorial paso a paso para la UI y para los agentes.
- **Interfaz bilingüe:** español por defecto e inglés con un clic.

| Casos de uso | Catálogo de modelos |
| --- | --- |
| ![Casos de uso](docs/img/casos-de-uso.png) | ![Modelos](docs/img/modelos.png) |

## Requisitos

- Python 3.12+ y [uv](https://docs.astral.sh/uv/)
- Node.js 20+ y [pnpm](https://pnpm.io/) (para la UI)
- [ffmpeg](https://ffmpeg.org/) con `ffprobe` (cambio de voz, audio original y aislamiento; también en las pruebas)
- Una clave de API de Higgsfield ([console.higgsfield.ai](https://console.higgsfield.ai)). Generar consume tus créditos.
- Opcional: una clave de API de ElevenLabs ([elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys))
  para voz, efectos y música. Vale con saldo de pago por uso o con un plan.

## Puesta en marcha

```bash
git clone https://github.com/Jjat00/hf-studio.git && cd hf-studio
uv sync
cp .env.example .env                      # pega tu clave de Higgsfield en HF_API_KEY (y ELEVENLABS_API_KEY si la tienes)
uv run hf-studio check-credentials        # valida la clave de Higgsfield sin gastar créditos
uv run hf-studio create-key web-ui        # clave hfs_… para la UI (se muestra una sola vez)
uv run hf-studio see-all web-ui           # la biblioteca de la UI muestra también lo que generan tus agentes
cp web/.env.example web/.env.local        # pega esa clave en HF_STUDIO_TOKEN
cd web && pnpm install && cd ..
./dev.sh                                  # API en :8787 (docs en /docs) y UI en http://localhost:3000
```

### Comandos

| Comando | Uso |
| --- | --- |
| `hf-studio serve` | Arranca la API y el worker |
| `hf-studio mcp` | Servidor MCP por stdio |
| `hf-studio create-key NOMBRE` · `list-keys` · `revoke-key NOMBRE` | Claves `hfs_…` por cliente (UI, Claude Code, Codex…) |
| `hf-studio see-all NOMBRE [--off]` | Deja que un cliente vea y gestione las generaciones de todos (pensado para la UI) |
| `hf-studio keep-source-audio ID` | Pone a una edición ya hecha el audio de su video de origen |
| `hf-studio check-credentials` | Valida la clave de Higgsfield sin gastar |
| `hf-studio sync-catalog` | Regenera `catalog.json` desde docs.higgsfield.ai |

### Claves y acceso

Cada cliente tiene su propia clave `hfs_…` y por defecto solo ve sus generaciones. Las credenciales de Higgsfield y
ElevenLabs solo las conoce la API.

> **Aviso:** el proxy de la UI no autentica a quien la visita, así que con `see-all` cualquiera que alcance el
> servidor Next puede ver, borrar y lanzar generaciones. `pnpm dev` y `pnpm start` escuchan solo en `127.0.0.1`; no lo
> expongas a otras máquinas sin poner autenticación delante.

## UI web (`web/`)

Next.js 16 y Tailwind 4, con un look inspirado en higgsfield.ai. El logo, el nombre y las ilustraciones son propios.

- **Páginas:** Explorar, Imagen, Video (Crear: texto, fotograma inicial y final, referencias · Genjutsu · Editar
  video · Movimiento), Voz, Audio, Casos de uso, Presets, Biblioteca (con detalle en `/history/<id>`), Modelos y MCP.
- **Formularios:** se generan desde el `input_schema` de cada modelo, así que los 82 endpoints funcionan sin código
  específico. El formato muestra un rectángulo con su proporción.
- **Voz** (`/voice`): elige un video, marca el tramo sobre la línea de tiempo, busca una voz (tu cuenta o la
  biblioteca pública de ElevenLabs, con escucha previa), añade un efecto y decide cuánto del audio original se oye.
- **Audio** (`/audio`): texto a voz (modelos expresivo v3, estable v2 o económico Flash, con idioma), efectos de
  sonido, música y aislamiento de voz de un video o audio.
- **Proxy:** el navegador solo habla con `/api/studio/*`, un proxy en el servidor de Next que añade la clave
  `hfs_…`. La clave nunca llega al cliente.
- **Casos de uso** (`/use-cases`, datos en `web/src/lib/use-cases.ts`): `?case=<slug>` abre uno y «Usar en el
  estudio» abre el estudio con `?prompt=` ya relleno.
- **Idiomas:** el idioma se guarda en la cookie `hfs-lang`, así que las URLs no cambian. Los textos están en
  `web/src/lib/i18n/dictionaries.ts` y los datos bilingües usan `l("es", "en")`. La API y el MCP siguen en inglés,
  así que la UI traduce en el cliente los presets de serie, las frases de costo y los nombres de flujo del
  catálogo. Los prompts de ejemplo y las opciones de los presets se envían en inglés.

## Conectar agentes (MCP)

Claude Code:

```bash
claude mcp add hf-studio --scope user \
  -e HF_STUDIO_URL=http://127.0.0.1:8787 -e HF_STUDIO_TOKEN=hfs_… \
  -- uv run --directory /ruta/absoluta/a/hf-studio hf-studio mcp
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.hf-studio]
command = "uv"
args = ["run", "--directory", "/ruta/absoluta/a/hf-studio", "hf-studio", "mcp"]
env = { HF_STUDIO_URL = "http://127.0.0.1:8787", HF_STUDIO_TOKEN = "hfs_…" }
```

Claude Desktop, ChatGPT desktop u otro cliente MCP por stdio usan el mismo comando (`hf-studio mcp`) con esas dos
variables. Crea una clave por cliente (`hf-studio create-key claude-desktop`). Los clientes cargan la lista de
herramientas al arrancar: tras actualizar HF Studio, reinícialos.

Herramientas (22):

| Grupo | Herramientas |
| --- | --- |
| Modelos | `find_models`, `get_model`, `recommend_models` |
| Generar | `upload_media`, `estimate_cost`, `generate`, `generate_batch` |
| Seguimiento | `get_generation`, `wait_generations`, `list_generations`, `cancel_generation`, `download_outputs` |
| Presets | `list_presets`, `run_preset`, `save_preset` |
| Voz (ElevenLabs) | `list_voices`, `change_voice` |
| Audio (ElevenLabs) | `text_to_speech`, `sound_effect`, `compose_music`, `isolate_voice`, `elevenlabs_account` |

**Nada se genera sin cotizar antes esa misma petición.** `estimate_cost`, y `generate_batch` o `run_preset`
con `dry_run=True`, devuelven el costo y un `quote_id`. `generate`, y los lotes y presets con `dry_run=False`,
exigen ese `quote_id` con los mismos parámetros. Las herramientas de ElevenLabs siguen el mismo patrón: sin
`quote_id` devuelven el costo; con él, generan. Cada cotización vale para una sola ejecución y dura 15 min; un
reintento con la misma `idempotency_key` no vuelve a cobrar. Si el precio está incompleto (falta
`input_video_seconds`, que en los lotes también puede ir por ítem en `hints`), hace falta además
`confirm_unknown_cost=True`, solo cuando el usuario acepta explícitamente un costo desconocido. `get_model` devuelve
también `studio_notes`, avisos de HF Studio como que `generate_audio=false` en una edición da un video mudo y cómo
conservar el audio original (`generate` con `keep_source_audio=true`). El MCP no conoce las credenciales de
Higgsfield ni de ElevenLabs, solo su propia clave `hfs_…`.

## API REST

Todas las rutas `/v1` requieren `Authorization: Bearer hfs_…`.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/v1/models?capability=&output=&q=` | Catálogo filtrable (lista de capacidades incluida) |
| GET | `/v1/models/{id}` | `input_schema`, notas de uso, `studio_notes`, enlace a docs |
| POST | `/v1/uploads` (multipart `file`) | Sube jpg/png/webp/gif/mp4/wav → URL pública |
| POST | `/v1/estimate` `{model, input, hints}` | Costo antes de generar: exacto, aproximado por fórmula o pendiente de medios |
| POST | `/v1/generations` `{model, input, keep_source_audio}` | Encola; 202 nuevo, 200 si se deduplicó. Header `Idempotency-Key` |
| GET | `/v1/generations/{id}?wait=60` | Estado; espera hasta N s a que sea terminal |
| GET | `/v1/generations?ids=a,b&wait=60` | Historial, o espera a que terminen varias |
| POST | `/v1/generations/batch` | Varias generaciones; `dry_run` devuelve el costo por ítem y el total |
| POST | `/v1/generations/{id}/cancel` | Solo en `pending`/`queued` |
| DELETE | `/v1/generations/{id}` | Borra una generación terminada y su copia local |
| GET | `/v1/generations/{id}/files/{name}` | Copia local de la salida |
| GET | `/v1/recommend?task=…` | Modelos sugeridos para una tarea (es/en) con su costo |
| GET/POST/DELETE | `/v1/presets` | Recetas de serie y propias; `POST /v1/presets/{slug}/run` (con `dry_run`) |
| POST | `/v1/presets/from-generation/{id}` | Guardar una generación como preset |
| GET | `/v1/voice/status` | ¿ElevenLabs configurado?, plan y créditos que quedan |
| GET | `/v1/voice/voices?search=&library=` | Voces de la cuenta o de la biblioteca pública |
| POST | `/v1/voice/estimate` · `/v1/voice/changes` | Cambio de voz en un tramo: cotiza (`voice_quote`) y lanza con ella |
| POST | `/v1/audio/{servicio}/estimate` · `/v1/audio/{servicio}` | `text-to-speech`, `sound-effects`, `music`, `voice-isolator`: cotiza (`audio_quote`) y lanza con ella |

Estados: `pending` (cola local) → `submitting` → `queued` → `in_progress` → `completed` | `failed` | `nsfw` |
`canceled` | `timed_out`. Cada respuesta incluye `stage` legible, `terminal`, `elapsed_seconds` y
`correlation_id` (para soporte de Higgsfield). Los trabajos de ElevenLabs (`elevenlabs/voice-changer`,
`elevenlabs/text-to-speech`, `elevenlabs/sound-effects`, `elevenlabs/music`, `elevenlabs/voice-isolator`) viven en la
misma tabla y se consultan con las mismas rutas de `/v1/generations`.

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
- **ElevenLabs como trabajos locales**: no pasan por el worker de Higgsfield ni ocupan su concurrencia. La API emite
  su propia cotización (de un solo uso, 15 min, ligada al cliente y a la petición) y la canjea de forma atómica; si
  el tramo o la fuente cambiaron desde que se cotizó, no se cobra. Un reinicio marca como fallidos los que quedaron a
  medias.
- **Medios que abre ffmpeg**: solo subidas propias o salidas de generaciones propias, y solo por `file` y `https`
  (nada de URLs arbitrarias, para evitar SSRF). La mezcla de audio nunca cambia la duración de la imagen.
- **Precios de ElevenLabs**: la cotización usa la tarifa de su API de pago por uso (a 2026-09): texto a voz 0,05–0,10
  USD por 1.000 caracteres; cambio de voz, efectos y aislamiento 0,12 USD/min; música 0,15 USD/min.

## Desarrollo

```bash
uv run pytest            # Higgsfield y ElevenLabs simulados con httpx.MockTransport: no gasta créditos
uv run ruff check src tests
cd web && pnpm lint && npx tsc --noEmit
```

## Revisiones

El código pasó por 13 rondas de revisión adversarial con Codex (gpt-6-sol), con veredicto de aprobado en las rondas
5, 8 y 12, y la 13 corregida después. Están en [`docs/revisiones/`](docs/revisiones/).

## Aviso

Proyecto personal, no afiliado a Higgsfield ni a ElevenLabs. Usa sus APIs públicas con tus propias claves y tus
créditos. Higgsfield, ElevenLabs y los nombres de los modelos pertenecen a sus dueños.
