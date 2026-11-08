"""Katana, montaje final: el nodo `hf-studio/katana-edit` (local y gratis).

Recibe los clips generados (`video_urls`), las imágenes (`image_urls`: fotogramas clave, placas, fotos), la
música (`music_url`, normalmente el audio de la referencia), los efectos de sonido (`sfx_urls`) y el EDL
(`edl`, ver `katana_compose.Edl`), que cita cada medio por su índice en esas listas. Renderiza la composición
con HyperFrames (la misma versión fijada que Content Factory, y la misma cola: un render a la vez) y mezcla el
audio con ffmpeg:

- La música se toma desde `audio.music_start`, con su volumen, fundido de entrada y de salida.
- Cada efecto de sonido entra en su tiempo (`adelay`) con su volumen.
- Sin efectos ni cambios de volumen, la música va tal cual (Katana no normaliza una banda sonora reutilizada);
  con mezcla, `amix normalize=0` y un limitador sin renormalizar dejan el pico por debajo de -1 dBTP.

Es un modelo más del catálogo: se cotiza (0 USD), se aprueba, aparece en el historial y en Spaces se conecta
como cualquier generador. `katana_plan` arma el lienzo que termina en este nodo.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from pydantic import ValidationError

from .audio import guarded
from .config import Settings
from .factory import HYPERFRAMES_VERSION, RENDER_TIMEOUT_MIN, renderer_problem, run_proc
from .katana_compose import Edl, build, edl_schema, font_files
from .media import _head, cached_source, download, matches_type
from .space_tools import KATANA_PROVIDER, BackgroundProvider

log = logging.getLogger("hf_studio.katana_edit")

KATANA_EDIT_MODEL = "hf-studio/katana-edit"
FPS = 30
MAX_VIDEOS = 30
MAX_IMAGES = 30
MAX_SFX = 20
ASSETS = Path(__file__).with_name("factory_assets")
_URI = {"type": "string", "format": "uri"}
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")


def _input_schema() -> dict:
    edl = edl_schema()
    defs = edl.pop("$defs", {})
    return {
        "type": "object",
        "required": ["edl"],
        "$defs": defs,
        "properties": {
            "video_urls": {"type": "array", "items": _URI, "maxItems": MAX_VIDEOS, "title": "Clips"},
            "image_urls": {"type": "array", "items": _URI, "maxItems": MAX_IMAGES, "title": "Images"},
            "music_url": {**_URI, "title": "Music"},
            "sfx_urls": {"type": "array", "items": _URI, "maxItems": MAX_SFX, "title": "Sound effects"},
            "edl": {**edl, "title": "Edit decision list"},
            "title": {"type": "string", "maxLength": 120, "title": "Title"},
        },
    }


KATANA_EDIT_NODE = {
    "id": KATANA_EDIT_MODEL,
    "title": "Katana Edit — Remix assembly API",
    "summary": (
        "Assembles a Katana remix: cuts the connected clips and images to an edit decision list with camera "
        "moves, flashes, shakes, zoom punches, glitches, grades, animated text and the music."
    ),
    "workflow": "Katana",
    "family": "HF Studio",
    "output": "video",
    "capabilities": ["katana-edit", "studio-tool"],
    "notes": [
        "Rendered locally with HyperFrames (needs Node.js 22+ and ffmpeg). Free.",
        (
            "The edl cites media by index: shots[].source is the position in video_urls (kind video) or "
            "image_urls (kind image); audio.sfx[].source the position in sfx_urls. Connect them in that order."
        ),
        "POST /v1/katana/projects/{id}/plan writes the plan and the canvas that ends in this node.",
    ],
    "docs_url": "",
    "input_schema": _input_schema(),
}


def is_katana_edit(model_id: str | None) -> bool:
    return model_id == KATANA_EDIT_MODEL


def edl_problem(arguments: dict) -> str | None:
    """Lo que impide montar esta entrada, o None. Se comprueba al cotizar, antes de gastar nada en el lienzo."""
    try:
        edl = Edl.model_validate(arguments.get("edl") or {})
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        return f"Invalid edl ({where}): {first.get('msg')}"
    videos = len(arguments.get("video_urls") or [])
    images = len(arguments.get("image_urls") or [])
    sfx = len(arguments.get("sfx_urls") or [])
    for i, s in enumerate(edl.shots):
        if s.kind == "video" and s.source >= videos:
            return f"Shot {i + 1} uses clip {s.source + 1} but only {videos} are connected"
        if s.kind == "image" and s.source >= images:
            return f"Shot {i + 1} uses image {s.source + 1} but only {images} are connected"
    for cue in edl.audio.sfx:
        if cue.source >= sfx:
            return f"A sound cue uses sound {cue.source + 1} but only {sfx} are connected"
    return None


def quote(arguments: dict) -> dict:
    return {"usd": 0.0, "kind": "exact", "basis": "Katana Edit (local render): free"}


class KatanaError(Exception):
    pass


class KatanaEditJobs(BackgroundProvider):
    """Proveedor interno del worker: descarga los medios, compone, renderiza y mezcla."""

    name = KATANA_PROVIDER
    title = "Katana Edit (local)"
    blurb = "Remix assembly rendered locally"
    work_name = "katana-work"

    def __init__(
        self, settings: Settings, transport=None, plain=None, slots: asyncio.Semaphore | None = None
    ):
        super().__init__(settings, transport, plain)
        self.slots = slots or asyncio.Semaphore(1)

    def accepts(self, model: str) -> bool:
        return model == KATANA_EDIT_MODEL

    async def _media(self, url: str) -> str:
        path = await cached_source(url, Path(self.settings.storage_dir), self.download_client,
                                   self.settings.max_upload_bytes)  # fmt: skip
        if path is None:
            raise KatanaError("A connected clip or sound could not be read as audio or video")
        return path

    async def _image(self, url: str, dest: Path) -> Path:
        if "://" not in url:
            src = Path(url)
            if not src.is_file():
                raise KatanaError("A connected image is missing")
            shutil.copyfile(src, dest)
        elif not await download(url, self.download_client, self.settings.max_upload_bytes, dest):
            raise KatanaError("A connected image could not be downloaded")
        head = _head(dest)
        kind = next((t for t in IMAGE_TYPES if matches_type(head, t)), None)
        if kind is None:
            raise KatanaError("A connected image is not PNG, JPEG or WebP")
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[kind]
        final = dest.with_suffix(ext)
        dest.replace(final)
        return final

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        folder = folder.resolve()
        problem = edl_problem(arguments)
        if problem:
            raise KatanaError(problem)
        edl = Edl.model_validate(arguments["edl"])
        project = folder / "project"
        (project / "media").mkdir(parents=True)
        (project / "fonts").mkdir()
        used_videos = sorted({s.source for s in edl.shots if s.kind == "video"})
        used_images = sorted({s.source for s in edl.shots if s.kind == "image"})
        video_files: list[str] = [""] * len(arguments.get("video_urls") or [])
        for i in used_videos:
            src = await self._media(arguments["video_urls"][i])
            dest = project / "media" / f"v{i}.mp4"
            try:
                os.link(src, dest)
            except OSError:
                shutil.copyfile(src, dest)
            video_files[i] = f"media/{dest.name}"
        image_files: list[str] = [""] * len(arguments.get("image_urls") or [])
        for i in used_images:
            final = await self._image(arguments["image_urls"][i], project / "media" / f"i{i}")
            image_files[i] = f"media/{final.name}"
        for name in font_files(edl):
            shutil.copyfile(ASSETS / "fonts" / name, project / "fonts" / name)
        (project / "index.html").write_text(build(edl, video_files, image_files), "utf-8")
        silent = folder / "render.mp4"
        async with self.slots:
            await self._render(project, silent, edl.duration)
        out = folder / "0-video.mp4"
        await self._mix(silent, arguments, edl, folder, out)
        for leftover in (project, silent):
            if leftover.is_dir():
                shutil.rmtree(leftover, ignore_errors=True)
            else:
                leftover.unlink(missing_ok=True)
        return "video", out.name, "video/mp4"

    async def _render(self, project: Path, out: Path, total: float) -> None:
        problem = renderer_problem()
        if problem:
            raise KatanaError(problem)
        env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "CI": "1"}
        code, msg = await run_proc(
            "npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "render", str(project), "-o", str(out),
            "--fps", str(FPS), "--quality", "looks", "--quiet",
            timeout=max(RENDER_TIMEOUT_MIN, total * 40), cwd=project, env=env,
        )  # fmt: skip
        if code != 0 or not out.is_file() or out.stat().st_size == 0:
            tail = "timed out" if msg == "timeout" else msg[-400:]
            raise KatanaError(f"HyperFrames could not render the edit: {tail}")
        log.info("Katana: render de %.1f s listo", total)

    async def _mix(self, silent: Path, arguments: dict, edl: Edl, folder: Path, out: Path) -> None:
        a = edl.audio
        total = edl.duration
        inputs: list[str] = guarded(str(silent))
        count = 1
        chains: list[str] = []
        labels: list[str] = []
        music = arguments.get("music_url")
        if music:
            path = await self._media(music)
            inputs += ["-ss", f"{a.music_start:.3f}", *guarded(path)]
            count += 1
            fx = [
                f"atrim=0:{total:.3f}",
                "asetpts=PTS-STARTPTS",
                "aresample=48000",
                f"volume={a.music_volume:.3f}",
            ]
            if a.fade_in > 0:
                fx.append(f"afade=t=in:st=0:d={a.fade_in:.3f}")
            if a.fade_out > 0:
                fx.append(f"afade=t=out:st={max(0.0, total - a.fade_out):.3f}:d={a.fade_out:.3f}")
            chains.append(f"[1:a]{','.join(fx)},apad=whole_dur={total:.3f}[m]")
            labels.append("[m]")
        sfx_urls = arguments.get("sfx_urls") or []
        n = count
        loaded: dict[int, int] = {}
        for k, cue in enumerate(a.sfx):
            if cue.t >= total:
                continue
            if cue.source not in loaded:
                inputs += guarded(await self._media(sfx_urls[cue.source]))
                loaded[cue.source] = n
                n += 1
            idx = loaded[cue.source]
            ms = int(cue.t * 1000)
            chains.append(
                f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={cue.volume:.3f},"
                f"adelay={ms}|{ms},atrim=0:{total:.3f}[s{k}]"
            )
            labels.append(f"[s{k}]")
        if not labels:
            code, msg = await run_proc(
                "ffmpeg", "-y", "-v", "error", *guarded(str(silent)), "-c:v", "copy", "-an",
                "-t", f"{total:.3f}", "-movflags", "+faststart", str(out), timeout=300,
            )  # fmt: skip
        else:
            if len(labels) == 1:
                graph = ";".join(chains) + f";{labels[0]}alimiter=limit=0.89:level=disabled[out]"
            else:
                graph = (
                    ";".join(chains)
                    + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first,"
                    "alimiter=limit=0.79:attack=1:release=40:level=disabled[out]"
                )
            code, msg = await run_proc(
                "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph,
                "-map", "0:v:0", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                "-t", f"{total:.3f}", "-movflags", "+faststart", str(out),
                timeout=300,
            )  # fmt: skip
        if code != 0 or not out.is_file():
            raise KatanaError(f"Could not mix the audio: {msg[-300:]}")
