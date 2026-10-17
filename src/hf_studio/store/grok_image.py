"""Grok Imagine (xAI) para imágenes en canales que no son el `xai/grok-imagine-image-2.0` del catálogo.

Fuentes (revisadas el 2026-10-17):
- APIMart `grok-imagine-image` y `grok-imagine-image-quality` (modelos oficiales) y `grok-imagine-1.5-apimart`
  (canal no oficial, alias `grok-imagine-1.5-ext`): https://docs.apimart.ai/en/api-reference/images/grok-imagine/generation.md
  Oficiales: `aspect_ratio` (con auto), `resolution` 1k/2k, `n` 1–10, hasta 5 imágenes (3 en quality). Precio por
  imagen `grok-imagine-image|<RES>` más `|input:image` por imagen de entrada. Canal 1.5: `size` 1:1, 16:9, 9:16, 3:2,
  2:3, `n` 1–10, 1–5 imágenes; precio `grok-imagine-1.5-apimart|default` (y `grok-imagine-1.5-edit-apimart|default`
  al editar: la tabla lo lista aparte, la documentación no publica ese id).
- KIE `grok-imagine/text-to-image` (`aspect_ratio` obligatorio, `enable_pro` = modo calidad) y
  `grok-imagine/image-to-image` (1–5 imágenes): https://docs.kie.ai/market/grok-imagine/text-to-image.md y
  https://docs.kie.ai/market/grok-imagine/image-to-image.md. Precio por tarea `grok-imagine, text-to-image`,
  `grok-imagine, text-to-image(quality)` y `grok-imagine, image-to-image`.
No se sabe si estos canales son el mismo modelo entre sí, así que cada uno es un modelo lógico propio.
`grok-imagine-2.0-ext` de APIMart no está: es Grok Imagine 2.0 (ya en el catálogo) y no reproduce su resolución
ni su calidad.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit
from ._common import choice, model, prompt, urls

APIMART_DOCS = "https://docs.apimart.ai/en/api-reference/images/grok-imagine/generation"
KIE_DOCS = "https://docs.kie.ai/market/grok-imagine"
OFFICIAL_RATIOS = ["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "9:19.5", "19.5:9", "9:20", "20:9",
                   "1:2", "2:1"]  # fmt: skip
EXT_RATIOS = ["1:1", "16:9", "9:16", "3:2", "2:3"]
KIE_RATIOS = ["1:1", "2:3", "3:2", "16:9", "9:16"]
COUNT = choice(list(range(1, 11)), 1, "Images per request.")
# Modelos oficiales de APIMart: (sufijo del id lógico, modelo, nombre, máximo de imágenes de entrada)
OFFICIAL = (("grok-imagine-image", "grok-imagine-image", "Grok Imagine Image", 5),
            ("grok-imagine-image-quality", "grok-imagine-image-quality", "Grok Imagine Image Quality", 3))  # fmt: skip
EXT = "grok-imagine-1.5-apimart"


def _models() -> list[dict[str, Any]]:
    found = []
    for slug, _, name, max_images in OFFICIAL:
        for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
            properties: dict[str, Any] = {
                "prompt": prompt(8000, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(
                    OFFICIAL_RATIOS, "auto", "Output aspect ratio; auto lets the model choose."
                ),
                "resolution": choice(["1k", "2k"], "1k", "Output resolution tier."),
                "num_images": COUNT,
            }
            required = ["prompt"]
            if mode == "edit":
                properties["image_urls"] = urls(
                    1, max_images, f"One to {max_images} images to edit or combine."
                )
                required.append("image_urls")
            found.append(
                model(
                    f"xai/{slug}/{mode}",
                    name=name,
                    workflow=workflow,
                    family=slug,
                    output="image",
                    capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                    properties=properties,
                    required=required,
                    docs_url=APIMART_DOCS,
                    notes=["xAI's official image model on APIMart (Higgsfield sells Grok Imagine 2.0 instead).",
                           "Each input image adds a small surcharge."],
                )
            )  # fmt: skip
    for mode, workflow in (("text-to-image", "Text to image"), ("edit", "Edit images")):
        properties = {"prompt": prompt(description="What to generate or, with images, what to change.")}
        required = ["prompt"]
        if mode == "edit":
            properties["image_urls"] = urls(1, 5, "One to five images to edit or combine.")
            required.append("image_urls")
        else:
            properties["aspect_ratio"] = choice(EXT_RATIOS, "1:1", "Output aspect ratio.")
        properties["num_images"] = COUNT
        found.append(
            model(
                f"xai/grok-imagine-image/v1.5/{mode}",
                name="Grok Imagine 1.5",
                workflow=workflow,
                family="grok-imagine-1.5-image",
                output="image",
                capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                properties=properties,
                required=required,
                docs_url=APIMART_DOCS,
                notes=["Only on APIMart's unofficial channel: cheap, may be less stable."],
            )
        )
    kie_notes = ["Only KIE sells this channel; KIE does not document how many images a task returns."]
    found.append(
        model(
            "xai/grok-imagine/text-to-image",
            name="Grok Imagine",
            workflow="Text to image",
            family="grok-imagine-image",
            output="image",
            capabilities=["text-to-image"],
            properties={
                "prompt": prompt(5000),
                "aspect_ratio": choice(KIE_RATIOS, "1:1", "Output aspect ratio."),
                "mode": choice(["speed", "quality"], "speed", "Quality mode is slower and costs a bit more."),
            },
            required=["prompt"],
            docs_url=f"{KIE_DOCS}/text-to-image",
            notes=kie_notes,
        )
    )
    found.append(
        model(
            "xai/grok-imagine/image-to-image",
            name="Grok Imagine",
            workflow="Image to image",
            family="grok-imagine-image",
            output="image",
            capabilities=["edit", "image-references"],
            properties={
                "prompt": prompt(description="What to make from the images; cite them as @image1, @image2…"),
                "image_urls": urls(1, 5, "One to five images."),
            },
            required=["prompt", "image_urls"],
            docs_url=f"{KIE_DOCS}/image-to-image",
            notes=kie_notes,
        )
    )
    return found


MODELS = _models()


def _official_price(name: str):
    def price(i: dict, h: dict, p: dict) -> float | None:
        base = per_unit(p, f"{name}|{str(i.get('resolution', '1k')).upper()}", i.get("num_images", 1))
        refs = len(i.get("image_urls") or [])
        extra = per_unit(p, f"{name}|input:image", refs) if refs else 0.0
        return None if base is None or extra is None else round(base + extra, 4)

    return price


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for slug, name, _, _ in OFFICIAL:
        for mode in ("text-to-image", "edit"):
            spec = Spec(
                provider, name, keep=("prompt", "aspect_ratio", "resolution", "image_urls"),
                rename={"num_images": "n"},
            )  # fmt: skip
            routes[f"xai/{slug}/{mode}"] = Route(provider, name, spec, _official_price(name))
    for mode, row in (("text-to-image", EXT), ("edit", "grok-imagine-1.5-edit-apimart")):
        spec = Spec(
            provider, EXT, keep=("prompt", "image_urls"), rename={"aspect_ratio": "size", "num_images": "n"}
        )
        routes[f"xai/grok-imagine-image/v1.5/{mode}"] = Route(
            provider, EXT, spec,
            lambda i, h, p, r=row: per_unit(p, f"{r}|default", i.get("num_images", 1)),
            official=False,
            notes=("Unofficial APIMart channel: much cheaper, may be less stable",),
        )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({"grok-imagine-image", "grok-imagine-image-quality", EXT})


def _pro(value: str) -> bool:
    return value == "quality"


def kie() -> dict[str, Route]:
    provider = "kie"
    t2i, i2i = "grok-imagine/text-to-image", "grok-imagine/image-to-image"
    return {
        "xai/grok-imagine/text-to-image": Route(
            provider, t2i,
            Spec(provider, t2i, keep=("prompt", "aspect_ratio"), rename={"mode": "enable_pro"},
                 convert={"mode": _pro}),
            lambda i, h, p: per_unit(
                p, "grok-imagine, text-to-image(quality)" if i.get("mode") == "quality"
                else "grok-imagine, text-to-image"),
        ),
        "xai/grok-imagine/image-to-image": Route(
            provider, i2i, Spec(provider, i2i, keep=("prompt", "image_urls")),
            lambda i, h, p: per_unit(p, "grok-imagine, image-to-image"),
        ),
    }  # fmt: skip
