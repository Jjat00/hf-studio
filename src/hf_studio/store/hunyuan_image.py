"""HY Image 3.5 Preview (Hunyuan, Tencent) en APIMart. Higgsfield y KIE no lo venden.

Fuentes (revisadas el 2026-11-11):
- APIMart `hy-image-v3.5-preview`, `POST /v1/images/generations` (un mismo id para texto a imagen y edición con
  `image_urls`): https://docs.apimart.ai/en/api-reference/images/hy-image-v3.5-preview/generation.md. `size` con
  10 relaciones o `auto` (en texto a imagen es 1:1; con referencias sigue la de la imagen), `resolution`
  1K/2K/4K, hasta 5 referencias, `negative_prompt`, `seed` (0 es aleatoria) y una sola imagen por tarea (`n` = 1).
- Precio fijo por imagen y nivel (tabla pública de APIMart): `hy-image-v3.5-preview|1K`, `|2K` y `|4K`. Con una
  relación de aspecto se cobra por el nivel de `resolution`.

Fuera a propósito: el tamaño exacto en píxeles (`width`/`height` o `size` como `2000x1104`), que se cobra por el
lado corto y no aporta nada que las relaciones y los niveles no den.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.apimart.ai/en/api-reference/images/hy-image-v3.5-preview/generation"
APIMART_MODEL = "hy-image-v3.5-preview"
RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


def _models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
        edit = mode == "edit"
        properties: dict[str, Any] = {
            "prompt": prompt(
                description="What to generate or, with images, what to change and what to keep."
            ),
            "aspect_ratio": choice(
                ["auto", *RATIOS], "auto", "Output aspect ratio; auto follows the first reference image."
            )
            if edit
            else choice(RATIOS, "1:1", "Output aspect ratio."),
            "resolution": choice(["1k", "2k", "4k"], "1k", "Output resolution tier."),
            "negative_prompt": {"type": "string", "description": "What to keep out of the image."},
            "seed": {
                "type": "integer",
                "minimum": 1,
                "maximum": 2147483647,
                "description": "Fixed seed for repeatable results.",
            },
        }
        required = ["prompt"]
        if edit:
            properties["image_urls"] = urls(1, 5, "One to five reference images to edit or combine.")
            required.append("image_urls")
        found.append(
            model(
                f"tencent/hy-image-3.5-preview/{mode}",
                name="HY Image 3.5 Preview",
                workflow=workflow,
                family="hy-image-3.5-preview",
                output="image",
                capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                properties=properties,
                required=required,
                docs_url=DOCS,
                notes=[
                    "Runs on APIMart only. Tencent Hunyuan image model, preview release; one image per request."
                ],
            )
        )
    return found


MODELS = _models()


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for mode in ("text-to-image", "edit"):
        spec = Spec(
            provider, APIMART_MODEL,
            keep=("prompt", "resolution", "negative_prompt", "seed", "image_urls"),
            rename={"aspect_ratio": "size"},
            convert={"resolution": upper},
            fixed={"n": 1},
        )  # fmt: skip
        routes[f"tencent/hy-image-3.5-preview/{mode}"] = Route(
            provider, APIMART_MODEL, spec,
            lambda i, h, p: per_unit(p, f"{APIMART_MODEL}|{upper(i.get('resolution', '1k'))}"),
        )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({APIMART_MODEL})
