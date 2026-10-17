"""Qwen Image (Alibaba) 1, 2.0, 2.0 Pro y 2.1 en las tiendas. Qwen Image 3 ya está en el catálogo de Higgsfield
(`alibaba/qwen-image-3/*`) y no se repite aquí.

Fuentes (revisadas el 2026-10-17):
- APIMart `qwen-image-2.0` / `qwen-image-2.0-pro`: https://docs.apimart.ai/en/api-reference/images/qwen-image/generation.md
  (`size` 7 relaciones, `resolution` 1K/2K, `n` 1–6, `negative_prompt` ≤ 500, `image_urls` para editar, prompt
  ≤ 800). Precio fijo por imagen: `qwen-image-2.0|default`, `qwen-image-2.0-pro|default`.
- KIE `qwen/image-to-image` (Qwen Image 1): https://docs.kie.ai/market/qwen/image-to-image.md. Precio por imagen
  `qwen image, image-to-image`.
- No se rutan (revisión 88): KIE `qwen2/*` (Qwen Image 2.0) no tiene resolución ni publica su tamaño de salida,
  así que no garantiza el `1k` del esquema; `qwen/text-to-image` y `qwen/image-edit` cobran por megapíxel y KIE no
  publica cuántos tiene cada `image_size`.
- KIE `qwen2-1/text-to-image` y `qwen2-1/image-to-image` (Qwen Image 2.1):
  https://docs.kie.ai/market/qwen2-1/text-to-image.md (y image-to-image). Precio
  `qwen-image-2.1, text to image, <res>` e `image to image, <res>`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, upper, url, urls

APIMART_DOCS = "https://docs.apimart.ai/en/api-reference/images/qwen-image/generation"
KIE_DOCS = "https://docs.kie.ai/market/qwen"

# --- Esquemas compartidos -------------------------------------------------------------------------


V2_RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"]
APIMART_V2_RATIOS = set(V2_RATIOS)
V21_RATIOS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9", "9:21"]


def flag(default: bool, description: str) -> dict[str, Any]:
    return {"type": "boolean", "default": default, "description": description}


def number(default: float, minimum: float, maximum: float, description: str, integer: bool = False):
    return {
        "type": "integer" if integer else "number",
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "description": description,
    }


SEED = {
    "type": "integer",
    "minimum": 0,
    "maximum": 2147483647,
    "description": "Fixed seed for repeatable results.",
}
NEGATIVE = {"type": "string", "maxLength": 500, "description": "What to keep out of the image."}


def _v1_models() -> list[dict[str, Any]]:
    """Qwen Image 1, imagen a imagen: solo KIE, parámetros de difusión."""
    common: dict[str, Any] = {
        "seed": SEED,
        "negative_prompt": NEGATIVE,
        "acceleration": choice(
            ["none", "regular", "high"], "none", "Faster generation at some quality cost."
        ),
        "output_format": choice(["png", "jpeg"], "png", "Output file format."),
    }
    notes = ["Only KIE sells it (not Higgsfield or APIMart)."]
    return [
        model(
            "alibaba/qwen-image/image-to-image",
            name="Qwen Image",
            workflow="Image to image",
            family="qwen-image",
            output="image",
            capabilities=["edit"],
            properties={
                "prompt": prompt(5000, "What the new image should look like."),
                "image_url": url("Image to transform."),
                "strength": number(0.8, 0, 1, "Denoising strength: 1 remakes the image, 0 keeps it."),
                "num_inference_steps": number(30, 2, 250, "Diffusion steps.", integer=True),
                "guidance_scale": number(2.5, 0, 20, "How closely to follow the prompt."),
                **common,
            },
            required=["prompt", "image_url"],
            docs_url=f"{KIE_DOCS}/image-to-image",
            notes=notes,
        ),
    ]


def _v2_models() -> list[dict[str, Any]]:
    """Qwen Image 2.0 y 2.0 Pro: solo APIMart."""
    found = []
    for tier, label in (("qwen-image-2.0", "Qwen Image 2.0"), ("qwen-image-2.0-pro", "Qwen Image 2.0 Pro")):
        for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
            edit = mode == "edit"
            properties: dict[str, Any] = {
                "prompt": prompt(800, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(V2_RATIOS, "1:1", "Output aspect ratio."),
                "resolution": choice(["1k", "2k"], "1k", "Output resolution tier (2k is about 2048 px)."),
                "num_images": choice([1, 2, 3, 4, 5, 6], 1, "Images per request."),
                "negative_prompt": NEGATIVE,
            }
            required = ["prompt"]
            if edit:
                properties["image_urls"] = urls(1, 3, "One to three images to edit or use as references.")
                required.append("image_urls")
            notes = ["Runs on APIMart only."]
            found.append(
                model(
                    f"alibaba/{tier}/{mode}",
                    name=label,
                    workflow=workflow,
                    family=tier,
                    output="image",
                    capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                    properties=properties,
                    required=required,
                    docs_url=APIMART_DOCS,
                    notes=notes,
                )
            )
    return found


def _v21_models() -> list[dict[str, Any]]:
    """Qwen Image 2.1: solo KIE, con fondo transparente y edición local con máscara."""
    found = []
    for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
        edit = mode == "edit"
        properties: dict[str, Any] = {
            "prompt": prompt(5000, "What to generate or, with images, what to change and what to keep."),
            "aspect_ratio": choice(
                ["auto", *V21_RATIOS], "auto", "Output aspect ratio; auto follows the first image."
            )
            if edit
            else choice(V21_RATIOS, "1:1", "Output aspect ratio."),
            "resolution": choice(["1k", "2k"], "1k", "Output resolution tier."),
            "background": choice(
                ["opaque", "transparent"], "opaque", "Transparent needs png or webp output."
            ),
            "output_format": choice(["png", "webp", "jpeg"], "png", "Output file format."),
            "enhance_prompt": flag(True, "Rewrite the prompt into a fuller description first."),
            "seed": SEED,
        }
        required = ["prompt"]
        if edit:
            properties["image_urls"] = urls(
                1, 10, "One to ten images, in the order the prompt refers to them."
            )
            properties["mask_url"] = url(
                "Optional black and white mask (white = area to change); one image only."
            )
            required.append("image_urls")
        found.append(
            model(
                f"alibaba/qwen-image-2.1/{mode}",
                name="Qwen Image 2.1",
                workflow=workflow,
                family="qwen-image-2.1",
                output="image",
                capabilities=["edit", "image-references"] if edit else ["text-to-image"],
                properties=properties,
                required=required,
                docs_url=f"https://docs.kie.ai/market/qwen2-1/{'image-to-image' if edit else 'text-to-image'}",
                notes=["Only KIE sells it (not Higgsfield or APIMart)."],
            )
        )
    return found


MODELS = [*_v1_models(), *_v2_models(), *_v21_models()]


# --- APIMart --------------------------------------------------------------------------------------


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for tier in ("qwen-image-2.0", "qwen-image-2.0-pro"):
        for mode in ("text-to-image", "edit"):
            spec = Spec(
                provider, tier,
                keep=("prompt", "resolution", "negative_prompt", "image_urls"),
                rename={"aspect_ratio": "size", "num_images": "n"},
                convert={"resolution": upper},
                allowed={"aspect_ratio": APIMART_V2_RATIOS},
            )  # fmt: skip
            routes[f"alibaba/{tier}/{mode}"] = Route(
                provider, tier, spec,
                lambda i, h, p, t=tier: per_unit(p, f"{t}|default", i.get("num_images", 1)),
            )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({"qwen-image-2.0", "qwen-image-2.0-pro"})


# --- KIE ------------------------------------------------------------------------------------------


def _qwen21_checks(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if source.get("background") == "transparent" and source.get("output_format") == "jpeg":
        raise unsupported("kie", "A transparent background needs png or webp output")
    if source.get("mask_url") and len(source.get("image_urls") or []) != 1:
        raise unsupported("kie", "A mask works with exactly one image")
    return out


def kie() -> dict[str, Route]:
    provider = "kie"
    routes: dict[str, Route] = {}
    common = ("prompt", "seed", "negative_prompt", "acceleration", "output_format", "num_inference_steps",
              "guidance_scale")  # fmt: skip
    name = "qwen/image-to-image"
    routes["alibaba/qwen-image/image-to-image"] = Route(
        provider, name, Spec(provider, name, keep=(*common, "image_url", "strength")),
        lambda i, h, p: per_unit(p, "qwen image, image-to-image"),
    )  # fmt: skip

    for mode, name, kie_mode in (
        ("text-to-image", "qwen2-1/text-to-image", "text to image"),
        ("edit", "qwen2-1/image-to-image", "image to image"),
    ):
        routes[f"alibaba/qwen-image-2.1/{mode}"] = Route(
            provider, name,
            Spec(provider, name,
                 keep=("prompt", "aspect_ratio", "background", "output_format", "enhance_prompt", "seed",
                       "image_urls", "mask_url"),
                 convert={"resolution": upper}, build=_qwen21_checks),
            lambda i, h, p, m=kie_mode: per_unit(p, f"qwen-image-2.1, {m}, {i.get('resolution', '1k')}"),
        )  # fmt: skip
    return routes
