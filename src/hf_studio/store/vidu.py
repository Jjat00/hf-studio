"""Vidu (Shengshu) en las tiendas: Q3 Pro/Turbo, Q3 y Q3 Mix (referencias) y Q4 Preview. Higgsfield no los tiene.

Fuentes (revisadas el 2026-10-17):
- APIMart `viduq3-pro` / `viduq3-turbo`: https://docs.apimart.ai/en/api-reference/videos/vidu-q3-pro/generation.md
  (texto a video y 0, 1 o 2 `image_urls` = primer / primer y último fotograma; 1–16 s; 540p/720p/1080p;
  `aspect_ratio` solo sin imágenes; `audio` encendido por defecto; `seed`). Precio por segundo `<modelo>|<RES>`.
- APIMart `viduq3` / `viduq3-mix`: https://docs.apimart.ai/en/api-reference/videos/vidu-q3/generation.md
  (1–7 imágenes de referencia obligatorias; `viduq3` 3–16 s y 540p/720p/1080p, `viduq3-mix` 1–16 s y 720p/1080p;
  `aspect_ratio` 16:9 por defecto; sin campo de audio). Precio por segundo `<modelo>|<RES>`.
- APIMart `viduq4-preview`: https://docs.apimart.ai/en/api-reference/videos/vidu-q4-preview/generation.md
  (un primer fotograma, o 1–15 referencias con hasta 3 audios MP3; 3–16 s; 540p/720p/1080p/2K/4K; `audio`;
  `seed`; sin texto a video ni último fotograma). Precio por segundo `viduq4-preview|<RES>`, con o sin audio.
- KIE `vidu-q4/image-to-video` y `vidu-q4/reference-to-video`:
  https://docs.kie.ai/market/vidu-q4/image-to-video.md y https://docs.kie.ai/market/vidu-q4/reference-to-video.md
  (mismos límites, sin `seed`). Precio por segundo `vidu q4, <modo>, <res>`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second
from ._common import choice, model, prompt, url, urls

DOCS_Q3_PRO = "https://docs.apimart.ai/en/api-reference/videos/vidu-q3-pro/generation"
DOCS_Q3 = "https://docs.apimart.ai/en/api-reference/videos/vidu-q3/generation"
DOCS_Q4 = "https://docs.kie.ai/market/vidu-q4/image-to-video"
RATIOS = ["16:9", "9:16", "4:3", "3:4", "1:1"]
# Q3 Pro y Turbo: texto a video e imagen a video (primer y último fotograma) con el mismo id de APIMart.
FRAMES = {"q3-pro": ("viduq3-pro", "Vidu Q3 Pro"), "q3-turbo": ("viduq3-turbo", "Vidu Q3 Turbo")}
# Q3 y Q3 Mix: solo referencia a video. (id de APIMart, nombre, duración mínima, resoluciones)
REFS = {
    "q3": ("viduq3", "Vidu Q3", 3, ["540p", "720p", "1080p"]),
    "q3-mix": ("viduq3-mix", "Vidu Q3 Mix", 1, ["720p", "1080p"]),
}
Q4_RES = ["540p", "720p", "1080p", "2k", "4k"]


def _id(version: str, mode: str) -> str:
    return f"vidu/{version}/{mode}"


def _seconds(low: int, high: int, default: int = 5) -> dict[str, Any]:
    return {"type": "integer", "minimum": low, "maximum": high, "default": default,
            "description": f"Video length in seconds ({low}–{high})."}  # fmt: skip


AUDIO = {
    "type": "boolean",
    "default": True,
    "description": "Generate dialogue and sound effects with the video.",
}
SEED = {"type": "integer", "description": "Seed for similar (not identical) results."}


def _models() -> list[dict[str, Any]]:
    found = []
    for version, (_, name) in FRAMES.items():
        common = {
            "prompt": prompt(2000, "What happens in the video, including camera movement."),
            "duration": _seconds(1, 16),
            "resolution": choice(["540p", "720p", "1080p"], "720p", "Output resolution."),
            "generate_audio": AUDIO,
            "seed": SEED,
        }
        found.append(model(
            _id(version, "text-to-video"), name=name, workflow="Text to video", family=f"vidu-{version}",
            output="video", capabilities=["text-to-video"],
            properties={**common, "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio.")},
            required=["prompt"], docs_url=DOCS_Q3_PRO,
            notes=["Runs on APIMart only. Audio is on by default."],
        ))  # fmt: skip
        found.append(model(
            _id(version, "image-to-video"), name=name, workflow="Image to video", family=f"vidu-{version}",
            output="video", capabilities=["image-to-video", "first-last-frame"],
            properties={**common, "image_url": url("First frame."),
                        "end_image_url": url("Optional last frame.")},
            required=["prompt", "image_url"], docs_url=DOCS_Q3_PRO,
            notes=["Runs on APIMart only. The aspect ratio follows the first frame. Audio is on by default."],
        ))  # fmt: skip
    for version, (_, name, low, resolutions) in REFS.items():
        found.append(model(
            _id(version, "reference-to-video"), name=name, workflow="Reference to video", family=f"vidu-{version}",
            output="video", capabilities=["reference-to-video", "image-references"],
            properties={
                "prompt": prompt(5000, "Actions and camera movement; appearance comes from the reference images."),
                "image_urls": urls(1, 7, "One to seven reference images (subjects, scene, style)."),
                "duration": _seconds(low, 16),
                "resolution": choice(resolutions, "720p", "Output resolution."),
                "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio."),
                "seed": SEED,
            },
            required=["prompt", "image_urls"], docs_url=DOCS_Q3,
            notes=["Runs on APIMart only. Images: PNG, JPEG or WebP, at least 128×128, ratio between 1:4 and 4:1."],
        ))  # fmt: skip
    q4 = {
        "prompt": prompt(20000, "What happens in the video."),
        "duration": _seconds(3, 16),
        "resolution": choice(Q4_RES, "720p", "Output resolution."),
        "generate_audio": AUDIO,
        "seed": {**SEED, "description": "Seed for similar results (APIMart only)."},
    }
    found.append(model(
        _id("q4", "image-to-video"), name="Vidu Q4", workflow="Image to video", family="vidu-q4",
        output="video", capabilities=["image-to-video"],
        properties={**q4, "image_url": url("First frame; the video keeps its aspect ratio.")},
        required=["prompt", "image_url"], docs_url=DOCS_Q4,
        notes=["Vidu Q4 preview on APIMart and KIE. No last frame. A fixed seed only runs on APIMart."],
    ))  # fmt: skip
    found.append(model(
        _id("q4", "reference-to-video"), name="Vidu Q4", workflow="Reference to video", family="vidu-q4",
        output="video", capabilities=["reference-to-video", "image-references", "audio-input"],
        properties={
            **q4,
            "prompt": prompt(20000, "What happens; cite inputs by order, e.g. 'the man in reference image 2'."),
            "image_urls": urls(1, 15, "One to fifteen reference images."),
            "audio_urls": urls(0, 3, "Up to three reference audio clips (MP3, 3–12 s each)."),
            "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio."),
        },
        required=["prompt", "image_urls"], docs_url="https://docs.kie.ai/market/vidu-q4/reference-to-video",
        notes=["Vidu Q4 preview on APIMart and KIE. A fixed seed only runs on APIMart."],
    ))  # fmt: skip
    return found


MODELS = _models()


def _apimart_res(value: str) -> str:
    """APIMart acepta la resolución sin distinguir mayúsculas; 2K y 4K se envían como en sus docs."""
    return value.upper() if value.endswith("k") else value


def _rate(model_name: str):
    return lambda i, h, p: per_second(
        p, f"{model_name}|{str(i.get('resolution', '720p')).upper()}", i.get("duration")
    )


def _frames(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Primer (y último) fotograma como `image_urls`: APIMart elige el modo por el número de imágenes."""
    out["image_urls"] = [u for u in (out.pop("image_url", None), out.pop("end_image_url", None)) if u]
    return out


