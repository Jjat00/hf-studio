"""LTX 2.5 (Lightricks) en KIE: ruta más barata de los modelos de Higgsfield y audio a video, que Higgsfield no tiene.

Fuentes (revisadas el 2026-11-19): https://docs.kie.ai/market/ltx/2-5-fast-text-to-video.md y sus hermanas
(`ltx/2-5-{fast,pro}-{text,image}-to-video`, `ltx/2-5-fast-audio-to-video`). Prompt 1–5000, `resolution`
720p|1080p (Fast también 1440p; 1080p por omisión), `fps` 24|25|48|50 (24 por omisión), `duration` 6–20 en Fast y
6|8|10 en Pro (10 por omisión), `aspect_ratio` solo en texto a video, `image_url` como primer fotograma (manda el
formato), `seed`. El audio se genera siempre. Precio por segundo de salida `ltx 2.5 <fast|pro>, <modo>, <res>`.

Lo que el esquema de Higgsfield pide y KIE no hace queda `unsupported` (sin traducción aproximada): 2k y 4k (no
hay constancia de que 1440p sea su 2k), apagar el audio, `camera_movement`, el último fotograma y, en imagen a
video, una relación de aspecto explícita (KIE la toma de la imagen). Como los valores por defecto difieren (KIE usa
1080p, 24 fps y 10 s), se envían siempre los del esquema de Higgsfield.

Audio a video (`ltx/2-5-fast-audio-to-video`): el sonido del video es el audio dado; `duration` (2–20 s, con
decimales) recorta desde su inicio y el audio no puede ser más corto. Se cobra por la duración real de la salida:
aquí la duración es obligatoria para tener precio exacto.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, only_default, per_second, unsupported
from ._common import choice, model, prompt, url

KIE_RES = {"720p", "1080p"}
AUDIO_ID = "lightricks/ltx-2.5/audio-to-video/fast"
AUDIO_KIE = "ltx/2-5-fast-audio-to-video"


def _hf(mode: str, tier: str) -> str:
    return f"lightricks/ltx-2.5/{mode}/{tier}"


def _price(tier: str, mode: str):
    label = mode.replace("-", " ")

    def price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
        return per_second(p, f"ltx 2.5 {tier}, {label}, {i.get('resolution', '720p')}", i.get("duration"))

    return price


def _audio_limits(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if (source.get("resolution") == "1440p" or source.get("fps") in (48, 50)) and float(
        source.get("duration", 0)
    ) > 10:
        raise unsupported("kie", "LTX 2.5 makes at most 10 s at 1440p or at 48/50 fps")
    return out


def kie() -> dict[str, Route]:
    routes: dict[str, Route] = {}
    for tier in ("fast", "pro"):
        for mode in ("text-to-video", "image-to-video"):
            name = f"ltx/2-5-{tier}-{mode}"
            keep = ["prompt", "duration", "resolution", "fps"]
            convert: dict[str, Any] = {"generate_audio": only_default("generate_audio", True)}
            drop: set[str] = set()
            if mode == "text-to-video":
                keep.append("aspect_ratio")
            else:
                keep.append("image_url")
                drop.add("aspect_ratio")  # KIE toma el formato de la imagen: solo vale el valor por defecto
            spec = Spec("kie", name, keep=keep, convert=convert, drop=drop, allowed={"resolution": KIE_RES})
            routes[_hf(mode, tier)] = Route(
                "kie", name, spec, _price(tier, mode),
                notes=("KIE always generates audio and has no camera movement or last frame",),
            )  # fmt: skip
    routes[AUDIO_ID] = Route(
        "kie",
        AUDIO_KIE,
        Spec(
            "kie",
            AUDIO_KIE,
            keep=("prompt", "audio_url", "image_url", "duration", "resolution", "fps"),
            build=_audio_limits,
        ),
        _price("fast", "audio-to-video"),
    )
    return routes


MODELS = [
    model(
        AUDIO_ID,
        name="LTX 2.5 Fast",
        workflow="Audio to video",
        family="ltx-2.5-fast",
        output="video",
        capabilities=["audio-input", "image-to-video"],
        properties={
            "prompt": prompt(5000, "What happens in the video; the soundtrack is your audio."),
            "audio_url": url(
                "Audio that becomes the soundtrack (MP3, WAV, M4A, AAC, OGG or FLAC, 2 s or more)."
            ),
            "image_url": url("Optional first frame; without it the video is 16:9."),
            "duration": {
                "type": "number",
                "minimum": 2,
                "maximum": 20,
                "default": 6,
                "description": "Seconds of the audio to use, from its start (up to 10 at 1440p or 48/50 fps). "
                "The audio must be at least this long.",
            },
            "resolution": choice(["720p", "1080p", "1440p"], "720p", "Output resolution."),
            "fps": choice([24, 25, 48, 50], 25, "Frames per second."),
        },
        required=["prompt", "audio_url"],
        docs_url="https://docs.kie.ai/market/ltx/2-5-fast-audio-to-video",
        notes=[
            (
                "Lightricks' LTX 2.5 Fast turns an audio track (voice, music) into a video synced to it. Higgsfield "
                "does not sell this mode: it runs on KIE."
            ),
            "Billed per second of output; the output lasts what duration says.",
        ],
        summary="A video synced to your audio (voice or music), with LTX 2.5 Fast through KIE.",
    )
]
