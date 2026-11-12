"""MiniMax H3 Image (texto a imagen y edición) en KIE y APIMart, y su versión rápida H3 Image Highspeed solo en
APIMart. Higgsfield solo tiene MiniMax H3 de video (`minimax/h3/*`); el video de las tiendas está en
`store/minimax.py`.

Fuentes (KIE revisada el 2026-11-11; APIMart, el 2026-11-12):
- KIE, API unificada (`jobs/createTask`): https://docs.kie.ai/market/minimax-h3/text-to-image.md
  (`minimax-h3/text-to-image`) y https://docs.kie.ai/market/minimax-h3/image-edit.md (`minimax-h3/image-edit`,
  1 a 16 referencias que el prompt cita como `<Picture 1>`, `<Picture 2>`…). Una imagen por tarea, prompt ≤ 5000,
  `resolution` 1K/2K/4K (2K por defecto, con su tabla de píxeles por relación), `aspect_ratio` con 10 relaciones
  o `auto` (en texto a imagen la elige el reescritor del prompt; en edición sigue a la primera referencia),
  `expand_prompt` (encendido por defecto), `seed`, `output_format` png o jpeg.
- Precio por imagen en KIE (tabla pública): `minimax h3 image, text to image, 1k / 2k (≤4.5 mp)` y
  `… 4k (≤20 mp)`; en edición, las mismas filas de `image edit` más `minimax h3 image, image edit, reference image
  (each)` por cada referencia, la primera incluida.
- APIMart `minimax-h3-image` y `minimax-h3-image-highspeed`, `POST /v1/images/generations` (un mismo id para texto
  a imagen y edición con `image_urls`, 1 a 16):
  https://docs.apimart.ai/en/api-reference/images/minimax-h3-image/generation.md y
  https://docs.apimart.ai/en/api-reference/images/minimax-h3-image-highspeed/generation.md (mismos parámetros).
  `size` es la relación (`auto` o `X:Y` de 1:3 a 3:1), `resolution` 1K/2K/4K (4K por defecto en APIMart: se envía
  siempre), `prompt_optimizer` equivale a `expand_prompt`, `output_format` png/jpeg/webp, `n` = 1. Sin `seed` (lo
  ignora). Apagar el reescritor solo vale en texto a imagen y con una relación explícita (no `auto`); en edición
  va siempre encendido.
- Precio en APIMart: por tokens (`billing_type: tiered_token` en la tabla pública; Highspeed cobra el doble por
  token), así que esas rutas no tienen precio (`None`) y la opción sale como «unavailable», igual que MAI Image
  (`store/mai_image.py`).

Fuera a propósito: el tamaño exacto en píxeles (`width`/`height` o `size` como `2048x1152`), que KIE cobra por
megapíxeles y no aporta nada que las relaciones y los niveles no den; en APIMart, `watermark` y
`output_compression`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.kie.ai/market/minimax-h3"
APIMART_DOCS = "https://docs.apimart.ai/en/api-reference/images"
RATIOS = ["1:1", "5:4", "4:5", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"]
MODES = {"text-to-image": ("minimax-h3/text-to-image", "text to image"),
         "edit": ("minimax-h3/image-edit", "image edit")}  # fmt: skip
# Id lógico → id en APIMart. El estándar lo venden KIE y APIMart; Highspeed, solo APIMart.
TIERS = {"minimax/h3-image": "minimax-h3-image", "minimax/h3-image-highspeed": "minimax-h3-image-highspeed"}
TOKENS = "Billed by tokens: the price is only known after generating."


def _models() -> list[dict[str, Any]]:
    found = []
    for base, apimart_id in TIERS.items():
        fast = base.endswith("highspeed")
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
                "resolution": choice(
                    ["1k", "2k", "4k"], "2k", "Output size tier: about 1, 4 or 16 megapixels."
                ),
                "expand_prompt": {
                    "type": "boolean",
                    "default": True,
                    "description": "Rewrite the prompt into a detailed English description first.",
                },
                "output_format": choice(["png", "jpeg"], "png", "Output file format."),
            }
            if not fast:  # APIMart ignora la semilla: solo la honra KIE
                properties["seed"] = {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 2147483647,
                    "description": "Fixed seed (KIE only); results repeat only with expand_prompt off.",
                }
            required = ["prompt"]
            if fast:
                notes = [TOKENS, "Runs on APIMart only. One image per request.",
                         "Faster version of MiniMax H3 Image; APIMart charges twice the standard rate per token."]  # fmt: skip
            else:
                notes = [
                    (
                        "Runs on KIE (priced per image) and APIMart (billed by tokens: the price is only known "
                        "after generating), not on Higgsfield. One image per request."
                    ),
                ]
            if edit:
                properties["image_urls"] = urls(1, 16, "One to sixteen reference images, in prompt order.")
                required.append("image_urls")
                notes.append(
                    "The prompt is always rewritten when editing."
                    if fast
                    else "On KIE each reference image adds a small charge, the first one included."
                )
            if fast:
                docs_url = f"{APIMART_DOCS}/{apimart_id}/generation"
            else:
                docs_url = f"{DOCS}/{'image-edit' if edit else 'text-to-image'}"
            found.append(
                model(
                    f"{base}/{mode}",
                    name="MiniMax H3 Image Highspeed" if fast else "MiniMax H3 Image",
                    workflow=workflow,
                    family=apimart_id,
                    output="image",
                    capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                    properties=properties,
                    required=required,
                    docs_url=docs_url,
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


def _rewriter(edit: bool):
    """APIMart: en edición el reescritor no se apaga; en texto a imagen, apagarlo exige una relación explícita."""

    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if source.get("expand_prompt", True):
            return out
        if edit:
            raise unsupported("apimart", "APIMart always rewrites the prompt when editing")
        if source.get("aspect_ratio", "1:1") == "auto":
            raise unsupported("apimart", "APIMart needs an explicit aspect ratio with expand_prompt off")
        return out

    return build


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for base, name in TIERS.items():
        for mode in MODES:
            edit = mode == "edit"
            spec = Spec(
                provider, name,
                keep=("prompt", "output_format", "image_urls"),
                rename={"aspect_ratio": "size", "expand_prompt": "prompt_optimizer"},
                convert={"resolution": upper},
                fixed={"n": 1},
                build=_rewriter(edit),
            )  # fmt: skip
            routes[f"{base}/{mode}"] = Route(
                provider, name, spec, lambda i, h, p: None, settles_later=True, notes=(TOKENS,)
            )
    return routes


APIMART_IMAGE_MODELS = frozenset(TIERS.values())
