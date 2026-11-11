"""MAI Image 2.6 y 2.6 Flash (Microsoft) en APIMart. Higgsfield y KIE no los venden.

Fuentes (revisadas el 2026-11-11):
- APIMart `mai-image-2.6` y `mai-image-2.6-flash`, `POST /v1/images/generations` (un mismo id para texto a imagen
  y edición con `image_urls`): https://docs.apimart.ai/en/api-reference/images/mai-image-2.6/generation.md. Una
  imagen por tarea (`n` = 1), PNG. En texto a imagen, `size` es una relación (con `resolution` 1K/2K y su tabla
  de píxeles) o `auto` (la elige el modelo según el prompt). Con referencias (1 a 5) el modelo decide el tamaño,
  unos 1 MP con la relación de las imágenes: `size` y `resolution` no cuentan. `web_grounding` busca información
  actual antes de generar.
- Precio: por tokens de entrada y salida (`billing_type: tiered_token` en la tabla pública), así que la ruta no
  tiene precio (`None`) y la opción sale como «unavailable»: generar exige aceptar un costo desconocido.
  APIMart cobra por adelantado un importe por nivel y luego ajusta al consumo real, devolviendo o cobrando más; no
  es un tope, así que no se usa como `reserve`.

Fuera a propósito: el tamaño exacto en píxeles (`width`/`height` o `size` como `1536x1024`) y las relaciones fuera
de la tabla de la documentación (admite cualquier relación entera de 1:4 a 4:1, pero solo publica los píxeles de
estas).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.apimart.ai/en/api-reference/images/mai-image-2.6/generation"
TIERS = {"mai-image-2.6": "MAI Image 2.6", "mai-image-2.6-flash": "MAI Image 2.6 Flash"}
RATIOS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21", "4:1", "1:4"]
TOKENS = "Billed by tokens: the price is only known after generating."


def _models() -> list[dict[str, Any]]:
    found = []
    for tier, label in TIERS.items():
        for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
            edit = mode == "edit"
            properties: dict[str, Any] = {
                "prompt": prompt(description="What to generate or, with images, what to change and combine."),
                "web_grounding": {
                    "type": "boolean",
                    "default": False,
                    "description": "Look up current information first (real people, places or events).",
                },
            }
            required = ["prompt"]
            if edit:
                properties["image_urls"] = urls(
                    1, 5, "One image to edit, or up to five to combine; the model picks the output size."
                )
                required.append("image_urls")
            else:
                properties["aspect_ratio"] = choice(
                    [*RATIOS, "auto"],
                    "1:1",
                    "Output aspect ratio; auto lets the model choose it from the prompt.",
                )
                properties["resolution"] = choice(
                    ["1k", "2k"], "1k", "Output size tier (1k square is 1024 px, 2k square 1536 px)."
                )
            notes = [TOKENS, "Runs on APIMart only. One PNG image per request."]
            if tier.endswith("flash"):
                notes.append("Faster, cheaper version with slightly lower image quality.")
            found.append(
                model(
                    f"microsoft/{tier}/{mode}",
                    name=label,
                    workflow=workflow,
                    family=tier,
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


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for tier in TIERS:
        for mode in ("text-to-image", "edit"):
            # Con referencias, el tamaño lo decide el modelo: la edición no envía relación ni nivel.
            edit = mode == "edit"
            spec = Spec(
                provider, tier,
                keep=("prompt", "web_grounding", "image_urls") if edit else ("prompt", "web_grounding"),
                rename={} if edit else {"aspect_ratio": "size"},
                convert={} if edit else {"resolution": upper},
                fixed={"n": 1},
            )  # fmt: skip
            routes[f"microsoft/{tier}/{mode}"] = Route(
                provider, tier, spec, lambda i, h, p: None, settles_later=True, notes=(TOKENS,)
            )
    return routes


APIMART_IMAGE_MODELS = frozenset(TIERS)
