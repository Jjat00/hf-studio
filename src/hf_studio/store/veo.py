"""Veo 3.1 (Google) en las tiendas: Higgsfield no lo vende como modelo propio.

Fuentes (revisadas el 2026-10-17):
- APIMart `veo3.1-lite` / `veo3.1-fast` / `veo3.1-quality` (canal no oficial, alias `-ext`):
  https://docs.apimart.ai/en/api-reference/videos/veo3/generation.md. Solo 8 s, 16:9 o 9:16, 720p/1080p/4k,
  hasta 3 `image_urls` con `generation_type` frame|reference (quality no tiene reference; lite no acepta
  imágenes). Precio por video: `veo3.1-<tier>|default` (720p y 1080p) y `|4K`.
- APIMart `veo3.1-fast-official` / `veo3.1-quality-official`:
  https://docs.apimart.ai/en/api-reference/videos/veo3/generation-official.md. 4/6/8 s, 720p/1080p/4K,
  `first_frame_image` / `last_frame_image`, `negative_prompt`, `seed`, `generate_audio` (apagado por
  defecto). Precio por segundo: `<modelo>|<RES>` y `|<RES>-audio` (en quality, 720p/1080p con audio es `|audio`).
- KIE Veo 3.1: https://docs.kie.ai/veo3-api/generate-veo-3-video.md. La versión nueva usa `jobs/createTask`
  con `model: veo-3-1` y el nivel en `input.model` (veo3_lite | veo3_fast | veo3); `generation_type`
  TEXT_2_VIDEO | FIRST_AND_LAST_FRAMES_2_VIDEO | REFERENCE_2_VIDEO (solo fast y lite, solo 8 s); siempre con
  audio. Precio por video: `google veo 3.1, <modo>, <tier>-<res>` (la fila de 1080p/4k ya suma la mejora).
  Lleva `KIE_ENDPOINTS` solo para leer el resultado: en 1080p/4k la URL puede venir en
  `resultJson.data.result_urls` en vez de `resultUrls`.
No se ofrecen la extensión ni la mejora posterior a 1080p/4K.
"""

from __future__ import annotations

import json
from typing import Any

from ..providers.base import Polled, media_kind
from ..providers.kie import KIEEndpoint, polled
from ..providers.routes import Route, Spec, only_default, per_second, per_unit
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.kie.ai/veo3-api/generate-veo-3-video"
TIERS = {"lite": "Lite", "fast": "Fast", "quality": "Quality"}
KIE_TIERS = {"lite": "veo3_lite", "fast": "veo3_fast", "quality": "veo3"}
# Modos por nivel: quality no tiene referencias en ninguna tienda.
MODES = {
    "lite": ("text-to-video", "image-to-video", "reference-to-video"),
    "fast": ("text-to-video", "image-to-video", "reference-to-video"),
    "quality": ("text-to-video", "image-to-video"),
}
WORKFLOWS = {
    "text-to-video": ("Text to video", ["text-to-video"]),
    "image-to-video": ("Image to video", ["image-to-video", "first-last-frame"]),
    "reference-to-video": ("Reference to video", ["reference-to-video", "image-references"]),
}
KIE_TYPES = {
    "text-to-video": "TEXT_2_VIDEO",
    "image-to-video": "FIRST_AND_LAST_FRAMES_2_VIDEO",
    "reference-to-video": "REFERENCE_2_VIDEO",
}
RATIOS = ["16:9", "9:16"]
EXT_NOTE = "Unofficial APIMart channel: cheaper, may be less stable; always 8 s with audio"


