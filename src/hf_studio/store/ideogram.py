"""Ideogram V3 e Ideogram Character en KIE. Ideogram 4.0 ya está en el catálogo de Higgsfield (`ideogram/v4.0`).

Fuentes (revisadas el 2026-10-17), todas en la API unificada de KIE (`jobs/createTask`):
- https://docs.kie.ai/market/ideogram/v3-text-to-image.md, v3-edit.md (relleno con máscara), v3-remix.md
- https://docs.kie.ai/market/ideogram/character.md, character-edit.md, character-remix.md (una sola imagen del
  personaje en `reference_image_urls`)
`image_size` usa los nombres de KIE (square_hd = 1:1 grande, portrait_16_9 = 9:16…) y `num_images` va como texto.
Precio por imagen según la velocidad: `ideogram v3, text-to-image, <speed>`, `ideogram v3-edit, image-to-image,
<speed>`, `ideogram character-remix, image-to-image, <speed>`… (no hay fila de APIMart: solo KIE).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.kie.ai/market/ideogram"
SIZES = ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
SPEEDS = ["TURBO", "BALANCED", "QUALITY"]
SEED = {"type": "integer", "description": "Fixed seed for repeatable results."}
NOTE = "Only KIE sells it (not Higgsfield or APIMart); Ideogram 4.0 is the Higgsfield model."


def _field(kind: str) -> dict[str, Any]:
    return {
        "rendering_speed": choice(
            SPEEDS, "BALANCED", "Faster and cheaper (TURBO) or slower and better (QUALITY)."
        ),
        "expand_prompt": {
            "type": "boolean",
            "default": True,
            "description": "Let MagicPrompt expand the prompt.",
        },
        "image_size": choice(SIZES, "square_hd", "Output size preset (square is smaller than square_hd)."),
        "num_images": choice([1, 2, 3, 4], 1, "Images per request."),
        "negative_prompt": {
            "type": "string",
            "maxLength": 500,
            "description": "What to keep out of the image.",
        },
        "seed": SEED,
        "mask_url": url("Mask with the same size as the image; the masked area is redrawn."),
        "v3_style": choice(["AUTO", "GENERAL", "REALISTIC", "DESIGN"], "AUTO", "Style type."),
        "character_style": choice(["AUTO", "REALISTIC", "FICTION"], "AUTO", "Style type."),
        "character_image_url": url("Image of the character to keep consistent."),
    }[kind]


# (id lógico, modelo de KIE, nombre, flujo, capacidades, campos, obligatorios, prefijo de la fila de precio)
VARIANTS: list[tuple[str, str, str, str, list[str], dict[str, Any], list[str], str]] = [
    (
        "ideogram/v3/text-to-image", "ideogram/v3-text-to-image", "Ideogram V3", "Text to image", ["text-to-image"],
        {"prompt": prompt(5000), "rendering_speed": _field("rendering_speed"), "style": _field("v3_style"),
         "expand_prompt": _field("expand_prompt"), "image_size": _field("image_size"),
         "negative_prompt": {**_field("negative_prompt"), "maxLength": 5000}, "seed": SEED},
        ["prompt"], "ideogram v3, text-to-image",
    ),
    (
        "ideogram/v3/edit", "ideogram/v3-edit", "Ideogram V3", "Edit with mask", ["edit"],
        {"prompt": prompt(5000, "What to draw inside the masked area."), "image_url": url("Image to edit."),
         "mask_url": _field("mask_url"), "rendering_speed": _field("rendering_speed"),
         "expand_prompt": _field("expand_prompt"), "seed": SEED},
        ["prompt", "image_url", "mask_url"], "ideogram v3-edit, image-to-image",
    ),
    (
        "ideogram/v3/remix", "ideogram/v3-remix", "Ideogram V3", "Remix", ["edit"],
        {"prompt": prompt(5000, "What the remixed image should show."), "image_url": url("Image to remix."),
         "strength": {"type": "number", "minimum": 0.01, "maximum": 1, "default": 0.8,
                      "description": "How much of the input image to keep."},
         "rendering_speed": _field("rendering_speed"), "style": _field("v3_style"),
         "expand_prompt": _field("expand_prompt"), "image_size": _field("image_size"),
         "num_images": _field("num_images"), "negative_prompt": {**_field("negative_prompt"), "maxLength": 5000},
         "seed": SEED},
        ["prompt", "image_url"], "ideogram v3-remix, image-to-image",
    ),
    (
        "ideogram/v3/character", "ideogram/character", "Ideogram Character", "Character scene",
        ["text-to-image", "image-references"],
        {"prompt": prompt(5000, "The scene to place the character in."),
         "character_image_url": _field("character_image_url"), "rendering_speed": _field("rendering_speed"),
         "style": _field("character_style"), "expand_prompt": _field("expand_prompt"),
         "image_size": _field("image_size"), "num_images": _field("num_images"),
         "negative_prompt": {**_field("negative_prompt"), "maxLength": 5000}, "seed": SEED},
        ["prompt", "character_image_url"], "ideogram character, image-to-image",
    ),
    (
        "ideogram/v3/character-edit", "ideogram/character-edit", "Ideogram Character", "Character edit",
        ["edit", "image-references"],
        {"prompt": prompt(5000, "What to draw inside the masked area."), "image_url": url("Image to edit."),
         "mask_url": _field("mask_url"), "character_image_url": _field("character_image_url"),
         "rendering_speed": _field("rendering_speed"), "style": _field("character_style"),
         "expand_prompt": _field("expand_prompt"), "num_images": _field("num_images"), "seed": SEED},
        ["prompt", "image_url", "mask_url", "character_image_url"], "ideogram character-edit, image-to-image",
    ),
    (
        "ideogram/v3/character-remix", "ideogram/character-remix", "Ideogram Character", "Character remix",
        ["edit", "image-references"],
        {"prompt": prompt(5000, "What the remixed image should show."), "image_url": url("Image to remix."),
         "character_image_url": _field("character_image_url"),
         "image_urls": urls(0, 5, "Optional style reference images."),
         "strength": {"type": "number", "minimum": 0.1, "maximum": 1, "default": 0.8,
                      "description": "How much of the input image to keep."},
         "rendering_speed": _field("rendering_speed"), "style": _field("character_style"),
         "expand_prompt": _field("expand_prompt"), "image_size": _field("image_size"),
         "num_images": _field("num_images"), "negative_prompt": _field("negative_prompt"), "seed": SEED},
        ["prompt", "image_url", "character_image_url"], "ideogram character-remix, image-to-image",
    ),
]  # fmt: skip


def _models() -> list[dict[str, Any]]:
    found = []
    for logical, kie_model, name, workflow, capabilities, properties, required, _ in VARIANTS:
        notes = [NOTE]
        if "character_image_url" in properties:
            notes.append("Ideogram takes a single character image.")
        found.append(
            model(
                logical,
                name=name,
                workflow=workflow,
                family="ideogram-character" if "character" in kie_model else "ideogram-v3",
                output="image",
                capabilities=capabilities,
                properties=properties,
                required=required,
                docs_url=f"{DOCS}/{kie_model.split('/')[1]}",
                notes=notes,
            )
        )
    return found


MODELS = _models()


def _character(value: str) -> list[str]:
    return [value]


def _count(value: int) -> str:
    return str(value)


def kie() -> dict[str, Route]:
    provider = "kie"
    routes = {}
    for logical, name, _, _, _, properties, _, row in VARIANTS:
        # Solo se convierten los campos que tiene la variante: uno de otra variante es `unsupported`.
        converters = {"character_image_url": _character, "num_images": _count}
        spec = Spec(
            provider, name,
            keep=tuple(k for k in properties if k not in converters),
            rename={"character_image_url": "reference_image_urls"},
            convert={k: f for k, f in converters.items() if k in properties},
        )  # fmt: skip
        routes[logical] = Route(
            provider, name, spec,
            lambda i, h, p, r=row: per_unit(p, f"{r}, {str(i.get('rendering_speed', 'BALANCED')).lower()}",
                                            i.get("num_images", 1)),
        )  # fmt: skip
    return routes
