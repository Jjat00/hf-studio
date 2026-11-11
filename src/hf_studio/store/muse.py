"""Muse Image en APIMart (`muse-image-ext`). Higgsfield y KIE no lo venden.

Fuentes (revisadas el 2026-11-11):
- APIMart `muse-image-ext`, `POST /v1/images/generations`:
  https://docs.apimart.ai/en/api-reference/images/muse-image-ext/generation.md. Una imagen WebP por tarea
  (`n` = 1), texto a imagen o hasta 9 referencias (11 MiB en total), `aspect_ratio` con 7 relaciones; sin ella,
  texto a imagen da 1:1 y con referencias sigue su composición (no se manda `"auto"`). El modelo decide el tamaño:
  no hay niveles 1K/2K/4K. No acepta `seed`, `negative_prompt` ni `output_format`.
- Precio fijo por imagen (tabla pública de APIMart): `muse-image-ext|default`.
- APIMart no dice quién hace el modelo; el id lógico usa `muse/` en vez de inventar un fabricante.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, urls

DOCS = "https://docs.apimart.ai/en/api-reference/images/muse-image-ext/generation"
APIMART_MODEL = "muse-image-ext"
RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]


def _models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
        edit = mode == "edit"
        properties: dict[str, Any] = {
            "prompt": prompt(
                description="What to generate or, with images, what to change and what to keep."
            ),
            "aspect_ratio": choice(
                ["auto", *RATIOS], "auto", "Output aspect ratio; auto follows the reference images."
            )
            if edit
            else choice(RATIOS, "1:1", "Output aspect ratio."),
        }
        required = ["prompt"]
        if edit:
            properties["image_urls"] = urls(1, 9, "One to nine reference images (11 MB in total at most).")
            required.append("image_urls")
        found.append(
            model(
                f"muse/muse-image/{mode}",
                name="Muse Image",
                workflow=workflow,
                family="muse-image",
                output="image",
                capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                properties=properties,
                required=required,
                docs_url=DOCS,
                notes=["Runs on APIMart only. One WebP image per request; the model picks the pixel size."],
            )
        )
    return found


MODELS = _models()


def _ratio(value: str) -> str | None:
    """`auto` no se envía: APIMart pide omitir la relación para que siga a las referencias."""
    return None if value == "auto" else value


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for mode in ("text-to-image", "edit"):
        spec = Spec(
            provider, APIMART_MODEL,
            keep=("prompt", "image_urls"),
            convert={"aspect_ratio": _ratio},
            fixed={"n": 1},
        )  # fmt: skip
        routes[f"muse/muse-image/{mode}"] = Route(
            provider, APIMART_MODEL, spec, lambda i, h, p: per_unit(p, f"{APIMART_MODEL}|default")
        )
    return routes


APIMART_IMAGE_MODELS = frozenset({APIMART_MODEL})
