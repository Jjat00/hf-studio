"""Herramientas de imagen de KIE: quitar el fondo y ampliar (Recraft, Topaz). Sin prompt: una imagen entra y sale otra.

Fuentes (revisadas el 2026-10-17), API unificada de KIE (`jobs/createTask`):
- `recraft/remove-background`: https://docs.kie.ai/market/recraft/remove-background.md (`image`; PNG/JPG/WEBP,
  ≤ 5 MB, ≤ 16 MP, lados de 256 a 4096 px). Precio `recraft remove background, image to image`.
- `recraft/crisp-upscale`: https://docs.kie.ai/market/recraft/crisp-upscale.md (`image`, ≤ 10 MB). Precio
  `recraft crisp upscale, image to image`.
- `topaz/image-upscale`: https://docs.kie.ai/market/topaz/image-upscale.md (`image_url`, `upscale_factor` "1", "2"
  o "4"). KIE cobra por el tamaño de salida (`topaz image upscaler, image-upscale, 2k` o `4k`; el ejemplo de la
  documentación, ×2, gastó 10 créditos = 0,05 USD) y el tamaño depende de la imagen de entrada, que no se conoce
  al cotizar: se cotiza con la fila de 4K (la más alta) y el precio es aproximado.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, url

DOCS = "https://docs.kie.ai/market"
NOTE = "Only KIE sells it (not Higgsfield or APIMart)."


def _models() -> list[dict[str, Any]]:
    return [
        model(
            "recraft/remove-background",
            name="Recraft Remove Background",
            workflow="Remove background",
            family="recraft-tools",
            output="image",
            capabilities=["edit"],
            properties={"image_url": url("PNG, JPG or WEBP up to 5 MB, 16 MP and 256 to 4096 px per side.")},
            required=["image_url"],
            docs_url=f"{DOCS}/recraft/remove-background",
            summary="Removes the background of an image with Recraft through KIE (not offered by Higgsfield).",
            notes=[NOTE, "Returns the subject on a transparent background."],
        ),
        model(
            "recraft/crisp-upscale",
            name="Recraft Crisp Upscale",
            workflow="Upscale",
            family="recraft-tools",
            output="image",
            capabilities=["edit"],
            properties={"image_url": url("PNG, JPG or WEBP up to 10 MB.")},
            required=["image_url"],
            docs_url=f"{DOCS}/recraft/crisp-upscale",
            summary="Upscales an image and sharpens its detail with Recraft through KIE (not offered by Higgsfield).",
            notes=[NOTE, "KIE does not document the upscale factor."],
        ),
        model(
            "topaz/image-upscale",
            name="Topaz Image Upscale",
            workflow="Upscale",
            family="topaz-image",
            output="image",
            capabilities=["edit"],
            properties={
                "image_url": url("PNG, JPG or WEBP up to 10 MB."),
                "upscale_factor": choice(
                    [1, 2, 4], 2, "How many times to multiply width and height (1 only enhances)."
                ),
            },
            required=["image_url"],
            docs_url=f"{DOCS}/topaz/image-upscale",
            summary="Upscales and enhances an image with Topaz through KIE (not offered by Higgsfield).",
            notes=[
                NOTE,
                "KIE bills by output size ($0.05 up to 2K, $0.10 at 4K); the quote assumes the 4K tier.",
            ],
        ),
    ]


MODELS = _models()


def _no_prompt(value: Any) -> None:
    # Estos modelos no tienen prompt y su esquema lo rechaza antes de llegar aquí (`catalog.validate`); solo
    # aparece en pruebas que añaden uno a todos los modelos.
    return None


def kie() -> dict[str, Route]:
    provider = "kie"
    routes = {}
    for logical, name, row in (
        (
            "recraft/remove-background",
            "recraft/remove-background",
            "recraft remove background, image to image",
        ),
        ("recraft/crisp-upscale", "recraft/crisp-upscale", "recraft crisp upscale, image to image"),
    ):
        routes[logical] = Route(
            provider, name,
            Spec(provider, name, rename={"image_url": "image"}, convert={"prompt": _no_prompt}),
            lambda i, h, p, r=row: per_unit(p, r),
        )  # fmt: skip
    topaz = "topaz/image-upscale"
    routes["topaz/image-upscale"] = Route(
        provider, topaz,
        Spec(provider, topaz, keep=("image_url",), convert={"upscale_factor": str, "prompt": _no_prompt}),
        lambda i, h, p: per_unit(p, "topaz image upscaler, image-upscale, 4k"),
        settles_later=True,
        notes=("Quoted at the 4K tier; outputs up to 2K cost half",),
    )  # fmt: skip
    return routes
