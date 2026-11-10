"""Servidor MCP (stdio) que expone HF Studio a Claude Code, Codex y otros agentes.

Es un cliente delgado de la API REST: no conoce las credenciales de Higgsfield, solo
HF_STUDIO_URL y HF_STUDIO_TOKEN (una clave `hfs_…` creada con `hf-studio create-key`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

INSTRUCTIONS = """Genera imágenes y videos con los modelos de Higgsfield, APIMart y KIE a través de HF Studio.
Proveedores: el mismo modelo puede salir por Higgsfield, APIMart o KIE. estimate_cost cotiza todos los que
tengan clave y elige el más barato (options trae cada precio, excluded el motivo de los descartados y
savings_vs_higgsfield el ahorro); generate envía al más barato. Si ese proveedor falla sin cobrar, HF Studio
prueba el siguiente: solo si cuesta lo mismo o menos; si cuesta más (o el precio cambió desde la
cotización), la generación queda en awaiting_approval: dile al usuario el nuevo precio (cost_usd) y, con su
OK, approve_fallback (o cancel_generation). reserve_usd en una opción es lo que el proveedor retiene al
empezar (devuelve la diferencia al terminar): menciónaselo al usuario.
provider="kie" (u otro) en estimate_cost y generate fuerza uno. providers_status muestra claves, saldos y
los enlaces para crear cuenta o recargar.
Modelos de tienda: el catálogo también trae modelos que Higgsfield no tiene y solo venden APIMart y KIE
(Nano Banana, GPT Image, Veo 3.1, Seedream, Flux, Midjourney, Vidu…); find_models los marca con store=true.
Necesitan la clave de APIMart o de KIE y se usan igual (estimate_cost, generate).
Atajos: recommend_models("lo que quiere el usuario") sugiere modelos con su costo; list_presets y
run_preset ejecutan recetas listas (primero con dry_run=True para mostrar costo y entrada final);
generate_batch hace variantes (primero dry_run=True) y wait_generations espera varias.
Flujo manual: 1) find_models por capacidad (text-to-video, image-to-video, first-last-frame, video-input,
reference-to-video, image-references, video-edit, video-extend, motion-transfer, restyle, text-to-image);
2) get_model para leer input_schema y notes; 3) upload_media si la entrada es un archivo local;
4) estimate_cost; 5) generate con su quote_id; 6) get_generation con wait_seconds hasta terminal=true;
7) download_outputs. La generación es asíncrona y cobra créditos: ANTES de generar, cotiza (estimate_cost,
o dry_run en lotes y presets), dile al usuario el costo y espera su OK (kind exact = créditos y USD;
REGLA FIJA: después de cotizar, termina tu turno con el costo y pregunta; lanza solo cuando el usuario responda
que sí en un mensaje nuevo. Pedir «crea» o «genera» no es aceptar el precio, y que el cliente tenga las
herramientas aprobadas sin preguntar tampoco. Única excepción: que el usuario haya dado en esta conversación
un tope explícito («sin preguntar hasta 1 USD») y el costo quepa en él;
approx = USD aproximado; formula/unavailable = falta subir medios o pasar input_video_seconds). Generar
exige el quote_id de esa cotización (un solo uso, 15 min; si reintentas tras un error, reutiliza la
misma idempotency_key); con precio incompleto, además confirm_unknown_cost=True solo si el
usuario acepta explícitamente un costo desconocido. No repitas generate
tras un error ambiguo, consulta list_generations primero. Reutiliza idempotency_key al reintentar.
Cambio de voz (ElevenLabs): list_voices busca voces (library=True para la biblioteca pública, p. ej.
"demon", "monster"); change_voice cambia la voz de un tramo [start, end] de un video conservando lo que
dice y su ritmo, con efecto opcional (deep, monster, ghost). Primero sin quote_id para ver el costo,
luego con el quote_id tras el OK del usuario; el resultado es una generación más (get_generation).
Más audio de ElevenLabs con el mismo patrón (sin quote_id cotiza; con él, lanza): text_to_speech,
sound_effect, compose_music e isolate_voice. elevenlabs_account muestra el plan y los créditos que quedan.
Crear voces: clone_voice clona una voz con muestras de audio o video (gratis, ocupa un espacio; solo con el
permiso de quien es dueño de la voz: consent=True cuando el usuario lo confirme). design_voice crea tres
muestras desde una descripción (cotiza sin quote_id; cobra el texto de muestra) y save_voice guarda la
elegida. delete_voice borra una voz de la cuenta (pide confirmación). Para español, usa language="es".
Al generar audio, pasa title, category (voice, scream, laugh, creature, ambience, impact, foley, transition,
music, other) y tags para que quede bien ordenado en la sonoteca. Antes de generar un sonido, busca en
list_sounds si ya existe uno que sirva: reutilizarlo es gratis.
Seedance 2.5 Draft (bytedance/seedance-2.5-draft/…, solo APIMart y KIE): borrador barato a 480p. Para la misma
escena en 1080p, genera bytedance/seedance-2.5-draft/final con draft_generation_id = id de la generación del
borrador (va a la tienda que lo hizo; vale 3 días en APIMart y 7 en KIE; precio aproximado). Úsalo para probar
varias versiones de una escena larga o cara antes de pagar la buena en 1080p.
Elementos: personajes, lugares o props reutilizables con nombre, descripción y 1 a 4 imágenes (Kling 3.0 pide 2+)
JPG/PNG. create_element los guarda; list_elements los muestra. Para usarlos, pon sus ids (el_…) en el campo
elements de un modelo Kling 3.0 y cítalos en el prompt con @nombre (p. ej. "@zorro corre por la nieve").
Solo salen por APIMart y KIE (KIE además exige image_url); nunca por Higgsfield.
Para partir de una creación anterior (animar una imagen, usarla de referencia, editar o extender un video),
use_output(generation_id) da su URL vigente; no reutilices URLs viejas de outputs, pueden haber caducado.
Genjutsu Restyle (higgsfield/genjutsu/restyle/v1.0) cambia el estilo de un video y conserva su movimiento y su
audio: elige el estilo con list_styles y pasa su id en preset_id. Ads Studio (higgsfield/ads-studio/v1.0) hace
de 1 a 8 anuncios en imagen a partir de un brief y fotos del producto (batch_size = número de imágenes).
Usa las funciones propias de Higgsfield antes que imitarlas con otros modelos. AI Influencer
(higgsfield/ai-influencer, 0,05 USD) hace la hoja del personaje (primer plano y cuerpo entero) a partir de tier,
selection (claves de list_model_options), brief, seed y una foto opcional; los tipos de animal fallan hoy en
Higgsfield. Para animarla como Higgsfield, Genjutsu motion transfer con la hoja en image_urls y un video del
movimiento en video_url: higgsfield/genjutsu-light/motion-transfer/v1.0 (unas 3 veces más barato, 15 s, conserva
el audio) o higgsfield/genjutsu/motion-transfer/v1.0. Kling 4.0 (kling-video/v4.0/…) hace clips de 3 a 30 s
desde texto, fotogramas, referencias (@image_1, @video_1) o editando un video; también sale por APIMart y
KIE (KIE, un 9 % más barato, no edita).
Spaces (lienzos de nodos): list_spaces, get_space, create_space y update_space leen y arman un lienzo; cada
nodo es texto, medio, nota, lista o generador (cualquier modelo del catálogo, incluidas las herramientas
gratis hf-studio/frame, hf-studio/combine y hf-studio/mix, el audio elevenlabs/tts, elevenlabs/sfx y
elevenlabs/music-gen, y claude/assistant, que escribe texto para el prompt de otros nodos si hay
ANTHROPIC_API_KEY). Una arista lleva la salida de un nodo a un campo de entrada de otro (targetHandle = clave
del input_schema: prompt, image_url, video_url, audio_urls…). Una lista hace que el generador conectado corra
una vez por elemento, y el lote baja en pares por la cadena; data.count (variantes) hace lo mismo con una sola
entrada. Un claude/assistant con values.list_items = N (1 a 20) escribe N elementos y, conectado a una lista de
texto (targetHandle "items"), la llena: el generador que sigue a la lista corre una vez por elemento. update_space con flow publica el lienzo como formulario simple (/flows/<id>) y run_space lo corre
con inputs. Para correrlo en el servidor:
estimate_space_run (precio de cada paso y total, con quote_id) → dile al usuario el total y espera su OK →
run_space con ese quote_id (si falla de forma ambigua, repítelo con el mismo quote_id: devuelve la misma
corrida) → get_space_run hasta que termine. Si la corrida queda en awaiting_approval (un
paso no cabe en el tope, no tiene precio o su respaldo cuesta más), dile el motivo y el nuevo total
(pause.needed_total_usd) y, con su OK, approve_space_run; cancel_space_run la detiene.
Katana (remixar un edit de referencia con el sujeto del usuario): katana_presets o upload_media del video →
katana_create (análisis gratis) → katana_plan sin max_usd (cotiza los tokens de Claude) → OK del usuario →
katana_plan con max_usd (crea el Space) → estimate_space_run → OK del usuario sobre ese total → run_space.
Tarjeta en el chat: en los clientes con widgets (Claude Desktop), generate, generate_batch, run_preset,
approve_fallback y las herramientas de audio abren una tarjeta que sigue el estado sola y muestra el video,
la imagen o el audio al terminar; si el usuario solo quiere verlo, no hace falta que sondees ni que
descargues. No llames show_generations con generaciones que ya tienen tarjeta en esta conversación (las que
lanzaste aquí): saldría repetida. Úsala solo para generaciones de antes o de otra conversación.
Biblioteca: favorite_generations, hide_generations (quita de la vista sin borrar) y delete_generation (borra,
confirma antes); list_approvals muestra lo que espera aprobación; list_uploads, lo ya subido; get_usage, el
gasto por día, proveedor y modelo. Voces gratis (sin créditos): list_free_voices y free_text_to_speech
(hasta 300 caracteres). delete_preset y delete_space borran (confirma antes)."""

# Tarjeta de generación (MCP Apps): en los clientes que muestran widgets (Claude Desktop, claude.ai) las
# herramientas que lanzan generaciones abren esta tarjeta en el chat; sigue el estado sola (get_generation /
# wait_generations desde la tarjeta) y muestra el video, la imagen o el audio al terminar. Los clientes sin
# widgets (Claude Code, Codex) reciben el mismo JSON de siempre.
GENERATION_UI = "ui://hf-studio/generation.html"
# Forma actual (`ui.resourceUri`) y la antigua (`ui/resourceUri`), que algunos clientes aún leen.
UI_META = {"ui": {"resourceUri": GENERATION_UI}, "ui/resourceUri": GENERATION_UI}
# Dominios de los que la tarjeta puede cargar medios directamente (CDN de Higgsfield, APIMart y KIE). Si una
# URL no carga (caducó o su dominio no está aquí), la tarjeta pide la copia local con generation_preview.
MEDIA_DOMAINS = [
    "https://*.cloudfront.net",
    "https://*.higgsfield.ai",
    "https://getapib.org",
    "https://*.getapib.org",
    "https://*.aiquickdraw.com",
    "https://*.apimart.ai",
    "https://*.kie.ai",
]


def _widget_html() -> str:
    html = (Path(__file__).parent / "mcp_ui" / "generation.html").read_text(encoding="utf-8")
    web = os.environ.get("HF_STUDIO_WEB_URL", "http://localhost:3000").rstrip("/")
    return html.replace("__HF_STUDIO_WEB__", json.dumps(web)[1:-1])


apps = Apps()
apps.add_html_resource(
    GENERATION_UI,
    _widget_html(),
    name="generation",
    title="Generación de HF Studio",
    description="Estado y resultado de una generación de HF Studio",
    csp=ResourceCsp(resource_domains=MEDIA_DOMAINS),
    prefers_border=False,
)
mcp = MCPServer("hf-studio", instructions=INSTRUCTIONS, extensions=[apps])
# Cada herramienta declara las cuatro pistas para que el cliente avise antes de invocarla: solo lectura
# (catálogo, biblioteca, estados), gasta créditos (siempre tras una cotización que vio el usuario, título
# «spends credits»), o modifica algo (cancelar, etiquetar, escribir archivos). estimate_cost cuenta como
# solo lectura: no gasta ni toca la base, aunque emite un quote_id en memoria (15 min, un solo uso).
# list_sounds no lo es: antes de listar registra en la sonoteca los audios terminados que falten.


def _is_studio_ref(url: str) -> bool:
    """Ruta relativa a HF_STUDIO_URL (sin esquema, sin host y sin segmentos '..'). Solo esas viajan con el token
    del cliente: httpx manda las cabeceras del cliente a cualquier URL absoluta, aunque el esquema venga en
    mayúsculas."""
    clean = str(url).strip()
    if not clean or "\\" in clean or not clean.startswith("/") or clean.startswith("//"):
        return False
    try:
        parsed = httpx.URL(clean)
    except httpx.InvalidURL:
        return False
    parts = urlsplit(clean)
    if parts.scheme or parts.netloc or parsed.scheme or parsed.host:
        return False
    return ".." not in parts.path.split("/")


def _client() -> httpx.Client:
    token = os.environ.get("HF_STUDIO_TOKEN")
    if not token:
        raise ToolError("Falta HF_STUDIO_TOKEN en el entorno del servidor MCP")
    base = os.environ.get("HF_STUDIO_URL", "http://127.0.0.1:8787")
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=150)


def _call(method: str, path: str, **kwargs: Any) -> Any:
    try:
        with _client() as http:
            response = http.request(method, path, **kwargs)
    except httpx.TransportError as exc:
        raise ToolError(f"HF Studio no responde ({exc}); ¿está corriendo `hf-studio serve`?") from exc
    if response.is_success:
        return response.json() if response.content else {"ok": True}
    try:
        error = response.json().get("error") or response.json()
    except ValueError:
        error = response.text
    raise ToolError(f"HTTP {response.status_code}: {error}")


@mcp.tool(
    title="Find models",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def find_models(capability: str | None = None, output: str | None = None, query: str | None = None) -> dict:
    """Busca modelos. capability: text-to-video, image-to-video, first-last-frame, video-input,
    reference-to-video, image-references, audio-input, video-edit, video-extend, motion-transfer,
    object-swap, restyle, text-to-image, edit. output: video | image. query: texto en id/título (p. ej. seedance)."""
    params = {k: v for k, v in {"capability": capability, "output": output, "q": query}.items() if v}
    return _call("GET", "/v1/models", params=params)


@mcp.tool(
    title="Get model schema",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def get_model(model_id: str) -> dict:
    """Esquema de entrada (JSON Schema), notas de uso y docs de un modelo, p. ej.
    bytedance/seedance-2.0/image-to-video. Léelo antes de generar, incluidas las studio_notes
    (avisos de HF Studio, p. ej. cómo conservar el audio del video de origen)."""
    return _call("GET", f"/v1/models/{model_id}")


@mcp.tool(
    title="List model styles",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def list_styles(model_id: str = "higgsfield/genjutsu/restyle/v1.0") -> dict:
    """Estilos vigentes de un modelo que elige uno por preset_id (hoy Genjutsu Restyle): id, nombre y
    preview_url. Pon el id en preset_id; cambian sin aviso, no reutilices uno viejo sin mirar la lista. Gratis."""
    return _call("GET", f"/v1/model-styles/{model_id}")


@mcp.tool(
    title="List model options",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def list_model_options(model_id: str = "higgsfield/ai-influencer") -> dict:
    """Rasgos vigentes de un modelo que los elige por clave (hoy AI Influencer): categorías con key, tiers, max y
    opciones (key, label, img, color, slot, exclusive). Pon en selection {categoría: [claves]}, solo de categorías
    cuyo tiers incluya tu tier, como mucho max por categoría, una opción exclusiva sola y una por slot. Cambian sin
    aviso. Gratis."""
    return _call("GET", f"/v1/model-options/{model_id}")


def _local_path(path: str) -> Path:
    """Traduce `C:\\Users\\…` o `C:/Users/…` a `/mnt/c/Users/…` cuando el MCP corre en WSL y el cliente
    (ChatGPT o Claude Desktop de Windows) pasa rutas de Windows."""
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", path.strip())
    if match and os.name != "nt" and Path("/mnt").is_dir():
        drive, rest = match.groups()
        return Path("/mnt", drive.lower(), *[p for p in re.split(r"[\\/]+", rest) if p])
    return Path(path).expanduser()


@mcp.tool(
    title="Upload local media",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def upload_media(path: str) -> dict:
    """Sube una imagen (jpg/png/webp/gif), video mp4 o audio wav local y devuelve una URL pública
    para usar en campos *_url / *_urls del modelo. Acepta rutas de Windows (C:\\...) si el MCP corre en WSL."""
    file = _local_path(path)
    if not file.is_file():
        raise ToolError(f"No existe el archivo {file}")
    content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    with file.open("rb") as fh:
        return _call("POST", "/v1/uploads", files={"file": (file.name, fh, content_type)})


@mcp.tool(
    title="Estimate cost",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def estimate_cost(
    model_id: str,
    input: dict,
    input_video_seconds: float | None = None,
    provider: str | None = None,
    input_audio_seconds: float | None = None,
) -> dict:
    """Costo de una generación sin ejecutarla, en cada proveedor (el más barato primero: `provider`, `usd`;
    todas en `options`). Funciona aunque falten los medios. Si el modelo cobra por segundos de video de
    entrada, pasa input_video_seconds (o sube el video antes: HF Studio lo mide); los avatares que cobran por
    segundo de audio, input_audio_seconds. `provider` cotiza solo
    ese. Devuelve quote_id: muéstrale el costo al usuario y pásalo a generate con los mismos parámetros."""
    hints = _hints(input_video_seconds, input_audio_seconds)
    payload = {"model": model_id, "input": input, "hints": hints, "provider": provider}
    estimate = _call("POST", "/v1/estimate", json=payload)
    return {**estimate, "quote_id": _issue_quote(payload, estimate)}


@mcp.tool(
    title="Generate (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def generate(
    model_id: str,
    input: dict,
    quote_id: str,
    idempotency_key: str | None = None,
    allow_duplicate: bool = False,
    input_video_seconds: float | None = None,
    confirm_unknown_cost: bool = False,
    keep_source_audio: bool = False,
    provider: str | None = None,
    input_audio_seconds: float | None = None,
) -> dict:
    """Encola una generación en el proveedor más barato de la cotización (o en `provider`, el mismo que
    se pasó a estimate_cost) y devuelve el trabajo (id, status, provider). No espera: usa get_generation.
    Requiere el quote_id de estimate_cost con los mismos model_id, input e input_*_seconds. Llámala solo
    después de que el usuario vio ese costo y dijo que sí en un mensaje nuevo (no en el mismo turno en que
    cotizaste), salvo que haya dado un tope explícito en el que quepa. Si reintentas tras un fallo de red, pasa la misma idempotency_key.
    Al editar un video (entrada video_url), generate_audio=false da un video MUDO, no conserva el sonido
    original; para conservarlo pasa keep_source_audio=true (gratis: HF Studio le pone el audio del
    video de origen al resultado). Lee studio_notes en get_model."""
    hints = _hints(input_video_seconds, input_audio_seconds)
    payload = {"model": model_id, "input": input, "hints": hints, "provider": provider}
    key, approved = _authorize(payload, quote_id, idempotency_key, confirm_unknown_cost)
    headers = {"Idempotency-Key": key}
    body = {
        "model": model_id,
        "input": input,
        "allow_duplicate": allow_duplicate,
        "keep_source_audio": keep_source_audio,
        "hints": hints,
        "provider": provider,
        # El precio que vio el usuario: si subió, la API responde 409 y hay que volver a cotizar.
        "max_usd": approved["usd"],
        "max_reserve_usd": approved["reserve_usd"],
        "accept_unknown_cost": approved["accept_unknown_cost"],
    }
    return _call("POST", "/v1/generations", json=body, headers=headers)


@mcp.tool(
    title="List voices",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def list_voices(search: str | None = None, library: bool = False, limit: int = 20) -> dict:
    """Voces de ElevenLabs para change_voice. Sin library: las de la cuenta (incluye predefinidas).
    Con library=True busca en la biblioteca pública (p. ej. search="demon", "monster", "horror",
    "villain"); esas voces traen public_owner_id, que hay que pasar a change_voice. preview_url
    permite escucharlas."""
    params = {"library": library, "limit": limit, **({"search": search} if search else {})}
    return _call("GET", "/v1/voice/voices", params=params)


_upload_cache: dict[tuple[str, int, float], str] = {}


def _uploaded_url(path: str) -> str:
    """Sube un archivo local una sola vez por versión (cotizar y ejecutar usan la misma URL)."""
    file = _local_path(path)
    if not file.is_file():
        raise ToolError(f"No existe el archivo {file}")
    stat = file.stat()
    key = (str(file.resolve()), stat.st_size, stat.st_mtime)
    if key not in _upload_cache:
        _upload_cache[key] = upload_media(path)["url"]
    return _upload_cache[key]


@mcp.tool(
    title="Change voice (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def change_voice(
    voice_id: str,
    source_generation_id: str | None = None,
    source_path: str | None = None,
    source_url: str | None = None,
    start: float = 0,
    end: float | None = None,
    public_owner_id: str | None = None,
    voice_name: str | None = None,
    effect: str = "none",
    original_volume: float = 0,
    remove_background_noise: bool = True,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Cambia la voz de un tramo de un video con ElevenLabs Voice Changer: conserva lo que se dice,
    el ritmo y la emoción, y solo toca el tramo [start, end] (en segundos; end vacío = hasta el final).
    Origen: source_generation_id (un video de la biblioteca), source_path (archivo local; se sube) o
    source_url. effect añade una capa: deep (grave), monster (monstruo), ghost (fantasma) o none.
    original_volume (0-1) deja el audio original de fondo dentro del tramo; 0 lo sustituye del todo.
    Sin quote_id devuelve el costo y un quote_id: muéstraselo al usuario y, con su OK, vuelve a llamar
    con los mismos argumentos y ese quote_id. Devuelve la generación (asíncrona: usa get_generation)."""
    quoted_source = {"source_path": source_path} if source_path else {}
    if source_path:
        source_url = _uploaded_url(source_path)
    body = {
        "voice_id": voice_id,
        "source_generation_id": source_generation_id,
        "source_url": source_url,
        "start": start,
        "end": end,
        "public_owner_id": public_owner_id,
        "voice_name": voice_name,
        "effect": effect,
        "original_volume": original_volume,
        "remove_background_noise": remove_background_noise,
    }
    body = {k: v for k, v in body.items() if v is not None}
    # Se cotiza sobre la ruta local, no sobre la URL de la subida.
    payload = {"voice_change": {**body, **quoted_source, **({"source_url": None} if source_path else {})}}
    if not quote_id:
        estimate = _call("POST", "/v1/voice/estimate", json=body)
        return {**estimate, "quote_id": _issue_quote(payload, estimate), "source_url": source_url}
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, False)}
    # La API solo gasta con su propia cotización (voice_quote), que viaja dentro de la del MCP.
    with _quotes_lock:
        voice_quote = _quotes[quote_id]["estimate"].get("voice_quote")
    return _call("POST", "/v1/voice/changes", json={**body, "voice_quote": voice_quote}, headers=headers)


