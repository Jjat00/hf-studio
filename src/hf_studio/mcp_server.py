"""Servidor MCP (stdio) que expone HF Studio a Claude Code, Codex y otros agentes.

Es un cliente delgado de la API REST: no conoce las credenciales de Higgsfield, solo
HF_STUDIO_URL y HF_STUDIO_TOKEN (una clave `hfs_…` creada con `hf-studio create-key`).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

INSTRUCTIONS = """Genera imágenes y videos con los modelos de Higgsfield a través de HF Studio.
Proveedores: el mismo modelo puede salir por Higgsfield, APIMart o KIE. estimate_cost cotiza todos los que
tengan clave y elige el más barato (options trae cada precio, excluded el motivo de los descartados y
savings_vs_higgsfield el ahorro); generate envía al más barato. Si ese proveedor falla sin cobrar, HF Studio
prueba el siguiente: solo si cuesta lo mismo o menos; si cuesta más (o el precio cambió desde la
cotización), la generación queda en awaiting_approval: dile al usuario el nuevo precio (cost_usd) y, con su
OK, approve_fallback (o cancel_generation). reserve_usd en una opción es lo que el proveedor retiene al
empezar (devuelve la diferencia al terminar): menciónaselo al usuario.
provider="kie" (u otro) en estimate_cost y generate fuerza uno. providers_status muestra claves, saldos y
los enlaces para crear cuenta o recargar.
Atajos: recommend_models("lo que quiere el usuario") sugiere modelos con su costo; list_presets y
run_preset ejecutan recetas listas (primero con dry_run=True para mostrar costo y entrada final);
generate_batch hace variantes (primero dry_run=True) y wait_generations espera varias.
Flujo manual: 1) find_models por capacidad (text-to-video, image-to-video, first-last-frame, video-input,
reference-to-video, image-references, video-edit, video-extend, motion-transfer, text-to-image);
2) get_model para leer input_schema y notes; 3) upload_media si la entrada es un archivo local;
4) estimate_cost; 5) generate con su quote_id; 6) get_generation con wait_seconds hasta terminal=true;
7) download_outputs. La generación es asíncrona y cobra créditos: ANTES de generar, cotiza (estimate_cost,
o dry_run en lotes y presets), dile al usuario el costo y espera su OK (kind exact = créditos y USD;
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
Al generar audio, pasa title, category (voice, scream, laugh, creature, ambience, impact, foley, transition,
music, other) y tags para que quede bien ordenado en la sonoteca. Antes de generar un sonido, busca en
list_sounds si ya existe uno que sirva: reutilizarlo es gratis.
Elementos (Kling 3.0): personajes, productos o lugares reutilizables con nombre, descripción y 2 a 4 imágenes
JPG/PNG. create_element los guarda; list_elements los muestra. Para usarlos, pon sus ids (el_…) en el campo
elements de un modelo Kling 3.0 y cítalos en el prompt con @nombre (p. ej. "@zorro corre por la nieve").
Solo salen por APIMart y KIE (KIE además exige image_url); nunca por Higgsfield.
Para partir de una creación anterior (animar una imagen, usarla de referencia, editar o extender un video),
use_output(generation_id) da su URL vigente; no reutilices URLs viejas de outputs, pueden haber caducado.
Spaces (lienzos de nodos): list_spaces, get_space, create_space y update_space leen y arman un lienzo; cada
nodo es texto, medio, nota, lista o generador (cualquier modelo del catálogo, incluidas las herramientas
gratis hf-studio/frame, hf-studio/combine y hf-studio/mix, el audio elevenlabs/tts, elevenlabs/sfx y
elevenlabs/music-gen, y claude/assistant, que escribe texto para el prompt de otros nodos si hay
ANTHROPIC_API_KEY). Una arista lleva la salida de un nodo a un campo de entrada de otro (targetHandle = clave
del input_schema: prompt, image_url, video_url, audio_urls…). Una lista hace que el generador conectado corra
una vez por elemento, y el lote baja en pares por la cadena; data.count (variantes) hace lo mismo con una sola
entrada. update_space con flow publica el lienzo como formulario simple (/flows/<id>) y run_space lo corre
con inputs. Para correrlo en el servidor:
estimate_space_run (precio de cada paso y total, con quote_id) → dile al usuario el total y espera su OK →
run_space con ese quote_id (si falla de forma ambigua, repítelo con el mismo quote_id: devuelve la misma
corrida) → get_space_run hasta que termine. Si la corrida queda en awaiting_approval (un
paso no cabe en el tope, no tiene precio o su respaldo cuesta más), dile el motivo y el nuevo total
(pause.needed_total_usd) y, con su OK, approve_space_run; cancel_space_run la detiene."""

mcp = MCPServer("hf-studio", instructions=INSTRUCTIONS)
# Cada herramienta declara las cuatro pistas para que el cliente avise antes de invocarla: solo lectura
# (catálogo, biblioteca, estados), gasta créditos (siempre tras una cotización que vio el usuario, título
# «spends credits»), o modifica algo (cancelar, etiquetar, escribir archivos). estimate_cost cuenta como
# solo lectura: no gasta ni toca la base, aunque emite un quote_id en memoria (15 min, un solo uso).
# list_sounds no lo es: antes de listar registra en la sonoteca los audios terminados que falten.


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
    object-swap, text-to-image, edit. output: video | image. query: texto en id/título (p. ej. seedance)."""
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
    model_id: str, input: dict, input_video_seconds: float | None = None, provider: str | None = None
) -> dict:
    """Costo de una generación sin ejecutarla, en cada proveedor (el más barato primero: `provider`, `usd`;
    todas en `options`). Funciona aunque falten los medios. Si el modelo cobra por segundos de video de
    entrada, pasa input_video_seconds (o sube el video antes: HF Studio lo mide). `provider` cotiza solo
    ese. Devuelve quote_id: muéstrale el costo al usuario y pásalo a generate con los mismos parámetros."""
    payload = {"model": model_id, "input": input, "hints": _hints(input_video_seconds), "provider": provider}
    estimate = _call("POST", "/v1/estimate", json=payload)
    return {**estimate, "quote_id": _issue_quote(payload, estimate)}


