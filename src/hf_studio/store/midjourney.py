"""Midjourney (Imagine) en APIMart. KIE no lo vende.

Fuente (revisada el 2026-10-17): https://docs.apimart.ai/en/api-reference/images/midjourney/imagine.md y
.../midjourney/query.md. Se envía a `POST /v1/midjourney/generations` (la ruta inyecta `model=midjourney`) con
campos estructurados que ganan a las banderas del prompt; el estado se lee con `GET /v1/tasks/{id}`, que
devuelve las cuatro imágenes recortadas en `result.images`. Precio por tarea:
`midjourney|imagine-<v|niji><versión>[-fast|-turbo]` (sin sufijo = relax).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, urls

DOCS = "https://docs.apimart.ai/en/api-reference/images/midjourney/imagine"
VERSIONS = ["8.2", "8.1", "7", "6.1", "5.2", "5.1", "niji 7", "niji 6"]
RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21", "5:4", "4:5"]
MODEL_ID = "midjourney/imagine/text-to-image"

MODELS = [
    model(
        MODEL_ID,
        name="Midjourney",
        workflow="Text to image",
        family="midjourney",
        output="image",
        capabilities=["text-to-image", "image-references"],
        properties={
            "prompt": prompt(description="What to generate. Structured fields below override --flags in it."),
            "version": choice(VERSIONS, "7", "Midjourney version; niji versions are the anime models."),
            "aspect_ratio": choice(RATIOS, "1:1", "Output aspect ratio (--ar)."),
            "speed": choice(
                ["relax", "fast", "turbo"], "fast", "Queue speed: relax is cheaper but can wait much longer."
            ),
            "stylize": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1000,
                "description": "Stylization (--s).",
            },
            "chaos": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Variety between the four images (--c).",
            },
            "weird": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3000,
                "description": "Unusual aesthetics (--w).",
            },
            "raw": {
                "type": "boolean",
                "default": False,
                "description": "Raw style: less Midjourney beautification.",
            },
            "seed": {"type": "integer", "minimum": 0, "maximum": 4294967295, "description": "Seed (--seed)."},
            "negative_prompt": {"type": "string", "description": "What to avoid (--no)."},
            "image_urls": urls(0, 5, "Optional images that guide the result (image prompts)."),
        },
        required=["prompt"],
        docs_url=DOCS,
        notes=[
            "Midjourney returns four images per task (the four tiles of its grid).",
            "Runs only on APIMart. relax is the cheapest speed but may queue for a long time.",
        ],
    )
]


def _version(value: str) -> str | None:
    return None if value.startswith("niji") else value


def _build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    version = source.get("version", "7")
    if version.startswith("niji"):
        out["niji"] = True
        out["version"] = version.removeprefix("niji ")
    if out.pop("raw", False):
        out["style"] = "raw"
    return out


def _price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
    version = str(i.get("version", "7"))
    tag = f"niji{version.removeprefix('niji ')}" if version.startswith("niji") else f"v{version}"
    speed = i.get("speed", "fast")
    return per_unit(p, f"midjourney|imagine-{tag}" + ("" if speed == "relax" else f"-{speed}"))


def apimart() -> dict[str, Route]:
    provider = "apimart"
    spec = Spec(
        provider, "midjourney",
        keep=("prompt", "speed", "stylize", "chaos", "weird", "seed", "negative_prompt", "image_urls", "raw"),
        rename={"aspect_ratio": "size"},
        convert={"version": _version},
        build=_build,
    )  # fmt: skip
    return {MODEL_ID: Route(provider, "midjourney", spec, _price)}


APIMART_PATHS = {"midjourney": "/v1/midjourney/generations"}
