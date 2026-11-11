"""MiniMax H3 Image en KIE (texto a imagen y edición). Higgsfield solo tiene MiniMax H3 de video (`minimax/h3/*`)
y APIMart no lo vende; el video de las tiendas está en `store/minimax.py`.

Fuentes (revisadas el 2026-11-11):
- KIE, API unificada (`jobs/createTask`): https://docs.kie.ai/market/minimax-h3/text-to-image.md
  (`minimax-h3/text-to-image`) y https://docs.kie.ai/market/minimax-h3/image-edit.md (`minimax-h3/image-edit`,
  1 a 16 referencias que el prompt cita como `<Picture 1>`, `<Picture 2>`…). Una imagen por tarea, prompt ≤ 5000,
  `resolution` 1K/2K/4K (2K por defecto, con su tabla de píxeles por relación), `aspect_ratio` con 10 relaciones
  o `auto` (en texto a imagen la elige el reescritor del prompt; en edición sigue a la primera referencia),
  `expand_prompt` (encendido por defecto), `seed`, `output_format` png o jpeg.
- Precio por imagen (tabla pública de KIE): `minimax h3 image, text to image, 1k / 2k (≤4.5 mp)` y
  `… 4k (≤20 mp)`; en edición, las mismas filas de `image edit` más `minimax h3 image, image edit, reference image
  (each)` por cada referencia, la primera incluida.

Fuera a propósito: el tamaño exacto en píxeles (`width`/`height`), que se cobra por megapíxeles y no aporta nada
que las relaciones y los niveles no den.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.kie.ai/market/minimax-h3"
RATIOS = ["1:1", "5:4", "4:5", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"]
MODES = {"text-to-image": ("minimax-h3/text-to-image", "text to image"),
         "edit": ("minimax-h3/image-edit", "image edit")}  # fmt: skip


def _models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
        edit = mode == "edit"
        properties: dict[str, Any] = {
            "prompt": prompt(
                5000,
                "What to generate or, with images, what to change; cite them as <Picture 1>, <Picture 2>…"
                if edit
                else "What to generate.",
            ),
            "aspect_ratio": choice(
                ["auto", *RATIOS],
                "auto" if edit else "1:1",
                "Output aspect ratio; auto follows the first reference image."
                if edit
                else "Output aspect ratio; auto lets the prompt rewriter choose it (1:1 without expand_prompt).",
            ),
            "resolution": choice(["1k", "2k", "4k"], "2k", "Output size tier: about 1, 4 or 16 megapixels."),
            "expand_prompt": {
                "type": "boolean",
                "default": True,
                "description": "Rewrite the prompt into a detailed English description first.",
            },
            "seed": {
                "type": "integer",
                "minimum": 0,
                "maximum": 2147483647,
                "description": "Fixed seed; results repeat only with expand_prompt off.",
            },
            "output_format": choice(["png", "jpeg"], "png", "Output file format."),
        }
        required = ["prompt"]
        notes = ["Only KIE sells it (not Higgsfield or APIMart). One image per request."]
        if edit:
            properties["image_urls"] = urls(1, 16, "One to sixteen reference images, in prompt order.")
            required.append("image_urls")
            notes.append("Each reference image adds a small charge, the first one included.")
        found.append(
            model(
                f"minimax/h3-image/{mode}",
                name="MiniMax H3 Image",
                workflow=workflow,
                family="minimax-h3-image",
                output="image",
                capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                properties=properties,
                required=required,
                docs_url=f"{DOCS}/{'image-edit' if edit else 'text-to-image'}",
                notes=notes,
            )
        )
    return found


MODELS = _models()


def _price(kie_mode: str):
    def price(i: dict[str, Any], hints: dict[str, Any], prices: dict[str, float]) -> float | None:
        tier = "4k (≤20 mp)" if i.get("resolution", "2k") == "4k" else "1k / 2k (≤4.5 mp)"
        image = per_unit(prices, f"minimax h3 image, {kie_mode}, {tier}")
        if kie_mode != "image edit" or image is None:
            return image
        refs = per_unit(
            prices, "minimax h3 image, image edit, reference image (each)", len(i.get("image_urls") or [])
        )
        return None if refs is None else round(image + refs, 4)

    return price


def kie() -> dict[str, Route]:
    provider = "kie"
    routes = {}
    for mode, (name, kie_mode) in MODES.items():
        spec = Spec(
            provider, name,
            keep=("prompt", "aspect_ratio", "expand_prompt", "seed", "output_format", "image_urls"),
            convert={"resolution": upper},
        )  # fmt: skip
        routes[f"minimax/h3-image/{mode}"] = Route(provider, name, spec, _price(kie_mode))
    return routes