def _roles(values: list[str]) -> list[dict[str, str]]:
    # Rol explícito: con una sola imagen sin rol APIMart haría imagen a video.
    return [{"url": v, "role": "reference_image"} for v in values]


def apimart() -> dict[str, Route]:
    p = "apimart"
    routes: dict[str, Route] = {}
    for version, (name, _) in FRAMES.items():
        common: dict[str, Any] = {"rename": {"generate_audio": "audio"}}
        routes[_id(version, "text-to-video")] = Route(
            p, name, Spec(p, name, keep=("prompt", "duration", "resolution", "aspect_ratio", "seed"), **common),
            _rate(name),
        )  # fmt: skip
        routes[_id(version, "image-to-video")] = Route(
            p, name,
            Spec(p, name, keep=("prompt", "duration", "resolution", "seed", "image_url", "end_image_url"),
                 build=_frames, **common),
            _rate(name),
        )  # fmt: skip
    for version, (name, *_) in REFS.items():
        routes[_id(version, "reference-to-video")] = Route(
            p, name, Spec(p, name, keep=("prompt", "duration", "resolution", "aspect_ratio", "seed", "image_urls")),
            _rate(name),
        )  # fmt: skip
    q4 = "viduq4-preview"
    routes[_id("q4", "image-to-video")] = Route(
        p, q4,
        Spec(p, q4, keep=("prompt", "duration", "seed"), rename={"generate_audio": "audio", "image_url": "first_frame_image"},
             convert={"resolution": _apimart_res}),
        _rate(q4),
    )  # fmt: skip
    routes[_id("q4", "reference-to-video")] = Route(
        p, q4,
        Spec(p, q4, keep=("prompt", "duration", "seed", "aspect_ratio", "audio_urls"),
             rename={"generate_audio": "audio", "image_urls": "image_with_roles"},
             convert={"resolution": _apimart_res, "image_urls": _roles, "audio_urls": lambda v: v or None}),
        _rate(q4),
    )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    p = "kie"
    routes: dict[str, Route] = {}
    for mode, extra in (
        ("image-to-video", {"keep": ("prompt", "duration", "resolution", "image_url")}),
        ("reference-to-video", {
            "keep": ("prompt", "duration", "resolution", "aspect_ratio"),
            "rename": {"image_urls": "reference_image_urls", "audio_urls": "reference_audio_urls"},
        }),
    ):  # fmt: skip
        name = f"vidu-q4/{mode}"
        rename = {"generate_audio": "audio", **extra.get("rename", {})}
        routes[_id("q4", mode)] = Route(
            p, name, Spec(p, name, keep=extra["keep"], rename=rename),  # sin `seed`: una semilla fija es unsupported
            lambda i, h, pr, m=mode: per_second(pr, f"vidu q4, {m}, {i.get('resolution', '720p')}", i.get("duration")),
        )  # fmt: skip
    return routes
