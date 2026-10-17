"""Imágenes de Google en las tiendas: Nano Banana (1, 2, 2.1, 2 Lite, Pro) e Imagen 4. Higgsfield no los vende.

Fuentes (revisadas el 2026-10-17):
- APIMart (todos por `POST /v1/images/generations`, una imagen por tarea salvo Lite, `size` es la relación):
  - `gemini-2.5-flash-image-preview` (alias `nano-banana-ext`; prompt ≤ 1000, solo 1K, ≤ 14 imágenes):
    https://docs.apimart.ai/en/api-reference/images/gemini-2.5-flash/generation.md
  - `gemini-3.1-flash-image-preview` (alias `nano-banana-2-ext`; 0.5K–4K, 14 relaciones, ≤ 14 imágenes,
    `google_search` y `google_image_search`):
    https://docs.apimart.ai/en/api-reference/images/gemini-3.1-flash/generation.md
  - `gemini-nano-banana-2.1-ext` (1K/2K/4K, 14 relaciones, n = 1):
    https://docs.apimart.ai/en/api-reference/images/gemini-nano-banana-2.1/generation.md
  - `gemini-3.1-flash-lite-image-ext` (solo 1K, 11 relaciones, n 1–4):
    https://docs.apimart.ai/en/api-reference/images/gemini-3.1-flash/generation-lite.md
  - `gemini-3-pro-image-preview` (alias `nano-banana-pro-ext`; 1K/2K/4K, ≤ 14 imágenes):
    https://docs.apimart.ai/en/api-reference/images/gemini-3-pro/generation.md
  - `imagen-4.0-apimart` (solo texto, relaciones 1:1, 4:3, 3:4, 16:9, 9:16; una relación desconocida cae
    en 16:9 sin error): https://docs.apimart.ai/en/api-reference/images/imagen-4.0-apimart/generation.md
  Los ids sin `-official` son los canales «estándar»/ext (no oficiales). Los `-official` y
  `gemini-nano-banana-2.1` se cobran por tokens y no tienen precio fijo en la tabla: no se ofrecen.
  Precio por imagen `<modelo>|<RES>` o `<modelo>|default` (Pro: `default` es 1K y 2K).
- KIE (API unificada `jobs/createTask`):
  - `google/nano-banana` (solo texto) y `google/nano-banana-edit` (≤ 10 `image_urls`):
    https://docs.kie.ai/market/google/nano-banana.md, https://docs.kie.ai/market/google/nano-banana-edit.md
  - `nano-banana-2` y `nano-banana-2-1` (≤ 10 `image_input`, 1K/2K/4K):
    https://docs.kie.ai/market/google/nanobanana2.md, https://docs.kie.ai/market/google/nanobanana-2-1.md
  - `nano-banana-2-lite` (`aspect_ratio` obligatorio, ≤ 10 `image_urls`, solo 1K):
    https://docs.kie.ai/market/google/nano-banana-2-lite.md
  - `nano-banana-pro` (texto o ≤ 8 `image_input`, 1K/2K/4K): https://docs.kie.ai/market/google/pro-image-to-image.md
  - `google/imagen4`, `google/imagen4-fast`, `google/imagen4-ultra` (`seed` es texto salvo en fast):
    https://docs.kie.ai/market/google/imagen4.md (y `imagen4-fast`, `imagen4-ultra`).
  Precios `google nano banana, text-to-image`, `google nano banana edit, image-to-image`,
  `google nano banana 2, <res>`, `nano-banana-2-1, <res>`, `nano-banana-2-lite, 1k`,
  `google nano banana pro, 1/2k|4k`, `google imagen4, text-to-image, default|fast|ultra`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..providers.routes import Route, Spec, only_default, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

KIE_DOCS = "https://docs.kie.ai/market/google/"
MODES = (("text-to-image", "Text to image"), ("edit", "Edit images"))

RATIOS_11 = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
RATIOS_15 = [*RATIOS_11, "1:4", "4:1", "1:8", "8:1"]
IMAGEN_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "auto"]

APIMART_NOTE = "Unofficial APIMart channel (standard/ext): cheaper, may be less stable"
STORE_NOTE = "Google's {name}. Higgsfield does not sell it on its own: it runs on APIMart or KIE."


def _id(family: str, mode: str) -> str:
    return f"google/{family}/{mode}"


# --- Familias Nano Banana ---------------------------------------------------------------------
# Cada una tiene un modelo de texto a imagen y uno de edición (con imágenes): en KIE, Nano Banana usa
# modelos distintos para cada modo, así que toda la familia se divide igual.

NANO_BANANA: dict[str, dict[str, Any]] = {
    "nano-banana": {
        "name": "Nano Banana",
        "docs": KIE_DOCS + "nano-banana",
        "ratios": RATIOS_11,
        "resolutions": None,  # solo 1K en las dos tiendas
        "notes": [
            "Gemini 2.5 Flash Image. Output is 1K.",
            "APIMart takes prompts up to 1,000 characters and up to 14 images; KIE up to 10 images.",
        ],
    },
    "nano-banana-2": {
        "name": "Nano Banana 2",
        "docs": KIE_DOCS + "nanobanana2",
        "ratios": RATIOS_15,
        "resolutions": ["0.5k", "1k", "2k", "4k"],
        "search": True,
        "notes": [
            "Gemini 3.1 Flash Image.",
            "0.5k, Google search grounding and more than 10 images only run on APIMart.",
        ],
    },
    "nano-banana-2.1": {
        "name": "Nano Banana 2.1",
        "docs": KIE_DOCS + "nanobanana-2-1",
        "ratios": RATIOS_15,
        "resolutions": ["1k", "2k", "4k"],
        "notes": [
            "A different model from Nano Banana 2 (Gemini 3.1 Flash Image), not an alias.",
            "More than 10 images only run on APIMart (unofficial ext channel).",
        ],
    },
    "nano-banana-2-lite": {
        "name": "Nano Banana 2 Lite",
        "docs": KIE_DOCS + "nano-banana-2-lite",
        "ratios": RATIOS_15,
        "resolutions": None,  # solo 1K
        "num_images": 4,
        "notes": [
            "Gemini 3.1 Flash Lite Image: the fastest and cheapest of the family. Output is 1K only.",
            "1:4, 4:1, 1:8 and 8:1 only run on KIE; num_images above 1 and more than 10 images only on APIMart.",
        ],
    },
    "nano-banana-pro": {
        "name": "Nano Banana Pro",
        "docs": KIE_DOCS + "pro-image-to-image",
        "ratios": RATIOS_11,
        "resolutions": ["1k", "2k", "4k"],
        "notes": [
            "Gemini 3 Pro Image: the highest quality of the family, best for text in images.",
            "KIE takes up to 8 images; APIMart up to 14.",
        ],
    },
}


def _nano_models() -> list[dict[str, Any]]:
    found = []
    for family, spec in NANO_BANANA.items():
        for mode, workflow in MODES:
            properties: dict[str, Any] = {
                "prompt": prompt(20000, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": choice(
                    spec["ratios"], "1:1" if mode == "text-to-image" else "auto",
                    "Output aspect ratio; auto lets the model choose (with images, it follows them).",
                ),
            }  # fmt: skip
            if spec["resolutions"]:
                properties["resolution"] = choice(spec["resolutions"], "1k", "Output resolution tier.")
            if spec.get("num_images"):
                properties["num_images"] = choice(
                    list(range(1, spec["num_images"] + 1)),
                    1,
                    "Images per request (more than one only on APIMart).",
                )
            if spec.get("search"):
                properties["google_search"] = {
                    "type": "boolean", "default": False,
                    "description": "Ground the image on Google web search results (APIMart only).",
                }  # fmt: skip
                properties["google_image_search"] = {
                    "type": "boolean", "default": False,
                    "description": "Also search Google Images for visual references; needs google_search.",
                }  # fmt: skip
            required = ["prompt"]
            if mode == "edit":
                properties["image_urls"] = urls(1, 14, "One to fourteen images to edit or use as references.")
                required.append("image_urls")
            entry = model(
                _id(family, mode),
                name=spec["name"],
                workflow=workflow,
                family=family,
                output="image",
                capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                properties=properties,
                required=required,
                docs_url=spec["docs"],
                notes=[STORE_NOTE.format(name=spec["name"]), *spec["notes"]],
            )
            if spec.get("search"):
                entry["input_schema"]["allOf"] = [{
                    "if": {"required": ["google_image_search"], "properties": {"google_image_search": {"const": True}}},
                    "then": {"required": ["google_search"], "properties": {"google_search": {"const": True}}},
                }]  # fmt: skip
            found.append(entry)
    return found


# --- Imagen 4 ---------------------------------------------------------------------------------

IMAGEN: dict[str, dict[str, Any]] = {
    # variante lógica: (sufijo del id, nombre, modelo en KIE, clave de precio en KIE, `seed` como texto)
    "standard": {"path": "imagen-4", "name": "Imagen 4", "kie": "google/imagen4", "price": "default",
                 "seed_text": True},
    "fast": {"path": "imagen-4/fast", "name": "Imagen 4 Fast", "kie": "google/imagen4-fast", "price": "fast",
             "seed_text": False},
    "ultra": {"path": "imagen-4/ultra", "name": "Imagen 4 Ultra", "kie": "google/imagen4-ultra", "price": "ultra",
              "seed_text": True},
}  # fmt: skip


def _imagen_models() -> list[dict[str, Any]]:
    found = []
    for variant, spec in IMAGEN.items():
        notes = [STORE_NOTE.format(name=spec["name"]), "Text to image only; one image per request."]
        if variant == "standard":
            notes.append("negative_prompt, seed and auto aspect ratio only run on KIE.")
        else:
            notes.append("Only offered by KIE.")
        found.append(
            model(
                _id(spec["path"], "text-to-image"),
                name=spec["name"],
                workflow="Text to image",
                family=f"imagen-4-{variant}" if variant != "standard" else "imagen-4",
                output="image",
                capabilities=["text-to-image"],
                properties={
                    "prompt": prompt(5000),
                    "negative_prompt": {
                        "type": "string",
                        "maxLength": 5000,
                        "description": "What to keep out of the image.",
                    },
                    "aspect_ratio": choice(
                        IMAGEN_RATIOS, "1:1", "Output aspect ratio; auto lets the model choose."
                    ),
                    "seed": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 2147483647,
                        "description": "Optional seed for reproducible results.",
                    },
                },
                required=["prompt"],
                docs_url=KIE_DOCS + spec["kie"].removeprefix("google/"),
                notes=notes,
            )
        )
    return found


MODELS = _nano_models() + _imagen_models()


# --- Piezas de traducción ----------------------------------------------------------------------


def _at_most(provider: str, field: str, limit: int) -> Callable[[Any], Any]:
    """Lista de medios con un máximo en el proveedor: más elementos es `unsupported`, no se recorta."""

    def check(values: Any) -> Any:
        if values and len(values) > limit:
            raise unsupported(provider, f"{provider} takes at most {limit} {field}")
        return values or None

    return check


def _max_length(provider: str, limit: int) -> Callable[[Any], Any]:
    def check(value: Any) -> Any:
        if len(value) > limit:
            raise unsupported(provider, f"{provider} takes prompts up to {limit} characters")
        return value

    return check


def _only_true(value: Any) -> Any:
    return True if value else None


# --- APIMart ----------------------------------------------------------------------------------

APIMART: dict[str, dict[str, Any]] = {
    # familia: modelo en APIMart, relaciones, resoluciones, máx. de prompt, búsqueda de Google y `n`
    "nano-banana": {"model": "gemini-2.5-flash-image-preview", "ratios": RATIOS_11, "prompt_max": 1000},
    "nano-banana-2": {"model": "gemini-3.1-flash-image-preview", "ratios": RATIOS_15,
                      "resolutions": {"0.5k", "1k", "2k", "4k"}, "search": True},
    "nano-banana-2.1": {"model": "gemini-nano-banana-2.1-ext", "ratios": RATIOS_15,
                        "resolutions": {"1k", "2k", "4k"}},
    "nano-banana-2-lite": {"model": "gemini-3.1-flash-lite-image-ext", "ratios": RATIOS_11, "num_images": True},
    "nano-banana-pro": {"model": "gemini-3-pro-image-preview", "ratios": RATIOS_11,
                        "resolutions": {"1k", "2k", "4k"}},
}  # fmt: skip
APIMART_IMAGEN = "imagen-4.0-apimart"


def _apimart_price(name: str) -> Callable[[dict, dict, dict], float | None]:
    """Precio por imagen por resolución (`<modelo>|1K`) o, si la tabla no la distingue, `<modelo>|default`."""

    def price(i: dict, h: dict, p: dict) -> float | None:
        res = i.get("resolution")
        key = f"{name}|{str(res).upper()}" if res else None
        key = key if key in p else f"{name}|default"
        return per_unit(p, key, i.get("num_images", 1))

    return price


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for family, cfg in APIMART.items():
        name = cfg["model"]
        for mode, _ in MODES:
            convert: dict[str, Callable[[Any], Any]] = {"image_urls": _at_most(provider, "images", 14)}
            if cfg.get("search"):
                # apagados por defecto en APIMart: solo se envían encendidos
                convert |= {"google_search": _only_true, "google_image_search": _only_true}
            allowed: dict[str, Any] = {"aspect_ratio": cfg["ratios"]}
            if cfg.get("resolutions"):
                convert["resolution"] = upper
                allowed["resolution"] = cfg["resolutions"]
            if cfg.get("prompt_max"):
                convert["prompt"] = _max_length(provider, cfg["prompt_max"])
            spec = Spec(
                provider, name, keep=("prompt",), convert=convert, allowed=allowed,
                rename={"aspect_ratio": "size", "num_images": "n"} if cfg.get("num_images") else {"aspect_ratio": "size"},
            )  # fmt: skip
            routes[_id(family, mode)] = Route(
                provider, name, spec, _apimart_price(name), official=False, notes=(APIMART_NOTE,)
            )
    imagen = Spec(
        provider, APIMART_IMAGEN, keep=("prompt",), rename={"aspect_ratio": "size"},
        allowed={"aspect_ratio": {"1:1", "16:9", "9:16", "4:3", "3:4"}},
    )  # fmt: skip
    routes[_id("imagen-4", "text-to-image")] = Route(
        provider, APIMART_IMAGEN, imagen, _apimart_price(APIMART_IMAGEN), official=False,
        notes=("Unofficial APIMart channel: cheaper, may be less stable",),
    )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({cfg["model"] for cfg in APIMART.values()} | {APIMART_IMAGEN})


# --- KIE --------------------------------------------------------------------------------------


def _kie_res(source: dict[str, Any]) -> str:
    return str(source.get("resolution", "1k"))


def kie() -> dict[str, Route]:
    provider = "kie"
    routes: dict[str, Route] = {}
    no_search = {"google_search": only_default("google_search", False),
                 "google_image_search": only_default("google_image_search", False)}  # fmt: skip

    # Nano Banana: un modelo por modo
    for mode, name, key in (
        ("text-to-image", "google/nano-banana", "google nano banana, text-to-image"),
        ("edit", "google/nano-banana-edit", "google nano banana edit, image-to-image"),
    ):
        spec = Spec(
            provider, name, keep=("prompt",), convert={"image_urls": _at_most(provider, "images", 10)},
            allowed={"aspect_ratio": RATIOS_11},
        )  # fmt: skip
        routes[_id("nano-banana", mode)] = Route(provider, name, spec, lambda i, h, p, k=key: per_unit(p, k))

    # Nano Banana 2, 2.1 y Pro: un modelo para los dos modos, imágenes en `image_input`
    for family, name, ratios, limit, price in (
        ("nano-banana-2", "nano-banana-2", RATIOS_15, 10,
         lambda i, h, p: per_unit(p, f"google nano banana 2, {_kie_res(i)}")),
        ("nano-banana-2.1", "nano-banana-2-1", RATIOS_15, 10,
         lambda i, h, p: per_unit(p, f"nano-banana-2-1, {_kie_res(i)}")),
        ("nano-banana-pro", "nano-banana-pro", RATIOS_11, 8,
         lambda i, h, p: per_unit(p, "google nano banana pro, " + ("4k" if _kie_res(i) == "4k" else "1/2k"))),
    ):  # fmt: skip
        for mode, _ in MODES:
            spec = Spec(
                provider, name, keep=("prompt",), rename={"image_urls": "image_input"},
                convert={"image_urls": _at_most(provider, "images", limit), "resolution": upper,
                         **(no_search if family == "nano-banana-2" else {})},
                allowed={"aspect_ratio": ratios, "resolution": {"1k", "2k", "4k"}},
            )  # fmt: skip
            routes[_id(family, mode)] = Route(provider, name, spec, price)

    # Nano Banana 2 Lite: `aspect_ratio` obligatorio (siempre llega con el valor por defecto lógico)
    for mode, _ in MODES:
        spec = Spec(
            provider, "nano-banana-2-lite", keep=("prompt",),
            convert={"image_urls": _at_most(provider, "images", 10), "num_images": only_default("num_images", 1)},
            allowed={"aspect_ratio": RATIOS_15},
        )  # fmt: skip
        routes[_id("nano-banana-2-lite", mode)] = Route(
            provider, "nano-banana-2-lite", spec, lambda i, h, p: per_unit(p, "nano-banana-2-lite, 1k")
        )

    # Imagen 4: tres variantes; `seed` es texto en la estándar y en ultra
    for spec_ in IMAGEN.values():
        spec = Spec(
            provider, spec_["kie"], keep=("prompt", "negative_prompt"),
            convert={"seed": str} if spec_["seed_text"] else {"seed": int},
            allowed={"aspect_ratio": IMAGEN_RATIOS},
        )  # fmt: skip
        routes[_id(spec_["path"], "text-to-image")] = Route(
            provider, spec_["kie"], spec,
            lambda i, h, p, k=spec_["price"]: per_unit(p, f"google imagen4, text-to-image, {k}"),
        )  # fmt: skip
    return routes
