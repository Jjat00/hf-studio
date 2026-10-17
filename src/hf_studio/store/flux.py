"""FLUX (Black Forest Labs) en las tiendas: FLUX.2 Flex/Pro/Max, FLUX 3 (imagen y video) y FLUX Kontext.

Fuentes (revisadas el 2026-10-17):
- APIMart FLUX.2 (`flux-2-flex`, `flux-2-pro`, `flux-2-max`):
  https://docs.apimart.ai/en/api-reference/images/flux-2/generation.md. `resolution` 1MP–4MP, `size` relación
  o `auto`, hasta 8 `image_urls`, `seed`, una imagen por tarea. Precio `flux-2-pro|1MP`…
- KIE vende FLUX.2 Pro y Flex (https://docs.kie.ai/market/flux2/pro-text-to-image.md) con `resolution` 1K/2K, pero
  no publica cuántos megapíxeles son: no se ruta allí porque el esquema promete megapíxeles exactos.
- APIMart FLUX 3 imagen (`flux-3-image`): https://docs.apimart.ai/en/api-reference/images/flux-3-image/generation.md
  (`resolution` 768sq/1k/1.5k/2k/4k, hasta 10 referencias sin recargo, sin semilla). Precio `flux-3-image|1K`…
- APIMart FLUX 3 video (`flux-3-video`): https://docs.apimart.ai/en/api-reference/videos/flux-3-video/generation.md
  (texto, fotogramas clave o continuación de video; 5–20 s; hd/fhd; audio). Precio por segundo
  `flux-3-video|HD`, `|FHD` y `|V2V-HD`, `|V2V-FHD` para la continuación.
- APIMart Kontext (`flux-kontext-pro`, `flux-kontext-max`):
  https://docs.apimart.ai/en/api-reference/images/flux-kontext/generation.md (~1 MP, hasta 4 referencias, png
  por defecto). Precio `flux-kontext-pro|default`.
- KIE Kontext: https://docs.kie.ai/flux-kontext-api/generate-or-edit-image.md. La versión nueva usa la API
  unificada con `model: flux1-kontext` e `input.model` pro|max, una sola `input_image`, 6 relaciones (sin
  relación en edición conserva la de la imagen), jpeg por defecto. Precio
  `black forest labs flux1-kontext, text-to-image, pro|max`; la tabla no tiene fila de edición y se usa esa.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, first, per_second, per_unit, unsupported
from ._common import choice, model, prompt, upper, url, urls

VENDOR = "black-forest-labs"
DOCS_FLUX2 = "https://docs.apimart.ai/en/api-reference/images/flux-2/generation"
DOCS_FLUX3 = "https://docs.apimart.ai/en/api-reference/images/flux-3-image/generation"
DOCS_FLUX3_VIDEO = "https://docs.apimart.ai/en/api-reference/videos/flux-3-video/generation"
DOCS_KONTEXT = "https://docs.apimart.ai/en/api-reference/images/flux-kontext/generation"
MODES = (("text-to-image", "Text to image"), ("edit", "Edit images"))
BFL_RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9", "9:21"]
SEED = {"type": "integer", "minimum": 0, "description": "Seed for reproducible results (APIMart only)."}


def _id(name: str, mode: str) -> str:
    return f"{VENDOR}/{name}/{mode}"


def _ratios(mode: str) -> dict[str, Any]:
    if mode == "edit":
        return choice(["auto", *BFL_RATIOS], "auto", "Output aspect ratio; auto follows the first image.")
    return choice(BFL_RATIOS, "1:1", "Output aspect ratio.")


def _refs(max_items: int, required: list[str], properties: dict[str, Any]) -> None:
    properties["image_urls"] = urls(1, max_items, f"One to {max_items} images to edit or use as references.")
    required.append("image_urls")


def _capabilities(mode: str) -> list[str]:
    return ["text-to-image"] if mode == "text-to-image" else ["edit", "image-references"]


# --- FLUX.2 -----------------------------------------------------------------------------------

FLUX2 = {"flex": "FLUX.2 Flex", "pro": "FLUX.2 Pro", "max": "FLUX.2 Max"}


def _flux2_models() -> list[dict[str, Any]]:
    found = []
    for tier, name in FLUX2.items():
        for mode, workflow in MODES:
            properties: dict[str, Any] = {
                "prompt": prompt(5000, "What to generate or, with images, what to change and what to keep."),
                "aspect_ratio": _ratios(mode),
                "resolution": choice(["1mp", "2mp", "3mp", "4mp"], "1mp", "Output size in megapixels."),
                "seed": SEED,
            }
            required = ["prompt"]
            if mode == "edit":
                _refs(8, required, properties)
            notes = ["Black Forest Labs' FLUX.2. Higgsfield does not sell it.", "Runs on APIMart only."]
            found.append(
                model(
                    _id(f"flux-2-{tier}", mode), name=name, workflow=workflow, family=f"flux-2-{tier}",
                    output="image", capabilities=_capabilities(mode), properties=properties, required=required,
                    docs_url=DOCS_FLUX2, notes=notes,
                )
            )  # fmt: skip
    return found


# --- FLUX 3 -----------------------------------------------------------------------------------

FLUX3_RATIOS = ["auto", "21:9", "2:1", "16:9", "3:2", "7:5", "4:3", "5:4", "1:1", "4:5", "3:4", "5:7", "2:3",
                "9:16", "1:2", "9:21"]  # fmt: skip
FLUX3_VIDEO_RATIOS = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
FLUX3_VIDEO_RES = {"720p": "hd", "1080p": "fhd"}


def _flux3_models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow in MODES:
        properties: dict[str, Any] = {
            "prompt": prompt(None, "What to generate or, with images, what to change. No negative prompts."),
            "aspect_ratio": choice(
                FLUX3_RATIOS, "auto",
                "Output aspect ratio; auto follows the first image or, without images, the prompt.",
            ),
            "resolution": choice(["768sq", "1k", "1.5k", "2k", "4k"], "1k",
                                 "Output tier: 768sq ~0.6 MP, 1k ~1 MP, 1.5k ~2 MP, 2k ~4 MP, 4k ~16 MP."),
        }  # fmt: skip
        required = ["prompt"]
        if mode == "edit":
            _refs(10, required, properties)
        found.append(
            model(
                _id("flux-3", mode), name="FLUX 3", workflow=workflow, family="flux-3", output="image",
                capabilities=_capabilities(mode), properties=properties, required=required, docs_url=DOCS_FLUX3,
                notes=["Black Forest Labs' FLUX 3. Higgsfield does not sell it: it runs on APIMart only.",
                       "References add no charge; the price depends only on the resolution."],
            )
        )  # fmt: skip
    video_modes = (
        ("text-to-video", "Text to video", ["text-to-video"]),
        ("image-to-video", "Image to video", ["image-to-video", "first-last-frame"]),
        ("video-extend", "Extend video", ["video-extend", "video-input"]),
    )
    for mode, workflow, capabilities in video_modes:
        properties = {
            "prompt": prompt(None, "What happens in the video."),
            "duration": choice(list(range(5, 21)), 5, "Length in seconds (5 to 20)."),
            "resolution": choice(list(FLUX3_VIDEO_RES), "720p", "Output resolution."),
            "generate_audio": {"type": "boolean", "title": "Sound", "default": True,
                               "description": "Synced audio (turning it off costs the same)."},
        }  # fmt: skip
        required = ["prompt"]
        if mode != "video-extend":
            properties["aspect_ratio"] = choice(FLUX3_VIDEO_RATIOS, "auto", "Output aspect ratio.")
        if mode == "image-to-video":
            properties["image_url"] = url("First frame.")
            properties["end_image_url"] = url("Optional last frame.")
            required.append("image_url")
        if mode == "video-extend":
            properties["video_url"] = url("MP4 video to continue.")
            required.append("video_url")
        notes = ["Black Forest Labs' FLUX 3 video. Higgsfield does not sell it: it runs on APIMart only."]
        if mode == "video-extend":
            notes.append(
                "Continuing a video costs more per second, and the result may be shorter than asked."
            )
        found.append(
            model(
                _id("flux-3", mode), name="FLUX 3 Video", workflow=workflow, family="flux-3-video", output="video",
                capabilities=capabilities, properties=properties, required=required, docs_url=DOCS_FLUX3_VIDEO,
                notes=notes,
            )
        )  # fmt: skip
    return found


# --- FLUX Kontext -----------------------------------------------------------------------------

KONTEXT = {"pro": "FLUX Kontext Pro", "max": "FLUX Kontext Max"}
KONTEXT_KIE_RATIOS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
KONTEXT_NOTES = [
    "Black Forest Labs' FLUX.1 Kontext (~1 MP). Higgsfield does not sell it: it runs on APIMart or KIE.",
    (
        "KIE takes a single image and 21:9, 16:9, 4:3, 1:1, 3:4 or 9:16; more images, other ratios and a "
        "fixed seed only run on APIMart."
    ),
]


def _kontext_models() -> list[dict[str, Any]]:
    found = []
    for tier, name in KONTEXT.items():
        for mode, workflow in MODES:
            properties: dict[str, Any] = {
                "prompt": prompt(
                    None, "What to generate or what to change in the image (English works best)."
                ),
                "aspect_ratio": _ratios(mode),
                "output_format": choice(["png", "jpeg"], "png", "Output image format."),
                "seed": SEED,
            }
            required = ["prompt"]
            if mode == "edit":
                _refs(4, required, properties)
            found.append(
                model(
                    _id(f"flux-kontext-{tier}", mode), name=name, workflow=workflow, family=f"flux-kontext-{tier}",
                    output="image", capabilities=_capabilities(mode), properties=properties, required=required,
                    docs_url=DOCS_KONTEXT,
                    notes=KONTEXT_NOTES,
                )
            )  # fmt: skip
    return found


MODELS = [*_flux2_models(), *_flux3_models(), *_kontext_models()]


# --- Rutas ------------------------------------------------------------------------------------


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes: dict[str, Route] = {}
    for tier in FLUX2:
        name = f"flux-2-{tier}"
        spec = Spec(
            provider, name, keep=("prompt", "image_urls", "seed"), rename={"aspect_ratio": "size"},
            convert={"resolution": upper},
        )  # fmt: skip
        for mode, _ in MODES:
            routes[_id(name, mode)] = Route(
                provider, name, spec,
                lambda i, h, p, m=name: per_unit(p, f"{m}|{str(i.get('resolution', '1mp')).upper()}"),
            )  # fmt: skip
    flux3 = Spec(
        provider, "flux-3-image", keep=("prompt", "image_urls", "aspect_ratio"), convert={"resolution": upper}
    )
    for mode, _ in MODES:
        routes[_id("flux-3", mode)] = Route(
            provider, "flux-3-image", flux3,
            lambda i, h, p: per_unit(p, f"flux-3-image|{str(i.get('resolution', '1k')).upper()}"),
        )  # fmt: skip
    routes.update(_flux3_video())
    for tier in KONTEXT:
        name = f"flux-kontext-{tier}"
        spec = Spec(
            provider, name, keep=("prompt", "image_urls", "seed", "output_format"), rename={"aspect_ratio": "size"}
        )  # fmt: skip
        for mode, _ in MODES:
            routes[_id(name, mode)] = Route(
                provider, name, spec, lambda i, h, p, m=name: per_unit(p, f"{m}|default")
            )
    return routes


def _video_frames(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if source.get("end_image_url") and not source.get("image_url"):
        raise unsupported("apimart", "flux-3-video needs a first frame to use a last frame")
    frames = [u for u in (source.get("image_url"), source.get("end_image_url")) if u]
    if frames:
        out["image_urls"] = frames
    return out


def _flux3_video() -> dict[str, Route]:
    provider, name = "apimart", "flux-3-video"
    routes = {}
    for mode, api_mode, prefix in (("text-to-video", "t2v", ""), ("image-to-video", "i2v", ""),
                                   ("video-extend", "v2v", "V2V-")):  # fmt: skip
        spec = Spec(
            provider, name,
            keep=("prompt", "duration", "aspect_ratio", "video_url"),
            rename={"generate_audio": "audio"},
            convert={"resolution": FLUX3_VIDEO_RES.__getitem__, "image_url": lambda v: None,
                     "end_image_url": lambda v: None},
            allowed={"resolution": FLUX3_VIDEO_RES},
            fixed={"mode": api_mode},
            build=_video_frames,
        )  # fmt: skip
        routes[_id("flux-3", mode)] = Route(
            provider, name, spec,
            lambda i, h, p, pre=prefix: per_second(
                p, f"{name}|{pre}{FLUX3_VIDEO_RES.get(i.get('resolution', '720p'), 'hd').upper()}", i.get("duration")
            ),
            # La continuación se cobra por adelantado por los segundos pedidos y devuelve la diferencia.
            notes=("Continuation may deliver fewer seconds than asked; the difference is refunded",)
            if mode == "video-extend" else (),
        )  # fmt: skip
    return routes


def _kontext_kie_build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    images = source.get("image_urls") or []
    if len(images) > 1:
        raise unsupported("kie", "KIE's Kontext edits a single image")
    if out.get("aspect_ratio") == "auto":
        out.pop("aspect_ratio")  # sin relación, KIE conserva la de la imagen: lo mismo que auto
    return out


def kie() -> dict[str, Route]:
    provider = "kie"
    routes: dict[str, Route] = {}
    # FLUX.2 no va a KIE: KIE pide 1K/2K y no publica cuántos megapíxeles son, así que no se puede garantizar
    # la resolución en megapíxeles que pide el esquema (revisión 87).
    for tier in KONTEXT:
        for mode, _ in MODES:
            ratios = KONTEXT_KIE_RATIOS | ({"auto"} if mode == "edit" else set())
            spec = Spec(
                provider, "flux1-kontext",
                keep=("prompt", "aspect_ratio", "output_format"),
                rename={"image_urls": "input_image"},
                convert={"image_urls": first},
                allowed={"aspect_ratio": ratios},
                fixed={"model": f"flux-kontext-{tier}"},
                build=_kontext_kie_build,
            )  # fmt: skip
            routes[_id(f"flux-kontext-{tier}", mode)] = Route(
                provider, "flux1-kontext", spec,
                lambda i, h, p, t=tier: per_unit(p, f"black forest labs flux1-kontext, text-to-image, {t}"),
            )  # fmt: skip
    return routes


APIMART_IMAGE_MODELS = frozenset(
    {*(f"flux-2-{t}" for t in FLUX2), "flux-3-image", *(f"flux-kontext-{t}" for t in KONTEXT)}
)
