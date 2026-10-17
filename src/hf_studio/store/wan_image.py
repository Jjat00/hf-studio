"""Wan 2.7 Image y Wan 2.7 Image Pro (Alibaba) en las tiendas. Higgsfield solo tiene los videos de Wan.

Fuentes (revisadas el 2026-10-17):
- APIMart `wan2.7-image` / `wan2.7-image-pro`: https://docs.apimart.ai/en/api-reference/images/wan2.7-image/generation.md
  (`size` como relación + `resolution` 1K/2K/4K, 4K solo en Pro sin imágenes ni modo secuencial; `n` 1–4 o 1–12
  en modo secuencial; hasta 9 `image_urls`; `thinking_mode` por defecto true). Precio por imagen
  `wan2.7-image|default`, `wan2.7-image-pro|default`.
- KIE `wan/2-7-image` / `wan/2-7-image-pro`: https://docs.kie.ai/market/wan/2-7-image.md y
  https://docs.kie.ai/market/wan/2-7-image-pro.md (`input_urls` hasta 9, `aspect_ratio` sin imágenes, `n` por
  defecto 4, `thinking_mode` por defecto false, sin `negative_prompt`). Precio por imagen `wan 2.7 image` y
  `wan 2.7 image pro`.
Los valores por defecto de las tiendas no coinciden (n, thinking_mode, resolución): todo se envía explícito.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.apimart.ai/en/api-reference/images/wan2.7-image/generation"
TIERS = {"standard": ("wan2.7-image", "wan/2-7-image", "wan 2.7 image", "Wan 2.7 Image"),
         "pro": ("wan2.7-image-pro", "wan/2-7-image-pro", "wan 2.7 image pro", "Wan 2.7 Image Pro")}  # fmt: skip
RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "8:1", "1:8"]
APIMART_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}
KIE_RATIOS = {"1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"}
SEED = {
    "type": "integer",
    "minimum": 0,
    "maximum": 2147483647,
    "description": "Fixed seed for repeatable results.",
}


def _id(tier: str, mode: str) -> str:
    return f"wan/v2.7-image{'-pro' if tier == 'pro' else ''}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for tier, (_, _, _, label) in TIERS.items():
        for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
            edit = mode == "edit"
            sizes = ["1k", "2k", "4k"] if tier == "pro" and not edit else ["1k", "2k"]
            properties: dict[str, Any] = {
                "prompt": prompt(5000, "What to generate or, with images, what to change and what to keep."),
                "resolution": choice(sizes, "2k", "Output resolution tier."),
                "num_images": choice(list(range(1, 13)), 1, "Images per request: 1–4, or up to 12 in sequential mode."),
                "enable_sequential": {
                    "type": "boolean", "default": False,
                    "description": "Make a coherent series of images (storyboards) instead of independent ones.",
                },
                "negative_prompt": {"type": "string", "description": "What to keep out of the image (APIMart only)."},
                "seed": SEED,
            }  # fmt: skip
            required = ["prompt"]
            notes = [
                "Alibaba's Wan 2.7 image model. Higgsfield does not sell it: it runs on APIMart or KIE.",
                "negative_prompt only runs on APIMart.",
            ]
            if edit:
                properties["image_urls"] = urls(1, 9, "One to nine images to edit or combine.")
                required.append("image_urls")
                notes.append("The output takes the aspect ratio of the last input image.")
            else:
                properties["aspect_ratio"] = choice(RATIOS, "1:1", "Output aspect ratio.")
                properties["thinking_mode"] = {
                    "type": "boolean", "default": True,
                    "description": "Reason before drawing: better images, slower (ignored in sequential mode).",
                }  # fmt: skip
                notes.append("3:2 and 2:3 only run on APIMart; 21:9, 8:1 and 1:8 only on KIE.")
                if tier == "pro":
                    notes.append("4k is for text to image without sequential mode.")
            found.append(
                model(
                    _id(tier, mode),
                    name=label,
                    workflow=workflow,
                    family=f"wan-2.7-image{'-pro' if tier == 'pro' else ''}",
                    output="image",
                    capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                    properties=properties,
                    required=required,
                    docs_url=DOCS,
                    notes=notes,
                )
            )
    return found


MODELS = _models()


def _limits(provider: str):
    """Límites que valen igual en las dos tiendas: hasta 4 imágenes sin modo secuencial y 4K sin secuencia."""

    def check(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        sequential = source.get("enable_sequential", False)
        if not sequential and source.get("num_images", 1) > 4:
            raise unsupported(provider, "More than 4 images need sequential mode")
        if sequential and source.get("resolution") == "4k":
            raise unsupported(provider, "4k is not available in sequential mode")
        return out

    return check


def _price(row: str):
    return lambda i, h, p: per_unit(p, row, i.get("num_images", 1))


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for tier, (name, _, _, _) in TIERS.items():
        for mode in ("text-to-image", "edit"):
            spec = Spec(
                provider, name,
                keep=("prompt", "resolution", "enable_sequential", "negative_prompt", "seed", "thinking_mode",
                      "image_urls"),
                rename={"aspect_ratio": "size", "num_images": "n"},
                convert={"resolution": upper},
                allowed={"aspect_ratio": APIMART_RATIOS},
                fixed={"watermark": False},
                build=_limits(provider),
            )  # fmt: skip
            routes[_id(tier, mode)] = Route(provider, name, spec, _price(f"{name}|default"))
    return routes


APIMART_IMAGE_MODELS = frozenset(name for name, _, _, _ in TIERS.values())


def kie() -> dict[str, Route]:
    provider = "kie"
    routes = {}
    for tier, (_, name, row, _) in TIERS.items():
        for mode in ("text-to-image", "edit"):
            spec = Spec(
                provider, name,
                keep=("prompt", "aspect_ratio", "resolution", "enable_sequential", "seed", "thinking_mode"),
                rename={"num_images": "n", "image_urls": "input_urls"},
                convert={"resolution": upper},
                allowed={"aspect_ratio": KIE_RATIOS},
                fixed={"watermark": False},
                build=_limits(provider),
            )  # fmt: skip
            routes[_id(tier, mode)] = Route(provider, name, spec, _price(row))
    return routes
