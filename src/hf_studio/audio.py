"""Audio del video de origen en las ediciones de video (opción propia de HF Studio, no de Higgsfield).

En Seedance video-edit/extend y similares, `generate_audio=false` devuelve un video mudo: no conserva
el sonido del original. Con `keep_source_audio` HF Studio le pone al resultado, ya descargado, la pista
de audio del video de entrada (`video_url`) con ffmpeg, sin volver a codificar la imagen.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SOURCE_KEY = "video_url"
TIMEOUT = 180

# Estado de la mezcla, guardado en job.files[i]["audio"].
MUXED = "source"
NO_SOURCE_AUDIO = "source_has_no_audio"
FAILED = "mux_failed"


def supports_source_audio(model: dict) -> bool:
    """Modelos de video que reciben un video de origen en `video_url`."""
    props = model.get("input_schema", {}).get("properties", {})
    return model.get("output") == "video" and SOURCE_KEY in props


def studio_notes(model: dict) -> list[str]:
    """Notas de HF Studio (no de Higgsfield) que el agente debe leer antes de generar."""
    if not supports_source_audio(model):
        return []
    props = model["input_schema"]["properties"]
    notes = []
    if "generate_audio" in props:
        notes.append(
            "generate_audio=false returns a SILENT video: it does not keep the audio of the source video. "
            "It does not change the price."
        )
    notes.append(
        "To keep the audio of the source video (video_url), call generate with keep_source_audio=true: "
        "HF Studio muxes the source audio onto the result after download (free, local, image untouched)."
    )
    return notes


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 1, "timeout"
    return proc.returncode or 0, (out or err).decode(errors="replace").strip()


async def has_audio(source: str, ffprobe: str = "ffprobe") -> bool:
    code, out = await _run(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        source,
    )
    return code == 0 and bool(out)


async def mux_source_audio(video: Path, source: str, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> str:
    """Sustituye el audio de `video` por el de `source` (recortado a la duración del video).

    El resultado generado se conserva como `<nombre>.generated<ext>`. Devuelve MUXED, NO_SOURCE_AUDIO o FAILED.
    """
    try:
        if not await has_audio(source, ffprobe):
            return NO_SOURCE_AUDIO
        tmp = video.with_name(f"{video.stem}.mux{video.suffix}")
        code, out = await _run(
            ffmpeg, "-y", "-v", "error", "-i", str(video), "-i", source,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(tmp),
        )  # fmt: skip
        if code != 0:
            tmp.unlink(missing_ok=True)
            log.warning("ffmpeg no pudo mezclar el audio de %s: %s", source, out[-300:])
            return FAILED
        video.replace(video.with_name(f"{video.stem}.generated{video.suffix}"))
        tmp.replace(video)
        return MUXED
    except OSError as exc:  # ffmpeg no instalado, disco lleno…
        log.warning("No se pudo mezclar el audio de %s: %s", source, exc)
        return FAILED


async def apply_to_files(files: list[dict], storage: Path, source: str, **bins: str) -> list[dict]:
    """Mezcla el audio de origen en cada video local de un trabajo y anota el resultado."""
    result = []
    for f in files:
        f = dict(f)
        if f.get("kind") == "video" and f.get("audio") != MUXED:
            f["audio"] = await mux_source_audio(storage / f["name"], source, **bins)
            if f["audio"] == MUXED:
                f["size"] = (storage / f["name"]).stat().st_size
        result.append(f)
    return result