def _audio(service: str, body: dict, quote_id: str | None, idempotency_key: str | None) -> dict:
    """Sin quote_id cotiza (y devuelve un quote_id); con él, lanza con la cotización de la API."""
    body = {k: v for k, v in body.items() if v is not None}
    payload = {"audio": service, **body}
    if not quote_id:
        estimate = _call("POST", f"/v1/audio/{service}/estimate", json=body)
        return {**estimate, "quote_id": _issue_quote(payload, estimate)}
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, False)}
    with _quotes_lock:
        audio_quote = _quotes[quote_id]["estimate"].get("audio_quote")
    return _call("POST", f"/v1/audio/{service}", json={**body, "audio_quote": audio_quote}, headers=headers)


@mcp.tool(
    title="Text to speech (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def text_to_speech(
    text: str,
    voice_id: str,
    model_id: str = "eleven_v4",
    language_code: str | None = None,
    public_owner_id: str | None = None,
    voice_name: str | None = None,
    stability: float | None = None,
    style: float | None = None,
    speed: float | None = None,
    title: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Texto a voz con ElevenLabs (MP3 en la biblioteca). voice_id de list_voices. model_id:
    eleven_v4 (por defecto, el más natural y con mejor acento en español; admite etiquetas como [excited],
    [whispers]; hasta 10.000 caracteres), eleven_v4_turbo (baja latencia, mitad de precio), eleven_v3 (expresivo,
    5.000), eleven_multilingual_v2 (estable, 10.000) o eleven_flash_v2_5 (mitad de precio, 40.000).
    language_code ISO 639-1 (p. ej. "es"; no en multilingual_v2). Precio por caracteres: sin quote_id
    devuelve el costo; con el OK del usuario, llama igual con ese quote_id."""
    return _audio("text-to-speech", {"text": text, "voice_id": voice_id, "model_id": model_id,
                  "language_code": language_code, "public_owner_id": public_owner_id, "voice_name": voice_name,
                  "stability": stability, "style": style, "speed": speed, "title": title, "category": category,
                  "tags": tags}, quote_id, idempotency_key)  # fmt: skip


@mcp.tool(
    title="Sound effect (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def sound_effect(
    text: str,
    duration_seconds: float = 5,
    prompt_influence: float = 0.3,
    loop: bool = False,
    title: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Efecto de sonido con ElevenLabs a partir de una descripción (mejor en inglés, p. ej. "evil laugh
    echoing in a cave", "door creaking slowly"). duration_seconds de 0.5 a 30; loop=True para que se
    repita sin cortes. Sin quote_id devuelve el costo; con el OK del usuario, llama con ese quote_id."""
    return _audio("sound-effects", {"text": text, "duration_seconds": duration_seconds,
                  "prompt_influence": prompt_influence, "loop": loop, "title": title, "category": category,
                  "tags": tags}, quote_id, idempotency_key)  # fmt: skip


@mcp.tool(
    title="Compose music (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def compose_music(
    prompt: str,
    seconds: float = 30,
    force_instrumental: bool = False,
    title: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Música con ElevenLabs a partir de una descripción (género, tempo, instrumentos, ánimo). seconds de
    3 a 600; force_instrumental=True garantiza que no haya voz. Sin quote_id devuelve el costo; con el OK
    del usuario, llama con ese quote_id."""
    return _audio("music", {"prompt": prompt, "seconds": seconds, "force_instrumental": force_instrumental,
                  "title": title, "category": category, "tags": tags}, quote_id, idempotency_key)  # fmt: skip


@mcp.tool(
    title="Isolate voice (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def isolate_voice(
    source_generation_id: str | None = None,
    source_path: str | None = None,
    source_url: str | None = None,
    title: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Aísla la voz de un video o audio (quita música y ruido) con ElevenLabs; devuelve un MP3.
    Origen: source_generation_id (de la biblioteca), source_path (archivo local; se sube) o source_url.
    Precio por minuto de la fuente: sin quote_id devuelve el costo; con el OK, llama con ese quote_id."""
    quoted = {"source_path": source_path} if source_path else {}
    if source_path:
        source_url = _uploaded_url(source_path)
    body = {"source_generation_id": source_generation_id, "source_url": source_url, "title": title,
            "category": category, "tags": tags}  # fmt: skip
    body = {k: v for k, v in body.items() if v is not None}
    # Se cotiza sobre la ruta local, no sobre la URL de la subida (igual que change_voice).
    payload = {"audio": "voice-isolator", **body, **quoted, **({"source_url": None} if source_path else {})}
    if not quote_id:
        estimate = _call("POST", "/v1/audio/voice-isolator/estimate", json=body)
        return {**estimate, "quote_id": _issue_quote(payload, estimate), "source_url": source_url}
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, False)}
    with _quotes_lock:
        audio_quote = _quotes[quote_id]["estimate"].get("audio_quote")
    return _call(
        "POST", "/v1/audio/voice-isolator", json={**body, "audio_quote": audio_quote}, headers=headers
    )


