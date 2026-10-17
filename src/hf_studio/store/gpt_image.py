"""GPT Image (OpenAI) en las tiendas. Higgsfield solo lo usa dentro de Marketing Studio.

Fuentes (revisadas el 2026-10-17):
- APIMart `gpt-image-2.5-ext`: https://docs.apimart.ai/en/api-reference/images/gpt-image-2.5-ext/generation.md
  (`version` flare|sunburst, `size`, `resolution` 1K/2K/4K, `n` 1–4, hasta 16 `image_urls`). Precio por
  imagen entregada: `gpt-image-2.5-ext|<version>@<RES>`. Es un canal «ext» (no oficial).
- KIE `gpt-image-2-5-<version>-text-to-image` / `-image-to-image`:
  https://docs.kie.ai/market/gpt/gpt-image-2-5-flare-text-to-image.md (y las otras tres). Una imagen por
  tarea, `background` solo en 1K, hasta 16 `input_urls`. Precio `gpt-image-2-5-<version>, <modo>, <res>`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, only_default, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.kie.ai/market/gpt/gpt-image-2-5-flare-text-to-image"
VERSIONS = {"flare": "Flare", "sunburst": "Sunburst"}
RATIOS = ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "21:9", "5:4", "4:5"]
KIE_RATIOS = {"auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "21:9"}
APIMART_RATIOS = {"auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"}


def _id(version: str, mode: str) -> str:
    return f"openai/gpt-image-2.5/{version}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for version, label in VERSIONS.items():
        for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
            properties: dict[str, Any] = {
                "prompt": prompt(20000, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(RATIOS, "auto", "Output aspect ratio; auto lets the model choose."),
                "resolution": choice(["1k", "2k", "4k"], "1k", "Output resolution tier."),
                "num_images": choice([1, 2, 3, 4], 1, "Images per request (more than one only on APIMart)."),
                "background": choice(
                    ["auto", "opaque", "transparent"], "auto",
                    "Background; transparent or opaque only at 1k and only on KIE.",
                ),
            }  # fmt: skip
            required = ["prompt"]
            if mode == "edit":
                properties["image_urls"] = urls(1, 16, "One to sixteen images to edit or use as references.")
                required.append("image_urls")
            found.append(
                model(
                    _id(version, mode),
                    name=f"GPT Image 2.5 {label}",
                    workflow=workflow,
                    family=f"gpt-image-2.5-{version}",
                    output="image",
                    capabilities=["text-to-image"]
                    if mode == "text-to-image"
                    else ["edit", "image-references"],
                    properties=properties,
                    required=required,
                    docs_url=DOCS,
                    notes=[
                        (
                            "OpenAI's GPT Image 2.5. Higgsfield does not sell it on its own: it runs on APIMart "
                            "(unofficial ext channel) or KIE."
                        ),
                        "num_images above 1 only runs on APIMart; KIE makes one image per task.",
                    ],
                )
            )
    return found


MODELS = _models()


def apimart() -> dict[str, Route]:
    provider, ext = "apimart", "gpt-image-2.5-ext"
    routes = {}
    for version in VERSIONS:
        for mode in ("text-to-image", "edit"):
            spec = Spec(
                provider, ext,
                keep=("prompt", "resolution", "image_urls"),
                rename={"aspect_ratio": "size", "num_images": "n"},
                convert={"resolution": upper, "background": only_default("background", "auto")},
                allowed={"aspect_ratio": APIMART_RATIOS},
                fixed={"version": version},
            )  # fmt: skip
            routes[_id(version, mode)] = Route(
                provider, ext, spec,
                lambda i, h, p, v=version: per_unit(
                    p, f"{ext}|{v}@{str(i.get('resolution', '1k')).upper()}", i.get("num_images", 1)
                ),
                official=False,
                notes=("Unofficial APIMart channel (ext): cheaper, may be less stable",),
            )  # fmt: skip
    return routes


def _kie_background(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if out.get("background", "auto") == "auto":
        out.pop("background", None)  # el valor por defecto de KIE; no se envía para que valga en 2K y 4K
    elif source.get("resolution", "1k") != "1k":
        raise unsupported("kie", "KIE only sets a transparent or opaque background at 1k")
    return out


def kie() -> dict[str, Route]:
    provider = "kie"
    routes = {}
    for version in VERSIONS:
        for mode, kie_mode in (("text-to-image", "text-to-image"), ("edit", "image-to-image")):
            name = f"gpt-image-2-5-{version}-{kie_mode}"
            spec = Spec(
                provider, name,
                keep=("prompt", "aspect_ratio", "resolution", "background"),
                rename={"image_urls": "input_urls"},
                convert={"resolution": upper, "num_images": only_default("num_images", 1)},
                allowed={"aspect_ratio": KIE_RATIOS},
                build=_kie_background,
            )  # fmt: skip
            routes[_id(version, mode)] = Route(
                provider, name, spec,
                lambda i, h, p, v=version, m=kie_mode: per_unit(
                    p, f"gpt-image-2-5-{v}, {m}, {i.get('resolution', '1k')}"
                ),
            )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({"gpt-image-2.5-ext"})