@mcp.tool(
    title="Generate (spends credits)",
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
) -> dict:
    """Encola una generación en el proveedor más barato de la cotización (o en `provider`, el mismo que
    se pasó a estimate_cost) y devuelve el trabajo (id, status, provider). No espera: usa get_generation.
    Requiere el quote_id de estimate_cost con los mismos model_id, input e input_video_seconds (el
    usuario debe haber visto ese costo). Si reintentas tras un fallo de red, pasa la misma idempotency_key.
    Al editar un video (entrada video_url), generate_audio=false da un video MUDO, no conserva el sonido
    original; para conservarlo pasa keep_source_audio=true (gratis: HF Studio le pone el audio del
    video de origen al resultado). Lee studio_notes en get_model."""
    payload = {"model": model_id, "input": input, "hints": _hints(input_video_seconds), "provider": provider}
    key, approved = _authorize(payload, quote_id, idempotency_key, confirm_unknown_cost)
    headers = {"Idempotency-Key": key}
    body = {
        "model": model_id,
        "input": input,
        "allow_duplicate": allow_duplicate,
        "keep_source_audio": keep_source_audio,
        "hints": _hints(input_video_seconds),
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
    name: str, description: str, paths: list[str] | None = None, image_urls: list[str] | None = None
) -> dict:
    """Crea un elemento (personaje, producto o lugar) con 2 a 4 imágenes JPG o PNG: rutas locales en paths
    (la primera, de frente) o URLs propias (de upload_media o de una generación) en image_urls. name va en
    minúsculas, sin espacios (letras, dígitos y _), y se cita en el prompt con @name. No gasta créditos."""
    files = []
    for path in paths or []:
        file = _local_path(path)
        if not file.is_file():
            raise ToolError(f"No existe el archivo {file}")
        files.append(
            ("files", (file.name, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "image/jpeg"))
        )
    data = {"name": name, "description": description, "image_urls": image_urls or []}
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
            if out.get("file_url"):
                response = http.get(out["file_url"])
            else:
                response = httpx.get(out["url"], timeout=150, follow_redirects=True)
            response.raise_for_status()
            suffix = Path(out.get("file_url") or out["url"]).suffix.split("?")[0] or ".bin"
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


def _hints(input_video_seconds: float | None) -> dict:
    return {"input_video_seconds": input_video_seconds} if input_video_seconds is not None else {}


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
                f"No complete price for this request ({missing}). Pass input_video_seconds with the real length "
                "of the input video, or tell the user the cost is unknown and, only if they explicitly accept, "
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
    por elemento marcado) o generator (data.model = id del catálogo,
    data.values = ajustes de su input_schema, p. ej. {"prompt": "…", "duration": 5}; data.count de 1 a 4 lo
    repite como variantes). edges: [{id, source, target, targetHandle, sourceHandle?}]: targetHandle es la
    clave del campo de entrada del generador destino (prompt, image_url, end_image_url, image_urls, video_url,
    video_urls, audio_urls…) y el tipo debe encajar (texto → prompt, imagen → campos de imagen…). De un
    generador de video, sourceHandle "last_frame" lleva su último fotograma (imagen) y "audio" su pista de
    audio; sin él, va la salida principal. Sin ciclos."""
    graph = {"nodes": nodes or [], "edges": edges or []}
    return _call("POST", "/v1/spaces", json={"title": title, "graph": graph})


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
    antes, responde 409 y hay que volver a leerlo. Pasa nodes y edges completos (sustituyen a los anteriores).
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
        body["graph"] = {**current, "nodes": nodes if nodes is not None else current["nodes"],
                         "edges": edges if edges is not None else current["edges"]}  # fmt: skip
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
    que aprobó (pause.needed_total_usd o más); accept_unknown_cost=True solo si aceptó un paso sin precio."""
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


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
