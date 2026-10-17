"""Avatares que hablan (imagen + audio → video) en KIE: MeiGen InfiniteTalk y OmniHuman 1.5 (ByteDance).

Fuentes (revisadas el 2026-10-17):
- KIE, API unificada (`jobs/createTask`):
  https://docs.kie.ai/market/infinitalk/from-audio.md (`infinitalk/from-audio`: imagen, audio y prompt
  obligatorios, 480p/720p, `seed` de 10000 a 1000000; la página https://kie.ai/infinitalk limita el audio a
  15 s por tarea) y https://docs.kie.ai/market/omnihuman-1-5.md (`omnihuman-1-5`: audio de menos de 60 s,
  hasta 5 máscaras de sujeto, prompt opcional de 300 caracteres, `output_resolution` 720/1080, `pe_fast_mode`).
- Tabla pública `api.kie.ai/client/v1/model-pricing/page`: las dos por segundo de video, que dura lo que el
  audio: `meigen-ai infinitetalk, lip sync, up to 15 seconds-<res>` y `omnihuman-1-5, lip sync`.

El precio depende de la duración del audio, que la entrada no dice: se lee de `hints["input_audio_seconds"]`
(sin ella, el precio queda pendiente y el proveedor no se descarta).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported
from ._common import choice, model, prompt, url, urls

K = "kie"
INFINITETALK_MAX_AUDIO = 15
OMNIHUMAN_MAX_AUDIO = 60


def audio_seconds(hints: dict[str, Any]) -> float | None:
    """Duración del audio de entrada (`input_audio_seconds`), como `video_seconds` para los videos."""
    value = hints.get("input_audio_seconds")
    return float(value) if isinstance(value, int | float) and value > 0 else None


def audio_limit(provider: str, limit: float, strict: bool = False):
    """`check` de ruta: con la duración del audio conocida, uno más largo que el límite queda fuera."""

    def check(source: dict, hints: dict) -> None:
        seconds = audio_seconds(hints)
        if seconds is not None and (seconds >= limit if strict else seconds > limit):
            raise unsupported(
                provider, f"{provider} takes audio {'under' if strict else 'up to'} {limit:g} s"
            )

    return check


MODELS = [
    model(
        "meigen/infinitetalk/image-to-video", name="InfiniteTalk", workflow="Talking video",
        family="infinitetalk", output="video", capabilities=["image-to-video", "audio-input"],
        properties={
            "image_url": url("The person or character (JPEG, PNG or WEBP, up to 10 MB)."),
            "audio_url": url("Speech that drives the lip sync (up to 15 s, 10 MB)."),
            "prompt": prompt(5000, "Scene, expression and movement while speaking."),
            "resolution": choice(["480p", "720p"], "480p", "Output resolution."),
            "seed": {"type": "integer", "minimum": -1, "maximum": 1000000,
                     "description": "Seed (10000–1000000); -1 or empty for random."},
        },
        required=["image_url", "audio_url", "prompt"], docs_url="https://docs.kie.ai/market/infinitalk/from-audio",
        notes=["MeiGen's InfiniteTalk lip sync: the video lasts as long as the audio, up to 15 s. KIE only.",
               "Billed per second of audio."],
    ),
    model(
        "bytedance/omnihuman-1.5/image-to-video", name="OmniHuman 1.5", workflow="Talking video",
        family="omnihuman-1.5", output="video", capabilities=["image-to-video", "audio-input"],
        properties={
            "image_url": url("Portrait of a person, pet or character, any aspect ratio (up to 10 MB)."),
            "audio_url": url("Speech or song, under 60 s (15 s or less recommended), up to 10 MB."),
            "prompt": prompt(300, "Optional direction: expression, gestures, camera."),
            "mask_urls": urls(0, 5, "Masks of the subjects that speak (from KIE's OmniHuman subject detection)."),
            "resolution": choice(["720p", "1080p"], "1080p", "Output resolution tier; the image sets the shape."),
            "fast_mode": {"type": "boolean", "default": False, "description": "Faster at some cost in quality."},
            "seed": {"type": "integer", "minimum": -1, "maximum": 2147483647,
                     "description": "Seed; -1 or empty for random."},
        },
        required=["image_url", "audio_url"], docs_url="https://docs.kie.ai/market/omnihuman-1-5",
        notes=[("ByteDance OmniHuman 1.5: a portrait and an audio become a talking or singing video as long as "
                "the audio. KIE only."),
               "Billed per second of audio; audio must be under 60 s."],
    ),
]  # fmt: skip


def _infinitetalk_seed(value: Any) -> Any:
    if value is None or value == -1:
        return None
    if not 10000 <= value <= 1000000:
        raise unsupported(K, "KIE takes InfiniteTalk seeds from 10000 to 1000000")
    return value


def kie() -> dict[str, Route]:
    return {
        "meigen/infinitetalk/image-to-video": Route(
            K, "infinitalk/from-audio",
            Spec(K, "infinitalk/from-audio", keep=("image_url", "audio_url", "prompt", "resolution"),
                 convert={"seed": _infinitetalk_seed}),
            lambda i, h, p: per_second(
                p, f"meigen-ai infinitetalk, lip sync, up to 15 seconds-{i.get('resolution', '480p')}",
                audio_seconds(h)),
            notes=("Billed per second of audio",),
            check=audio_limit(K, INFINITETALK_MAX_AUDIO),
        ),
        "bytedance/omnihuman-1.5/image-to-video": Route(
            K, "omnihuman-1-5",
            Spec(K, "omnihuman-1-5", keep=("image_url", "audio_url", "seed"),
                 rename={"mask_urls": "mask_url", "resolution": "output_resolution", "fast_mode": "pe_fast_mode"},
                 convert={"prompt": lambda v: v or None, "mask_urls": lambda v: v or None,
                          "resolution": lambda v: v.removesuffix("p")}),
            lambda i, h, p: per_second(p, "omnihuman-1-5, lip sync", audio_seconds(h)),
            notes=("Billed per second of audio",),
            check=audio_limit(K, OMNIHUMAN_MAX_AUDIO, strict=True),
        ),
    }  # fmt: skip
