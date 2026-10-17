"""Grok Imagine Video (xAI) en las tiendas, por modo. El catálogo de Higgsfield solo tiene
`xai/grok-imagine-video/v1.5/reference-to-video` (todo en uno); aquí van el modelo base y el 1.5 separados en texto a
video, imagen a video y, en el base, edición de video.

Fuentes (revisadas el 2026-10-17):
- APIMart `grok-imagine-video` y `grok-imagine-video-1.5` (oficiales):
  https://docs.apimart.ai/en/api-reference/videos/grok-imagine/official.md. Prompt 1–8000; 1–15 s (8 por
  defecto); 480p/720p (el 1.5 también 1080p); `aspect_ratio` auto|1:1|16:9|9:16|4:3|3:4|3:2|2:3; `image_urls`
  opcional; el base edita un video con `video: {url}` (la duración sale del video). Precio por segundo
  `<modelo>|<RES>` + `|input:image` por imagen; la edición, `|720P` + `|input:video:default` por segundo del video.
- APIMart `grok-imagine-1.5-video-ext` (canal no oficial; la tabla lo lista como `grok-imagine-1.5-video-apimart`):
  https://docs.apimart.ai/en/api-reference/videos/grok-imagine/generation.md. 6–15 s, 480p/720p, `size`
  16:9|9:16|1:1|3:2|2:3 sin imágenes (con imágenes el formato sale de ellas), hasta 7 imágenes.
- KIE `grok-imagine/text-to-video` y `grok-imagine/image-to-video`:
  https://docs.kie.ai/market/grok-imagine/text-to-video.md e image-to-video.md. 6–30 s (texto en número, imagen en
  texto), 480p/720p/1080p, `mode` fun|normal|spicy (spicy no con imágenes externas), `aspect_ratio`
  2:3|3:2|1:1|16:9|9:16 (con una sola imagen no vale: manda la imagen), hasta 7 imágenes (1 a 1080p). Precio por
  segundo `grok-imagine, <modo>, <res>`.
- KIE `grok-imagine-video-1-5-preview`: https://docs.kie.ai/market/grok-imagine/1-5-preview.md. Prompt hasta 4096,
  1–15 s, 480p/720p/1080p, `aspect_ratio` auto|1:1|16:9|9:16|3:2|2:3 (no vale con una sola imagen), `image_urls`
  opcional, hasta 7 (1 a 1080p). Precio por segundo `grok-imagine-video-1-5-preview, [image-to-video, ]<res>`.
- Todos los videos llevan audio generado y no se puede apagar.
- Descartado: KIE `grok-imagine/extend` (solo extiende el `task_id` de una tarea de Grok en la misma cuenta de KIE).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, only_default, per_second, per_unit, unsupported, video_seconds
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.apimart.ai/en/api-reference/videos/grok-imagine/official"
RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]
KIE_RATIOS = {"1:1", "16:9", "9:16", "3:2", "2:3"}  # grok-imagine base: sin auto
KIE_15_RATIOS = {"auto", "1:1", "16:9", "9:16", "3:2", "2:3"}
EXT_RATIOS = {"16:9", "9:16", "1:1", "3:2", "2:3"}
EXT = "grok-imagine-1.5-video-ext"
AUDIO_NOTE = "Videos come with generated audio (spoken dialogue from the prompt); it cannot be turned off."


def _id(version: str, mode: str) -> str:
    return f"xai/grok-imagine-video/{version}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for version, label, max_seconds, max_prompt in (("v1", "Grok Imagine Video", 30, 5000),
                                                    ("v1.5", "Grok Imagine Video 1.5", 15, 4096)):  # fmt: skip
        base = version == "v1"
        common: dict[str, Any] = {
            "prompt": prompt(max_prompt, "What happens in the video; dialogue in the prompt is spoken."),
            "duration": {"type": "integer", "minimum": 1, "maximum": max_seconds, "default": 8,
                         "description": f"Video length in seconds (1–{max_seconds})."},
            "resolution": choice(["480p", "720p", "1080p"], "480p", "Output resolution."),
        }  # fmt: skip
        stores = (
            "APIMart takes 1–15 s at 480p or 720p; KIE takes 6–30 s and also 1080p."
            if base
            else "Runs on APIMart (official and a cheaper unofficial channel) and on KIE's preview channel."
        )
        t2v = {
            **common,
            "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio; auto lets the model choose."),
        }
        i2v = {
            **common,
            "image_urls": urls(
                1, 7, "One to seven images: one is animated, several are references (cite @image1…)."
            ),
            "aspect_ratio": choice(RATIOS, "auto", "Output aspect ratio; auto follows the image."),
        }
        if base:
            t2v["mode"] = choice(
                ["normal", "fun", "spicy"], "normal", "Motion style (fun and spicy only on KIE)."
            )
            i2v["mode"] = choice(["normal", "fun"], "normal", "Motion style (fun only on KIE).")
        found.append(model(
            _id(version, "text-to-video"), name=label, workflow="Text to video",
            family=f"grok-imagine-video-{version}", output="video", capabilities=["text-to-video"],
            properties=t2v, required=["prompt"], docs_url=DOCS, notes=[stores, AUDIO_NOTE],
        ))  # fmt: skip
        found.append(model(
            _id(version, "image-to-video"), name=label, workflow="Image to video",
            family=f"grok-imagine-video-{version}", output="video",
            capabilities=["image-to-video", "image-references"], properties=i2v, required=["prompt", "image_urls"],
            docs_url=DOCS, notes=[stores, AUDIO_NOTE, "With one image, an explicit aspect ratio only runs on APIMart."],
        ))  # fmt: skip
    found.append(model(
        _id("v1", "video-edit"), name="Grok Imagine Video", workflow="Edit video", family="grok-imagine-video-v1",
        output="video", capabilities=["video-edit", "video-input"],
        properties={"prompt": prompt(8000, "What to change in the video."),
                    "video_url": url("Video to edit; the result keeps its length.")},
        required=["prompt", "video_url"], docs_url=DOCS,
        notes=["Runs on APIMart only. Priced per second of the source video."],
    ))  # fmt: skip
    return found


MODELS = _models()


def _count(i: dict[str, Any]) -> int:
    return len(i.get("image_urls") or [])


def _apimart_price(name: str):
    def price(i: dict, h: dict, p: dict) -> float | None:
        base = per_second(p, f"{name}|{str(i.get('resolution', '480p')).upper()}", i.get("duration"))
        extra = per_unit(p, f"{name}|input:image", _count(i)) if _count(i) else 0.0
        return None if base is None or extra is None else round(base + extra, 4)

    return price


def _edit_price(i: dict, h: dict, p: dict) -> float | None:
    seconds = video_seconds(h)
    rate = (p.get("grok-imagine-video|720P"), p.get("grok-imagine-video|input:video:default"))
    return None if seconds is None or None in rate else round((rate[0] + rate[1]) * seconds, 4)


def _ext(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Canal no oficial: con imágenes el formato sale de la imagen; sin ellas `size` es explícito (no hay auto)."""
    ratio = out.pop("aspect_ratio", "auto")
    if out.get("image_urls"):
        if ratio != "auto":
            raise unsupported("apimart", "APIMart's ext channel takes the aspect ratio from the image")
    elif ratio not in EXT_RATIOS:
        raise unsupported("apimart", f"APIMart's ext channel has no aspect ratio {ratio!r}")
    else:
        out["size"] = ratio
    return out


