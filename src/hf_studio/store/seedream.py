"""Seedream (ByteDance) en las tiendas: 3.0, 4.0, 4.5, 5.0 (Lite, Flash y Pro) y 5.5. Higgsfield no lo vende.

Fuentes (revisadas el 2026-10-17; 5.5 el 2026-11-11):
- APIMart, `POST /v1/images/generations` (un mismo id para texto a imagen y edición con `image_urls`):
  https://docs.apimart.ai/en/api-reference/images/seedream-4/generation.md (`seedream-4-0`: 1K/2K/4K, prompt
  hasta 1000 caracteres), .../seedream-4.5/generation.md (`seedream-4-5`: 2K/4K),
  .../seedream-5-lite/generation.md (`seedream-5-0-lite`: 2K/3K/4K, sin 9:21),
  .../seedream-5-0-pro/generation.md y .../seedream-5-0-flash/generation.md (1K/1.5K/2K, hasta 10
  referencias, una imagen por tarea). En 4.0, 4.5 y Lite, referencias + `n` ≤ 15. Precio por imagen:
  `<id>|default`, y en Pro `seedream-5-0-pro|1K` o `|2K` (1.5K cuesta lo mismo que 1K).
- KIE, API unificada (`jobs/createTask`), un id por modo:
  https://docs.kie.ai/market/seedream/seedream.md (3.0, `bytedance/seedream`, `image_size` por presets),
  .../seedream-v4-text-to-image.md y .../seedream-v4-edit.md (`image_size` + `image_resolution`, hasta 10
  imágenes, `seed`), .../4-5-text-to-image.md y .../4-5-edit.md (`quality` basic=2K, high=4K, hasta 14),
  .../5-lite-text-to-image.md y https://docs.kie.ai/market/seedream-5-lite-image-to-image.md (`quality`
  basic=2K, high=3K, ultra=4K, hasta 14), .../5-pro-text-to-image.md y .../5-pro-image-to-image.md
  (`quality` basic=1K, high=2K, hasta 10; cada referencia después de la primera tiene recargo),
  .../5-flash-text-to-image.md y .../5-flash-image-to-image.md (`size` 1K/1.5K/2K, hasta 10).
  Precios `seedream v4, text-to-image`, `seedream 4.5, image-to-image`, `seedream 5 pro, text-to-image, 1k`…
- Seedream 5.5 (2026-11-11). APIMart `seedream-5-5`, mismo `POST /v1/images/generations`:
  https://docs.apimart.ai/en/api-reference/images/seedream-5-5/generation.md (`size` relación + `resolution`
  1K/1.5K/2K; 10 relaciones sin 9:21; hasta 10 referencias; `background` auto/transparent/opaque,
  transparente solo en png; png por defecto). Precio `seedream-5-5|1K` (también 1.5K, lo dice la doc) y
  `|2K`. Cobra aparte cada imagen de entrada, la primera incluida, pero la tabla no publica ese importe: la
  edición 5.5 no se ruta a APIMart (siempre tendría precio desconocido), solo el texto a imagen.
  KIE: https://docs.kie.ai/market/seedream/5-5-text-to-image.md y .../5-5-image-to-image.md (`size`
  1K/1.5K/2K, 8 relaciones, `auto` solo en edición, hasta 10 imágenes, prompt de 5 a 5000 caracteres,
  `background`). Precios `seedream 5.5, text to image, 1k`, `seedream 5.5, image to image, 1k` y, por cada
  imagen de entrada, `seedream 5.5, input image, image to image / layer decomposition`.

Fuera a propósito: la generación en serie (`n`/`max_images`, que da un conjunto y no N variantes), la
descomposición en capas (5.0 y 5.5: devuelve una base más un número variable de capas y se cobra por las que
salen, así que el precio no se conoce antes; además trae metadatos de capas y OCR que el estudio no muestra) y
el fondo transparente de 5.0 Pro/Flash. En 5.5 el fondo sí está: ambas tiendas lo aceptan igual.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..providers.routes import Route, Spec, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

DOCS = "https://docs.kie.ai/market/seedream/5-pro-text-to-image"
# Relaciones que KIE acepta en 4.5 y 5.0 (obligatoria, sin `auto`).
KIE_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9")
# 3.0 y 4.0 en KIE: `image_size` por presets. 1:1 es `square_hd` (`square` es una versión más pequeña).
KIE_V3_SIZES = {"1:1": "square_hd", "3:4": "portrait_4_3", "9:16": "portrait_16_9",
                "4:3": "landscape_4_3", "16:9": "landscape_16_9"}  # fmt: skip
KIE_V4_SIZES = {**KIE_V3_SIZES, "2:3": "portrait_3_2", "3:2": "landscape_3_2", "21:9": "landscape_21_9"}


@dataclass(frozen=True)
class Version:
    key: str  # parte del id lógico: bytedance/seedream-<key>/<modo>
    name: str
    resolutions: tuple[str, ...]  # en minúsculas, como el catálogo
    default_resolution: str | None
    ratios: tuple[str, ...]  # relaciones del esquema lógico (unión de las tiendas)
    prompt_max: int
    max_images: int  # referencias en el esquema lógico (la mayor de las tiendas)
    apimart: str | None  # id en APIMart (el de su tabla de precios)
    apimart_ratios: frozenset[str]
    kie_t2i: str
    kie_edit: str | None
    kie_max_images: int
    output_format: bool = False  # 5.0: png o jpeg en ambas tiendas
    seed: bool = False  # solo KIE en 3.0 y 4.0
    default_format: str = "jpeg"
    background: bool = False  # 5.5: auto, transparent u opaque en ambas tiendas
    # False: la edición no va a APIMart (5.5: cobra cada imagen de entrada sin publicar el importe) y usa las
    # relaciones de KIE, con `auto`.
    apimart_edit: bool = True


APIMART_V4_RATIOS = frozenset(
    {"1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "2:1", "1:2", "21:9", "9:21"}
)
APIMART_V5_RATIOS = APIMART_V4_RATIOS - {"9:21"}
V4_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9", "2:1", "1:2", "9:21")
V5_RATIOS = V4_RATIOS[:-1]

VERSIONS = {
    v.key: v
    for v in (
        Version("3.0", "Seedream 3.0", (), None, tuple(KIE_V3_SIZES), 5000, 0, None, frozenset(),
                "bytedance/seedream", None, 0, seed=True),
        Version("4.0", "Seedream 4.0", ("1k", "2k", "4k"), "2k", V4_RATIOS, 5000, 14, "seedream-4-0",
                APIMART_V4_RATIOS, "bytedance/seedream-v4-text-to-image", "bytedance/seedream-v4-edit", 10,
                seed=True),
        Version("4.5", "Seedream 4.5", ("2k", "4k"), "2k", V4_RATIOS, 3000, 14, "seedream-4-5",
                APIMART_V4_RATIOS, "seedream/4.5-text-to-image", "seedream/4.5-edit", 14),
        Version("5.0-lite", "Seedream 5.0 Lite", ("2k", "3k", "4k"), "2k", V5_RATIOS, 2995, 14,
                "seedream-5-0-lite", APIMART_V5_RATIOS, "seedream/5-lite-text-to-image",
                "seedream/5-lite-image-to-image", 14, output_format=True),
        Version("5.0-flash", "Seedream 5.0 Flash", ("1k", "1.5k", "2k"), "1k", V5_RATIOS, 5000, 10,
                "seedream-5-0-flash", APIMART_V5_RATIOS, "seedream/5-flash-text-to-image",
                "seedream/5-flash-image-to-image", 10, output_format=True),
        Version("5.0-pro", "Seedream 5.0 Pro", ("1k", "1.5k", "2k"), "1k", V5_RATIOS, 5000, 10,
                "seedream-5-0-pro", APIMART_V5_RATIOS, "seedream/5-pro-text-to-image",
                "seedream/5-pro-image-to-image", 10, output_format=True),
        Version("5.5", "Seedream 5.5", ("1k", "1.5k", "2k"), "2k", V5_RATIOS, 5000, 10, "seedream-5-5",
                APIMART_V5_RATIOS, "seedream/5-5-text-to-image", "seedream/5-5-image-to-image", 10,
                output_format=True, default_format="png", background=True, apimart_edit=False),
    )
}  # fmt: skip
# KIE `quality` según la resolución (4.5: basic=2K, high=4K; Lite: +ultra=4K con high=3K; Pro: 1K y 2K).
KIE_QUALITY = {
    "4.5": {"2k": "basic", "4k": "high"},
    "5.0-lite": {"2k": "basic", "3k": "high", "4k": "ultra"},
    "5.0-pro": {"1k": "basic", "2k": "high"},
}


def _id(version: str, mode: str) -> str:
    return f"bytedance/seedream-{version}/{mode}"


def _modes(v: Version) -> tuple[str, ...]:
    return ("text-to-image", "edit") if v.kie_edit else ("text-to-image",)


def _models() -> list[dict[str, Any]]:
    found = []
    for v in VERSIONS.values():
        for mode in _modes(v):
            kie_only = mode == "edit" and not v.apimart_edit
            ratios = list(KIE_RATIOS if kie_only else v.ratios) + (["auto"] if mode == "edit" else [])
            if mode != "edit":
                ratio_help = "Output aspect ratio."
            elif kie_only:
                ratio_help = "Output aspect ratio; auto lets the model choose."
            else:
                ratio_help = "Output aspect ratio; auto follows the reference image (APIMart only)."
            properties: dict[str, Any] = {
                "prompt": prompt(v.prompt_max, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(ratios, "1:1", ratio_help),
            }  # fmt: skip
            if v.resolutions:
                properties["resolution"] = choice(
                    list(v.resolutions), v.default_resolution, "Output resolution tier."
                )
            if v.output_format:
                properties["output_format"] = choice(
                    ["jpeg", "png"], v.default_format, "Output image format."
                )
            if v.background:
                properties["background"] = choice(
                    ["auto", "transparent", "opaque"], "auto",
                    "Output background; auto lets the model decide. Transparent needs png.",
                )  # fmt: skip
            if v.key == "3.0":
                properties["guidance_scale"] = {
                    "type": "number", "minimum": 1, "maximum": 10, "default": 2.5,
                    "description": "How closely the image follows the prompt (1 to 10).",
                }  # fmt: skip
            if v.seed:
                properties["seed"] = {
                    "type": "integer", "minimum": 0, "maximum": 1000000,
                    "description": "Seed for reproducible results (KIE only); omit for a random one.",
                }  # fmt: skip
            required = ["prompt"]
            if mode == "edit":
                properties["image_urls"] = urls(
                    1, v.max_images, f"One to {v.max_images} images to edit or use as references."
                )
                required.append("image_urls")
            notes = ["ByteDance's Seedream. Higgsfield does not sell it: it runs on APIMart or KIE."]
            if not v.apimart:
                notes = ["ByteDance's Seedream 3.0. Higgsfield does not sell it: it runs on KIE only."]
            if v.max_images and v.kie_max_images < v.max_images:
                notes.append(f"More than {v.kie_max_images} images only runs on APIMart.")
            if v.key == "4.0":
                notes.append("Prompts over 1000 characters and a fixed seed only run on KIE.")
            if kie_only:
                notes = [
                    ("ByteDance's Seedream. Higgsfield does not sell it, and APIMart does not publish what it "
                     "charges per input image: edits run on KIE only."),
                    "Every input image is charged on top of the output, the first one included.",
                    "Prompts must have 5 characters or more.",
                ]  # fmt: skip
            elif set(v.ratios) - set(KIE_RATIOS):
                extra = ", ".join(r for r in v.ratios if r not in KIE_RATIOS and r not in KIE_V4_SIZES)
                notes.append(
                    f"Aspect ratios {extra}{' and auto' if mode == 'edit' else ''} only run on APIMart."
                )
            if v.key == "5.5" and not kie_only:
                notes.append("Prompts under 5 characters only run on APIMart.")
            if v.key == "5.0-pro":
                notes.append("1.5k only runs on APIMart (same price as 1k). Each reference after the first adds a "
                             "small charge on KIE.")  # fmt: skip
            found.append(
                model(
                    _id(v.key, mode),
                    name=v.name,
                    workflow="Text to image" if mode == "text-to-image" else "Edit images",
                    family=f"seedream-{v.key}",
                    output="image",
                    capabilities=["text-to-image"]
                    if mode == "text-to-image"
                    else ["edit", "image-references"],
                    properties=properties,
                    required=required,
                    docs_url=DOCS,
                    notes=notes,
                )
            )
    return found


MODELS = _models()


def _limits(
    provider: str, max_prompt: int | None, max_images: int, min_prompt: int = 0
) -> Callable[[dict, dict], dict]:
    """Límites que el esquema lógico no expresa por tienda: largo del prompt y número de imágenes."""

    def check(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        length = len(source.get("prompt") or "")
        if max_prompt and length > max_prompt:
            raise unsupported(provider, f"{provider} takes prompts of at most {max_prompt} characters here")
        if length < min_prompt:
            raise unsupported(provider, f"{provider} takes prompts of at least {min_prompt} characters here")
        if len(source.get("image_urls") or []) > max_images:
            raise unsupported(provider, f"{provider} takes at most {max_images} images here")
        # Ambas tiendas rechazan el fondo transparente en jpeg (5.5).
        if source.get("background") == "transparent" and source.get("output_format") == "jpeg":
            raise unsupported(provider, "a transparent background needs output_format png")
        return out

    return check


# APIMart cobra en 5.0 Pro y Flash un recargo fijo por cada referencia después de la primera, sin publicar su
# importe (docs y tabla a 2026-10-17): con dos o más referencias el precio queda desconocido, nunca por debajo.
SURCHARGED = {"5.0-pro", "5.0-flash"}


def _apimart_price(v: Version) -> Callable[..., float | None]:
    def price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
        if v.key in SURCHARGED and len(i.get("image_urls") or []) > 1:
            return None
        if v.key in ("5.0-pro", "5.5"):  # 1.5K cuesta lo mismo que 1K
            return per_unit(p, f"{v.apimart}|{'2K' if i.get('resolution') == '2k' else '1K'}")
        return per_unit(p, f"{v.apimart}|default")

    return price


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for v in VERSIONS.values():
        if not v.apimart:
            continue
        for mode in _modes(v):
            if mode == "edit" and not v.apimart_edit:
                continue
            ratios = set(v.apimart_ratios) | ({"auto"} if mode == "edit" else set())
            spec = Spec(
                provider, v.apimart,
                keep=("prompt", "image_urls", "output_format", "background"),
                rename={"aspect_ratio": "size"},
                convert={"resolution": upper},
                allowed={"aspect_ratio": ratios},
                build=_limits(provider, 1000 if v.key == "4.0" else None, 14 if v.max_images == 14 else 10),
            )  # fmt: skip
            routes[_id(v.key, mode)] = Route(provider, v.apimart, spec, _apimart_price(v))
    return routes


def _kie_spec(v: Version, mode: str) -> Spec:
    provider = "kie"
    name = v.kie_t2i if mode == "text-to-image" else v.kie_edit
    assert name
    build = _limits(provider, None, v.kie_max_images, 5 if v.key == "5.5" else 0)
    keep = ("prompt", "image_urls", "output_format", "seed", "guidance_scale", "background")
    if v.key in ("3.0", "4.0"):
        sizes = KIE_V3_SIZES if v.key == "3.0" else KIE_V4_SIZES
        return Spec(
            provider, name, keep=keep,
            rename={"aspect_ratio": "image_size", "resolution": "image_resolution"},
            convert={"aspect_ratio": sizes.__getitem__, "resolution": upper},
            allowed={"aspect_ratio": sizes}, build=build,
        )  # fmt: skip
    if v.key in ("5.0-flash", "5.5"):
        ratios = set(KIE_RATIOS) | ({"auto"} if not v.apimart_edit and mode == "edit" else set())
        return Spec(
            provider, name, keep=keep, rename={"resolution": "size"}, convert={"resolution": upper},
            allowed={"aspect_ratio": ratios}, build=build,
        )  # fmt: skip
    quality = KIE_QUALITY[v.key]
    return Spec(
        provider, name, keep=keep, rename={"resolution": "quality"}, convert={"resolution": quality.__getitem__},
        allowed={"aspect_ratio": KIE_RATIOS, "resolution": quality}, build=build,
    )  # fmt: skip


def _kie_price(v: Version, mode: str) -> Callable[..., float | None]:
    if v.key == "3.0":
        return lambda i, h, p: per_unit(p, "seedream 3.0")
    if v.key == "4.0":
        return lambda i, h, p: per_unit(
            p, f"seedream v4, {'text-to-image' if mode == 'text-to-image' else 'edit'}"
        )
    i2i = mode == "edit"
    if v.key == "4.5":
        return lambda i, h, p: per_unit(p, f"seedream 4.5, {'image-to-image' if i2i else 'text-to-image'}")
    if v.key == "5.0-lite":
        return lambda i, h, p: per_unit(
            p, f"seedream 5.0 lite, {'image-to-image' if i2i else 'text-to-image'}"
        )
    if v.key == "5.0-flash":
        return lambda i, h, p: per_unit(
            p,
            f"seedream 5 flash, {'image to image' if i2i else 'text to image'}, {i.get('resolution', '1k')}",
        )
    if v.key == "5.5":
        # KIE cobra cada imagen de entrada, la primera incluida (doc de 5.5 y su ejemplo: 6.3 + 1.44 créditos).
        def v55(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
            base = per_unit(
                p,
                f"seedream 5.5, {'image to image' if i2i else 'text to image'}, {i.get('resolution', '2k')}",
            )
            count = len(i.get("image_urls") or [])
            inputs = (
                per_unit(p, "seedream 5.5, input image, image to image / layer decomposition", count)
                if count
                else 0.0
            )
            return None if base is None or inputs is None else round(base + inputs, 4)

        return v55

    def pro(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
        base = per_unit(
            p, f"seedream 5 pro, {'image-to-image' if i2i else 'text-to-image'}, {i.get('resolution')}"
        )
        extra = max(0, len(i.get("image_urls") or []) - 1)
        surcharge = per_unit(p, "seedream 5 pro, input image, first image free", extra) if extra else 0.0
        return None if base is None or surcharge is None else round(base + surcharge, 4)

    return pro


def kie() -> dict[str, Route]:
    routes = {}
    for v in VERSIONS.values():
        for mode in _modes(v):
            spec = _kie_spec(v, mode)
            routes[_id(v.key, mode)] = Route("kie", spec.model, spec, _kie_price(v, mode))
    return routes


APIMART_IMAGE_MODELS = frozenset(v.apimart for v in VERSIONS.values() if v.apimart)
