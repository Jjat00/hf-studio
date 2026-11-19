"""Kling Image 4.0 (Kuaishou) en las tiendas: rutas más baratas del modelo de Higgsfield y Long Image.

Higgsfield vende `kling-image/v4.0/{text-to-image,edit}` (una imagen, 2k/4k/8k, referencias gratis; está en
`catalog.json`). Aquí van sus rutas de tienda y el modo de imagen larga, que Higgsfield no tiene (revisado el
2026-11-19):

- KIE `kling-4-0/image`: https://docs.kie.ai/market/kling-4-0/image.md. `prompt` hasta 20000 (cita `@image_1`…,
  como Higgsfield), `image_urls` hasta 10 (JPG o PNG de 20 MB), `resolution` 2k/4k/8k, `aspect_ratio` auto y las 8
  relaciones de Higgsfield; `mode` default con `count` 1 por omisión. Precio por imagen `kling image 4.0, image,
  <res>` más `..., reference image or element (each)` por referencia. No se usan `elements` ni la serie.
- APIMart `kling-v4-image`: https://docs.apimart.ai/en/api-reference/images/kling-v4-image/generation.md. Solo
  2K y 4K (sin 8K), `size` auto y las mismas 8 relaciones, `n` 1 por omisión. Precio `kling-v4-image|<RES>` por
  imagen. Solo texto a imagen: cobra las referencias una vez por pedido con una clave (`kling-v4-image@input`)
  que su tabla no publica, así que la edición no tendría precio.
- Long Image, una sola imagen muy alta (una página de producto desde 1 a 3 fotos, o el diseño de una web):
  KIE `kling-4-0/long-image` (https://docs.kie.ai/market/kling-4-0/long-image.md: `skill` ecommerce|webpage,
  `length` short|medium|long solo en ecommerce, `resolution` 1k|2k, `image_urls` 1 a 3 en ecommerce,
  `style_image` y `subject_image` en webpage; precio `kling image 4.0, long-image, e-commerce <length> <res>` o
  `..., webpage <res>` más `..., input image (each)` por imagen) y APIMart `kling-v4-long-image`
  (https://docs.apimart.ai/en/api-reference/images/kling-v4-long-image/generation.md: igual con `image_with_roles`
  style|subject en webpage; retiene al enviar y cobra `kling-v4-long-image|<RES>-<LENGTH>` o `|<RES>-WEBPAGE` más
  cada imagen de entrada con una clave sin publicar). Por eso APIMart solo hace la web sin imágenes; el resto va
  por KIE.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, upper, url, urls

HF = "kling-image/v4.0"
KIE_IMAGE = "kling-4-0/image"
KIE_LONG = "kling-4-0/long-image"
APIMART_IMAGE = "kling-v4-image"
APIMART_LONG = "kling-v4-long-image"
APIMART_IMAGE_MODELS = frozenset({APIMART_IMAGE, APIMART_LONG})
KIE_MAX_PROMPT = 20000
REF_PRICE = "kling image 4.0, image, reference image or element (each)"
LONG_INPUT_PRICE = "kling image 4.0, long-image, input image (each)"

LONG = "kling-image/v4.0/long-image"
ECOMMERCE, WEBPAGE = f"{LONG}/ecommerce", f"{LONG}/webpage"
LONG_DOCS = "https://docs.kie.ai/market/kling-4-0/long-image"
LONG_NOTE = (
    "Kling Image 4.0 long image: one very tall image (its height follows the content). Higgsfield does not sell "
    "it: it runs on KIE (and the web page without images also on APIMart). It can take several minutes."
)


def _models() -> list[dict[str, Any]]:
    resolution = choice(["1k", "2k"], "2k", "Output width: 1k is 1024 px and 2k is 2048 px wide.")
    ecommerce = model(
        ECOMMERCE, name="Kling Image 4.0 Long Image", workflow="E-commerce page", family="kling-image-4-long",
        output="image", capabilities=["edit", "image-references"],
        properties={
            "prompt": prompt(KIE_MAX_PROMPT, "The product and the page you want; cite the photos as @image_1…"),
            "image_urls": urls(1, 3, "One to three photos of the product (JPG or PNG, at least 300 px per side)."),
            "length": choice(["short", "medium", "long"], "medium",
                             "Page length: short has about 2–5 sections, medium 6–10 and long 11–18."),
            "resolution": resolution,
        },
        required=["prompt", "image_urls"], docs_url=LONG_DOCS,
        notes=[LONG_NOTE, "Priced by length and width, plus a small charge for each product photo."],
        summary="A tall product detail page from one to three product photos, with Kling Image 4.0 through KIE.",
    )  # fmt: skip
    webpage = model(
        WEBPAGE, name="Kling Image 4.0 Long Image", workflow="Web page", family="kling-image-4-long",
        output="image", capabilities=["text-to-image", "image-references"],
        properties={
            "prompt": prompt(KIE_MAX_PROMPT, "The web page to design: sections, copy and style."),
            "style_image_url": url("Optional style reference (cite it as @style)."),
            "subject_image_url": url("Optional subject to feature, such as a product or a person (cite it as @subject)."),
            "resolution": resolution,
        },
        required=["prompt"], docs_url=LONG_DOCS,
        notes=[LONG_NOTE, "With a style or subject image it runs on KIE only, which charges a little per image."],
        summary="A full web page design as one tall image, with Kling Image 4.0 through KIE or APIMart.",
    )  # fmt: skip
    return [ecommerce, webpage]


MODELS = _models()


def _kie_prompt(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if len(source.get("prompt") or "") > KIE_MAX_PROMPT:
        raise unsupported("kie", f"KIE takes prompts of at most {KIE_MAX_PROMPT} characters here")
    return out


def _kie_image_price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
    base = per_unit(p, f"kling image 4.0, image, {i.get('resolution', '2k')}")
    refs = len(i.get("image_urls") or [])
    extra = per_unit(p, REF_PRICE, refs) if refs else 0.0
    return None if base is None or extra is None else round(base + extra, 4)


def _long_images(i: dict[str, Any]) -> int:
    return len(i.get("image_urls") or []) + sum(
        1 for k in ("style_image_url", "subject_image_url") if i.get(k)
    )


def _kie_long_price(kind: str):
    def price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
        res = i.get("resolution", "2k")
        row = f"e-commerce {i.get('length', 'medium')} {res}" if kind == "ecommerce" else f"webpage {res}"
        base = per_unit(p, f"kling image 4.0, long-image, {row}")
        count = _long_images(i)
        extra = per_unit(p, LONG_INPUT_PRICE, count) if count else 0.0
        return None if base is None or extra is None else round(base + extra, 4)

    return price


def kie() -> dict[str, Route]:
    image = Spec(
        "kie", KIE_IMAGE, keep=("prompt", "image_urls", "resolution", "aspect_ratio"), build=_kie_prompt
    )
    long_keep = ("prompt", "resolution")
    return {
        f"{HF}/text-to-image": Route("kie", KIE_IMAGE, image, _kie_image_price),
        f"{HF}/edit": Route("kie", KIE_IMAGE, image, _kie_image_price),
        ECOMMERCE: Route(
            "kie",
            KIE_LONG,
            Spec(
                "kie",
                KIE_LONG,
                keep=(*long_keep, "image_urls", "length"),
                fixed={"skill": "ecommerce"},
                build=_kie_prompt,
            ),
            _kie_long_price("ecommerce"),
        ),
        WEBPAGE: Route(
            "kie",
            KIE_LONG,
            Spec(
                "kie",
                KIE_LONG,
                keep=long_keep,
                rename={"style_image_url": "style_image", "subject_image_url": "subject_image"},
                fixed={"skill": "webpage"},
                build=_kie_prompt,
            ),
            _kie_long_price("webpage"),
        ),
    }


def _apimart_webpage(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if _long_images(source):
        raise unsupported("apimart", "APIMart charges input images without publishing the price")
    return out


def apimart() -> dict[str, Route]:
    return {
        f"{HF}/text-to-image": Route(
            "apimart",
            APIMART_IMAGE,
            Spec(
                "apimart",
                APIMART_IMAGE,
                keep=("prompt",),
                rename={"aspect_ratio": "size"},
                convert={"resolution": upper},
                allowed={"resolution": {"2k", "4k"}},
            ),
            lambda i, h, p: per_unit(p, f"{APIMART_IMAGE}|{str(i.get('resolution', '2k')).upper()}"),
        ),
        WEBPAGE: Route(
            "apimart",
            APIMART_LONG,
            Spec(
                "apimart",
                APIMART_LONG,
                keep=("prompt",),
                convert={"resolution": upper},
                fixed={"skill": "webpage"},
                build=_apimart_webpage,
            ),
            lambda i, h, p: per_unit(p, f"{APIMART_LONG}|{str(i.get('resolution', '2k')).upper()}-WEBPAGE"),
        ),
    }
