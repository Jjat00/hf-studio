"""Herramientas locales de HF Studio (Spaces, fase 2b): fotograma de un video, combinar videos y mezclar audio.

Son modelos más del catálogo (`hf-studio/frame`, `hf-studio/combine`, `hf-studio/mix`) con su `input_schema`,
así que en Spaces se conectan, se ajustan y se ejecutan igual que un generador, y entran en las corridas.
Cuestan 0 USD: el router las cotiza aquí (`tool_plan`) y el worker las envía a `LocalTools`, un proveedor que
solo existe dentro del worker (no aparece en `/v1/providers` ni en `setup`). `LocalTools` corre ffmpeg en
segundo plano y entrega las salidas como archivos locales.

ffmpeg solo abre copias locales de medios propios (descargadas con `media.cached_source`, con las mismas
restricciones de formato que `audio.py`); la API comprueba antes que cada URL sea una subida o una salida del
cliente (`trusted_media`).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from .audio import _run, duration, guarded, has_audio
from .config import Settings
from .media import cached_source
from .providers.base import KeyCheck, Polled, Provider, ProviderError, Submitted

log = logging.getLogger("hf_studio.space_tools")

TOOL_PROVIDER = "hf-studio"
AUDIO_PROVIDER = "elevenlabs"
ASSISTANT_PROVIDER = "anthropic"
# Proveedores internos del worker que trabajan dentro de este proceso (salidas `local://`): su copia guardada
# es obligatoria y se pueden cancelar en curso.
BACKGROUND_PROVIDERS = (TOOL_PROVIDER, AUDIO_PROVIDER, ASSISTANT_PROVIDER)
LOCAL_SCHEME = "local://"
MAX_COMBINE = 10
MAX_MIX_AUDIO = 4

_URI = {"type": "string", "format": "uri"}


def _tool(model_id: str, title: str, workflow: str, output: str, summary: str, schema: dict) -> dict:
    return {
        "id": model_id,
        "title": f"{title} — {workflow} API",
        "summary": summary,
        "workflow": workflow,
        "family": "HF Studio",
        "output": output,
        "capabilities": ["studio-tool"],
        "notes": ["Local and free: runs ffmpeg inside HF Studio."],
        "docs_url": "",
        "input_schema": {"type": "object", **schema},
    }


TOOLS: dict[str, dict] = {
    t["id"]: t
    for t in (
        _tool(
            "hf-studio/frame",
            "Frame",
            "Video frame",
            "image",
            "First or last frame of a video, as an image (to chain clips).",
            {
                "required": ["video_url"],
                "properties": {
                    "video_url": {**_URI, "title": "Video"},
                    "which": {
                        "type": "string",
                        "enum": ["first", "last"],
                        "default": "last",
                        "title": "Frame",
                    },
                },
            },
        ),
        _tool(
            "hf-studio/combine",
            "Combine videos",
            "Combine videos",
            "video",
            "Joins videos in the order they are connected, at the size of the first one.",
            {
                "required": ["video_urls"],
                "properties": {
                    "video_urls": {
                        "type": "array",
                        "items": _URI,
                        "minItems": 2,
                        "maxItems": MAX_COMBINE,
                        "title": "Videos",
                    },
                },
            },
        ),
        _tool(
            "hf-studio/mix",
            "Mix audio",
            "Mix audio",
            "video",
            "Puts one or more audio tracks (voice, music, effects) over a video.",
            {
                "required": ["video_url", "audio_urls"],
                "properties": {
                    "video_url": {**_URI, "title": "Video"},
                    "audio_urls": {
                        "type": "array",
                        "items": _URI,
                        "minItems": 1,
                        "maxItems": MAX_MIX_AUDIO,
                        "title": "Audio",
                    },
                    "keep_original": {"type": "boolean", "default": True, "title": "Keep the video's audio"},
                    "audio_volume": {"type": "number", "minimum": 0, "maximum": 2, "default": 1},
                    "original_volume": {"type": "number", "minimum": 0, "maximum": 2, "default": 1},
                },
            },
        ),
    )
}


def is_tool(model_id: str | None) -> bool:
    return model_id in TOOLS


def tool_media(arguments: dict) -> list[str]:
    """URLs de medios de la entrada de una herramienta (las que ffmpeg va a abrir)."""
    urls: list[str] = []
    for key, value in arguments.items():
        if key.endswith(("_url", "_urls")):
            urls.extend(v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str))
    return urls


class ToolError(Exception):
    pass


class BackgroundProvider(Provider):
    """Proveedor interno del worker: cada envío es una tarea asyncio de este proceso que deja su salida en
    `storage/tool-work/<id>/`. Se puede cancelar en curso, se cierra al apagar, limpia sus parciales y su
    salida se copia a almacenamiento propio antes de borrarla. Las subclases implementan `produce`."""

    env_var = ""
    base_url = ""
    signup_url = ""
    key_url = ""
    work_name = "tool-work"

    def __init__(self, settings: Settings, transport=None, plain=None):
        super().__init__(settings, transport)
        self.download_client = plain or self._plain  # descargas de los medios de entrada (CDN de Higgsfield)
        self.work = Path(settings.storage_dir) / self.work_name
        self.tasks: dict[str, asyncio.Task] = {}
        # Tareas canceladas a propósito: un sondeo que llegue a la vez las informa como canceladas, no como
        # perdidas por un reinicio (revisión 59).
        self.canceled: set[str] = set()

    @classmethod
    def key_from(cls, settings: Settings) -> str:
        return "local"

    async def check_key(self) -> KeyCheck:
        return KeyCheck(valid=True)

    def accepts(self, model: str) -> bool:
        raise NotImplementedError

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        """Genera la salida en `folder` y devuelve (tipo, nombre de archivo, content type)."""
        raise NotImplementedError

    async def submit_job(
        self, model: str, arguments: dict[str, Any], webhook_url: str | None = None
    ) -> Submitted:
        if not self.accepts(model):
            raise ProviderError("unsupported", f"Unknown model {model!r}", provider=self.name)
        request_id = f"{self.name}-{uuid.uuid4().hex}"
        self.tasks[request_id] = asyncio.create_task(self._run(request_id, model, arguments), name=request_id)
        return Submitted(request_id=request_id, status="in_progress")

    async def poll_job(self, request_id: str, status_url: str | None = None) -> Polled:
        if request_id in self.canceled:
            return Polled("canceled")
        task = self.tasks.get(request_id)
        if task is None:
            return Polled("failed", error="Interrupted by a server restart")
        if not task.done():
            return Polled("in_progress")
        self.tasks.pop(request_id, None)
        if task.cancelled():
            return Polled("canceled")
        exc = task.exception()
        if exc is not None:
            return Polled("failed", error=str(getattr(exc, "message", None) or exc) or type(exc).__name__)
        kind, name, content_type = task.result()
        return Polled("completed", outputs=[{"kind": kind, "url": f"{LOCAL_SCHEME}{request_id}/{name}",
                                             "content_type": content_type}])  # fmt: skip

    async def cancel_job(self, request_id: str, cancel_url: str | None = None) -> None:
        """Cancela la tarea (y su subproceso) y espera a que termine; sus archivos de trabajo se borran."""
        self.canceled.add(request_id)
        task = self.tasks.pop(request_id, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        shutil.rmtree(self.work / request_id, ignore_errors=True)

    async def aclose(self) -> None:
        """Al apagar: ninguna tarea local sigue viva (revisión 58)."""
        for request_id in list(self.tasks):
            await self.cancel_job(request_id)
        await super().aclose()

    def sweep(self) -> None:
        """Al arrancar no hay tareas: lo que quede en `tool-work` es de un proceso anterior y nadie lo entregará
        (sus trabajos fallan como interrumpidos al sondearse)."""
        if not self.tasks:
            shutil.rmtree(self.work, ignore_errors=True)
            self.canceled.clear()

    async def download(self, url: str, dest: Path) -> tuple[int, str | None]:
        """Copia la salida a almacenamiento propio. El original solo se borra después de copiarlo entero: si la
        copia falla, sigue ahí para reintentar (revisión 58)."""
        if not url.startswith(LOCAL_SCHEME):
            raise OSError(f"Not a local output: {url}")
        request_id, name = url[len(LOCAL_SCHEME) :].split("/", 1)
        if "/" in name or ".." in request_id:
            raise OSError(f"Invalid local output: {url}")
        src = self.work / request_id / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copyfile(src, tmp)
        tmp.replace(dest)
        shutil.rmtree(self.work / request_id, ignore_errors=True)
        types = {".png": "image/png", ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".txt": "text/plain"}
        return dest.stat().st_size, types.get(dest.suffix, "application/octet-stream")

    async def _run(self, request_id: str, model: str, arguments: dict) -> tuple[str, str, str]:
        folder = self.work / request_id
        folder.mkdir(parents=True, exist_ok=True)
        try:
            return await self.produce(folder, model, arguments)
        except (
            BaseException
        ):  # fallo o cancelación: no quedan parciales (la salida buena se guarda al entregarla)
            shutil.rmtree(folder, ignore_errors=True)
            raise


class LocalTools(BackgroundProvider):
    """Herramientas locales (ffmpeg): fotograma, combinar y mezclar."""

    name = TOOL_PROVIDER
    title = "HF Studio (local)"
    blurb = "Local tools (ffmpeg), free"

    def accepts(self, model: str) -> bool:
        return model in TOOLS

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        if model == "hf-studio/frame":
            return await self._frame(folder, arguments)
        if model == "hf-studio/combine":
            return await self._combine(folder, arguments)
        return await self._mix(folder, arguments)

    async def _local(self, url: str) -> str:
        path = await cached_source(url, Path(self.settings.storage_dir), self.download_client,
                                   self.settings.max_upload_bytes)  # fmt: skip
        if path is None:
            raise ToolError("A connected file could not be read as audio or video")
        return path

    async def _frame(self, folder: Path, a: dict) -> tuple[str, str, str]:
        src = await self._local(a["video_url"])
        out = folder / "0-image.png"
        if a.get("which", "last") == "first":
            args = [*guarded(src), "-frames:v", "1", str(out)]
        else:
            # Desde el último segundo, cada fotograma reescribe el archivo: queda el último.
            args = ["-sseof", "-1", *guarded(src), "-update", "1", str(out)]
        code, msg = await _run("ffmpeg", "-y", "-v", "error", *args)
        if code != 0 or not out.is_file():
            raise ToolError(f"Could not extract the frame: {msg[:200]}")
        return "image", out.name, "image/png"

    async def _combine(self, folder: Path, a: dict) -> tuple[str, str, str]:
        sources = [await self._local(u) for u in a["video_urls"][:MAX_COMBINE]]
        size = await _size(sources[0])
        if size is None:
            raise ToolError("Could not read the first video")
        w, h = size
        inputs: list[str] = []
        parts: list[str] = []
        for i, src in enumerate(sources):
            inputs += guarded(src)
            parts.append(
                f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,fps=30,format=yuv420p[v{i}]"
            )
        # Un video sin sonido aporta silencio de su misma duración: concat exige audio en todos.
        audio_inputs = len(sources)
        for i, src in enumerate(sources):
            if await has_audio(src):
                parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
            else:
                secs = await duration(src) or 1.0
                inputs += ["-f", "lavfi", "-t", f"{secs:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                parts.append(f"[{audio_inputs}:a]anull[a{i}]")
                audio_inputs += 1
        chain = "".join(f"[v{i}][a{i}]" for i in range(len(sources)))
        parts.append(f"{chain}concat=n={len(sources)}:v=1:a=1[v][a]")
        out = folder / "0-video.mp4"
        code, msg = await _run(
            "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-movflags", "+faststart", str(out),
        )  # fmt: skip
        if code != 0 or not out.is_file():
            raise ToolError(f"Could not combine the videos: {msg[:200]}")
        return "video", out.name, "video/mp4"

    async def _mix(self, folder: Path, a: dict) -> tuple[str, str, str]:
        video = await self._local(a["video_url"])
        tracks = [await self._local(u) for u in a["audio_urls"][:MAX_MIX_AUDIO]]
        secs = await duration(video)
        if secs is None:
            raise ToolError("Could not read the video")
        inputs = [*guarded(video)]
        parts: list[str] = []
        labels: list[str] = []
        if a.get("keep_original", True) and await has_audio(video):
            parts.append(f"[0:a]volume={float(a.get('original_volume', 1)):.3f}[o]")
            labels.append("[o]")
        for i, track in enumerate(tracks, start=1):
            inputs += guarded(track)
            parts.append(f"[{i}:a]volume={float(a.get('audio_volume', 1)):.3f}[t{i}]")
            labels.append(f"[t{i}]")
        parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[a]")
        out = folder / "0-video.mp4"
        code, msg = await _run(
            "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-t", f"{secs:.3f}", "-movflags", "+faststart", str(out),
        )  # fmt: skip
        if code != 0 or not out.is_file():
            raise ToolError(f"Could not mix the audio: {msg[:200]}")
        return "video", out.name, "video/mp4"


async def _size(source: str) -> tuple[int, int] | None:
    from .audio import PROBE_GUARD

    code, out = await _run(
        "ffprobe", "-v", "error", *PROBE_GUARD, "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", source,
    )  # fmt: skip
    try:
        w, h = (int(x) for x in out.split("x")[:2]) if code == 0 else (0, 0)
    except ValueError:
        return None
    if not w or not h:
        return None
    return w - w % 2, h - h % 2
