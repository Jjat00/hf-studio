"""Runway Gen-4 Turbo en KIE. Ni Higgsfield ni APIMart lo venden.

Fuentes (revisadas el 2026-10-17):
- KIE `runway`: https://docs.kie.ai/runway-api/generate-ai-video.md. Ya usa la API unificada
  (`jobs/createTask` + `jobs/recordInfo`, con `resultJson.resultUrls`), así que no necesita `KIE_ENDPOINTS`.
  Texto a video (exige `aspect_ratio`: 16:9, 4:3, 1:1, 3:4, 9:16) o imagen a video (`image_url`; el formato sale de
  la imagen y `aspect_ratio` no vale). `duration` 5 o 10, `quality` 720p o 1080p, y 1080p solo a 5 s. `watermark`
  es un texto; vacío = sin marca. Prompt hasta 1800 caracteres. La versión (Gen-4 Turbo) la dice https://kie.ai/runway-api.
- Precio por video: `runway, <text|image>-to-video, <d>.0s-<res>`.
- Descartados: Aleph (`runway/gen4-aleph`, retirado de KIE según https://docs.kie.ai/runway-api/generate-aleph-video.md)
  y la extensión (`runway/extend-ai-video`, solo acepta el `task_id` de una tarea de Runway en la misma cuenta de KIE).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, url

DOCS = "https://docs.kie.ai/runway-api/generate-ai-video"
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16"]
MODEL = "runway"


def _id(mode: str) -> str:
    return f"runway/gen4-turbo/{mode}"


def _models() -> list[dict[str, Any]]:
    common = {
        "prompt": prompt(1800, "What happens in the video: subject, action, style and setting."),
        "duration": choice([5, 10], 5, "Video length in seconds (1080p: 5 only)."),
        "resolution": choice(["720p", "1080p"], "720p", "Output resolution (1080p only for 5 s)."),
    }
    notes = ["Runway Gen-4 Turbo. Runs on KIE only, without watermark."]
    return [
        model(
            _id("text-to-video"), name="Runway Gen-4 Turbo", workflow="Text to video", family="runway-gen4-turbo",
            output="video", capabilities=["text-to-video"],
            properties={**common, "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio.")},
            required=["prompt"], docs_url=DOCS, notes=notes,
        ),
        model(
            _id("image-to-video"), name="Runway Gen-4 Turbo", workflow="Image to video", family="runway-gen4-turbo",
            output="video", capabilities=["image-to-video"],
            properties={**common, "image_url": url("Image to animate; the video keeps its aspect ratio.")},
            required=["prompt", "image_url"], docs_url=DOCS, notes=notes,
        ),
    ]  # fmt: skip


MODELS = _models()


def _check(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if source.get("resolution") == "1080p" and source.get("duration") != 5:
        raise unsupported("kie", "Runway only makes 1080p videos of 5 seconds")
    return out


def kie() -> dict[str, Route]:
    p = "kie"
    routes: dict[str, Route] = {}
    for mode, keep in (("text-to-video", ("prompt", "duration", "aspect_ratio")),
                       ("image-to-video", ("prompt", "duration", "image_url"))):  # fmt: skip
        routes[_id(mode)] = Route(
            p, MODEL,
            Spec(p, MODEL, keep=keep, rename={"resolution": "quality"}, fixed={"watermark": ""}, build=_check),
            lambda i, h, pr, m=mode: per_unit(
                pr, f"runway, {m}, {i.get('duration', 5)}.0s-{i.get('resolution', '720p')}"
            ),
        )  # fmt: skip
    return routes
