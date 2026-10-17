"""Seedream (ByteDance) en las tiendas: 3.0, 4.0, 4.5 y 5.0 (Lite, Flash y Pro). Higgsfield no lo vende.

Fuentes (revisadas el 2026-10-17):
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

Fuera a propósito: la generación en serie (`n`/`max_images`, que da un conjunto y no N variantes), la
descomposición en capas y el fondo transparente de 5.0 Pro/Flash.
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
            ratios = list(v.ratios) + (["auto"] if mode == "edit" else [])
            properties: dict[str, Any] = {
                "prompt": prompt(v.prompt_max, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(
                    ratios, "1:1",
                    "Output aspect ratio" + ("; auto follows the reference image (APIMart only)." if mode == "edit"
                                             else "."),
                ),
            }  # fmt: skip
            if v.resolutions:
                properties["resolution"] = choice(
                    list(v.resolutions), v.default_resolution, "Output resolution tier."
                )
            if v.output_format:
                properties["output_format"] = choice(["jpeg", "png"], "jpeg", "Output image format.")
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
            if set(v.ratios) - set(KIE_RATIOS):
                extra = ", ".join(r for r in v.ratios if r not in KIE_RATIOS and r not in KIE_V4_SIZES)
                notes.append(
                    f"Aspect ratios {extra}{' and auto' if mode == 'edit' else ''} only run on APIMart."
                )
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


def _limits(provider: str, max_prompt: int | None, max_images: int) -> Callable[[dict, dict], dict]:
    """Límites que el esquema lógico no expresa por tienda: largo del prompt y número de imágenes."""

    def check(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if max_prompt and len(source.get("prompt") or "") > max_prompt:
            raise unsupported(provider, f"{provider} takes prompts of at most {max_prompt} characters here")
        if len(source.get("image_urls") or []) > max_images:
            raise unsupported(provider, f"{provider} takes at most {max_images} images here")
        return out

    return check


# APIMart cobra en 5.0 Pro y Flash un recargo fijo por cada referencia después de la primera, sin publicar su
# importe (docs y tabla a 2026-10-17): con dos o más referencias el precio queda desconocido, nunca por debajo.
SURCHARGED = {"5.0-pro", "5.0-flash"}


def _apimart_price(v: Version) -> Callable[..., float | None]:
    def price(i: dict[str, Any], h: dict[str, Any], p: dict[str, float]) -> float | None:
        if v.key in SURCHARGED and len(i.get("image_urls") or []) > 1:
            return None
        if v.key == "5.0-pro":  # 1.5K cuesta lo mismo que 1K
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
            ratios = set(v.apimart_ratios) | ({"auto"} if mode == "edit" else set())
            spec = Spec(
                provider, v.apimart,
                keep=("prompt", "image_urls", "output_format"),
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
    build = _limits(provider, None, v.kie_max_images)
    keep = ("prompt", "image_urls", "output_format", "seed", "guidance_scale")
    if v.key in ("3.0", "4.0"):
        sizes = KIE_V3_SIZES if v.key == "3.0" else KIE_V4_SIZES
        return Spec(
            provider, name, keep=keep,
            rename={"aspect_ratio": "image_size", "resolution": "image_resolution"},
            convert={"aspect_ratio": sizes.__getitem__, "resolution": upper},
            allowed={"aspect_ratio": sizes}, build=build,
        )  # fmt: skip
    if v.key == "5.0-flash":
        return Spec(
            provider, name, keep=keep, rename={"resolution": "size"}, convert={"resolution": upper},
            allowed={"aspect_ratio": KIE_RATIOS}, build=build,
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
