"""GPT Image 2, GPT Image 1.5 y GPT-4o Image (OpenAI) en las tiendas. Higgsfield no los vende sueltos.

GPT Image 2.5 vive en `gpt_image.py`. Fuentes (revisadas el 2026-10-17):
- APIMart `gpt-image-2`: https://docs.apimart.ai/en/api-reference/images/gpt-image-2/generation.md
  (`size` auto + 15 relaciones, `resolution` 1k/2k/4k, `n` solo 1, hasta 15 `image_urls`). Es un alias de
  `gpt-image-2-ext` (canal no oficial). Precio por imagen: `gpt-image-2|<RES>`. El canal oficial
  (`gpt-image-2-official`, https://docs.apimart.ai/en/api-reference/images/gpt-image-2/official.md) no tiene
  fila de precio y queda fuera.
- KIE `gpt-image-2-text-to-image` / `gpt-image-2-image-to-image`:
  https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image.md y .../gpt-image-2-image-to-image.md. Una imagen
  por tarea, hasta 16 `input_urls`; en 2K no hay 5:4, 4:5, 3:1, 1:3 ni 9:21 y en 4K no hay 3:1, 1:3 ni 9:21;
  `background` solo en 1K. Precio `gpt image 2, <modo>, <res>`.
- KIE `gpt-image/1.5-text-to-image` / `gpt-image/1.5-image-to-image`:
  https://docs.kie.ai/market/gpt-image/1-5-text-to-image.md y .../1-5-image-to-image.md (`aspect_ratio`
  1:1|2:3|3:2 y `quality` medium|high obligatorios, hasta 16 `input_urls`). Precio
  `gpt image 1.5, <modo>, <quality>`. APIMart documenta GPT-Image 1/1.5 pero no tiene fila de precio.
- KIE `4o-image-api` (GPT-4o Image), ya en la API unificada `jobs/createTask` + `jobs/recordInfo`:
  https://docs.kie.ai/4o-image-api/generate-4-o-image.md (`size` 1:1|3:2|2:3 obligatorio, hasta 5
  `files_url`). Solo hay una fila de precio, `openai 4o image, text-to-image`, que se usa también al editar.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, only_default, per_unit, unsupported
from ._common import choice, model, prompt, upper, urls

MODES = (("text-to-image", "Text to image"), ("edit", "Edit images"))
KIE_MODE = {"text-to-image": "text-to-image", "edit": "image-to-image"}

# --- GPT Image 2 ----------------------------------------------------------------------------------

GPT2_DOCS = "https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image"
GPT2_RATIOS = [
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16",
    "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
]  # fmt: skip
# Relaciones que KIE no admite en cada resolución (la de 1K las admite todas).
KIE_GPT2_MISSING = {"2k": {"5:4", "4:5", "3:1", "1:3", "9:21"}, "4k": {"3:1", "1:3", "9:21"}}


def _gpt2_id(mode: str) -> str:
    return f"openai/gpt-image-2/{mode}"


def _gpt2_models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in MODES:
        properties: dict[str, Any] = {
            "prompt": prompt(20000, "What to generate or, with images, what to change and what to keep."),
            # APIMart convierte «auto» en 1:1: en texto a imagen el valor por defecto es 1:1 y «auto» solo va a KIE.
            "aspect_ratio": choice(
                GPT2_RATIOS, "1:1" if mode == "text-to-image" else "auto",
                "Output aspect ratio; auto lets the model choose (KIE only).",
            ),
            "resolution": choice(["1k", "2k", "4k"], "1k", "Output resolution tier."),
            "background": choice(
                ["auto", "opaque", "transparent"], "auto",
                "Background; transparent or opaque only at 1k and only on KIE.",
            ),
        }  # fmt: skip
        required = ["prompt"]
        if mode == "edit":
            properties["image_urls"] = urls(1, 16, "One to sixteen images to edit or use as references.")
            required.append("image_urls")
        found.append(
            model(
                _gpt2_id(mode),
                name="GPT Image 2",
                workflow=workflow,
                family="gpt-image-2",
                output="image",
                capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                properties=properties,
                required=required,
                docs_url=GPT2_DOCS,
                notes=[
                    (
                        "OpenAI's GPT Image 2. Higgsfield does not sell it on its own: it runs on APIMart "
                        "(unofficial channel) or KIE. One image per request."
                    ),
                    "On KIE, 2k has no 5:4, 4:5, 3:1, 1:3 or 9:21 and 4k has no 3:1, 1:3 or 9:21.",
                    *(["APIMart takes up to 15 images; 16 only runs on KIE."] if mode == "edit" else []),
                ],
            )
        )
    return found


def _apimart_gpt2_images(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if len(source.get("image_urls") or ()) > 15:
        raise unsupported("apimart", "gpt-image-2 takes at most 15 images on APIMart")
    return out


def _kie_gpt2(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    resolution = source.get("resolution", "1k")
    if source.get("aspect_ratio") in KIE_GPT2_MISSING.get(resolution, ()):
        raise unsupported("kie", f"KIE has no {source['aspect_ratio']} at {resolution} for GPT Image 2")
    if out.get("background", "auto") == "auto":
        out.pop("background", None)  # el valor por defecto de KIE; no se envía para que valga en 2K y 4K
    elif resolution != "1k":
        raise unsupported("kie", "KIE only sets a transparent or opaque background at 1k")
    return out


# --- GPT Image 1.5 --------------------------------------------------------------------------------

GPT15_DOCS = "https://docs.kie.ai/market/gpt-image/1-5-text-to-image"


def _gpt15_id(mode: str) -> str:
    return f"openai/gpt-image-1.5/{mode}"


def _gpt15_models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in MODES:
        properties: dict[str, Any] = {
            "prompt": prompt(
                description="What to generate or, with images, what to change and what to keep."
            ),
            "aspect_ratio": choice(["1:1", "2:3", "3:2"], "1:1", "Output aspect ratio."),
            "quality": choice(
                ["medium", "high"], "medium", "medium is balanced; high is slower and more detailed."
            ),
        }
        required = ["prompt"]
        if mode == "edit":
            properties["image_urls"] = urls(1, 16, "One to sixteen images to edit or use as references.")
            required.append("image_urls")
        found.append(
            model(
                _gpt15_id(mode),
                name="GPT Image 1.5",
                workflow=workflow,
                family="gpt-image-1.5",
                output="image",
                capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                properties=properties,
                required=required,
                docs_url=GPT15_DOCS,
                notes=[
                    "OpenAI's GPT Image 1.5, only on KIE (APIMart lists it without a price). One image per task.",
                    "high quality costs about five times medium.",
                ],
            )
        )
    return found


# --- GPT-4o Image ---------------------------------------------------------------------------------

GPT4O_DOCS = "https://docs.kie.ai/4o-image-api/generate-4-o-image"
GPT4O_MODEL = "4o-image-api"


def _gpt4o_id(mode: str) -> str:
    return f"openai/gpt-4o-image/{mode}"


def _gpt4o_models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in MODES:
        properties: dict[str, Any] = {
            "prompt": prompt(
                description="What to generate or, with images, what to change and what to keep."
            ),
            "aspect_ratio": choice(["1:1", "3:2", "2:3"], "1:1", "Output aspect ratio."),
        }
        required = ["prompt"]
        if mode == "edit":
            properties["image_urls"] = urls(1, 5, "One to five images to edit or use as references.")
            required.append("image_urls")
        found.append(
            model(
                _gpt4o_id(mode),
                name="GPT-4o Image",
                workflow=workflow,
                family="gpt-4o-image",
                output="image",
                capabilities=["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"],
                properties=properties,
                required=required,
                docs_url=GPT4O_DOCS,
                notes=[
                    "OpenAI's GPT-4o image generation (the original ChatGPT image model), only on KIE.",
                    "KIE keeps the images for 14 days; download them before then.",
                ],
            )
        )
    return found


MODELS = _gpt2_models() + _gpt15_models() + _gpt4o_models()


def apimart() -> dict[str, Route]:
    provider, name = "apimart", "gpt-image-2"
    routes = {}
    for mode, _ in MODES:
        spec = Spec(
            provider, name,
            keep=("prompt", "resolution", "image_urls"),
            rename={"aspect_ratio": "size"},
            convert={"background": only_default("background", "auto")},
            # «auto» en APIMart es 1:1, no lo que elija el modelo: no se reproduce.
            allowed={"aspect_ratio": set(GPT2_RATIOS) - {"auto"}},
            fixed={"n": 1},
            build=_apimart_gpt2_images,
        )  # fmt: skip
        routes[_gpt2_id(mode)] = Route(
            provider, name, spec,
            lambda i, h, p: per_unit(p, f"{name}|{str(i.get('resolution', '1k')).upper()}"),
            official=False,
            notes=("Unofficial APIMart channel (alias of gpt-image-2-ext): cheaper, may be less stable",),
        )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    provider = "kie"
    routes: dict[str, Route] = {}
    for mode, _ in MODES:
        kie_mode = KIE_MODE[mode]

        name = f"gpt-image-2-{kie_mode}"
        spec = Spec(
            provider, name,
            keep=("prompt", "aspect_ratio", "resolution", "background"),
            rename={"image_urls": "input_urls"},
            convert={"resolution": upper},
            build=_kie_gpt2,
        )  # fmt: skip
        routes[_gpt2_id(mode)] = Route(
            provider, name, spec,
            lambda i, h, p, m=kie_mode: per_unit(p, f"gpt image 2, {m}, {i.get('resolution', '1k')}"),
        )  # fmt: skip

        name = f"gpt-image/1.5-{kie_mode}"
        spec = Spec(
            provider, name,
            keep=("prompt", "aspect_ratio", "quality"),
            rename={"image_urls": "input_urls"},
            allowed={"aspect_ratio": {"1:1", "2:3", "3:2"}, "quality": {"medium", "high"}},
        )  # fmt: skip
        routes[_gpt15_id(mode)] = Route(
            provider, name, spec,
            lambda i, h, p, m=kie_mode: per_unit(p, f"gpt image 1.5, {m}, {i.get('quality', 'medium')}"),
        )  # fmt: skip

        spec = Spec(
            provider, GPT4O_MODEL,
            keep=("prompt",),
            rename={"aspect_ratio": "size", "image_urls": "files_url"},
            allowed={"aspect_ratio": {"1:1", "3:2", "2:3"}},
        )  # fmt: skip
        routes[_gpt4o_id(mode)] = Route(
            provider, GPT4O_MODEL, spec,
            # KIE solo publica la fila de texto a imagen (6 créditos); se supone el mismo precio al editar.
            lambda i, h, p: per_unit(p, "openai 4o image, text-to-image"),
        )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset({"gpt-image-2"})
