"""Herramientas de video de las tiendas: el escalador de video de Topaz (KIE). Higgsfield no lo vende.

Fuentes (revisadas el 2026-10-17):
- KIE, API unificada (`jobs/createTask`): https://docs.kie.ai/market/topaz/video-upscale.md
  (`topaz/video-upscale`: `video_url` MP4, MOV o MKV de hasta 50 MB, `upscale_factor` "1", "2" o "4").
- Tabla pública `api.kie.ai/client/v1/model-pricing/page`: por segundo de video,
  `topaz video upscaler, upscale factor 1x/2x` y `topaz video upscaler, upscale factor 4x`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported, video_seconds
from ._common import choice, model, url

K = "kie"

MODELS = [
    model(
        "topaz/video-upscale", name="Topaz Video Upscale", workflow="Upscale video", family="topaz-video",
        output="video", capabilities=["video-edit", "video-input"],
        properties={
            "video_url": url("Video to upscale (MP4, MOV or MKV, up to 50 MB)."),
            "upscale_factor": choice([1, 2, 4], 2, "1 enhances at the same size; 2 or 4 multiply the resolution."),
        },
        required=["video_url"], docs_url="https://docs.kie.ai/market/topaz/video-upscale",
        summary="Upscale and enhance a video with Topaz through KIE (not offered by Higgsfield).",
        notes=["No prompt: Topaz enhances and upscales the video as it is. Runs on KIE only.",
               "Billed per second of the input video; 4x costs more than 1x or 2x."],
    ),
]  # fmt: skip


def _no_prompt(value: Any) -> Any:
    if value:
        raise unsupported(K, "Topaz video upscale takes no prompt")
    return None


def kie() -> dict[str, Route]:
    def price(i: dict, h: dict, p: dict) -> float | None:
        factor = "4x" if i.get("upscale_factor", 2) == 4 else "1x/2x"
        return per_second(p, f"topaz video upscaler, upscale factor {factor}", video_seconds(h))

    return {
        "topaz/video-upscale": Route(
            K, "topaz/video-upscale",
            Spec(K, "topaz/video-upscale", keep=("video_url",), convert={"upscale_factor": str, "prompt": _no_prompt}),
            price,
            notes=("Billed by the length of the input video",),
        )
    }  # fmt: skip
