"""Muse Video en APIMart (`muse-video-ext`). Higgsfield y KIE no lo venden.

Fuentes (revisadas el 2026-11-11):
- APIMart `muse-video-ext`, `POST /v1/videos/generations`:
  https://docs.apimart.ai/en/api-reference/videos/muse-video-ext/generation.md. Un MP4 por tarea (`n` = 1), de
  2 a 10 s (`duration`, 10 por defecto), solo 720p y siempre con sonido (`audio: false` se rechaza). Texto a video
  o hasta 9 imágenes de referencia (11 MiB en total) que guían el video sin ser su primer fotograma exacto: por
  eso el modo con imágenes es «reference-to-video», no «image-to-video». `aspect_ratio` con 7 relaciones; sin ella,
  texto a video da 16:9 y con referencias sigue su composición (no se manda `"auto"`). No acepta `seed`,
  `negative_prompt`, fotogramas inicial y final, video ni audio de referencia.
- Precio: la tabla pública de APIMart (`/api/pricing/models/all`) cobra por segundo pero trae dos tarifas,
  `muse-video-ext|default` a 0,024 USD/s y `muse-video-ext|720P` a 0,002352 USD/s, para la única salida que hay
  (720p), y no dice cuál se aplica. El precio queda desconocido (`None`): el usuario tiene que aceptarlo.
- APIMart no dice quién hace el modelo; el id lógico usa `muse/` como Muse Image (`store/muse.py`).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec
from ._common import choice, model, prompt, urls

DOCS = "https://docs.apimart.ai/en/api-reference/videos/muse-video-ext/generation"
APIMART_MODEL = "muse-video-ext"
RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]
MODES = {
    "text-to-video": ("Text to video", ["text-to-video"]),
    "reference-to-video": ("Reference to video", ["reference-to-video", "image-references"]),
}
UNKNOWN_PRICE = (
    "The price cannot be known in advance: APIMart's price table lists two per-second rates "
    "($0.024 and $0.002352) for its only output and does not say which one applies."
)


def _id(mode: str) -> str:
    return f"muse/muse-video/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for mode, (workflow, capabilities) in MODES.items():
        refs = mode == "reference-to-video"
        properties: dict[str, Any] = {
            "prompt": prompt(description="What happens in the video; with images, how to use them."),
            "duration": choice(list(range(2, 11)), 5, "Length in seconds."),
            "aspect_ratio": choice(["auto", *RATIOS], "auto", "Output aspect ratio; auto follows the images.")
            if refs
            else choice(RATIOS, "16:9", "Output aspect ratio."),
        }
        required = ["prompt"]
        if refs:
            properties["image_urls"] = urls(
                1,
                9,
                "One to nine reference images (11 MB in total); they guide the video, not its first frame.",
            )
            required.append("image_urls")
        found.append(
            model(
                _id(mode), name="Muse Video", workflow=workflow, family="muse-video", output="video",
                capabilities=capabilities, properties=properties, required=required, docs_url=DOCS,
                notes=["Runs on APIMart only. One 720p video with sound per request.", UNKNOWN_PRICE],
            )
        )  # fmt: skip
    return found


MODELS = _models()


def _ratio(value: str) -> str | None:
    """`auto` no se envía: APIMart pide omitir la relación para que siga a las referencias."""
    return None if value == "auto" else value


def _price(i: dict, h: dict, p: dict) -> float | None:
    return None  # dos tarifas por segundo en la tabla y ninguna regla para elegir: precio desconocido


def apimart() -> dict[str, Route]:
    provider = "apimart"
    routes = {}
    for mode in MODES:
        spec = Spec(
            provider, APIMART_MODEL,
            keep=("prompt", "duration", "image_urls"),
            convert={"aspect_ratio": _ratio},
            fixed={"resolution": "720p", "n": 1},
        )  # fmt: skip
        routes[_id(mode)] = Route(provider, APIMART_MODEL, spec, _price, notes=(UNKNOWN_PRICE,))
    return routes
