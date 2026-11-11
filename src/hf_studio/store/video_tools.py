"""Herramientas de video de las tiendas: los escaladores de video de Topaz y de KIE (KIE). Higgsfield no los vende.

Fuentes (revisadas el 2026-10-17):
- KIE, API unificada (`jobs/createTask`): https://docs.kie.ai/market/topaz/video-upscale.md
  (`topaz/video-upscale`: `video_url` MP4, MOV o MKV de hasta 50 MB, `upscale_factor` "1", "2" o "4").
- Tabla pública `api.kie.ai/client/v1/model-pricing/page`: por segundo de video,
  `topaz video upscaler, upscale factor 1x/2x` y `topaz video upscaler, upscale factor 4x`.
- KIE `video/upscale` («Kie - Video Upscale», revisado el 2026-11-11): https://docs.kie.ai/market/kie/video-upscale.md
  (`video_url` MP4, MOV o MKV de hasta 50 MB y 60 s; `resolution` 1080P|2K|4K es la caja de salida: el video se
  ajusta a ella sin recortar y conserva proporción, fotogramas, duración y audio). Precio por segundo
  (`creditUnit` «per second»): `kie video upscale, video to video, <1080p|2k|4k> output, per second`; como el
  video conserva sus fotogramas, se cotiza con la duración del de entrada.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported, video_seconds
from ._common import choice, model, upper, url

K = "kie"
KIE_UPSCALE = "kie/video-upscale"
KIE_UPSCALE_MAX_SECONDS = 60

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
    model(
        KIE_UPSCALE, name="KIE Video Upscale", workflow="Upscale video", family="kie-video-upscale",
        output="video", capabilities=["video-edit", "video-input"],
        properties={
            "video_url": url("Video to upscale (MP4, MOV or MKV, up to 50 MB and 60 s)."),
            "resolution": choice(["1080p", "2k", "4k"], "2k",
                                 "Output box (1920×1080, 2560×1440 or 3840×2160, rotated for portrait)."),
        },
        required=["video_url"], docs_url="https://docs.kie.ai/market/kie/video-upscale",
        summary="Upscale a video to 1080p, 2K or 4K with KIE's own upscaler (not offered by Higgsfield).",
        notes=[("No prompt: the video is fitted into the output box without cropping and keeps its aspect ratio, "
                "frame rate, length and audio. Runs on KIE only."),
               "Billed per second of the input video; higher outputs cost more."],
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

    def kie_price(i: dict, h: dict, p: dict) -> float | None:
        row = f"kie video upscale, video to video, {i.get('resolution', '2k')} output, per second"
        return per_second(p, row, video_seconds(h))

    def max_length(source: dict, hints: dict) -> None:
        seconds = video_seconds(hints)
        if seconds is not None and seconds > KIE_UPSCALE_MAX_SECONDS:
            raise unsupported(K, f"KIE Video Upscale takes videos up to {KIE_UPSCALE_MAX_SECONDS} s")

    return {
        "topaz/video-upscale": Route(
            K, "topaz/video-upscale",
            Spec(K, "topaz/video-upscale", keep=("video_url",), convert={"upscale_factor": str, "prompt": _no_prompt}),
            price,
            notes=("Billed by the length of the input video",),
        ),
        KIE_UPSCALE: Route(
            K, "video/upscale",
            Spec(K, "video/upscale", keep=("video_url",), convert={"resolution": upper, "prompt": _no_prompt}),
            kie_price,
            notes=("Billed by the length of the input video",),
            check=max_length,
        ),
    }  # fmt: skip
