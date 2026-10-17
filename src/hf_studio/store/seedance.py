"""Seedance (ByteDance) en las tiendas: las variantes que Higgsfield no tiene (1.0, 1.5 Pro, 2.0 Fast y Mini).

Seedance 2.0 y 2.5 ya están en el catálogo con rutas de tienda (`providers/*_routes.py`); aquí no se repiten.

Fuentes (revisadas el 2026-10-17):
- APIMart `seedance-1-0-pro-quality` / `seedance-1-0-pro-fast`:
  https://docs.apimart.ai/en/api-reference/videos/doubao/generation.md (2–12 s, 480p–1080p, primer fotograma
  en `image_with_roles`; último fotograma solo en quality). Precio por segundo `<modelo>|<RES>`.
- APIMart `seedance-1-5-pro`: https://docs.apimart.ai/en/api-reference/videos/seedance-1-5-pro/generation.md
  (4–12 s, `audio`, `camerafixed`, primer y último fotograma). Precio por segundo `seedance-1-5-pro|<RES>`.
- APIMart `seedance-2.0-fast` / `seedance-2.0-mini`:
  https://docs.apimart.ai/en/api-reference/videos/seedance-2-0/generation.md (como `seedance-2.0`, pero solo
  480p y 720p). Precio por segundo `<modelo>|<RES>` y, con video de referencia, `|<RES>-input` por segundo de
  entrada más salida (igual que `seedance-2.0` en `apimart_routes`).
- KIE `bytedance/v1-lite-text-to-video`, `-image-to-video`, `bytedance/v1-pro-text-to-video`,
  `-image-to-video`, `bytedance/v1-pro-fast-image-to-video`: https://docs.kie.ai/market/bytedance/v1-pro-text-to-video.md
  y hermanas (duración "5"|"10"). Precio `bytedance/seedance-v1-<tier>, <modo>, <res>` por segundo; pro-fast
  por video, `..., <res>-<d>s`.
- KIE `bytedance/seedance-1.5-pro`: https://docs.kie.ai/market/bytedance/seedance-1-5-pro.md (`input_urls`
  0–2, `fixed_lens`, `generate_audio`). Precio por segundo `bytedance/seedance-1.5-pro, with|without audio-<res>`.
- KIE `bytedance/seedance-2-fast` / `bytedance/seedance-2-mini`: https://docs.kie.ai/market/bytedance/seedance-2-fast.md
  y seedance-2-mini.md (480p y 720p). Precio por segundo `bytedance/seedance-2 fast, <res> no|with video input`
  y `bytedance/seedance-2-mini, <res> no|with video`.
No se usan `seedance-2.0-face` ni `seedance-2.0-fast-face` de APIMart: tienen precio pero ninguna página de
documentación dice qué cambian ni cómo se piden.
"""

from __future__ import annotations

from typing import Any

from ..providers.apimart_routes import _frames, _seedance_price
from ..providers.kie_routes import SEEDANCE_FRAMES, SEEDANCE_REFS
from ..providers.routes import Route, Spec, only_default, per_second, per_unit, video_seconds
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.kie.ai/market/bytedance/seedance-1-5-pro"
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
NOT_HIGGSFIELD = "Higgsfield does not offer this Seedance variant: it runs on APIMart or KIE."


def _seconds(minimum: int, maximum: int, default: int = 5) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum, "default": default,
            "description": "Length in seconds."}  # fmt: skip


def _bool(default: bool, description: str) -> dict[str, Any]:
    return {"type": "boolean", "default": default, "description": description}


SEED = {"type": "integer", "minimum": -1, "maximum": 2147483647, "description": "Seed; -1 is random."}
AUDIO = _bool(True, "Generate a soundtrack with the video.")
CAMERA = _bool(False, "Keep the camera still.")
FIRST = url("First frame of the video.")


def _entry(model_id: str, name: str, family: str, mode: str, properties: dict, required: list, notes: list):
    workflow, capabilities = {
        "text-to-video": ("Text to video", ["text-to-video"]),
        "image-to-video": ("Image to video", ["image-to-video", *(["first-last-frame"] if "end_image_url" in properties else [])]),
        "reference-to-video": ("Reference to video", ["audio-input", "image-references", "reference-to-video", "video-input"]),
    }[mode]  # fmt: skip
    return model(
        model_id, name=name, workflow=workflow, family=family, output="video", capabilities=capabilities,
        properties=properties, required=required, docs_url=DOCS, notes=[NOT_HIGGSFIELD, *notes],
    )  # fmt: skip