def _id(tier: str, mode: str) -> str:
    return f"google/veo-3.1/{tier}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for tier, label in TIERS.items():
        for mode in MODES[tier]:
            workflow, capabilities = WORKFLOWS[mode]
            durations = [8] if mode == "reference-to-video" else [4, 6, 8]
            properties: dict[str, Any] = {
                "prompt": prompt(description="What happens in the video, including any dialogue or sound."),
                "aspect_ratio": choice(RATIOS, "16:9", "Landscape (16:9) or portrait (9:16)."),
                "resolution": choice(["720p", "1080p", "4k"], "720p", "Output resolution."),
                "duration": choice(durations, 8, "Length in seconds."),
                "generate_audio": {
                    "type": "boolean", "default": True,
                    "description": "Generate the soundtrack. Only APIMart's official channel can turn it off.",
                },
            }  # fmt: skip
            notes = [
                "Google's Veo 3.1. Higgsfield does not sell it on its own: it runs on APIMart or KIE.",
            ]
            if mode != "reference-to-video" and tier != "lite":
                properties["negative_prompt"] = {
                    "type": "string", "description": "What to avoid (only APIMart's official channel)."
                }  # fmt: skip
                properties["seed"] = {
                    "type": "integer", "minimum": 0, "maximum": 4294967295,
                    "description": "Seed for reproducible results (only APIMart's official channel).",
                }  # fmt: skip
                notes.append(
                    "4 and 6 second clips, a fixed seed and silent video skip APIMart's unofficial channel."
                )
            required = ["prompt"]
            if mode == "image-to-video":
                properties["image_url"] = url("First frame of the video.")
                properties["end_image_url"] = url("Optional last frame; the video transitions to it.")
                required.append("image_url")
            elif mode == "reference-to-video":
                properties["image_urls"] = urls(
                    1, 3, "One to three images of subjects, products or styles to keep."
                )
                required.append("image_urls")
                notes.append("Reference mode only makes 8 second clips.")
            found.append(
                model(
                    _id(tier, mode),
                    name=f"Veo 3.1 {label}",
                    workflow=workflow,
                    family=f"veo-3.1-{tier}",
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


# --- APIMart ------------------------------------------------------------------------------------


def _ext_build(mode: str):
    """Canal no oficial: primer y último fotograma (`frame`) o referencias (`reference`) en `image_urls`."""

    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if mode == "image-to-video":
            out["image_urls"] = [
                source["image_url"],
                *([source["end_image_url"]] if source.get("end_image_url") else []),
            ]
            out.pop("image_url", None)
            out.pop("end_image_url", None)
            out["generation_type"] = "frame"
        elif mode == "reference-to-video":
            out["generation_type"] = "reference"
        return out

    return build


def _ext_price(name: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        return per_unit(prices, f"{name}|{'4K' if i.get('resolution') == '4k' else 'default'}")

    return price


def _official_res(value: str) -> str:
    return "4K" if value == "4k" else value


def _official_price(name: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        res = str(i.get("resolution", "720p")).upper()
        key = f"{name}|{res}"
        if i.get("generate_audio", True):
            # quality no tiene fila 720P-audio ni 1080P-audio: su precio con audio es `audio`.
            key = f"{key}-audio" if f"{key}-audio" in prices else f"{name}|audio"
        return per_second(prices, key, i.get("duration"))

    return price


def _official_route(tier: str, mode: str) -> Route:
    name = f"veo3.1-{tier}-official"
    keep = ("prompt", "duration", "aspect_ratio", "negative_prompt", "seed", "generate_audio")
    rename = (
        {"image_url": "first_frame_image", "end_image_url": "last_frame_image"}
        if mode == "image-to-video"
        else {}
    )
    spec = Spec(
        "apimart", name, keep=keep, rename=rename,
        convert={"resolution": _official_res}, allowed={"aspect_ratio": set(RATIOS)},
    )  # fmt: skip
    return Route("apimart", name, spec, _official_price(name))


def _ext_route(tier: str, mode: str) -> Route:
    name = f"veo3.1-{tier}"
    keep = ("prompt", "duration", "aspect_ratio", "resolution")
    if mode == "image-to-video":
        keep = (*keep, "image_url", "end_image_url")
    elif mode == "reference-to-video":
        keep = (*keep, "image_urls")
    spec = Spec(
        "apimart", name, keep=keep,
        convert={"generate_audio": only_default("generate_audio", True)},
        allowed={"duration": {8}, "aspect_ratio": set(RATIOS)},
        build=_ext_build(mode),
    )  # fmt: skip
    return Route("apimart", name, spec, _ext_price(name), official=False, notes=(EXT_NOTE,))


def apimart() -> dict[str, Route | tuple[Route, ...]]:
    routes: dict[str, Route | tuple[Route, ...]] = {}
    for tier in TIERS:
        for mode in MODES[tier]:
            found = []
            # Oficial: fast y quality, sin referencias.
            if tier != "lite" and mode != "reference-to-video":
                found.append(_official_route(tier, mode))
            # No oficial: lite solo texto; quality sin referencias.
            if mode == "text-to-video" or (
                tier != "lite" and not (tier == "quality" and mode == "reference-to-video")
            ):
                found.append(_ext_route(tier, mode))
            if found:
                routes[_id(tier, mode)] = found[0] if len(found) == 1 else tuple(found)
    return routes


# --- KIE ----------------------------------------------------------------------------------------

KIE_MODEL = "veo-3-1"


def _kie_build(tier: str, mode: str):
    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        if mode == "image-to-video":
            out["image_urls"] = [
                source["image_url"],
                *([source["end_image_url"]] if source.get("end_image_url") else []),
            ]
            out.pop("image_url", None)
            out.pop("end_image_url", None)
        out["model"] = KIE_TIERS[tier]
        out["generation_type"] = KIE_TYPES[mode]
        return out

    return build


def _kie_price(tier: str, mode: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        return per_unit(prices, f"google veo 3.1, {mode}, {tier}-{i.get('resolution', '720p')}")

    return price


def kie() -> dict[str, Route]:
    routes = {}
    for tier in TIERS:
        for mode in MODES[tier]:
            keep = ("prompt", "duration", "aspect_ratio", "resolution")
            if mode == "image-to-video":
                keep = (*keep, "image_url", "end_image_url")
            elif mode == "reference-to-video":
                keep = (*keep, "image_urls")
            spec = Spec(
                "kie", KIE_MODEL, keep=keep,
                convert={"generate_audio": only_default("generate_audio", True)},
                allowed={"aspect_ratio": set(RATIOS)},
                build=_kie_build(tier, mode),
            )  # fmt: skip
            routes[_id(tier, mode)] = Route("kie", KIE_MODEL, spec, _kie_price(tier, mode))
    return routes


def _kie_body(model_name: str, arguments: dict[str, Any], callback_url: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model_name, "input": arguments}
    if callback_url:
        body["callBackUrl"] = callback_url
    return body


def _kie_parse(data: dict[str, Any]) -> Polled:
    """Estado de la API unificada; en 1080p/4k la URL final puede venir en `resultJson.data.result_urls`."""
    result = polled(data)
    if result.status != "completed" or result.outputs:
        return result
    try:
        parsed = json.loads(data.get("resultJson") or "{}")
    except ValueError:
        parsed = {}
    inner = parsed.get("data") if isinstance(parsed, dict) else None
    found = (inner or {}).get("result_urls") or (inner or {}).get("resultUrls") or []
    if not found:
        return result
    outputs = [{"kind": media_kind(u), "url": u, "content_type": None} for u in found if isinstance(u, str)]
    return Polled("completed", outputs, raw=data)


KIE_ENDPOINTS = {
    KIE_MODEL: KIEEndpoint(
        "veo-3-1", "/api/v1/jobs/createTask", "/api/v1/jobs/recordInfo", _kie_body, _kie_parse
    )
}
