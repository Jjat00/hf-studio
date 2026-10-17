"""Kling que Higgsfield no trae: Kling 2.1 (Standard, Pro y Master) y Kling AI Avatar (imagen + audio), en KIE.

Fuentes (revisadas el 2026-10-17):
- KIE, API unificada (`jobs/createTask`), un id por variante:
  https://docs.kie.ai/market/kling/v2-1-standard.md y .../v2-1-pro.md (imagen a video; Pro admite
  `tail_image_url`), .../v2-1-master-text-to-video.md y .../v2-1-master-image-to-video.md. Todas: `duration`
  "5" o "10", `negative_prompt` hasta 500 caracteres, `cfg_scale` de 0 a 1 en pasos de 0,1.
  https://docs.kie.ai/market/kling/ai-avatar-standard.md y .../ai-avatar-pro.md: imagen, audio (hasta 5
  minutos) y prompt obligatorios.
- Tabla pública `api.kie.ai/client/v1/model-pricing/page`: Kling 2.1 por video (`kling 2.1, video-generation,
  standard-5.0s`, `kling 2.1, image-to-video, master-10.0s`…); AI Avatar por segundo de audio
  (`kling ai avatar, lip sync, pro-1080p (audio up to 5 minutes)`).

APIMart no vende Kling 2.1 ni AI Avatar (sin filas en su tabla). El precio del avatar depende de la duración
del audio: `hints["input_audio_seconds"]` (ver `avatars.audio_seconds`).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, per_unit, unsupported
from ._common import choice, model, prompt, url
from .avatars import audio_limit, audio_seconds

K = "kie"
DOCS = "https://docs.kie.ai/market/kling"
AVATAR_MAX_AUDIO = 300  # 5 minutos

# (id lógico, id en KIE, nombre, modo de la fila de precio)
V21 = (
    ("kling-video/v2.1/standard/image-to-video", "kling/v2-1-standard", "Kling 2.1 Standard",
     "video-generation, standard"),
    ("kling-video/v2.1/pro/image-to-video", "kling/v2-1-pro", "Kling 2.1 Pro", "video-generation, pro"),
    ("kling-video/v2.1/master/image-to-video", "kling/v2-1-master-image-to-video", "Kling 2.1 Master",
     "image-to-video, master"),
    ("kling-video/v2.1/master/text-to-video", "kling/v2-1-master-text-to-video", "Kling 2.1 Master",
     "text-to-video, master"),
)  # fmt: skip
AVATARS = (("standard", "Standard", "720p"), ("pro", "Pro", "1080p"))


def _v21_models() -> list[dict[str, Any]]:
    found = []
    for model_id, kie_id, name, _ in V21:
        text = model_id.endswith("text-to-video")
        properties: dict[str, Any] = {
            "prompt": prompt(5000),
            "duration": choice([5, 10], 5, "Length in seconds."),
            "negative_prompt": {"type": "string", "default": "", "maxLength": 500, "description": "What to avoid."},
            "cfg_scale": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5,
                          "description": "How closely to follow the prompt (steps of 0.1)."},
        }  # fmt: skip
        caps = ["text-to-video"] if text else ["image-to-video"]
        if text:
            properties["aspect_ratio"] = choice(["16:9", "9:16", "1:1"], "16:9", "Output aspect ratio.")
        else:
            properties["image_url"] = url("First frame (JPEG or PNG, up to 10 MB).")
        if kie_id == "kling/v2-1-pro":
            properties["end_image_url"] = url("Optional last frame (JPEG or PNG, up to 10 MB).")
            caps.append("first-last-frame")
        found.append(
            model(
                model_id,
                name=name,
                workflow="Text to video" if text else "Image to video",
                family="kling-2.1",
                output="video",
                capabilities=caps,
                properties=properties,
                required=["prompt"] if text else ["prompt", "image_url"],
                docs_url=f"{DOCS}/{kie_id.removeprefix('kling/')}",
                notes=["Kling 2.1, silent video. Higgsfield does not sell it; it runs on KIE."],
            )
        )
    return found


def _avatar_models() -> list[dict[str, Any]]:
    return [
        model(
            f"kling/ai-avatar/{tier}",
            name=f"Kling AI Avatar {label}",
            workflow="Talking video",
            family="kling-ai-avatar",
            output="video",
            capabilities=["image-to-video", "audio-input"],
            properties={
                "image_url": url("The avatar: a person or character (JPEG or PNG, up to 10 MB)."),
                "audio_url": url("Speech that drives the avatar (up to 5 minutes, 100 MB)."),
                "prompt": prompt(5000, "Expression, movement and camera; the words come from the audio."),
            },
            required=["image_url", "audio_url", "prompt"],
            docs_url=f"{DOCS}/ai-avatar-{tier}",
            notes=[
                f"Lip-synced avatar video at {res}, as long as the audio. Runs on KIE only.",
                "Billed per second of audio.",
            ],
        )
        for tier, label, res in AVATARS
    ]


MODELS = [*_v21_models(), *_avatar_models()]


def _tenth(value: Any) -> Any:
    """`cfg_scale` en pasos de 0,1 (KIE); otro valor no se puede reproducir."""
    if round(float(value) * 10, 6) != round(float(value) * 10):
        raise unsupported(K, "KIE takes cfg_scale in steps of 0.1")
    return value


def kie() -> dict[str, Route]:
    routes: dict[str, Route] = {}
    for model_id, kie_id, _, row in V21:
        routes[model_id] = Route(
            K, kie_id,
            Spec(K, kie_id, keep=("prompt", "aspect_ratio", "image_url"),
                 rename={"end_image_url": "tail_image_url"} if kie_id == "kling/v2-1-pro" else {},
                 convert={"duration": str, "cfg_scale": _tenth, "negative_prompt": lambda v: v or None}),
            lambda i, h, p, r=row: per_unit(p, f"kling 2.1, {r}-{i.get('duration', 5)}.0s"),
        )  # fmt: skip
    for tier, label, res in AVATARS:
        kie_id = f"kling/ai-avatar-{tier}"
        routes[f"kling/ai-avatar/{tier}"] = Route(
            K, kie_id,
            Spec(K, kie_id, keep=("image_url", "audio_url", "prompt")),
            lambda i, h, p, lb=label, r=res: per_second(
                p, f"kling ai avatar, lip sync, {lb.lower()}-{r} (audio up to 5 minutes)", audio_seconds(h)),
            notes=("Billed per second of audio",),
            check=audio_limit(K, AVATAR_MAX_AUDIO),
        )  # fmt: skip
    return routes