# --- Seedance 1.0 (lite, pro, pro-fast) ------------------------------------------------------------

V1 = {"lite": "Seedance 1.0 Lite", "pro": "Seedance 1.0 Pro", "pro-fast": "Seedance 1.0 Pro Fast"}


def _v1_models() -> list[dict[str, Any]]:
    found = []
    for tier, name in V1.items():
        duration = choice([5, 10], 5, "Length in seconds.") if tier == "lite" else _seconds(2, 12)
        notes = (
            [] if tier == "lite" else ["KIE only makes 5 or 10 second clips; other lengths run on APIMart."]
        )
        for mode in ("text-to-video", "image-to-video"):
            props: dict[str, Any] = {
                "prompt": prompt(10000),
                "duration": duration,
                "resolution": choice(["480p", "720p", "1080p"], "720p", "Output resolution."),
                "seed": SEED,
            }
            if tier != "pro-fast":
                props["camera_fixed"] = CAMERA
            required = ["prompt"]
            if mode == "text-to-video":
                ratios = ["16:9", "4:3", "1:1", "3:4", "9:16", "9:21"] if tier == "lite" else RATIOS
                props["aspect_ratio"] = choice(ratios, "16:9", "Output aspect ratio.")
            else:
                props["image_url"] = FIRST
                required.append("image_url")
                if tier != "pro-fast":
                    props["end_image_url"] = url(
                        "Optional last frame." + (" Only on APIMart." if tier == "pro" else "")
                    )
            extra = list(notes)
            if tier == "pro-fast" and mode == "image-to-video":
                extra.append("KIE renders only 720p or 1080p.")
            found.append(
                _entry(f"bytedance/seedance-1.0-{tier}/{mode}", name, f"seedance-1.0-{tier}", mode, props,
                       required, extra)
            )  # fmt: skip
    return found


def _v1_apimart() -> dict[str, Route]:
    routes = {}
    for tier, name in (("pro", "seedance-1-0-pro-quality"), ("pro-fast", "seedance-1-0-pro-fast")):

        def price(i: dict, h: dict, p: dict, n: str = name) -> float | None:
            return per_second(p, f"{n}|{str(i.get('resolution', '720p')).upper()}", i.get("duration"))

        convert = {"camera_fixed": only_default("camera_fixed", False)} if tier == "pro" else {}
        base = ("prompt", "duration", "resolution", "seed")
        routes[f"bytedance/seedance-1.0-{tier}/text-to-video"] = Route(
            "apimart", name, Spec("apimart", name, keep=(*base, "aspect_ratio"), convert=convert), price
        )
        frames = ("image_url", "end_image_url") if tier == "pro" else ("image_url",)
        routes[f"bytedance/seedance-1.0-{tier}/image-to-video"] = Route(
            "apimart",
            name,
            Spec("apimart", name, keep=(*base, *frames), convert=convert, build=_frames),
            price,
        )
    return routes


def _v1_kie() -> dict[str, Route]:
    routes = {}
    for tier in ("lite", "pro"):
        for mode in ("text-to-video", "image-to-video"):
            name = f"bytedance/v1-{tier}-{mode}"
            keep = ["prompt", "resolution", "seed", "camera_fixed"]
            if mode == "text-to-video":
                keep.append("aspect_ratio")
            else:
                keep += ["image_url", *(["end_image_url"] if tier == "lite" else [])]

            def price(i: dict, h: dict, p: dict, t: str = tier, m: str = mode) -> float | None:
                key = f"bytedance/seedance-v1-{t}, {m}, {i.get('resolution', '720p')}"
                return per_second(p, key, i.get("duration"))

            spec = Spec("kie", name, keep=keep, convert={"duration": str}, allowed={"duration": {5, 10}})
            routes[f"bytedance/seedance-1.0-{tier}/{mode}"] = Route("kie", name, spec, price)
    name = "bytedance/v1-pro-fast-image-to-video"

    def fast_price(i: dict, h: dict, p: dict) -> float | None:
        key = f"bytedance/seedance-v1-pro-fast, image-to-video, {i.get('resolution', '720p')}-{i.get('duration')}s"
        return per_unit(p, key)

    spec = Spec(
        "kie", name, keep=("prompt", "resolution", "image_url"), convert={"duration": str},
        allowed={"duration": {5, 10}, "resolution": {"720p", "1080p"}},
    )  # fmt: skip
    routes["bytedance/seedance-1.0-pro-fast/image-to-video"] = Route("kie", name, spec, fast_price)
    return routes


