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

INSTRUCTIONS = """Genera imágenes y videos con los modelos de Higgsfield a través de HF Studio.
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
luego con el quote_id tras el OK del usuario; el resultado es una generación más (get_generation)."""

mcp = MCPServer("hf-studio", instructions=INSTRUCTIONS)


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
        return response.json()
    try:
        error = response.json().get("error") or response.json()
    except ValueError:
        error = response.text
    raise ToolError(f"HTTP {response.status_code}: {error}")


@mcp.tool()
def find_models(capability: str | None = None, output: str | None = None, query: str | None = None) -> dict:
    """Busca modelos. capability: text-to-video, image-to-video, first-last-frame, video-input,
    reference-to-video, image-references, audio-input, video-edit, video-extend, motion-transfer,
    object-swap, text-to-image, edit. output: video | image. query: texto en id/título (p. ej. seedance)."""
    params = {k: v for k, v in {"capability": capability, "output": output, "q": query}.items() if v}
    return _call("GET", "/v1/models", params=params)


@mcp.tool()
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


@mcp.tool()
def upload_media(path: str) -> dict:
    """Sube una imagen (jpg/png/webp/gif), video mp4 o audio wav local y devuelve una URL pública
    para usar en campos *_url / *_urls del modelo. Acepta rutas de Windows (C:\\...) si el MCP corre en WSL."""
    file = _local_path(path)
    if not file.is_file():
        raise ToolError(f"No existe el archivo {file}")
    content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    with file.open("rb") as fh:
        return _call("POST", "/v1/uploads", files={"file": (file.name, fh, content_type)})


@mcp.tool()
def estimate_cost(model_id: str, input: dict, input_video_seconds: float | None = None) -> dict:
    """Costo de una generación sin ejecutarla. Funciona aunque falten los medios. Si el modelo cobra
    por segundos de video de entrada, pasa input_video_seconds (duración del video que subirás).
    Devuelve quote_id: muéstrale el costo al usuario y pásalo a generate con los mismos parámetros."""
    payload = {"model": model_id, "input": input, "hints": _hints(input_video_seconds)}
    estimate = _call("POST", "/v1/estimate", json=payload)
    return {**estimate, "quote_id": _issue_quote(payload, estimate)}


@mcp.tool()
def generate(
    model_id: str,
    input: dict,
    quote_id: str,
    idempotency_key: str | None = None,
    allow_duplicate: bool = False,
    input_video_seconds: float | None = None,
    confirm_unknown_cost: bool = False,
    keep_source_audio: bool = False,
) -> dict:
    """Encola una generación y devuelve el trabajo (id, status). No espera: usa get_generation.
    Requiere el quote_id de estimate_cost con los mismos model_id, input e input_video_seconds (el
    usuario debe haber visto ese costo). Si reintentas tras un fallo de red, pasa la misma idempotency_key.
    Al editar un video (entrada video_url), generate_audio=false da un video MUDO, no conserva el sonido
    original; para conservarlo pasa keep_source_audio=true (gratis: HF Studio le pone el audio del
    video de origen al resultado). Lee studio_notes en get_model."""
    payload = {"model": model_id, "input": input, "hints": _hints(input_video_seconds)}
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, confirm_unknown_cost)}
    body = {
        "model": model_id,
        "input": input,
        "allow_duplicate": allow_duplicate,
        "keep_source_audio": keep_source_audio,
    }
    return _call("POST", "/v1/generations", json=body, headers=headers)


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def get_generation(generation_id: str, wait_seconds: int = 50) -> dict:
    """Estado de una generación. Espera hasta wait_seconds (máx. 120) a que sea terminal.
    Los videos suelen tardar de 1 a 10 minutos: repite la llamada mientras terminal sea false."""
    wait = max(0, min(wait_seconds, 120))
    return _call("GET", f"/v1/generations/{generation_id}", params={"wait": wait})


@mcp.tool()
def list_generations(status: str | None = None, limit: int = 20) -> dict:
    """Lista tus generaciones recientes (status: pending, queued, in_progress, completed, failed…)."""
    params = {"limit": limit, **({"status": status} if status else {})}
    return _call("GET", "/v1/generations", params=params)


@mcp.tool()
def cancel_generation(generation_id: str) -> dict:
    """Cancela una generación que aún no empezó (pending o queued). Lo cancelado se reembolsa."""
    return _call("POST", f"/v1/generations/{generation_id}/cancel")


@mcp.tool()
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


@mcp.tool()
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


def _issue_quote(payload: dict, estimate: dict) -> str:
    with _quotes_lock:
        now = time.monotonic()
        for qid in [q for q, v in _quotes.items() if v["expires"] < now]:
            del _quotes[qid]
        qid = "q_" + uuid.uuid4().hex[:16]
        _quotes[qid] = {
            "request": _fingerprint(payload),
            "estimate": estimate,
            "expires": now + QUOTE_TTL,
            "key": None,
        }
        return qid


def _redeem_quote(
    payload: dict, quote_id: str | None, idempotency_key: str | None, confirm_unknown_cost: bool
) -> str:
    """Regla del dueño: no se gasta sin que el usuario haya visto el precio de esta misma petición.
    Cada cotización sirve para una sola ejecución; reintentar con la misma clave no vuelve a cobrar.
    Devuelve la clave de idempotencia que debe usarse."""
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
        return key


@mcp.tool()
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
    Sin total completo se rechaza salvo confirm_unknown_cost=True (solo si el usuario acepta un costo desconocido)."""
    payload = {"items": items, "hints": _hints(input_video_seconds)}
    if dry_run:
        quote = _call("POST", "/v1/generations/batch", json={**payload, "dry_run": True})
        return {**quote, "quote_id": _issue_quote(payload, quote["total"])}
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, confirm_unknown_cost)}
    return _call("POST", "/v1/generations/batch", json={**payload, "dry_run": False}, headers=headers)


@mcp.tool()
def wait_generations(generation_ids: list[str], wait_seconds: int = 60) -> dict:
    """Espera hasta wait_seconds (máx. 120) a que terminen varias generaciones y devuelve su estado.
    Repite mientras all_terminal sea false."""
    params = {"ids": ",".join(generation_ids), "wait": max(0, min(wait_seconds, 120)), "limit": 100}
    return _call("GET", "/v1/generations", params=params)


@mcp.tool()
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


@mcp.tool()
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
    headers = {"Idempotency-Key": _redeem_quote(payload, quote_id, idempotency_key, confirm_unknown_cost)}
    return _call("POST", f"/v1/presets/{slug}/run", json={**body, "dry_run": False}, headers=headers)


@mcp.tool()
def save_preset(generation_id: str, slug: str, title: str, description: str = "") -> dict:
    """Guarda una generación como preset propio: mismos ajustes y medios, con el prompt como variable."""
    body = {"slug": slug, "title": title, "description": description}
    return _call("POST", f"/v1/presets/from-generation/{generation_id}", json=body)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