@mcp.tool(
    title="Clone voice",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def clone_voice(
    name: str,
    consent: bool = False,
    sample_paths: list[str] | None = None,
    source_generation_ids: list[str] | None = None,
    source_urls: list[str] | None = None,
    description: str | None = None,
    language: str = "es",
    remove_background_noise: bool = False,
) -> dict:
    """Clona una voz en la cuenta de ElevenLabs (clonación instantánea) con muestras de audio o video:
    sample_paths (archivos locales: mp3, wav, m4a, mp4, webm, ogg…), source_generation_ids (videos o audios de
    la biblioteca) o source_urls (de upload_media). Lo ideal es 1 a 2 minutos de voz limpia de una sola
    persona, sin música; mínimo 10 s. language (ISO, por defecto es) queda como etiqueta de la voz.
    remove_background_noise solo si las muestras tienen ruido (en audio limpio empeora el clon).
    consent=True solo si el usuario confirma que la voz es suya o que su dueño le dio permiso de clonarla.
    No gasta créditos, pero ocupa un espacio de voces del plan; devuelve voice_id, que ya sirve en
    text_to_speech (mejor con eleven_v4 o eleven_multilingual_v2 y language_code="es") y change_voice.
    Tras un error, revisa list_voices antes de reintentar para no crear la voz dos veces."""
    data = {
        "name": name,
        "consent": "true" if consent else "false",
        "language": language,
        "remove_background_noise": "true" if remove_background_noise else "false",
        **({"description": description} if description else {}),
        **({"source_generation_ids": source_generation_ids} if source_generation_ids else {}),
        **({"source_urls": source_urls} if source_urls else {}),
    }
    files = []
    for path in sample_paths or []:
        file = _local_path(path)
        if not file.is_file():
            raise ToolError(f"No existe el archivo {file}")
        files.append(("files", (file.name, file.read_bytes(), "application/octet-stream")))
    return _call("POST", "/v1/voice/clone", data=data, files=files or None)


@mcp.tool(
    title="Design voice (spends credits)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def design_voice(
    description: str,
    language: str = "es",
    text: str | None = None,
    model_id: str = "eleven_ttv_v3",
    guidance_scale: float | None = None,
    seed: int | None = None,
    should_enhance: bool = False,
    dest_dir: str = ".",
    quote_id: str | None = None,
) -> dict:
    """Diseña una voz nueva a partir de una descripción (ElevenLabs Voice Design): devuelve tres muestras.
    description (20 a 1000 caracteres; mejor en inglés o español detallado): edad, género, acento, tono,
    ritmo y emoción, p. ej. "mujer de 30 años, acento colombiano, cálida y pausada". language (es por
    defecto) fija el idioma del texto de muestra; text propio (100 a 1000 caracteres) para otro idioma o
    para oírla con tu guion. Cobra los caracteres del texto una sola vez: sin quote_id devuelve el costo;
    con el OK del usuario, llama igual con ese quote_id. Las muestras se descargan a dest_dir para que el
    usuario las escuche; guarda la elegida con save_voice (gratis) o descarta todas."""
    body = {"description": description, "language": language, "text": text, "model_id": model_id,
            "guidance_scale": guidance_scale, "seed": seed, "should_enhance": should_enhance}  # fmt: skip
    body = {k: v for k, v in body.items() if v is not None}
    payload = {"voice_design": body}
    if not quote_id:
        estimate = _call("POST", "/v1/voice/design/estimate", json=body)
        return {**estimate, "quote_id": _issue_quote(payload, estimate)}
    _redeem_quote(payload, quote_id, None, False)
    with _quotes_lock:
        voice_quote = _quotes[quote_id]["estimate"].get("voice_quote")
        _quotes.pop(quote_id, None)  # un solo uso: la API ya no aceptaría su voice_quote
    result = _call("POST", "/v1/voice/design", json={**body, "voice_quote": voice_quote})
    dest = _local_path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with _client() as http:
        for i, preview in enumerate(result.get("previews", []), 1):
            response = http.get(preview["preview_url"])
            response.raise_for_status()
            target = dest / f"voz-{i}-{preview['generated_voice_id']}.mp3"
            target.write_bytes(response.content)
            preview["file"] = str(target.resolve())
    return result


@mcp.tool(
    title="Save designed voice",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def save_voice(generated_voice_id: str, name: str, description: str, language: str = "es") -> dict:
    """Guarda en la cuenta de ElevenLabs la muestra elegida de design_voice como voz nueva (gratis; ocupa un
    espacio de voces). description: la misma con que se diseñó. Devuelve voice_id para text_to_speech."""
    body = {"generated_voice_id": generated_voice_id, "name": name, "description": description,
            "language": language}  # fmt: skip
    return _call("POST", "/v1/voice/design/save", json=body)


@mcp.tool(
    title="Delete voice",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
    ),
)
def delete_voice(voice_id: str) -> dict:
    """Borra de la cuenta de ElevenLabs una voz clonada o diseñada y libera su espacio. No se puede deshacer:
    pide confirmación al usuario con el nombre de la voz antes de llamar."""
    return _call("DELETE", f"/v1/voice/voices/{voice_id}")


@mcp.tool(
    title="Use a generation as input",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def use_output(generation_id: str, index: int = 0) -> dict:
    """URL vigente de una salida de una generación terminada (index 0 = la primera), para usarla como
    entrada de otra: fotograma inicial (image_url), referencia (image_urls / video_urls), video a editar o
    extender (video_url), o imagen de un elemento (create_element con image_urls). No gasta créditos."""
    return _call("POST", f"/v1/generations/{generation_id}/outputs/{index}/use")


@mcp.tool(
    title="List elements",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_elements() -> dict:
    """Elementos de HF Studio para Kling 3.0: id (el_…), nombre para citar en el prompt (mention, @nombre),
    descripción y sus imágenes."""
    return _call("GET", "/v1/elements")


@mcp.tool(
    title="Create element",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def create_element(
    name: str,
    description: str,
    paths: list[str] | None = None,
    image_urls: list[str] | None = None,
    category: Literal["character", "location", "prop", "other"] = "other",
) -> dict:
    """Crea un elemento (personaje, lugar o prop, según category) con 1 a 4 imágenes JPG o PNG (Kling 3.0 pide
    2 o más): rutas locales en paths (la primera, de frente) o URLs propias (de upload_media o de una
    generación) en image_urls. name va en minúsculas, sin espacios (letras, dígitos y _), y se cita en el
    prompt con @name. No gasta créditos."""
    files = []
    for path in paths or []:
        file = _local_path(path)
        if not file.is_file():
            raise ToolError(f"No existe el archivo {file}")
        files.append(
            ("files", (file.name, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "image/jpeg"))
        )
    data = {"name": name, "description": description, "image_urls": image_urls or [], "category": category}
    return _call("POST", "/v1/elements", data=data, files=files or None)


@mcp.tool(
    title="Delete element",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def delete_element(element_id: str) -> dict:
    """Borra un elemento y sus imágenes locales. Las generaciones hechas con él no cambian."""
    return _call("DELETE", f"/v1/elements/{element_id}")


@mcp.tool(
    title="List sound library",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_sounds(category: str | None = None, search: str | None = None, limit: int = 50) -> dict:
    """Sonoteca: sonidos de ElevenLabs ya generados (voces, efectos, música, voz aislada), para
    reutilizarlos sin volver a pagar. category: voice, scream, laugh, creature, ambience, impact, foley,
    transition, music u other; search busca en título, texto y etiquetas. Cada uno trae file_url."""
    params = {
        "limit": limit,
        **({"category": category} if category else {}),
        **({"q": search} if search else {}),
    }
    return _call("GET", "/v1/sounds", params=params)


@mcp.tool(
    title="Label sound",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def label_sound(
    sound_id: str, title: str | None = None, category: str | None = None, tags: list[str] | None = None
) -> dict:
    """Corrige el título, la categoría o las etiquetas de un sonido de la sonoteca (gratis)."""
    body = {k: v for k, v in {"title": title, "category": category, "tags": tags}.items() if v is not None}
    return _call("PATCH", f"/v1/sounds/{sound_id}", json=body)


@mcp.tool(
    title="Import ElevenLabs history",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def import_elevenlabs_history() -> dict:
    """Trae a la sonoteca las voces generadas fuera de HF Studio (web de ElevenLabs u otras apps).
    Gratis. La API de ElevenLabs no expone los efectos ni la música de su historial."""
    return _call("POST", "/v1/sounds/import-elevenlabs")


@mcp.tool(
    title="ElevenLabs account",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def elevenlabs_account() -> dict:
    """Estado de ElevenLabs: si está configurado, el plan y los créditos que quedan."""
    return _call("GET", "/v1/voice/status")


@mcp.tool(
    title="Get generation",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def get_generation(generation_id: str, wait_seconds: int = 50) -> dict:
    """Estado de una generación. Espera hasta wait_seconds (máx. 120) a que sea terminal.
    Los videos suelen tardar de 1 a 10 minutos: repite la llamada mientras terminal sea false."""
    wait = max(0, min(wait_seconds, 120))
    return _call("GET", f"/v1/generations/{generation_id}", params={"wait": wait})


@mcp.tool(
    title="List generations",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_generations(status: str | None = None, limit: int = 20) -> dict:
    """Lista tus generaciones recientes (status: pending, queued, in_progress, completed, failed…)."""
    params = {"limit": limit, **({"status": status} if status else {})}
    return _call("GET", "/v1/generations", params=params)


@mcp.tool(
    title="Approve fallback provider (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def approve_fallback(
    generation_id: str,
    max_usd: float | None = None,
    max_reserve_usd: float | None = None,
    accept_unknown_cost: bool = False,
) -> dict:
    """Para una generación en awaiting_approval: el proveedor anterior falló sin cobrar o el precio cambió
    desde la cotización, y la opción actual (`provider`, `cost_usd`) cuesta más de lo aprobado. Dile al
    usuario ese precio y, con su OK, llama con `max_usd` igual a ese precio. HF Studio vuelve a cotizar: si
    ahora cuesta más que max_usd, falla sin gastar, guarda el precio actual y lo devuelve.
    Si la opción tiene `reserve_usd` (retiene más al empezar y devuelve la diferencia), díselo al usuario y
    pásalo en max_reserve_usd. Si el precio es desconocido (cost_usd null) y el usuario acepta
    explícitamente un costo desconocido, pasa accept_unknown_cost=True: sin max_usd queda sin tope; con
    max_usd, ese tope sigue mandando si el precio vuelve a conocerse."""
    body = {
        "max_usd": max_usd,
        "max_reserve_usd": max_reserve_usd,
        "accept_unknown_cost": accept_unknown_cost,
    }
    return _call("POST", f"/v1/generations/{generation_id}/approve", json=body)


@mcp.tool(
    title="Providers status",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def providers_status() -> dict:
    """Proveedores (Higgsfield, APIMart, KIE…): si tienen clave, si es válida, el saldo en USD y los enlaces
    para crear cuenta (signup_url), copiar la clave (key_url) o recargar (billing_url). Con más proveedores
    configurados los videos salen más baratos y hay respaldo si uno falla."""
    return _call("GET", "/v1/providers")


@mcp.tool(
    title="Cancel generation",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
    ),
)
def cancel_generation(generation_id: str) -> dict:
    """Cancela una generación que aún no empezó (pending, queued o awaiting_approval). Lo cancelado
    se reembolsa."""
    return _call("POST", f"/v1/generations/{generation_id}/cancel")


@mcp.tool(
    title="Download outputs",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
    ),
)
def download_outputs(generation_id: str, dest_dir: str = ".") -> dict:
    """Descarga las salidas de una generación completada a dest_dir y devuelve las rutas locales."""
    job = _call("GET", f"/v1/generations/{generation_id}")
    if job["status"] != "completed":
        raise ToolError(f"La generación está en {job['status']}, no en completed")
    dest = Path(dest_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    with _client() as http:
        for i, out in enumerate(job["outputs"]):
            # Preferir la copia propia (no caduca); si no existe, la URL de Higgsfield (≥ 7 días).
            target_url = str(out.get("file_url") or out["url"]).strip()
            if out.get("file_url") and _is_studio_ref(out["file_url"]):
                response = http.get(target_url)
            else:  # URL absoluta del proveedor: sin el token de HF Studio
                parts = urlsplit(target_url)
                if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
                    raise ToolError("Esa salida no tiene una URL válida")
                response = httpx.get(target_url, timeout=150, follow_redirects=True)
            response.raise_for_status()
            suffix = Path(target_url).suffix.split("?")[0] or ".bin"
            target = dest / f"{generation_id[:8]}-{i}-{out['kind']}{suffix}"
            target.write_bytes(response.content)
            saved.append(str(target.resolve()))
    base = os.environ.get("HF_STUDIO_URL", "http://127.0.0.1:8787")
    return {
        "files": saved,
        "remote": [urljoin(base, o["file_url"]) if o.get("file_url") else o["url"] for o in job["outputs"]],
    }


@mcp.tool(
    title="Recommend models",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def recommend_models(task: str, output: str | None = None, limit: int = 5) -> dict:
    """Sugiere modelos para una tarea en lenguaje natural (es/en), p. ej. 'video barato entre dos fotos',
    con el costo de una configuración estándar (5 s, 720p). output opcional: video | image."""
    params = {"task": task, "limit": limit, **({"output": output} if output else {})}
    return _call("GET", "/v1/recommend", params=params)


def _hints(input_video_seconds: float | None, input_audio_seconds: float | None = None) -> dict:
    found = {"input_video_seconds": input_video_seconds, "input_audio_seconds": input_audio_seconds}
    return {k: v for k, v in found.items() if v is not None}


def _complete(estimate: dict) -> bool:
    if "complete" in estimate:
        return bool(estimate["complete"])
    return estimate.get("usd") is not None and not estimate.get("missing")


# Cotizaciones vistas por el usuario, de un solo uso: quote_id → petición, precio, vencimiento y clave usada.
QUOTE_TTL = 15 * 60
_quotes: dict[str, dict] = {}
# Las herramientas síncronas corren en hilos: emitir y canjear cotizaciones debe ser atómico.
_quotes_lock = threading.Lock()


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _issue_quote(payload: dict, estimate: dict, key: str | None = None) -> str:
    """`key`: la cotización queda ligada a esa Idempotency-Key (recuperar un lote a medias con su clave)."""
    with _quotes_lock:
        now = time.monotonic()
        for qid in [q for q, v in _quotes.items() if v["expires"] < now]:
            del _quotes[qid]
        qid = "q_" + uuid.uuid4().hex[:16]
        _quotes[qid] = {
            "request": _fingerprint(payload),
            "estimate": estimate,
            "expires": now + QUOTE_TTL,
            "key": key,
        }
        return qid


def _redeem_quote(
    payload: dict, quote_id: str | None, idempotency_key: str | None, confirm_unknown_cost: bool
) -> str:
    return _authorize(payload, quote_id, idempotency_key, confirm_unknown_cost)[0]


def _authorize(
    payload: dict, quote_id: str | None, idempotency_key: str | None, confirm_unknown_cost: bool
) -> tuple[str, dict]:
    """Regla del dueño: no se gasta sin que el usuario haya visto el precio de esta misma petición.
    Cada cotización sirve para una sola ejecución; reintentar con la misma clave no vuelve a cobrar.
    Devuelve, leídas bajo el mismo lock, la clave de idempotencia y una copia de lo aprobado: `usd` (tope de
    precio, None solo si el usuario aceptó explícitamente un costo desconocido) y `reserve_usd` (retención
    inicial vista). Así una limpieza concurrente de cotizaciones no puede quitar el tope (revisión 29)."""
    with _quotes_lock:
        q = _quotes.get(quote_id or "")
        if not q or q["expires"] < time.monotonic() or q["request"] != _fingerprint(payload):
            raise ToolError(
                "Missing, expired or mismatched quote_id. Quote this exact request first (dry_run / estimate_cost), "
                "show the cost to the user, and call again with the returned quote_id once they agree."
            )
        if not _complete(q["estimate"]) and not confirm_unknown_cost:
            missing = ", ".join(q["estimate"].get("missing") or []) or "price not available"
            raise ToolError(
                f"No complete price for this request ({missing}). Pass input_video_seconds (or input_audio_seconds) "
                "with the real length of the input media, or tell the user the cost is unknown and, only if they explicitly accept, "
                "retry with confirm_unknown_cost=True."
            )
        key = idempotency_key or q["key"] or f"quote-{quote_id}"
        if q["key"] and key != q["key"]:
            raise ToolError(
                "This quote_id was already used. To retry the same run, reuse its idempotency_key; "
                "for a new run, quote again and get the user's OK."
            )
        q["key"] = key
        estimate = dict(q["estimate"])
        complete = _complete(estimate)
        # La retención vista se aprueba siempre por separado, también con un precio desconocido aceptado.
        approved = {"usd": estimate.get("usd") if complete else None, "reserve_usd": estimate.get("reserve_usd"),
                    "accept_unknown_cost": not complete}  # fmt: skip
        return key, approved


@mcp.tool(
    title="Generate batch (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def generate_batch(
    items: list[dict],
    dry_run: bool = True,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
    input_video_seconds: float | None = None,
    confirm_unknown_cost: bool = False,
) -> dict:
    """Varias generaciones de una vez. items: [{model, input, count, hints}] (count = variantes, máx. 8;
    hints opcional por ítem, p. ej. {"input_video_seconds": 12} si cada ítem usa un video distinto).
    input_video_seconds aplica a todos los ítems: úsalo solo si comparten el mismo video.
    1) dry_run=True devuelve el costo por ítem, el total y quote_id: muéstraselo al usuario.
    2) Con su OK, dry_run=False con el mismo lote y ese quote_id (y la misma idempotency_key si reintentas).
    Si un lote falla a medias (p. ej. sin cupos) o cambió su precio, recotiza con dry_run=True y la MISMA
    idempotency_key (por defecto quote-<quote_id> del primer intento): el total cuenta lo ya creado con su costo de
    entonces, y esa cotización solo vale con esa clave; con otra clave se crearía otro lote.
    Sin total completo se rechaza salvo confirm_unknown_cost=True (solo si el usuario acepta un costo desconocido)."""
    payload = {"items": items, "hints": _hints(input_video_seconds)}
    if dry_run:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        quote = _call("POST", "/v1/generations/batch", json={**payload, "dry_run": True}, headers=headers)
        return {**quote, "quote_id": _issue_quote(payload, quote["total"], idempotency_key)}
    key, approved = _authorize(payload, quote_id, idempotency_key, confirm_unknown_cost)
    headers = {"Idempotency-Key": key}
    body = {**payload, "dry_run": False, "max_total_usd": approved["usd"],
            "max_total_reserve_usd": approved["reserve_usd"], "accept_unknown_cost": approved["accept_unknown_cost"]}  # fmt: skip
    return _call("POST", "/v1/generations/batch", json=body, headers=headers)


@mcp.tool(
    title="Wait for generations",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def wait_generations(generation_ids: list[str], wait_seconds: int = 60) -> dict:
    """Espera hasta wait_seconds (máx. 120) a que terminen varias generaciones y devuelve su estado.
    Repite mientras all_terminal sea false."""
    params = {"ids": ",".join(generation_ids), "wait": max(0, min(wait_seconds, 120)), "limit": 100}
    return _call("GET", "/v1/generations", params=params)


@mcp.tool(
    title="List presets",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_presets() -> dict:
    """Recetas disponibles (de serie y propias): slug, modelo, variables que piden y salida."""
    presets = _call("GET", "/v1/presets")["presets"]
    return {
        "presets": [
            {
                k: p[k]
                for k in (
                    "slug",
                    "title",
                    "description",
                    "category",
                    "output",
                    "model",
                    "variables",
                    "builtin",
                )
            }
            for p in presets
        ]
    }


@mcp.tool(
    title="Run preset (spends credits)",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def run_preset(
    slug: str,
    variables: dict,
    dry_run: bool = True,
    quote_id: str | None = None,
    idempotency_key: str | None = None,
    input_video_seconds: float | None = None,
    confirm_unknown_cost: bool = False,
) -> dict:
    """Ejecuta un preset. Variables de medios (image/images/video) llevan URLs públicas (usa upload_media).
    1) dry_run=True devuelve la entrada final, el costo y quote_id: muéstraselo al usuario.
    2) Con su OK, dry_run=False con las mismas variables y ese quote_id. Si el preset usa un video, pasa
    input_video_seconds. Sin precio completo se rechaza salvo confirm_unknown_cost=True."""
    payload = {"slug": slug, "variables": variables, "hints": _hints(input_video_seconds)}
    body = {"variables": variables, "hints": payload["hints"]}
    if dry_run:
        quote = _call("POST", f"/v1/presets/{slug}/run", json={**body, "dry_run": True})
        return {**quote, "quote_id": _issue_quote(payload, quote["estimate"])}
    key, approved = _authorize(payload, quote_id, idempotency_key, confirm_unknown_cost)
    headers = {"Idempotency-Key": key}
    body = {**body, "dry_run": False, "max_usd": approved["usd"], "max_reserve_usd": approved["reserve_usd"],
            "accept_unknown_cost": approved["accept_unknown_cost"]}  # fmt: skip
    return _call("POST", f"/v1/presets/{slug}/run", json=body, headers=headers)


@mcp.tool(
    title="Save preset",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),
)
def save_preset(generation_id: str, slug: str, title: str, description: str = "") -> dict:
    """Guarda una generación como preset propio: mismos ajustes y medios, con el prompt como variable."""
    body = {"slug": slug, "title": title, "description": description}
    return _call("POST", f"/v1/presets/from-generation/{generation_id}", json=body)


# --- Spaces --------------------------------------------------------------------------------------


@mcp.tool(
    title="List spaces",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_spaces() -> dict:
    """Lienzos de nodos (Spaces) del cliente: id, título, versión, número de nodos y fechas."""
    return _call("GET", "/v1/spaces")


@mcp.tool(
    title="Get space",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def get_space(space_id: str) -> dict:
    """Un lienzo con su grafo completo (nodes, edges) y su `version` (la necesitan update_space y las corridas)."""
    return _call("GET", f"/v1/spaces/{space_id}")


@mcp.tool(
    title="Create space",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),
)
def create_space(title: str, nodes: list[dict] | None = None, edges: list[dict] | None = None) -> dict:
    """Crea un lienzo de nodos (no genera nada ni gasta). El usuario lo ve en la UI, en /spaces.
    nodes: [{id, type, position: {x, y}, data}] con type text (data.text), media (data.url de upload_media o
    use_output, data.kind image|video|audio), note (data.text), list (data.kind text|image|video|audio,
    data.items = [{id, value, checked}], hasta 20: textos o URLs propias; el generador conectado corre una vez
    por elemento marcado; una lista de texto puede llenarla un claude/assistant con values.list_items = N,
    conectándolo a ella con targetHandle "items") o generator (data.model = id del catálogo,
    data.values = ajustes de su input_schema, p. ej. {"prompt": "…", "duration": 5}; data.count de 1 a 4 lo
    repite como variantes). edges: [{id, source, target, targetHandle, sourceHandle?}]: targetHandle es la
    clave del campo de entrada del generador destino (prompt, image_url, end_image_url, image_urls, video_url,
    video_urls, audio_urls…) y el tipo debe encajar (texto → prompt, imagen → campos de imagen…). De un
    generador de video, sourceHandle "last_frame" lleva su último fotograma (imagen) y "audio" su pista de
    audio; sin él, va la salida principal. Sin ciclos."""
    graph = {"nodes": nodes or [], "edges": edges or []}
    return _call("POST", "/v1/spaces", json={"title": title, "graph": graph})


def _keep_runs(nodes: list[dict], current: list[dict]) -> list[dict]:
    """Un generador que sigue en el lienzo conserva sus generaciones (`runs`, `selected`) si el agente no las
    pasa: reescribir un prompt no debe borrar lo que el usuario ya generó en la UI."""
    before = {n.get("id"): n.get("data") or {} for n in current if n.get("type") == "generator"}
    out = []
    for n in nodes:
        old = before.get(n.get("id"))
        data = n.get("data") or {}
        if n.get("type") == "generator" and old and "runs" not in data and old.get("runs"):
            kept = {"runs": old["runs"], **({"selected": old["selected"]} if "selected" in old else {})}
            n = {**n, "data": {**data, **kept}}
        out.append(n)
    return out


@mcp.tool(
    title="Update space",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
    ),
)
def update_space(
    space_id: str,
    version: int,
    title: str | None = None,
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
    flow: dict | None = None,
    unpublish: bool = False,
) -> dict:
    """Reemplaza el título o el grafo de un lienzo (no gasta). `version` es la de get_space: si alguien guardó
    antes, responde 409 y hay que volver a leerlo. Pasa nodes y edges completos (sustituyen a los anteriores);
    un generador que ya existía conserva sus generaciones (runs) si no las pasas. La UI abierta se actualiza sola.
    flow publica el lienzo como formulario simple en /flows/<id>: {title, description, inputs: [{node_id,
    label}]}, hasta 10 entradas, cada una un nodo de texto, medio o lista que se pide al correrlo (run_space
    con inputs). unpublish=True lo retira."""
    body: dict[str, Any] = {"version": version}
    if title is not None:
        body["title"] = title
    if unpublish:
        body["flow"] = None
    elif flow is not None:
        body["flow"] = flow
    if nodes is not None or edges is not None:
        current = _call("GET", f"/v1/spaces/{space_id}")["graph"]
        body["graph"] = {**current, "nodes": _keep_runs(nodes, current["nodes"]) if nodes is not None
                         else current["nodes"], "edges": edges if edges is not None else current["edges"]}  # fmt: skip
    return _call("PUT", f"/v1/spaces/{space_id}", json=body)


def _run_payload(
    space_id: str, mode: str, node_id: str | None, version: int, inputs: dict | None = None
) -> dict:
    if mode not in ("workflow", "downstream"):
        raise ToolError(
            "mode must be workflow (todo el lienzo) or downstream (un nodo y lo que depende de él)"
        )
    return {"space_id": space_id, "mode": mode, "node_id": node_id, "version": version, "inputs": inputs}


@mcp.tool(
    title="Estimate space run",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def estimate_space_run(
    space_id: str, mode: str = "workflow", node_id: str | None = None, inputs: dict | None = None
) -> dict:
    """Precio de correr un lienzo en el servidor, sin gastar: cada paso (`steps`, status ok, unknown, later si se
    cotiza al llegar o error) y `total_usd`. mode workflow = todo; downstream = node_id y lo que depende de él.
    Devuelve quote_id: dile al usuario el total (y que los pasos `later` se cotizan al llegar: si no caben en
    el tope, la corrida se pausa para preguntarle) y pásalo a run_space. No gasta, pero para cotizar puede
    subir a Higgsfield (gratis) las salidas previas que el lienzo usa como entrada y registrarlas.
    Un Space publicado como flujo (su `flow` en list_spaces) se corre con `inputs`: {node_id de cada entrada:
    texto, URL de upload_media/use_output o lista de textos/URLs}; el lienzo no cambia."""
    version = _call("GET", f"/v1/spaces/{space_id}")["version"]
    payload = _run_payload(space_id, mode, node_id, version, inputs)
    body = {"mode": mode, "version": version, "dry_run": True, **({"node_id": node_id} if node_id else {}),
            **({"inputs": inputs} if inputs is not None else {})}  # fmt: skip
    quote = _call("POST", f"/v1/spaces/{space_id}/runs", json=body)
    estimate = {"usd": quote["total_usd"], "reserve_usd": None, "complete": True, "missing": []}
    return {**quote, "version": version, "quote_id": _issue_quote(payload, estimate)}


@mcp.tool(
    title="Run space (spends credits)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def run_space(
    space_id: str,
    quote_id: str,
    mode: str = "workflow",
    node_id: str | None = None,
    version: int | None = None,
    max_total_usd: float | None = None,
    idempotency_key: str | None = None,
    inputs: dict | None = None,
) -> dict:
    """Arranca la corrida cotizada con estimate_space_run (mismos space_id, mode, node_id e inputs; version es
    la que devolvió). El tope es el total que vio el usuario; max_total_usd solo si el usuario aprobó explícitamente
    un tope mayor (para cubrir pasos que se cotizan al llegar). No espera: usa get_space_run.
    Tras un error ambiguo, repite con el mismo quote_id (y la misma idempotency_key si pasaste una): devuelve
    la misma corrida, nunca arranca otra ni paga dos veces."""
    if version is None:
        raise ToolError("Pass the version returned by estimate_space_run")
    payload = _run_payload(space_id, mode, node_id, version, inputs)
    # La clave queda ligada a la cotización: repetir run_space con el mismo quote_id (p. ej. tras un error
    # ambiguo) devuelve la misma corrida en vez de arrancar otra (revisión 64).
    key, approved = _authorize(payload, quote_id, idempotency_key, False)
    budget = approved["usd"] or 0.0
    if max_total_usd is not None:
        if max_total_usd + 1e-9 < budget:
            raise ToolError(f"max_total_usd cannot be lower than the quoted total ({budget})")
        budget = max_total_usd
    body = {
        "mode": mode,
        "version": version,
        "max_total_usd": budget,
        **({"node_id": node_id} if node_id else {}),
        **({"inputs": inputs} if inputs is not None else {}),
    }
    return _call("POST", f"/v1/spaces/{space_id}/runs", json=body, headers={"Idempotency-Key": key})


@mcp.tool(
    title="Get space run",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def get_space_run(space_id: str, run_id: str | None = None) -> dict:
    """Estado de una corrida (o de las últimas, sin run_id): status, nodes (estado y job_id de cada paso),
    committed_usd, max_total_usd y pause (motivo y needed_total_usd si espera aprobación)."""
    if run_id:
        return _call("GET", f"/v1/spaces/{space_id}/runs/{run_id}")
    return _call("GET", f"/v1/spaces/{space_id}/runs", params={"limit": 5})


@mcp.tool(
    title="Approve space run (spends credits)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def approve_space_run(
    space_id: str, run_id: str, max_total_usd: float | None = None, accept_unknown_cost: bool = False
) -> dict:
    """Reanuda una corrida en awaiting_approval, solo con el OK del usuario: max_total_usd = el nuevo total
    que aprobó (pause.needed_total_usd o más); accept_unknown_cost=True solo si aceptó un paso sin precio (vale
    también para los pasos sin precio que faltan de esa corrida: díselo al usuario)."""
    body: dict[str, Any] = {"accept_unknown": accept_unknown_cost}
    if max_total_usd is not None:
        body["max_total_usd"] = max_total_usd
    return _call("POST", f"/v1/spaces/{space_id}/runs/{run_id}/approve", json=body)


@mcp.tool(
    title="Cancel space run",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def cancel_space_run(space_id: str, run_id: str) -> dict:
    """Detiene una corrida: no envía más pasos y cancela los que aún no cuestan; lo terminado se conserva."""
    return _call("POST", f"/v1/spaces/{space_id}/runs/{run_id}/cancel")


# --- Tarjeta de generación (MCP Apps) ------------------------------------------------------------

PREVIEW_MAX_BYTES = 20 * 1024 * 1024  # lo que la tarjeta recibe en base64 si la URL del medio no carga


@mcp.tool(
    title="Show generations",
    meta=UI_META,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def show_generations(generation_ids: list[str]) -> dict:
    """Muestra generaciones ya lanzadas en una tarjeta del chat (en los clientes con widgets, como Claude
    Desktop): su estado, que se actualiza solo, y al terminar el video, la imagen o el audio. Úsala cuando el
    usuario quiera ver resultados de antes o de otra conversación. No la llames para lo que lanzaste en esta
    conversación con generate, generate_batch, run_preset o el audio: su tarjeta ya lo muestra y saldría
    repetido. No espera; devuelve el estado actual."""
    if not generation_ids:
        raise ToolError("Pasa al menos un generation_id")
    params = {"ids": ",".join(generation_ids[:20]), "wait": 0, "limit": 100}
    return _call("GET", "/v1/generations", params=params)


def _fetch_capped(http: httpx.Client, url: str) -> tuple[bytes, str]:
    """Descarga hasta PREVIEW_MAX_BYTES; más grande, falla sin cargarlo entero en memoria."""
    with http.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        size = int(response.headers.get("content-length") or 0)
        if size > PREVIEW_MAX_BYTES:
            raise ToolError("El archivo es muy grande para mostrarlo en el chat; ábrelo en HF Studio")
        chunks, total = [], 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > PREVIEW_MAX_BYTES:
                raise ToolError("El archivo es muy grande para mostrarlo en el chat; ábrelo en HF Studio")
            chunks.append(chunk)
        return b"".join(chunks), response.headers.get("content-type", "").split(";")[0]


@mcp.tool(
    title="Generation preview (widget only)",
    meta={"ui": {"visibility": ["app"]}},
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def generation_preview(generation_id: str, index: int = 0) -> dict:
    """Uso interno de la tarjeta de generación: devuelve una salida en base64 (máx. 20 MB) cuando su URL no
    carga en el chat. No la uses para descargar: para eso está download_outputs."""
    job = _call("GET", f"/v1/generations/{generation_id}")
    outputs = job.get("outputs") or []
    if job.get("status") != "completed" or not 0 <= index < len(outputs):
        raise ToolError("Esa salida no existe o la generación no ha terminado")
    out = outputs[index]
    # La copia local primero (no caduca); si no hay, la URL del proveedor.
    target = str(out.get("file_url") or out.get("url") or "").strip()
    try:
        if _is_studio_ref(target):
            with _client() as http:
                data, mime = _fetch_capped(http, target)
        else:  # absoluta (https://, HTTPS://, //host…): nunca con el token de HF Studio
            parts = urlsplit(target)
            if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
                raise ToolError("Esa salida no tiene una URL válida")
            with httpx.Client(timeout=150) as remote:
                data, mime = _fetch_capped(remote, target)
    except httpx.HTTPError as exc:
        raise ToolError(f"No se pudo leer la salida: {exc}") from exc
    if not mime or mime == "application/octet-stream":
        guessed = mimetypes.guess_type(str(out.get("file_url") or out.get("url") or ""))[0]
        mime = guessed or {"video": "video/mp4", "audio": "audio/mpeg"}.get(out.get("kind"), "image/png")
    return {"mime_type": mime, "bytes": len(data), "data_base64": base64.b64encode(data).decode()}


# --- Biblioteca: favoritas, ocultas, borrar y aprobaciones pendientes --------------------------------


@mcp.tool(
    title="Favorite generations",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def favorite_generations(generation_ids: list[str], favorite: bool = True) -> dict:
    """Marca (o desmarca con favorite=False) generaciones como favoritas en la biblioteca de HF Studio."""
    return _call("POST", "/v1/generations/favorite", json={"ids": generation_ids, "favorite": favorite})


@mcp.tool(
    title="Hide generations",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def hide_generations(generation_ids: list[str], hidden: bool = True) -> dict:
    """Oculta (o vuelve a mostrar con hidden=False) generaciones terminadas del historial y los listados.
    Siguen accesibles por su id; no borra nada."""
    return _call("POST", "/v1/generations/hide", json={"ids": generation_ids, "hidden": hidden})


@mcp.tool(
    title="Delete generation",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def delete_generation(generation_id: str) -> dict:
    """Borra una generación terminada del historial y su copia local (y su sonido de la sonoteca). No se
    puede deshacer: confirma con el usuario antes. Si solo quiere quitarla de la vista, usa hide_generations."""
    return _call("DELETE", f"/v1/generations/{generation_id}")


@mcp.tool(
    title="List pending approvals",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_approvals(limit: int = 50) -> dict:
    """Generaciones que esperan la aprobación del usuario (cambió el precio, la retención o el proveedor). Las
    de una corrida de Spaces traen space_run: se aprueban con approve_space_run, no con approve_fallback."""
    return _call("GET", "/v1/approvals", params={"limit": max(1, min(limit, 100))})


@mcp.tool(
    title="List uploads",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def list_uploads(limit: int = 50) -> dict:
    """Archivos que ya subiste con upload_media (o desde la app), con su URL pública para reutilizarlos."""
    return _call("GET", "/v1/uploads", params={"limit": max(1, min(limit, 200))})


@mcp.tool(
    title="Usage and spend",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def get_usage(days: int = 30) -> dict:
    """Gasto de las generaciones terminadas por día, proveedor y modelo en los últimos `days` días (0 = todo
    el historial), como la página /usage. Es el precio cotizado, no el cobro conciliado con el proveedor."""
    offset = (time.localtime().tm_gmtoff or 0) // 60
    return _call("GET", "/v1/usage", params={"days": max(0, min(days, 3650)), "utc_offset": offset})


# --- Voces gratis (edge-tts) ------------------------------------------------------------------------


@mcp.tool(
    title="List free voices",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def list_free_voices(lang: str = "es") -> dict:
    """Voces neuronales gratis (Microsoft Edge, sin clave ni créditos) de un idioma; Colombia primero en
    español. Su voice_id sirve en free_text_to_speech."""
    return _call("GET", "/v1/voice/free-voices", params={"lang": lang})


@mcp.tool(
    title="Free text to speech",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
    ),
)
def free_text_to_speech(text: str, voice_id: str, rate: str = "+0%", dest_dir: str = ".") -> dict:
    """Locución gratis con una voz de list_free_voices (hasta 300 caracteres; rate de -20% a +30%). Guarda
    el MP3 en dest_dir y devuelve su ruta. No gasta créditos; para voces de ElevenLabs usa text_to_speech."""
    params = {"voice": voice_id, "text": text, "rate": rate}
    try:
        with _client() as http:
            response = http.get("/v1/voice/free-sample", params=params)
    except httpx.TransportError as exc:
        raise ToolError(f"HF Studio no responde ({exc}); ¿está corriendo `hf-studio serve`?") from exc
    if not response.is_success:
        try:
            error = response.json().get("error") or response.json()
        except ValueError:
            error = response.text
        raise ToolError(f"HTTP {response.status_code}: {error}")
    dest = _local_path(dest_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{voice_id}|{rate}|{text}".encode()).hexdigest()[:10]
    target = dest / f"{voice_id}-{key}.mp3"
    target.write_bytes(response.content)
    return {"file": str(target.resolve()), "bytes": len(response.content), "voice_id": voice_id}


# --- Borrar presets y Spaces -------------------------------------------------------------------------


@mcp.tool(
    title="Delete preset",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def delete_preset(slug: str) -> dict:
    """Borra un preset propio (los incluidos de fábrica no se borran). Confirma con el usuario antes."""
    return _call("DELETE", f"/v1/presets/{slug}")


@mcp.tool(
    title="Delete space",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def delete_space(space_id: str) -> dict:
    """Borra un lienzo de Spaces y sus corridas; sus generaciones siguen en el historial. Confirma antes."""
    return _call("DELETE", f"/v1/spaces/{space_id}")


@mcp.tool(
    title="Create Katana remix (analyze reference)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def katana_create(reference_url: str, title: str | None = None) -> dict:
    """Katana (remix de un edit de referencia con el sujeto del usuario), paso 1: copia la referencia (URL de
    upload_media o de una generación propia, o el video_url de un preset de katana_presets) y la analiza gratis en
    local: cortes, destellos, sacudidas, movimientos de cámara, golpes de audio, tempo y hojas de contacto. Devuelve
    el proyecto con `analysis`; sigue con katana_plan."""
    return _call("POST", "/v1/katana/projects", json={"reference_url": reference_url, "title": title})


@mcp.tool(
    title="List Katana presets",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),
)
def katana_presets(lang: Literal["es", "en"] = "es") -> dict:
    """La galería de Katana de higgsfield.ai (la lee de su CMS público): categorías y presets de la comunidad con
    descripción y autor. El video_url de un preset sirve de referencia en katana_create; su description se puede
    pasar como preset_context a katana_plan."""
    return _call("GET", "/v1/katana/presets", params={"lang": lang})


@mcp.tool(
    title="Get Katana remix",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def katana_get(project_id: str | None = None) -> dict:
    """Un proyecto de Katana (análisis, plan y space_id), o la lista si no se pasa project_id."""
    if project_id:
        return _call("GET", f"/v1/katana/projects/{project_id}")
    return _call("GET", "/v1/katana/projects")


@mcp.tool(
    title="Plan Katana remix (spends credits)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
def katana_plan(
    project_id: str,
    subject_urls: list[str],
    brief: str = "",
    aspect: str | None = None,
    duration: float | None = None,
    resolution: str = "720p",
    max_clips: int = 3,
    max_video_seconds: int = 30,
    music: str = "reference",
    language: str = "es",
    preset_context: str | None = None,
    max_usd: float | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Katana, paso 2: Claude escribe el plan del remix (concepto, placas de lugar, fotograma clave, clips de
    Seedance 2.5 y el EDL con la energía medida) y se crea un Space que lo produce, terminado en hf-studio/katana-edit.
    subject_urls: fotos del sujeto (upload_media). Sin max_usd solo cotiza (no gasta): dile al usuario el max_usd
    (tokens de Claude) y, con su OK, repite con ese max_usd. Planear no genera video: después
    estimate_space_run(space_id) y, con el OK del usuario sobre ese total, run_space. preset_context: la
    description del preset de katana_presets, si la referencia es uno. Reintenta con la misma idempotency_key: no
    vuelve a cobrar (409 si cambia el encargo)."""
    body = {"subject_urls": subject_urls, "brief": brief, "aspect": aspect, "duration": duration,
            "resolution": resolution, "max_clips": max_clips, "max_video_seconds": max_video_seconds,
            "music": music, "language": language, "preset_context": preset_context}  # fmt: skip
    if max_usd is None:
        return _call("POST", f"/v1/katana/projects/{project_id}/plan/estimate", json=body)
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return _call(
        "POST", f"/v1/katana/projects/{project_id}/plan", json={**body, "max_usd": max_usd}, headers=headers
    )


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
