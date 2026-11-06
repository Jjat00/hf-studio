"""GPT Image 2.6 (OpenAI) en las tiendas. Higgsfield no lo vende.

Fuentes (revisadas el 2026-11-06):
- APIMart `gpt-image-2.6-ext`: https://docs.apimart.ai/en/api-reference/images/gpt-image-2.6-ext/generation.md
  (`version` flare|sunburst, `size` auto + 10 relaciones, solo `resolution` 1k: 2k/4k responden 403
  `model_price_not_configured`; `n` solo 1; `quality` y `complexity` no cambian el precio; hasta 16
  `image_urls`). Precio por imagen: `gpt-image-2.6-ext|<version>@1K`. Canal «ext» (no oficial).
- KIE `gpt-image-2-6/economy-text-to-image` / `-image-to-image`:
  https://docs.kie.ai/market/gpt/gpt-image-2-6-economy-text-to-image.md (solo 1K, 8 relaciones, solo png,
  `background`, hasta 16 `input_urls`). Precio `gpt-image-2-6-economy, <modo>, 1k`.
Quedan fuera los canales que cobran por tokens (KIE `gpt-image-2-6/flare-*` y `sunburst-*`, APIMart
`gpt-image-2.6-flare` y `-sunburst` oficiales): los tokens de salida no se conocen antes de generar, así que no
se pueden cotizar. Son los únicos con 2K y 4K.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, urls

EXT = "gpt-image-2.6-ext"
EXT_DOCS = "https://docs.apimart.ai/en/api-reference/images/gpt-image-2.6-ext/generation"
ECONOMY_DOCS = "https://docs.kie.ai/market/gpt/gpt-image-2-6-economy-text-to-image"
VERSIONS = {"flare": "Flare", "sunburst": "Sunburst"}
EXT_RATIOS = ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "21:9"]
ECONOMY_RATIOS = ["auto", "1:1", "16:9", "9:16", "3:2", "2:3", "21:9", "4:3"]
MODES = {"text-to-image": "Text to image", "edit": "Edit images"}


def _id(version: str, mode: str) -> str:
    return f"openai/gpt-image-2.6/{version}/{mode}"


def _entry(version: str, mode: str, label: str, properties: dict[str, Any], docs: str, notes: list[str]):
    required = ["prompt"]
    if mode == "edit":
        properties["image_urls"] = urls(
            1, 16, "One to sixteen images to edit or use as references, by order."
        )
        required.append("image_urls")
    return model(
        _id(version, mode),
        name=f"GPT Image 2.6 {label}",
        workflow=MODES[mode],
        family=f"gpt-image-2.6-{version}",
        output="image",
        capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
        properties=properties,
        required=required,
        docs_url=docs,
        notes=notes,
    )


def _models() -> list[dict[str, Any]]:
    found = []
    for version, label in VERSIONS.items():
        for mode in MODES:
            properties: dict[str, Any] = {
                "prompt": prompt(32000, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(EXT_RATIOS, "auto", "Output aspect ratio; auto lets the model choose."),
                "quality": choice(
                    ["auto", "low", "medium", "high", "xhigh", "max"], "auto",
                    "Rendering quality; higher is slower, same price.",
                ),
                "complexity": choice(
                    ["low", "medium", "high"], "high",
                    "Planning level: low for simple icons and focused edits, high for dense text and layouts.",
                ),
                "output_format": choice(["png", "jpeg", "webp"], "png", "Image file format."),
            }  # fmt: skip
            focus = "speed first" if version == "flare" else "detail and edit consistency first"
            notes = [
                (
                    f"OpenAI's GPT Image 2.6 {label} ({focus}). Runs on APIMart's unofficial ext channel at 1K, "
                    "one image per request."
                ),
                "2K and 4K exist only on channels billed by tokens, which cannot be quoted before generating.",
            ]
            found.append(_entry(version, mode, label, properties, EXT_DOCS, notes))
    for mode in MODES:
        properties = {
            "prompt": prompt(32000, "What to generate or, with images, what to change and what to keep."),
            "aspect_ratio": choice(
                ECONOMY_RATIOS, "auto", "Output aspect ratio; auto lets the model choose."
            ),
            "background": choice(["auto", "opaque", "transparent"], "auto", "Background (PNG output)."),
        }
        notes = ["The cost-efficient GPT Image 2.6 variant: 1K PNG only, one image per task, on KIE."]
        found.append(_entry("economy", mode, "Economy", properties, ECONOMY_DOCS, notes))
    return found


MODELS = _models()


def apimart() -> dict[str, Route]:
    routes = {}
    for version in VERSIONS:
        for mode in MODES:
            spec = Spec(
                "apimart", EXT,
                keep=("prompt", "quality", "complexity", "output_format", "image_urls"),
                rename={"aspect_ratio": "size"},
                fixed={"version": version, "resolution": "1k", "n": 1},
            )  # fmt: skip
            routes[_id(version, mode)] = Route(
                "apimart", EXT, spec,
                lambda i, h, p, v=version: per_unit(p, f"{EXT}|{v}@1K"),
                official=False,
                notes=("Unofficial APIMart channel (ext): cheaper, may be less stable",),
            )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    routes = {}
    for mode, kie_mode in (("text-to-image", "text-to-image"), ("edit", "image-to-image")):
        name = f"gpt-image-2-6/economy-{kie_mode}"
        spec = Spec(
            "kie", name,
            keep=("prompt", "aspect_ratio", "background"),
            rename={"image_urls": "input_urls"},
        )  # fmt: skip
        routes[_id("economy", mode)] = Route(
            "kie", name, spec, lambda i, h, p, m=kie_mode: per_unit(p, f"gpt-image-2-6-economy, {m}, 1k")
        )
    return routes


APIMART_IMAGE_MODELS = frozenset({EXT})