# --- Seedance 1.5 Pro --------------------------------------------------------------------------


def _v15_models() -> list[dict[str, Any]]:
    found = []
    for mode in ("text-to-video", "image-to-video"):
        props: dict[str, Any] = {
            "prompt": prompt(4000),
            "duration": _seconds(4, 12),
            "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio."),
            "resolution": choice(["480p", "720p", "1080p"], "720p", "Output resolution."),
            "generate_audio": AUDIO,
            "camera_fixed": CAMERA,
            "seed": {**SEED, "description": "Seed; -1 is random (APIMart only)."},
        }
        required = ["prompt"]
        if mode == "image-to-video":
            props["image_url"] = FIRST
            props["end_image_url"] = url("Optional last frame.")
            required.append("image_url")
        found.append(
            _entry(f"bytedance/seedance-1.5-pro/{mode}", "Seedance 1.5 Pro", "seedance-1.5-pro", mode, props,
                   required, ["KIE's Seedance 1.5 Pro service ends on 2026-11-11."])
        )  # fmt: skip
    return found


def _v15_apimart() -> dict[str, Route]:
    name = "seedance-1-5-pro"

    def price(i: dict, h: dict, p: dict) -> float | None:
        return per_second(p, f"{name}|{str(i.get('resolution', '720p')).upper()}", i.get("duration"))

    keep = ("prompt", "duration", "resolution", "aspect_ratio", "seed")
    rename = {"generate_audio": "audio", "camera_fixed": "camerafixed"}
    return {
        "bytedance/seedance-1.5-pro/text-to-video": Route(
            "apimart", name, Spec("apimart", name, keep=keep, rename=rename), price
        ),
        "bytedance/seedance-1.5-pro/image-to-video": Route(
            "apimart", name,
            Spec("apimart", name, keep=(*keep, "image_url", "end_image_url"), rename=rename, build=_frames),
            price,
        ),
    }  # fmt: skip


def _input_urls(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out["input_urls"] = [
        source["image_url"],
        *([source["end_image_url"]] if source.get("end_image_url") else []),
    ]
    out.pop("image_url", None)
    out.pop("end_image_url", None)
    return out


def _v15_kie() -> dict[str, Route]:
    name = "bytedance/seedance-1.5-pro"

    def price(i: dict, h: dict, p: dict) -> float | None:
        audio = "with" if i.get("generate_audio", True) else "without"
        return per_second(p, f"{name}, {audio} audio-{i.get('resolution', '720p')}", i.get("duration"))

    keep = ("prompt", "duration", "resolution", "aspect_ratio", "generate_audio")
    rename = {"camera_fixed": "fixed_lens"}
    return {
        "bytedance/seedance-1.5-pro/text-to-video": Route("kie", name, Spec("kie", name, keep=keep, rename=rename),
                                                          price),
        "bytedance/seedance-1.5-pro/image-to-video": Route(
            "kie", name, Spec("kie", name, keep=(*keep, "image_url", "end_image_url"), rename=rename,
                              build=_input_urls), price,
        ),
    }  # fmt: skip


# --- Seedance 2.0 Fast y Mini (mismo esquema que bytedance/seedance-2.0/*, solo 480p y 720p) ---------

V2 = {"fast": ("Seedance 2.0 Fast", "seedance-2.0-fast", "bytedance/seedance-2-fast", "bytedance/seedance-2 fast"),
      "mini": ("Seedance 2.0 Mini", "seedance-2.0-mini", "bytedance/seedance-2-mini", "bytedance/seedance-2-mini")}  # fmt: skip


def _v2_models() -> list[dict[str, Any]]:
    found = []
    for variant, (name, *_) in V2.items():
        common = {
            "prompt": prompt(description="What happens in the video."),
            "duration": _seconds(4, 15),
            "resolution": choice(["480p", "720p"], "720p", "Output resolution (no 1080p on this variant)."),
            "generate_audio": AUDIO,
        }
        ratio = {"aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio.")}
        family, base = f"seedance-2.0-{variant}", f"bytedance/seedance-2.0-{variant}"
        found.append(_entry(f"{base}/text-to-video", name, family, "text-to-video", {**common, **ratio},
                            ["prompt"], ["Output framing follows aspect_ratio."]))  # fmt: skip
        frames = {"image_url": FIRST, "end_image_url": url("Optional last frame.")}
        found.append(_entry(f"{base}/image-to-video", name, family, "image-to-video", {**common, **frames},
                            ["image_url"], ["Output framing follows image_url."]))  # fmt: skip
        refs = {
            "image_urls": urls(1, 9, "Reference images (up to 9)."),
            "video_urls": urls(1, 3, "Reference videos (up to 3, 15 s in total)."),
            "audio_urls": urls(1, 3, "Reference audio (up to 3, 15 s in total); needs images or videos too."),
        }
        entry = _entry(f"{base}/reference-to-video", name, family, "reference-to-video", {**common, **ratio, **refs},
                       [], ["Provide image_urls or video_urls; audio alone is not enough."])  # fmt: skip
        entry["input_schema"]["if"] = {"required": ["image_urls"]}
        entry["input_schema"]["else"] = {"required": ["video_urls"]}
        found.append(entry)
    return found