def _kie_images(ratios: set[str]):
    """KIE: una sola imagen fija el formato (solo `auto`, que no se envía); con varias, el formato es explícito."""

    def build(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        images = out.get("image_urls") or []
        ratio = out.pop("aspect_ratio", "auto")
        if source.get("resolution") == "1080p" and len(images) > 1:
            raise unsupported("kie", "KIE takes a single image at 1080p")
        if len(images) == 1:
            if ratio != "auto":
                raise unsupported("kie", "with one image KIE takes the aspect ratio from the image")
        elif ratio not in ratios:
            raise unsupported("kie", f"KIE has no aspect ratio {ratio!r} here")
        else:
            out["aspect_ratio"] = ratio
        return out

    return build


def apimart() -> dict[str, Route | tuple[Route, ...]]:
    p = "apimart"
    routes: dict[str, Route | tuple[Route, ...]] = {}
    base = "grok-imagine-video"
    v1 = {"keep": ("prompt", "duration", "resolution", "aspect_ratio", "image_urls"),
          "allowed": {"duration": range(1, 16), "resolution": {"480p", "720p"}},
          "convert": {"mode": only_default("mode", "normal")}}  # fmt: skip
    for mode in ("text-to-video", "image-to-video"):
        routes[_id("v1", mode)] = Route(p, base, Spec(p, base, **v1), _apimart_price(base))
    routes[_id("v1", "video-edit")] = Route(
        p, base, Spec(p, base, keep=("prompt",), rename={"video_url": "video"}, convert={"video_url": lambda v: {"url": v}}),
        _edit_price,
    )  # fmt: skip
    v15 = "grok-imagine-video-1.5"
    for mode in ("text-to-video", "image-to-video"):
        routes[_id("v1.5", mode)] = (
            Route(p, v15, Spec(p, v15, keep=("prompt", "duration", "resolution", "aspect_ratio", "image_urls")),
                  _apimart_price(v15)),
            Route(
                p, EXT,
                Spec(p, EXT, keep=("prompt", "duration", "resolution", "aspect_ratio", "image_urls"),
                     allowed={"duration": range(6, 16), "resolution": {"480p", "720p"}}, build=_ext),
                lambda i, h, pr: per_second(
                    pr, f"grok-imagine-1.5-video-apimart|{str(i.get('resolution', '480p')).upper()}", i.get("duration")
                ),
                official=False,
                notes=("Unofficial APIMart channel: much cheaper, may be less stable",),
            ),
        )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    p = "kie"
    routes: dict[str, Route] = {}
    t2v, i2v = "grok-imagine/text-to-video", "grok-imagine/image-to-video"
    routes[_id("v1", "text-to-video")] = Route(
        p, t2v,
        Spec(p, t2v, keep=("prompt", "duration", "resolution", "aspect_ratio", "mode"),
             allowed={"duration": range(6, 31), "aspect_ratio": KIE_RATIOS}),
        lambda i, h, pr: per_second(pr, f"grok-imagine, text-to-video, {i.get('resolution', '480p')}", i.get("duration")),
    )  # fmt: skip
    routes[_id("v1", "image-to-video")] = Route(
        p, i2v,
        Spec(p, i2v, keep=("prompt", "resolution", "aspect_ratio", "mode", "image_urls"),
             convert={"duration": str}, allowed={"duration": range(6, 31)}, build=_kie_images(KIE_RATIOS)),
        lambda i, h, pr: per_second(pr, f"grok-imagine, image-to-video, {i.get('resolution', '480p')}", i.get("duration")),
    )  # fmt: skip
    preview = "grok-imagine-video-1-5-preview"
    keep = ("prompt", "duration", "resolution", "aspect_ratio", "image_urls")
    routes[_id("v1.5", "text-to-video")] = Route(
        p, preview, Spec(p, preview, keep=keep, allowed={"aspect_ratio": KIE_15_RATIOS}),
        lambda i, h, pr: per_second(pr, f"{preview}, {i.get('resolution', '480p')}", i.get("duration")),
        official=False, notes=("KIE preview channel",),
    )  # fmt: skip
    routes[_id("v1.5", "image-to-video")] = Route(
        p, preview, Spec(p, preview, keep=keep, build=_kie_images(KIE_15_RATIOS)),
        lambda i, h, pr: per_second(pr, f"{preview}, {i.get('resolution', '480p')}", i.get("duration")),
        official=False, notes=("KIE preview channel",),
    )  # fmt: skip
    return routes
