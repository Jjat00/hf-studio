"""MiniMax en las tiendas: Hailuo 02, Hailuo 2.3 Fast y Pro, y H3 Max. Higgsfield solo tiene H3 y Hailuo 2.3 Standard
(rutas en `providers/*_routes.py`).

Fuentes (revisadas el 2026-10-17):
- KIE `hailuo/02-{text,image}-to-video-{standard,pro}`: https://docs.kie.ai/market/hailuo/02-text-to-video-standard.md
  (y las otras tres). Standard: 6 o 10 s (texto 768P; imagen 512P/768P y último fotograma). Pro: 1080P y 6 s fijos,
  sin campos de duración ni resolución. Precio por video `hailuo 02, <modo>, <tier>-<d>.0s-<res>`.
- APIMart `MiniMax-Hailuo-2.3-Fast`: https://docs.apimart.ai/en/api-reference/videos/minimax-hailuo-2.3/generation.md
  (primer fotograma obligatorio; 6 o 10 s; 768p/1080p, 1080p solo 6 s). Precio por segundo `|default` (768p) o `|1080P`.
- KIE `hailuo/2-3-image-to-video-pro`: https://docs.kie.ai/market/hailuo/2-3-image-to-video-pro.md (6 o 10 s,
  768P/1080P, 1080P solo 6 s, sin `prompt_optimizer`). Precio por video `hailuo 2.3, image-to-video, pro-<d>.0s-<res>`.
- APIMart `MiniMax-H3-Max`: https://docs.apimart.ai/en/api-reference/videos/minimax-h3/max.md (5–15 s; 480P/768P/1080P;
  texto, primer/último fotograma o referencias: hasta 9 imágenes, 3 videos y 3 audios; marca de agua solo en
  480P/768P). Precio: `|<RES>` por segundo + `|input:image` por imagen después de las 2 primeras +
  `|input:video:<RES>` por segundo de video de referencia.
- Descartados: APIMart `MiniMax-Hailuo-02`
  (https://docs.apimart.ai/en/api-reference/videos/minimax-hailuo/generation.md documenta 5 o 10 s, y 1080p solo
  5 s, frente a los 6 o 10 s del modelo en KIE: un mismo pedido no daría el mismo video), `MiniMax-H3-Context-IR` (devuelve texto, no un video) y `MiniMax-H3-Regeneration` (solo acepta el
  `task_id` de una tarea H3 768P de la misma cuenta de APIMart).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, per_unit, unsupported, video_seconds
from ._common import choice, model, prompt, url, urls

DOCS_02 = "https://docs.kie.ai/market/hailuo/02-text-to-video-standard"
DOCS_23 = "https://docs.kie.ai/market/hailuo/2-3-image-to-video-pro"
DOCS_23_FAST = "https://docs.apimart.ai/en/api-reference/videos/minimax-hailuo-2.3/generation"
DOCS_H3_MAX = "https://docs.apimart.ai/en/api-reference/videos/minimax-h3/max"
H3_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
OPTIMIZER = {
    "type": "boolean",
    "default": True,
    "description": "Let MiniMax rewrite the prompt for better results.",
}
WATERMARK = {
    "type": "boolean",
    "default": False,
    "description": "Add MiniMax's AIGC watermark (not at 1080p).",
}


def _id(*parts: str) -> str:
    return "minimax/" + "/".join(parts)


def _models() -> list[dict[str, Any]]:
    found = []
    # Hailuo 02: Standard (768P, o 512P con imagen) y Pro (1080P), como los separa KIE.
    for tier, label in (("standard", "Standard"), ("pro", "Pro")):
        pro = tier == "pro"
        base: dict[str, Any] = {
            "prompt": prompt(1500, "What happens in the video, including camera movement."),
            "prompt_optimizer": OPTIMIZER,
        }
        if not pro:
            base["duration"] = choice([6, 10], 6, "Video length in seconds.")
        res_note = "Output is 1080p and 6 s long." if pro else "Text to video is 768p."
        for mode, workflow in (("text-to-video", "Text to video"), ("image-to-video", "Image to video")):
            properties = dict(base)
            required = ["prompt"]
            caps = ["text-to-video"]
            if mode == "image-to-video":
                properties["image_url"] = url("First frame.")
                properties["end_image_url"] = url("Optional last frame.")
                if not pro:
                    properties["resolution"] = choice(["512p", "768p"], "768p", "Output resolution.")
                required.append("image_url")
                caps = ["image-to-video", "first-last-frame"]
            found.append(model(
                _id("hailuo-02", tier, mode), name=f"Hailuo 02 {label}", workflow=workflow,
                family=f"hailuo-02-{tier}", output="video", capabilities=caps, properties=properties,
                required=required, docs_url=DOCS_02,
                notes=[res_note, "Runs on KIE only."],
            ))  # fmt: skip
    found.append(model(
        _id("hailuo-2.3", "fast", "image-to-video"), name="Hailuo 2.3 Fast", workflow="Image to video",
        family="hailuo-2-3-fast", output="video", capabilities=["image-to-video"],
        properties={
            "prompt": prompt(2000, "What happens; camera commands like [推进] are supported."),
            "image_url": url("First frame."),
            "duration": choice([6, 10], 6, "Video length in seconds (1080p: 6 only)."),
            "resolution": choice(["768p", "1080p"], "768p", "Output resolution."),
            "prompt_optimizer": OPTIMIZER,
        },
        required=["prompt", "image_url"], docs_url=DOCS_23_FAST,
        notes=["Lower-latency Hailuo 2.3. Runs on APIMart only. 1080p only makes 6 s videos."],
    ))  # fmt: skip
    found.append(model(
        _id("hailuo-2.3", "pro", "image-to-video"), name="Hailuo 2.3 Pro", workflow="Image to video",
        family="hailuo-2-3-pro", output="video", capabilities=["image-to-video"],
        properties={
            "prompt": prompt(5000, "What happens in the video."),
            "image_url": url("First frame."),
            "duration": choice([6, 10], 6, "Video length in seconds (1080p: 6 only)."),
            "resolution": choice(["768p", "1080p"], "768p", "Output resolution."),
        },
        required=["prompt", "image_url"], docs_url=DOCS_23,
        notes=["Runs on KIE only. 1080p only makes 6 s videos."],
    ))  # fmt: skip
    h3 = {
        "prompt": prompt(7000, "What happens in the video; dialogue, music and effects can be described."),
        "duration": {"type": "integer", "minimum": 5, "maximum": 15, "default": 5,
                     "description": "Video length in seconds (5–15)."},
        "resolution": choice(["480p", "768p", "1080p"], "768p", "Output resolution."),
        "aigc_watermark": WATERMARK,
    }  # fmt: skip
    h3_notes = ["Faster MiniMax H3 with audio. Runs on APIMart only. No 2K (use MiniMax H3 for 2K)."]
    found.append(model(
        _id("h3-max", "text-to-video"), name="MiniMax H3 Max", workflow="Text to video", family="minimax-h3-max",
        output="video", capabilities=["text-to-video"],
        properties={**h3, "aspect_ratio": choice(H3_RATIOS, "16:9", "Output aspect ratio.")},
        required=["prompt"], docs_url=DOCS_H3_MAX, notes=h3_notes,
    ))  # fmt: skip
    found.append(model(
        _id("h3-max", "image-to-video"), name="MiniMax H3 Max", workflow="Image to video", family="minimax-h3-max",
        output="video", capabilities=["image-to-video", "first-last-frame"],
        properties={**h3, "image_url": url("First frame; the video keeps its aspect ratio."),
                    "end_image_url": url("Optional last frame.")},
        required=["prompt", "image_url"], docs_url=DOCS_H3_MAX, notes=h3_notes,
    ))  # fmt: skip
    found.append(model(
        _id("h3-max", "reference-to-video"), name="MiniMax H3 Max", workflow="Reference to video",
        family="minimax-h3-max", output="video",
        capabilities=["reference-to-video", "image-references", "video-input", "audio-input"],
        properties={
            **h3,
            "image_urls": urls(0, 9, "Up to nine reference images."),
            "video_urls": urls(0, 3, "Up to three reference videos, 2–15 s each and 15 s in total."),
            "audio_urls": urls(0, 3, "Up to three reference audio clips, 2–15 s each; needs an image or a video."),
            "aspect_ratio": choice(["adaptive", *H3_RATIOS], "adaptive", "Output aspect ratio; adaptive follows the references."),
        },
        required=["prompt"], docs_url=DOCS_H3_MAX,
        notes=[*h3_notes, "Give at least one reference image or video. Images after the first two are charged."],
    ))  # fmt: skip
    return found


MODELS = _models()


def _upper(value: str) -> str:
    return value.upper()


def _str(value: Any) -> str:
    return str(value)


# --- Hailuo 02 ---------------------------------------------------------------------------------


def _hailuo02_kie(tier: str, mode: str) -> Route:
    p = "kie"
    name = f"hailuo/02-{mode}-{tier}"
    pro = tier == "pro"
    keep = ["prompt", "prompt_optimizer"]
    rename: dict[str, str] = {}
    convert: dict[str, Any] = {}
    allowed: dict[str, Any] = {} if pro else {"duration": {6, 10}}
    if not pro:  # Pro hace siempre 6 s a 1080P y no tiene esos campos
        convert["duration"] = _str
    if mode == "image-to-video":
        keep += ["image_url", "end_image_url"]
        if not pro:
            convert["resolution"] = _upper
    spec = Spec(p, name, keep=keep, rename=rename, convert=convert, allowed=allowed)

    def price(i: dict, h: dict, pr: dict) -> float | None:
        res = "1080p" if pro else i.get("resolution", "768p")
        return per_unit(pr, f"hailuo 02, {mode}, {tier}-{i.get('duration', 6)}.0s-{res}")

    return Route(p, name, spec, price)


# --- Hailuo 2.3 Fast (APIMart) y Pro (KIE) ----------------------------------------------------------


def _no_long_1080p(provider: str):
    def build(source: dict, out: dict) -> dict:
        if str(source.get("resolution", "")).lower() == "1080p" and source.get("duration") != 6:
            raise unsupported(provider, "1080p only makes 6 s videos")
        return out

    return build


# --- H3 Max (APIMart) -----------------------------------------------------------------------------


def _h3_build(mode: str):
    def build(source: dict, out: dict) -> dict:
        # A 1080P la marca de agua ni siquiera se puede enviar en false.
        if source.get("resolution") == "1080p" and out.pop("watermark", False):
            raise unsupported("apimart", "MiniMax H3 Max has no watermark at 1080p")
        if mode == "reference-to-video":
            for key in ("image_urls", "video_urls", "audio_urls"):
                if not out.get(key):
                    out.pop(key, None)
            if not (out.get("image_urls") or out.get("video_urls")):
                raise unsupported("apimart", "MiniMax H3 Max needs at least one reference image or video")
        return out

    return build


def _h3_price(i: dict, hints: dict, prices: dict) -> float | None:
    res = str(i.get("resolution", "768p")).upper()
    base = per_second(prices, f"MiniMax-H3-Max|{res}", i.get("duration"))
    if base is None:
        return None
    images = len([u for u in (i.get("image_url"), i.get("end_image_url")) if u]) + len(
        i.get("image_urls") or []
    )
    if images > 2:
        base += per_unit(prices, "MiniMax-H3-Max|input:image", images - 2) or 0.0
    if i.get("video_urls"):
        seconds = video_seconds(hints)
        if seconds is None:
            return None
        base += per_second(prices, f"MiniMax-H3-Max|input:video:{res}", seconds) or 0.0
    return round(base, 4)


def apimart() -> dict[str, Route]:
    p = "apimart"
    routes: dict[str, Route] = {}
    fast = "MiniMax-Hailuo-2.3-Fast"
    routes[_id("hailuo-2.3", "fast", "image-to-video")] = Route(
        p, fast,
        Spec(p, fast, keep=("prompt", "duration", "resolution", "prompt_optimizer"),
             rename={"image_url": "first_frame_image"}, fixed={"watermark": False}, build=_no_long_1080p(p)),
        lambda i, h, pr: per_second(pr, f"{fast}|{'1080P' if i.get('resolution') == '1080p' else 'default'}",
                                    i.get("duration")),
    )  # fmt: skip
    h3 = "MiniMax-H3-Max"
    common = {"convert": {"resolution": _upper}, "rename": {"aigc_watermark": "watermark"}}
    routes[_id("h3-max", "text-to-video")] = Route(
        p, h3, Spec(p, h3, keep=("prompt", "duration", "aspect_ratio"), build=_h3_build("text-to-video"), **common),
        _h3_price,
    )  # fmt: skip
    routes[_id("h3-max", "image-to-video")] = Route(
        p, h3,
        Spec(p, h3, keep=("prompt", "duration"), convert={"resolution": _upper},
             rename={"aigc_watermark": "watermark", "image_url": "first_frame_image",
                     "end_image_url": "last_frame_image"},
             build=_h3_build("image-to-video")),
        _h3_price,
    )  # fmt: skip
    routes[_id("h3-max", "reference-to-video")] = Route(
        p, h3,
        Spec(p, h3, keep=("prompt", "duration", "aspect_ratio", "image_urls", "video_urls", "audio_urls"),
             build=_h3_build("reference-to-video"), **common),
        _h3_price,
    )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    p = "kie"
    routes: dict[str, Route] = {}
    for tier in ("standard", "pro"):
        for mode in ("text-to-video", "image-to-video"):
            routes[_id("hailuo-02", tier, mode)] = _hailuo02_kie(tier, mode)
    pro = "hailuo/2-3-image-to-video-pro"
    routes[_id("hailuo-2.3", "pro", "image-to-video")] = Route(
        p, pro,
        Spec(p, pro, keep=("prompt", "image_url"), convert={"duration": _str, "resolution": _upper},
             build=_no_long_1080p(p)),
        lambda i, h, pr: per_unit(
            pr, f"hailuo 2.3, image-to-video, pro-{i.get('duration', 6)}.0s-{i.get('resolution', '768p')}"
        ),
    )  # fmt: skip
    return routes
