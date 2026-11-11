"""Gemini Omni (Google), modelo de video multimodal, en las tiendas. Higgsfield no lo ofrece.

Fuentes (revisadas el 2026-10-17):
- KIE `google/gemini-omni-flash-1-1`: https://docs.kie.ai/market/google/gemini-omni-flash-1-1.md (`duration`
  "4"|"6"|"8"|"10" obligatorio, 16:9|9:16, 360p–4k, `first_frame_url` + `last_frame_url` o hasta 7
  `image_urls`, `seed`). Precio por video: `google/gemini-omni-flash-1-1, video, <d>s <res> no video input`.
- KIE `gemini-omni-video` (Gemini Omni Flash): https://docs.kie.ai/market/gemini-omni-video.md (igual, pero
  720p–4k y sin fotograma inicial). Precio `gemini-omni-video, video, <d>s <res> no video input`.
- APIMart `gemini-omni-1.1-flash-ext` (canal no oficial; en la tabla de precios `Omni-Flash-Ext`):
  https://docs.apimart.ai/en/api-reference/videos/omni-flash-ext/generation.md (4/6/8/10 s, 360p–4k, una
  imagen como primer fotograma o 1 o 3 referencias, sin último fotograma). Precio por video
  `Omni-Flash-Ext|<RES>-<d>S`.
No se usan `gemini-omni-1.1-flash` ni `gemini-omni-flash-preview` de APIMart: no tienen duración (el modelo
la elige, 3–10 s) y cobran por segundo, así que no reproducen la duración pedida ni se pueden cotizar. Tampoco
se ofrece la entrada de video (KIE pide recortarla con `start`/`ends`, que la entrada lógica no dice).

Gemini Omni 1.2 Flash:
- APIMart `gemini-omni-1.2-flash` (revisado el 2026-11-06):
  https://docs.apimart.ai/en/api-reference/videos/gemini-omni-1.2-flash/generation.md (3–15 s, 3–10 s con
  último fotograma, 16:9|9:16, 360p–4k, `first_frame_image` + `last_frame_image`, hasta 10 `image_urls`,
  edición con `video_urls`). Se liquida por tokens: el precio por segundo de la tabla
  (`gemini-omni-1.2-flash|<RES>`) es aproximado, y al enviar retiene `max(10, duración)` segundos (la edición,
  15). No se ofrece la extensión: no está claro si cobra solo el tramo añadido.
- KIE `google/gemini-omni-flash-1-2` (revisado el 2026-11-11):
  https://docs.kie.ai/market/google/gemini-omni-flash-1-2.md (un modo por pedido: texto o hasta 6 `image_urls`,
  `first_frame_url` con `last_frame_url` opcional (3–10 s con los dos) o edición con `video_list` de un video
  de hasta 15 s y sin `duration`; 3–15 s, 360p–4k, `seeds` 10000–99999). Precio fijo por segundo de salida
  `google/gemini-omni-flash-1-2, video, <res>` (`creditUnit` «per second»); según https://kie.ai/gemini-omni-1-2-flash
  la edición se cobra por la duración del video de entrada a la misma tarifa.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, per_unit, unsupported, video_seconds
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.kie.ai/market/google/gemini-omni-flash-1-1"
EXT = "gemini-omni-1.1-flash-ext"
# Variante lógica -> (nombre, modelo de KIE, resoluciones, modos)
VARIANTS = {
    "gemini-omni-1.1-flash": (
        "Gemini Omni 1.1 Flash", "google/gemini-omni-flash-1-1", ["360p", "720p", "1080p", "4k"],
        ("text-to-video", "image-to-video", "reference-to-video"),
    ),
    "gemini-omni-flash": (
        "Gemini Omni Flash", "gemini-omni-video", ["720p", "1080p", "4k"], ("text-to-video", "reference-to-video"),
    ),
}  # fmt: skip
WORKFLOWS = {
    "text-to-video": ("Text to video", ["text-to-video"]),
    "image-to-video": ("Image to video", ["image-to-video", "first-last-frame"]),
    "reference-to-video": ("Reference to video", ["reference-to-video", "image-references"]),
}


def _id(variant: str, mode: str) -> str:
    return f"google/{variant}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for variant, (name, _, resolutions, modes) in VARIANTS.items():
        for mode in modes:
            workflow, capabilities = WORKFLOWS[mode]
            properties: dict[str, Any] = {
                "prompt": prompt(20000, "What happens in the video; with images, how to use each one."),
                "duration": choice([4, 6, 8, 10], 8, "Length in seconds."),
                "aspect_ratio": choice(["16:9", "9:16"], "16:9", "Landscape (16:9) or portrait (9:16)."),
                "resolution": choice(resolutions, "720p", "Output resolution."),
                "seed": {
                    "type": "integer", "minimum": 0, "maximum": 2147483647,
                    "description": "Seed for more repeatable results (KIE only).",
                },
            }  # fmt: skip
            required = ["prompt"]
            notes = [
                f"Google's {name} video model with generated audio, through APIMart or KIE (not Higgsfield)."
            ]
            if mode == "image-to-video":
                properties["image_url"] = url("First frame of the video.")
                properties["end_image_url"] = url("Optional last frame (KIE only).")
                required.append("image_url")
            elif mode == "reference-to-video":
                properties["image_urls"] = urls(1, 7, "One to seven images of characters, scenes or styles.")
                required.append("image_urls")
                if variant == "gemini-omni-1.1-flash":
                    notes.append(
                        "APIMart takes exactly 1 or 3 reference images; other counts run on KIE only."
                    )
            found.append(
                model(
                    _id(variant, mode),
                    name=name,
                    workflow=workflow,
                    family=variant,
                    output="video",
                    capabilities=capabilities,
                    properties=properties,
                    required=required,
                    docs_url=DOCS,
                    notes=notes,
                )
            )
    return found


MODELS = _models()


# --- Gemini Omni 1.2 Flash (APIMart) -----------------------------------------------------------------

V12 = "gemini-omni-1.2-flash"
V12_DOCS = "https://docs.apimart.ai/en/api-reference/videos/gemini-omni-1.2-flash/generation"
V12_MODES = {**WORKFLOWS, "video-edit": ("Edit video", ["video-edit", "video-input"])}


def _v12_models() -> list[dict[str, Any]]:
    found = []
    note = "Google's Gemini Omni 1.2 Flash with generated audio (24 fps), through APIMart or KIE (not Higgsfield)."
    billing = (
        "KIE bills a fixed rate per second. APIMart bills by tokens afterwards (approximate quote) and first "
        "holds at least 10 s."
    )
    for mode, (workflow, capabilities) in V12_MODES.items():
        properties: dict[str, Any] = {
            "prompt": prompt(20000, "What happens in the video; with images, how to use each one."),
            "duration": choice(list(range(3, 16)), 10, "Length in seconds (at most 10 with a last frame)."),
            "aspect_ratio": choice(["16:9", "9:16"], "16:9", "Landscape (16:9) or portrait (9:16)."),
            "resolution": choice(["360p", "720p", "1080p", "4k"], "720p", "Output resolution (1080p and 4k are upsampled)."),
        }  # fmt: skip
        required = ["prompt"]
        notes = [note, billing]
        if mode == "image-to-video":
            properties["image_url"] = url("First frame of the video.")
            properties["end_image_url"] = url("Optional last frame, same aspect ratio as the first.")
            required.append("image_url")
        elif mode == "reference-to-video":
            properties["image_urls"] = urls(1, 10, "One to ten images of characters, products or places.")
            required.append("image_urls")
            notes.append("For characters, use at most 2 with up to 3 images each. KIE takes up to 6 images.")
        elif mode == "video-edit":
            del properties["duration"]
            properties["prompt"] = prompt(
                20000, "What to change; add 'Keep everything else the same' for local edits."
            )
            properties["video_url"] = url("Video to edit (up to 15 s); the result keeps its length.")
            required.append("video_url")
            notes[1] = (
                "Billed by the source length: a fixed rate per second on KIE; by tokens afterwards on APIMart "
                "(approximate quote, holds 15 s)."
            )
        found.append(
            model(
                _id(V12, mode), name="Gemini Omni 1.2 Flash", workflow=workflow, family=V12, output="video",
                capabilities=capabilities, properties=properties, required=required, docs_url=V12_DOCS,
                notes=notes,
            )
        )  # fmt: skip
    return found


MODELS = [*MODELS, *_v12_models()]


def _v12_build(mode: str):
    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if mode == "image-to-video" and source.get("end_image_url") and int(source.get("duration", 10)) > 10:
            raise unsupported("apimart", "Gemini Omni 1.2 takes at most 10 s with a last frame")
        if mode == "reference-to-video":
            out["omni_reference_task_type"] = "reference"
        elif mode == "video-edit":
            out["video_urls"] = [out.pop("video_url")]
            out["omni_reference_task_type"] = "edit"
        return out

    return build


def _v12_rate_key(i: dict) -> str:
    return f"{V12}|{str(i.get('resolution', '720p')).upper()}"


def _v12_price(mode: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        seconds = video_seconds(hints) if mode == "video-edit" else i.get("duration")
        return per_second(prices, _v12_rate_key(i), seconds)

    return price


def _v12_reserve(mode: str):
    def reserve(i: dict, hints: dict, prices: dict) -> float | None:
        seconds = 15 if mode == "video-edit" else max(10, int(i.get("duration", 10)))
        return per_second(prices, _v12_rate_key(i), seconds)

    return reserve


def _v12_routes() -> dict[str, Route]:
    routes = {}
    for mode in V12_MODES:
        keep: tuple[str, ...] = ("prompt", "duration", "aspect_ratio", "resolution")
        rename = {}
        if mode == "image-to-video":
            rename = {"image_url": "first_frame_image", "end_image_url": "last_frame_image"}
        elif mode == "reference-to-video":
            keep = (*keep, "image_urls")
        elif mode == "video-edit":
            keep = ("prompt", "aspect_ratio", "resolution", "video_url")
        routes[_id(V12, mode)] = Route(
            "apimart", V12, Spec("apimart", V12, keep=keep, rename=rename, build=_v12_build(mode)),
            _v12_price(mode), reserve=_v12_reserve(mode), settles_later=True,
        )  # fmt: skip
    return routes


def _ext_build(mode: str):
    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if mode == "image-to-video":
            out["image_urls"] = [out.pop("image_url")]
            out["generation_type"] = "frame"
        elif mode == "reference-to-video":
            if len(source["image_urls"]) not in (1, 3):
                raise unsupported("apimart", "APIMart's Gemini Omni takes exactly 1 or 3 reference images")
            out["generation_type"] = "reference"
        return out

    return build


def _ext_price(i: dict, hints: dict, prices: dict) -> float | None:
    return per_unit(prices, f"Omni-Flash-Ext|{str(i.get('resolution', '720p')).upper()}-{i.get('duration')}S")


def apimart() -> dict[str, Route]:
    routes = {}
    variant = "gemini-omni-1.1-flash"
    for mode in VARIANTS[variant][3]:
        keep = ("prompt", "duration", "aspect_ratio", "resolution")
        if mode == "image-to-video":
            keep = (*keep, "image_url")
        elif mode == "reference-to-video":
            keep = (*keep, "image_urls")
        routes[_id(variant, mode)] = Route(
            "apimart", EXT, Spec("apimart", EXT, keep=keep, build=_ext_build(mode)), _ext_price,
            official=False, notes=("Unofficial APIMart channel (ext): cheaper, may be less stable",),
        )  # fmt: skip
    routes.update(_v12_routes())
    return routes


def _kie_price(row: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        return per_unit(
            prices, f"{row}, video, {i.get('duration')}s {i.get('resolution', '720p')} no video input"
        )

    return price


V12_KIE = "google/gemini-omni-flash-1-2"
V12_KIE_MAX_REFS = 6
V12_MAX_EDIT_SECONDS = 15


def _v12_kie_build(mode: str):
    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if mode == "image-to-video" and source.get("end_image_url") and int(source.get("duration", 10)) > 10:
            raise unsupported("kie", "Gemini Omni 1.2 takes at most 10 s with a last frame")
        if mode == "reference-to-video" and len(source["image_urls"]) > V12_KIE_MAX_REFS:
            raise unsupported(
                "kie", f"KIE's Gemini Omni 1.2 takes at most {V12_KIE_MAX_REFS} reference images"
            )
        if mode == "video-edit":
            out["video_list"] = [out.pop("video_url")]
        return out

    return build


def _v12_kie_price(mode: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        seconds = video_seconds(hints) if mode == "video-edit" else i.get("duration")
        return per_second(prices, f"{V12_KIE}, video, {i.get('resolution', '720p')}", seconds)

    return price


def _edit_length(source: dict[str, Any], hints: dict[str, Any]) -> None:
    seconds = video_seconds(hints)
    if seconds is not None and seconds > V12_MAX_EDIT_SECONDS:
        raise unsupported("kie", f"KIE's Gemini Omni 1.2 edits videos up to {V12_MAX_EDIT_SECONDS} s")


def _v12_kie_routes() -> dict[str, Route]:
    routes = {}
    for mode in V12_MODES:
        keep: tuple[str, ...] = ("prompt", "duration", "aspect_ratio", "resolution")
        rename = {}
        if mode == "image-to-video":
            rename = {"image_url": "first_frame_url", "end_image_url": "last_frame_url"}
        elif mode == "reference-to-video":
            keep = (*keep, "image_urls")
        elif mode == "video-edit":
            keep = ("prompt", "aspect_ratio", "resolution", "video_url")
        routes[_id(V12, mode)] = Route(
            "kie", V12_KIE, Spec("kie", V12_KIE, keep=keep, rename=rename, build=_v12_kie_build(mode)),
            _v12_kie_price(mode), check=_edit_length if mode == "video-edit" else None,
        )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    routes = _v12_kie_routes()
    for variant, (_, name, _, modes) in VARIANTS.items():
        for mode in modes:
            keep = ("prompt", "aspect_ratio", "resolution", "seed")
            rename = {}
            if mode == "image-to-video":
                rename = {"image_url": "first_frame_url", "end_image_url": "last_frame_url"}
            elif mode == "reference-to-video":
                keep = (*keep, "image_urls")
            spec = Spec("kie", name, keep=keep, rename=rename, convert={"duration": str})
            routes[_id(variant, mode)] = Route("kie", name, spec, _kie_price(name))
    return routes
