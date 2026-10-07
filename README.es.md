# HF Studio

[![CI](https://github.com/Jjat00/hf-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Jjat00/hf-studio/actions/workflows/ci.yml)
[![M8ven Score](https://m8ven.ai/badge/mcp/jjat00/hf-studio)](https://m8ven.ai/mcp/jjat00/hf-studio)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-40%20herramientas-8A2BE2.svg)](#conectar-agentes-mcp)

**Español** · [English](README.md) · [Web y ejemplos](https://hf-studio-gold.vercel.app)

Tu propio estudio de video, imagen y audio con IA sobre la [API de Higgsfield](https://docs.higgsfield.ai) y la de
[ElevenLabs](https://elevenlabs.io/docs): una **API** y un **servidor MCP** para que tus agentes (Claude Code, Codex,
Claude Desktop, ChatGPT…) generen por ti, y una **interfaz web** para hacerlo a mano. Todo comparte la misma
biblioteca.

![Estudio de video](docs/img/estudio-video.png)

## Más barato con varios proveedores

El mismo modelo suele venderse en varios proveedores a precios muy distintos. HF Studio puede enviar cada generación
al proveedor más barato que ofrezca **exactamente el mismo modelo y la misma configuración**:

| Proveedor | Clave | Qué aporta |
| --- | --- | --- |
| [Higgsfield](https://higgsfield.ai) | `HF_API_KEY`, obligatoria | Todos los modelos del catálogo; además guarda tus archivos de entrada (subir es gratis) |
| [APIMart](https://apimart.ai) | `APIMART_API_KEY`, opcional | Suele ser el más barato en Seedance y Wan |
| [KIE](https://kie.ai) | `KIE_API_KEY`, opcional | Suele ser el más barato en Hailuo y MiniMax |

- **Cotiza en todos y genera en el más barato.** `/v1/estimate`, la UI y `estimate_cost` muestran cada opción, el
  ahorro frente a Higgsfield y por qué se descartó un proveedor (sin clave, sin saldo o sin equivalente exacto para
  tu configuración). Los precios salen de la tabla pública de cada revendedor, actualizada a diario. El 2026-10-03,
  Seedance 2.0 a 720p y 5 s costaba 0,71 USD en APIMart, 1,025 en KIE y 1,51 en Higgsfield.
- **El mismo modelo, nunca un sustituto.** Un ajuste que un proveedor no puede reproducir (una semilla fija, un
  bitrate, una relación de aspecto…) deja fuera a ese proveedor en vez de descartarse.
- **Canales no oficiales, señalados.** Un proveedor puede vender además un canal no oficial más barato del mismo
  modelo (p. ej. `grok-imagine-1.5-video-ext` de APIMart para Grok Imagine 1.5, unas 6 veces más barato). Es una
  opción más, marcada como «canal no oficial»; si falla, el oficial es el respaldo con la regla de aprobación de
  siempre, y una vez apruebas un canal, se envía ese.
- **Cada generación dice cuánto costó.** El historial muestra el proveedor, el modelo en el proveedor (y si el canal
  es no oficial) y el costo en USD (`~` si es estimado); las fallidas no muestran costo.
- **Elementos de Kling 3.0.** Guarda personajes, productos o lugares en la página **Elementos** (o con
  `create_element`): nombre, descripción y de 2 a 4 imágenes JPG/PNG, guardadas en local y compartidas entre la UI y
  tus agentes. Elígelos en Kling 3.0 (hasta 3) y cítalos en el prompt con `@nombre`. Salen por APIMart y KIE (KIE
  además pide fotograma inicial); la API pública de Higgsfield no permite crear ni leer elementos, así que esos
  pedidos no van por Higgsfield.
- **Respaldo sin cobros dobles.** Si un proveedor rechaza el pedido o la tarea falla sin cobrar, el siguiente se
  prueba solo si cuesta lo mismo o menos que lo aprobado; si no, la generación espera tu aprobación. Un envío que pudo
  llegar al proveedor (timeout, respuesta dudosa) nunca se reintenta en ninguno.
- **Precios comprobados antes de enviar.** APIMart y KIE se cotizan con tablas locales, así que se recotizan justo
  antes de cada envío; las cotizaciones de Higgsfield se reutilizan 15 minutos y se piden de nuevo después. Antes del
  primer envío automático se rehace el plan entero con los precios de ese momento. La generación se detiene a esperar
  tu aprobación cuando el precio comprobado supera el tope aprobado, cuando el precio pasa a ser desconocido y no
  aceptaste un costo desconocido para esa opción, o cuando una retención inicial (algunos proveedores retienen más de
  lo que cobran y devuelven la diferencia) supera la que aprobaste. Si aceptaste un costo desconocido sin tope para
  una opción, esa opción puede correr al precio que acabe teniendo; las retenciones siempre se aprueban aparte.
- **Añadir una clave:** `uv run hf-studio providers --add apimart` (o `kie`) la pide, la valida gratis y la guarda;
  `--open NOMBRE` abre la página donde se crea y `hf-studio providers` muestra estado y saldos. La UI tiene la página
  **Proveedores** con los mismos enlaces.
- **Añadir un proveedor (desarrollo):** una subclase de `Provider` en `src/hf_studio/providers/` (comprobar clave,
  enviar, consultar, tabla de precios opcional) con su tabla de modelos, listada en `registry.py`. Setup, la UI, el
  MCP y el worker la recogen de ahí.

## Qué incluye

- **Spaces, un lienzo de nodos para generar por pasos** (`/spaces`, inspirado en Magnific Spaces): conecta textos,
  medios, listas y cualquier modelo del catálogo; la salida de cada paso alimenta al siguiente. Cada nodo muestra su
  costo en USD antes de generar y guarda su historial. Clic derecho o `/` para añadir un nodo; arrastra una salida a un
  espacio vacío para añadir el siguiente paso ya conectado.
  - **Corridas en el servidor** («Ejecutar todo» o «Generar este y los siguientes»): se cotiza cada paso, apruebas un
    tope total y la corrida se pausa para preguntarte si un paso no cabe, no tiene precio o su proveedor de respaldo
    cuesta más. Sigue aunque cierres la pestaña y nunca paga dos veces tras un reinicio.
  - **Listas para lotes:** un generador conectado a una lista corre una vez por elemento marcado, y el lote sigue la
    cadena en pares (5 prompts → 5 imágenes → 5 videos).
  - **Herramientas locales gratis** (ffmpeg): primer o último fotograma de un video, combinar videos, mezclar audio
    sobre un video.
  - **Nodos de audio** (ElevenLabs): voz en off con tus voces, efectos de sonido y música.
  - **Nodo Assistant** (Claude, `ANTHROPIC_API_KEY` opcional): escribe o mejora prompts, describe imágenes y redacta
    guiones; su texto alimenta a otros nodos.
  - **Flujos:** publica un lienzo con entradas etiquetadas y córrelo desde Presets llenando un formulario.
- **82 endpoints de Higgsfield** (66 de video, 15 de imagen y 1 de referencias personalizadas), cada uno con su JSON
  Schema sacado de la documentación oficial (`hf-studio sync-catalog`).
- **Todas las capacidades de video e imagen:** texto a video, imagen a video, fotograma inicial y final, videos de
  referencia, edición y extensión de video, transferencia de movimiento, cambio de objetos (Genjutsu), texto a imagen
  y edición de imagen. Se busca por capacidad, no por marca.
- **Audio con ElevenLabs (opcional):** cambio de voz en un tramo de un video, con efectos de terror (grave, monstruo,
  fantasma), texto a voz, efectos de sonido, música y aislamiento de voz.
- **Conservar el audio original** en las ediciones de video: HF Studio le pone al resultado el sonido del video de
  entrada (gratis, con ffmpeg), útil cuando el modelo lo devuelve mudo.
- **El costo se ve antes de generar.** En la UI aparece junto al botón. Por MCP, generar exige una cotización previa
  de esa misma petición, de un solo uso. En la API REST, las rutas de ElevenLabs exigen su propia cotización; las de
  Higgsfield ofrecen `/v1/estimate` y `dry_run` y confían en quien tiene la clave `hfs_…`.
- **Trabajos asíncronos y persistentes:** validación antes de gastar créditos, deduplicación, `Idempotency-Key`, cola
  local según la concurrencia de la cuenta, sondeo con backoff, webhooks opcionales y copia local de las salidas
  (Higgsfield solo las guarda 7 días).
- **Biblioteca** en cuadrícula masonry con todo lo generado desde la UI y desde los agentes (con su origen), filtros por
  tipo y una página de detalle por resultado con su configuración completa (modelo, prompt, parámetros, archivos de
  entrada y JSON).
- **Sonoteca:** todos tus sonidos de ElevenLabs (los de HF Studio y las voces generadas en su web, que se importan
  gratis) ordenados por lo que son (voces, gritos, risas, criaturas, ambientes, golpes, objetos y pasos, transiciones,
  música) con título y etiquetas editables, para reutilizarlos sin volver a pagar.
- **Presets** (recetas con variables), **lotes** con cotización total, **recomendador** de modelos en lenguaje
  natural (es/en) y **22 casos de uso** con tutorial paso a paso para la UI y para los agentes.
- **Interfaz bilingüe:** español por defecto e inglés con un clic.

| Casos de uso | Catálogo de modelos |
| --- | --- |
| ![Casos de uso](docs/img/casos-de-uso.png) | ![Modelos](docs/img/modelos.png) |

## Requisitos

Funciona nativo en Windows, macOS y Linux (y en WSL). El CI prueba el backend en los tres.

- Python 3.12+ y [uv](https://docs.astral.sh/uv/)
- Node.js 20+ y [pnpm](https://pnpm.io/) (para la UI)
- [ffmpeg](https://ffmpeg.org/) con `ffprobe` (cambio de voz, audio original y aislamiento; también en las pruebas).
  Linux: `sudo apt install ffmpeg`. Windows: `winget install ffmpeg`. macOS: `brew install ffmpeg-full`, porque la
  fórmula `ffmpeg` normal no trae el filtro `rubberband` de los efectos de voz (HF Studio encuentra `ffmpeg-full` solo
  y avisa al arrancar si falta el filtro).
- Una clave de API de Higgsfield ([console.higgsfield.ai](https://console.higgsfield.ai)). Generar consume tus créditos.
- Opcional: claves de APIMart y KIE, para abaratar los videos (ver [Más barato con varios proveedores](#más-barato-con-varios-proveedores)).
- Opcional: una clave de API de ElevenLabs ([elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys))
  para voz, efectos y música. Vale con saldo de pago por uso o con un plan.

## Puesta en marcha

```bash
git clone https://github.com/Jjat00/hf-studio.git
cd hf-studio
./dev.sh        # macOS, Linux, WSL
.\dev          # Windows (cmd o PowerShell)
```

Los dos son atajos de `uv run hf-studio start`, que funciona igual en Windows, macOS y Linux.

La primera vez pide tu clave de Higgsfield (y, si quieres, la de ElevenLabs), la valida sin gastar créditos, crea
`.env` y la clave de la UI, instala las dependencias y arranca todo. Para añadir la de ElevenLabs más tarde, ponla en
`ELEVENLABS_API_KEY` dentro de `.env` y reinicia.

- UI web: http://localhost:3000
- API y documentación interactiva: http://127.0.0.1:8787/docs

¿Solo lo vas a usar desde tus agentes? `./dev.sh api` (en Windows `.\dev api`, o en cualquier sistema
`uv run hf-studio start --api-only`) arranca solo la API, sin Node.js. Luego conecta tu agente con
una línea (ver [Conectar agentes](#conectar-agentes-mcp)):

```bash
uv run hf-studio connect claude-code     # o: codex, claude-desktop, json
```

¿Lo instala un agente de IA? Pásale [AGENTS.md](AGENTS.md).

### Comandos

| Comando | Uso |
| --- | --- |
| `hf-studio start [--api-only]` | Prepara todo la primera vez y arranca la API y la UI (o solo la API); `./dev.sh` y `dev.cmd` lo ejecutan |
| `hf-studio setup [--no-input]` | Primera puesta en marcha: `.env`, validación de la clave y clave de la UI (la ejecuta `start`) |
| `hf-studio connect CLIENTE [--print]` | Registra el MCP en `claude-code` o `codex`, o imprime la configuración (`claude-desktop`, `json`) |
| `hf-studio serve` | Arranca la API y el worker |
| `hf-studio mcp` | Servidor MCP por stdio |
| `hf-studio create-key NOMBRE` · `list-keys` · `revoke-key NOMBRE` | Claves `hfs_…` por cliente (UI, Claude Code, Codex…) |
| `hf-studio see-all NOMBRE [--off]` | Deja que un cliente vea y gestione las generaciones de todos (pensado para la UI) |
| `hf-studio keep-source-audio ID` | Pone a una edición ya hecha el audio de su video de origen |
| `hf-studio providers [--add NOMBRE \| --open NOMBRE]` | Estado y saldo de los proveedores; añade una clave o abre la página para crearla |
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
  video · Movimiento), Voz, Audio, Sonoteca, Casos de uso, Presets (con los flujos publicados en `/flows/<id>`), Spaces
  (`/spaces`), Biblioteca (con detalle en `/history/<id>`), Modelos y MCP.
- **Formularios:** se generan desde el `input_schema` de cada modelo, así que los 82 endpoints funcionan sin código
  específico. El formato muestra un rectángulo con su proporción.
- **Voz** (`/voice`): elige un video, marca el tramo sobre la línea de tiempo, busca una voz (tu cuenta o la
  biblioteca pública de ElevenLabs, con escucha previa), añade un efecto y decide cuánto del audio original se oye.
- **Audio** (`/audio`): texto a voz (modelos expresivo v3, estable v2 o económico Flash, con idioma), efectos de
  sonido, música y aislamiento de voz de un video o audio.
- **Proxy:** el navegador solo habla con `/api/studio/*`, un proxy en el servidor de Next que añade la clave
  `hfs_…`. La clave nunca llega al cliente.
- **Casos de uso** (`/use-cases`, datos en `web/src/lib/use-cases.ts`): `?case=<slug>` abre uno y «Usar en el
  estudio» abre el estudio (o Audio) con `?prompt=` ya relleno.
- **Idiomas:** el idioma se guarda en la cookie `hfs-lang`, así que las URLs no cambian. Los textos están en
  `web/src/lib/i18n/dictionaries.ts` y los datos bilingües usan `l("es", "en")`. La API y el MCP siguen en inglés,
  así que la UI traduce en el cliente los presets de serie, las frases de costo y los nombres de flujo del
  catálogo. Los prompts de ejemplo y las opciones de los presets se envían en inglés.

## Conectar agentes (MCP)

Con la API en marcha (`hf-studio start`, `./dev.sh` o `.\dev`), lo más fácil es **pedirle a tu agente que se conecte
solo**. Pega esto en Claude Code, Codex u otro agente (la página MCP de la UI lo trae con tu ruta real ya puesta):

```text
Conecta a ti mismo (este agente) el servidor MCP de HF Studio. Está instalado en: /ruta/absoluta/a/hf-studio

1. Comprueba que su API está en marcha: GET http://127.0.0.1:8787/health debe responder {"ok": true, ...}. Si no responde, pídeme que la arranque con `uv run hf-studio start` en esa carpeta y espera.
2. Regístralo con el comando de tu cliente:
   - Claude Code: uv run --directory '/ruta/absoluta/a/hf-studio' hf-studio connect claude-code
   - Codex: uv run --directory '/ruta/absoluta/a/hf-studio' hf-studio connect codex
   - Otro cliente MCP: uv run --directory '/ruta/absoluta/a/hf-studio' hf-studio connect json, y añade la configuración que imprime a tu configuración de MCP.
   El comando crea una clave solo para ti. Si dice que hf-studio ya está registrado, pregúntame antes de quitar el registro anterior. Si tu sandbox no te deja ejecutarlo, muéstrame el comando para que lo ejecute yo.
3. Dime que te reinicie para que cargues las herramientas.
4. Lee la sección "Use it through MCP" del AGENTS.md de esa carpeta. Regla clave: antes de generar, cotiza, dime el costo y espera mi OK.
```

O hazlo tú: un comando crea la clave del agente y registra el servidor:

```bash
uv run hf-studio connect claude-code     # ejecuta `claude mcp add` por ti
uv run hf-studio connect codex           # ejecuta `codex mcp add` por ti
uv run hf-studio connect claude-desktop  # imprime el JSON para claude_desktop_config.json
uv run hf-studio connect json            # imprime la configuración para otro cliente MCP por stdio
```

Con `--print` imprime el comando o la configuración (con una clave nueva) en vez de registrarlo. Si la CLI del agente
no está instalada, no se registra nada: imprime el comando, con su clave nueva, para ejecutarlo donde esté esa CLI.
Desde WSL, `claude-desktop` imprime una configuración que entra a WSL con `wsl.exe`, para cuando HF Studio corre en
WSL y Claude Desktop en Windows. Reinicia el cliente después para que cargue las herramientas. Cada conexión
tiene su propia clave `hfs_…` revocable (`codex`, `codex-2`…; ver `hf-studio list-keys`, `revoke-key NOMBRE`) y nunca
se tocan las que ya existen. Si el agente ya tiene `hf-studio`, `connect` se detiene: quítalo antes
(`claude mcp remove hf-studio`). A
mano, el servidor es `uv run --directory /ruta/absoluta/a/hf-studio hf-studio mcp` con
`HF_STUDIO_URL=http://127.0.0.1:8787` y `HF_STUDIO_TOKEN=hfs_…` en su entorno.

Herramientas (40). Todas declaran las cuatro pistas MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`) y las que gastan créditos lo dicen en su título, para que el cliente avise antes de usarlas.

| Grupo | Herramientas |
| --- | --- |
| Modelos | `find_models`, `get_model`, `recommend_models` |
| Generar | `upload_media`, `estimate_cost`, `generate`, `generate_batch` |
| Seguimiento | `get_generation`, `wait_generations`, `list_generations`, `cancel_generation`, `download_outputs`, `approve_fallback` |
| Proveedores | `providers_status` |
| Presets | `list_presets`, `run_preset`, `save_preset` |
| Voz (ElevenLabs) | `list_voices`, `change_voice` |
| Audio (ElevenLabs) | `text_to_speech`, `sound_effect`, `compose_music`, `isolate_voice`, `elevenlabs_account` |
| Sonoteca | `list_sounds`, `label_sound`, `import_elevenlabs_history` |
| Reutilizar y elementos | `use_output`, `list_elements`, `create_element`, `delete_element` |
| Spaces | `list_spaces`, `get_space`, `create_space`, `update_space`, `estimate_space_run`, `run_space`, `get_space_run`, `approve_space_run`, `cancel_space_run` |

**Ninguna herramienta MCP genera sin cotizar antes esa misma petición.** `estimate_cost`, y `generate_batch` o `run_preset`
con `dry_run=True`, devuelven el costo y un `quote_id`. `generate`, y los lotes y presets con `dry_run=False`,
exigen ese `quote_id` con los mismos parámetros. Las herramientas de ElevenLabs siguen el mismo patrón: sin
`quote_id` devuelven el costo; con él, generan. Cada cotización vale para una sola ejecución y dura 15 min; un
reintento con la misma `idempotency_key` no vuelve a cobrar. Si el precio está incompleto (falta
`input_video_seconds`, que en los lotes también puede ir por ítem en `hints`), hace falta además
`confirm_unknown_cost=True`, solo cuando el usuario acepta explícitamente un costo desconocido. **Aprobar una
generación pendiente es un paso aparte, sin `quote_id`:** una generación en `awaiting_approval` (su proveedor falló
sin cobrar, o el precio superó lo aprobado) muestra el precio nuevo en `cost_usd` y la retención inicial en
`reserve_usd`; con el OK del usuario, `approve_fallback` recibe `max_usd` (ese precio), `max_reserve_usd` (esa
retención) o, solo si el usuario acepta un costo desconocido, `accept_unknown_cost=True` (sin `max_usd` queda sin
tope; con él, el tope sigue mandando cuando el precio se conoce). HF Studio recotiza al aprobar y responde 409 con
el precio actual si subió. `get_model` devuelve
también `studio_notes`, avisos de HF Studio como que `generate_audio=false` en una edición da un video mudo y cómo
conservar el audio original (`generate` con `keep_source_audio=true`). El MCP no conoce las credenciales de
Higgsfield ni de ElevenLabs, solo su propia clave `hfs_…`. Tampoco puede comprobar que una persona vio el precio:
mostrarlo y esperar el OK le toca al agente, como piden las instrucciones del servidor.

**Spaces sigue la misma regla.** `estimate_space_run` cotiza cada paso y el total y devuelve un `quote_id`;
`run_space` lo exige y usa ese total como tope de la corrida (un `max_total_usd` mayor solo si el usuario lo aprobó).
Repetir `run_space` con el mismo `quote_id` devuelve la misma corrida. Una corrida en `awaiting_approval` muestra el
motivo y el nuevo total en `pause.needed_total_usd`; con el OK del usuario, `approve_space_run`. Un flujo publicado se
corre con `inputs`.

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
| GET/PATCH | `/v1/sounds?category=&q=` · `/v1/sounds/{id}` | Sonoteca con recuento por categoría; corregir título, categoría y etiquetas |
| GET/POST/DELETE | `/v1/elements` · `/v1/elements/{id}` | Elementos de Kling 3.0: listar, crear (multipart `name`, `description`, 2 a 4 `files` o `image_urls` propias) y borrar |
| POST | `/v1/sounds/import-elevenlabs` | Trae a la sonoteca las voces del historial de ElevenLabs (gratis) |
| POST | `/v1/audio/{servicio}/estimate` · `/v1/audio/{servicio}` | `text-to-speech`, `sound-effects`, `music`, `voice-isolator`: cotiza (`audio_quote`) y lanza con ella |
| GET/POST/PUT/DELETE | `/v1/spaces` · `/v1/spaces/{id}` | Lienzos de nodos (grafo validado, guardado con `version`); `flow` publica uno |
| POST | `/v1/spaces/{id}/runs` | Corrida en el servidor: `dry_run` cotiza cada paso y el total; con `max_total_usd` arranca (`Idempotency-Key`) |
| GET/POST | `/v1/spaces/{id}/runs/{run}` · `…/approve` · `…/cancel` | Seguir, aprobar una pausa (nuevo total) o detener una corrida |
| GET | `/v1/flows` | Flujos publicados con sus entradas |

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
cd web && pnpm lint && pnpm exec next typegen && npx tsc --noEmit
```

## Licencia

[MIT](LICENSE).

## Aviso

Proyecto personal, no afiliado a Higgsfield ni a ElevenLabs. Usa sus APIs públicas con tus propias claves y tus
créditos. Higgsfield, ElevenLabs y los nombres de los modelos pertenecen a sus dueños.