def _v2_apimart() -> dict[str, Route]:
    routes = {}
    keep = ("prompt", "duration", "resolution", "generate_audio")
    for variant, (_, name, _, _) in V2.items():
        base, price = f"bytedance/seedance-2.0-{variant}", _seedance_price(name)
        routes[f"{base}/text-to-video"] = Route(
            "apimart", name, Spec("apimart", name, keep=keep, rename={"aspect_ratio": "size"}), price
        )
        routes[f"{base}/image-to-video"] = Route(
            "apimart", name,
            Spec("apimart", name, keep=(*keep, "image_url", "end_image_url"), fixed={"size": "adaptive"},
                 build=_frames),
            price,
        )  # fmt: skip
        routes[f"{base}/reference-to-video"] = Route(
            "apimart", name,
            Spec("apimart", name, keep=(*keep, "image_urls", "video_urls", "audio_urls"),
                 rename={"aspect_ratio": "size"}),
            price,
        )  # fmt: skip
    return routes


def _v2_kie_price(row: str, no_video: str, with_video: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        res = i.get("resolution", "720p")
        if i.get("video_urls"):
            seconds = video_seconds(hints)
            if seconds is None:
                return None
            return per_second(prices, f"{row}, {res} {with_video}", seconds + i.get("duration", 5))
        return per_second(prices, f"{row}, {res} {no_video}", i.get("duration"))

    return price


def _v2_kie() -> dict[str, Route]:
    routes = {}
    keep = ("prompt", "duration", "resolution", "aspect_ratio", "generate_audio")
    for variant, (_, _, name, row) in V2.items():
        base = f"bytedance/seedance-2.0-{variant}"
        suffix = ("no video input", "with video input") if variant == "fast" else ("no video", "with video")
        price = _v2_kie_price(row, *suffix)
        routes[f"{base}/text-to-video"] = Route("kie", name, Spec("kie", name, keep=keep), price)
        routes[f"{base}/image-to-video"] = Route(
            "kie", name, Spec("kie", name, keep=keep, rename=SEEDANCE_FRAMES, fixed={"aspect_ratio": "adaptive"}),
            price,
        )  # fmt: skip
        routes[f"{base}/reference-to-video"] = Route(
            "kie", name, Spec("kie", name, keep=keep, rename=SEEDANCE_REFS), price
        )
    return routes


MODELS = [*_v1_models(), *_v15_models(), *_v2_models()]


def apimart() -> dict[str, Route]:
    return {**_v1_apimart(), **_v15_apimart(), **_v2_apimart()}


def kie() -> dict[str, Route]:
    return {**_v1_kie(), **_v15_kie(), **_v2_kie()}
