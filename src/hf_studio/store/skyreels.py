"""SkyReels V4 (Skywork) en APIMart, en sus dos niveles: Fast y Std. Higgsfield y KIE no lo tienen.

Fuente (revisada el 2026-10-17): https://docs.apimart.ai/en/api-reference/videos/skyreels-v4/generation.md
- Un solo id por nivel (`skyreels-v4-fast`, `skyreels-v4-std`); el modo sale de los campos: solo texto, fotogramas
  (`first_frame_image`, `end_frame_image`) u «Omni» (`ref_images`, `ref_videos`). 3–15 s, 480p/720p/1080p (1080p
  por defecto en APIMart), `aspect_ratio` 16:9/4:3/1:1/9:16/3:4 (ignorado con fotogramas o con `ref_videos`),
  `prompt_optimizer` encendido por defecto.
- Omni: cada referencia lleva un `tag` que empieza por `@` y **debe aparecer en el prompt**. Imágenes `type=image`:
  1–3 elementos de 1–5 imágenes cada uno. `ref_videos` `type=extend` continúa un video (≤ 15 s) y se cobra por la
  duración pedida. No se ofrecen los fotogramas intermedios, la cuadrícula ni el video de referencia de movimiento
  (`type=reference`, que impone su propia duración).
- Precio por segundo de salida `skyreels-v4-<nivel>|<RES>`; con video de entrada, `|<RES>-refvideo`.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported
from ._common import choice, model, prompt, url, urls

DOCS = "https://docs.apimart.ai/en/api-reference/videos/skyreels-v4/generation"
TIERS = {"fast": "SkyReels V4 Fast", "std": "SkyReels V4 Std"}
RATIOS = ["16:9", "4:3", "1:1", "9:16", "3:4"]
MODES = {
    "text-to-video": ("Text to video", ["text-to-video"]),
    "image-to-video": ("Image to video", ["image-to-video", "first-last-frame"]),
    "reference-to-video": ("Reference to video", ["reference-to-video", "image-references"]),
    "video-extend": ("Extend video", ["video-extend", "video-input"]),
}


def _id(tier: str, mode: str) -> str:
    return f"skyreels/v4/{tier}/{mode}"


def _models() -> list[dict[str, Any]]:
    found = []
    for tier, name in TIERS.items():
        for mode, (workflow, caps) in MODES.items():
            properties: dict[str, Any] = {
                "prompt": prompt(description="What happens in the video (up to 1280 tokens)."),
                "duration": {"type": "integer", "minimum": 3, "maximum": 15, "default": 5,
                             "description": "Video length in seconds (3–15); when extending, the added length."},
                "resolution": choice(["480p", "720p", "1080p"], "720p", "Output resolution."),
                "prompt_optimizer": {"type": "boolean", "default": True,
                                     "description": "Let SkyReels rewrite the prompt for better results."},
            }  # fmt: skip
            required = ["prompt"]
            notes = ["Runs on APIMart only. Std costs about 25–30% more than Fast for higher quality."]
            if mode in ("text-to-video", "reference-to-video"):
                properties["aspect_ratio"] = choice(RATIOS, "16:9", "Output aspect ratio.")
            if mode == "image-to-video":
                properties["image_url"] = url("First frame; the video keeps its aspect ratio.")
                properties["end_image_url"] = url("Optional last frame.")
                required.append("image_url")
            elif mode == "reference-to-video":
                properties["image_urls"] = urls(
                    1, 3, "One to three subject images, tagged @image1, @image2, @image3."
                )
                required.append("image_urls")
                notes.append(
                    "Each image is tagged @image1, @image2… in order. Cite the tags in the prompt; "
                    "any tag the prompt leaves out is appended at its end, because SkyReels requires them."
                )
            elif mode == "video-extend":
                properties["video_url"] = url("Video to continue (MP4 or MOV, up to 15 s); tagged @video1.")
                required.append("video_url")
                notes.append(
                    "The source video is tagged @video1 and is appended to the prompt if it is not cited."
                )
            found.append(model(
                _id(tier, mode), name=name, workflow=workflow, family=f"skyreels-v4-{tier}", output="video",
                capabilities=caps, properties=properties, required=required, docs_url=DOCS, notes=notes,
            ))  # fmt: skip
    return found


MODELS = _models()


def _cite(text: str, tags: list[str]) -> str:
    """SkyReels rechaza un `tag` que no aparezca en el prompt: se añaden al final los que falten, sin tocar el resto."""
    missing = [t for t in tags if t not in text]
    return f"{text} {' '.join(missing)}" if missing else text


def _refs(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    images = out.pop("image_urls", None) or []
    if not 1 <= len(images) <= 3:
        raise unsupported("apimart", "SkyReels V4 takes one to three reference images")
    tags = [f"@image{n}" for n in range(1, len(images) + 1)]
    out["ref_images"] = [
        {"tag": t, "type": "image", "image_urls": [u]} for t, u in zip(tags, images, strict=True)
    ]
    out["prompt"] = _cite(out["prompt"], tags)
    return out


def _extend(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out["ref_videos"] = [{"tag": "@video1", "type": "extend", "video_url": out.pop("video_url")}]
    out["prompt"] = _cite(out["prompt"], ["@video1"])
    return out


def _price(tier: str, mode: str):
    suffix = "-refvideo" if mode == "video-extend" else ""
    return lambda i, h, p: per_second(
        p, f"skyreels-v4-{tier}|{str(i.get('resolution', '720p')).upper()}{suffix}", i.get("duration")
    )


def apimart() -> dict[str, Route]:
    p = "apimart"
    routes: dict[str, Route] = {}
    for tier in TIERS:
        name = f"skyreels-v4-{tier}"
        keep = ("prompt", "duration", "resolution", "prompt_optimizer")
        specs = {
            "text-to-video": Spec(p, name, keep=(*keep, "aspect_ratio")),
            "image-to-video": Spec(p, name, keep=keep,
                                   rename={"image_url": "first_frame_image", "end_image_url": "end_frame_image"}),
            "reference-to-video": Spec(p, name, keep=(*keep, "aspect_ratio", "image_urls"), build=_refs),
            "video-extend": Spec(p, name, keep=(*keep, "video_url"), build=_extend),
        }  # fmt: skip
        for mode, spec in specs.items():
            routes[_id(tier, mode)] = Route(p, name, spec, _price(tier, mode))
    return routes
