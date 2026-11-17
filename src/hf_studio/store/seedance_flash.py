"""Seedance 2.5 Flash (ByteDance): la versión rápida y barata de Seedance 2.5, solo 480p y 720p, de 4 a 30 s.

Higgsfield no la vende; la ofrecen las dos tiendas (revisado el 2026-11-16):

- APIMart `seedance-2-5-flash`: https://docs.apimart.ai/en/api-reference/videos/seedance-2-5-flash/generation.md.
  Texto, primer y último fotograma (`image_with_roles`, `size: adaptive`), referencias (hasta 10 imágenes,
  5 videos y 5 audios, 30 s en total de video y de audio; solo audio también vale), edición
  (`omni_reference_task_type: edit`, video de 4 a 30 s, `duration: -1`) y extensión (`extend`). Al enviar
  retiene la tarifa por segundo de la resolución (`seedance-2-5-flash|<RES>`; con video de referencia
  `|<RES>-input` por salida más segundos de referencia; `duration: -1` retiene 30 s de salida) y liquida por
  tokens: el precio es aproximado, como Seedance 2.5.
- KIE `bytedance/seedance-2-5-flash`: https://docs.kie.ai/market/bytedance/seedance-2-5-flash.md. Lo mismo con
  `first_frame_url`/`last_frame_url` y `reference_*_urls`; edición y extensión con `omni_reference_task_type`
  (a diferencia de Seedance 2.5 en KIE). Precio por segundo `bytedance/seedance-2-5-flash, <res> no video` y,
  con video de referencia, `..., <res> with video` por salida más segundos de referencia.
No se exponen `web_search`, `return_last_frame`, `nsfw_check` ni los `asset://` de caras aprobadas.
"""

from __future__ import annotations

from typing import Any

from ..providers.apimart_routes import _frames, _seedance_price, _seedance_reserve
from ..providers.kie_routes import SEEDANCE_FRAMES, SEEDANCE_REFS
from ..providers.kie_routes import _seedance_price as _kie_seedance_price
from ..providers.routes import Route, Spec, unsupported, video_seconds
from ._common import choice, model, prompt, url, urls

FAMILY = "bytedance/seedance-2.5-flash"
NAME = "Seedance 2.5 Flash"
DOCS = "https://docs.apimart.ai/en/api-reference/videos/seedance-2-5-flash/generation"
APIMART = "seedance-2-5-flash"
KIE = "bytedance/seedance-2-5-flash"
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
MODES = ("text-to-video", "image-to-video", "reference-to-video", "video-edit", "video-extend")
MAX_VIDEO_SECONDS = 30  # suma de los videos de entrada (referencia, edición o extensión)
MIN_EDIT_SECONDS = 4
NOTE = (
    "ByteDance's fast Seedance 2.5 (480p or 720p, 4 to 30 s, optional audio), through APIMart or KIE "
    "(not Higgsfield). Cheaper than Seedance 2.5; use Seedance 2.5 for 1080p."
)
BILLING = "APIMart bills by tokens afterwards (approximate quote); KIE bills a fixed rate per second."
WITH_VIDEO = "With input video, the input seconds are billed too (at a lower rate) on top of the output."


def _id(mode: str) -> str:
    return f"{FAMILY}/{mode}"


def _models() -> list[dict[str, Any]]:
    common = {
        "prompt": prompt(20000, "What happens in the video; cite references as @image1, @video1, @audio1."),
        "duration": {"type": "integer", "minimum": 4, "maximum": 30, "default": 5, "description": "Length in seconds."},
        "resolution": choice(["480p", "720p"], "720p", "Output resolution (no 1080p on Flash)."),
        "generate_audio": {"type": "boolean", "default": True, "description": "Generate a soundtrack with the video."},
    }  # fmt: skip
    ratio = {"aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio.")}
    images = urls(1, 10, "Reference images (up to 10): characters, products, places or styles.")
    audios = urls(1, 5, "Reference audio (up to 5, 2 to 30 s each, 30 s in total).")
    found = []
    for mode in MODES:
        notes = [NOTE, BILLING]
        props: dict[str, Any] = dict(common)
        required = ["prompt"]
        if mode == "text-to-video":
            workflow, caps = "Text to video", ["text-to-video"]
            props.update(ratio)
        elif mode == "image-to-video":
            workflow, caps = "Image to video", ["first-last-frame", "image-to-video"]
            props["image_url"] = url("First frame of the video.")
            props["end_image_url"] = url("Optional last frame.")
            required.append("image_url")
            notes.append("Output framing follows image_url.")
        elif mode == "reference-to-video":
            workflow, caps = "Reference to video", ["audio-input", "image-references", "reference-to-video", "video-input"]  # fmt: skip
            props.update(ratio)
            props["image_urls"] = images
            props["video_urls"] = urls(1, 5, "Reference videos (up to 5, 2 to 30 s each, 30 s in total).")
            props["audio_urls"] = audios
            notes += ["Provide image_urls, video_urls or audio_urls (audio alone is enough).", WITH_VIDEO]
        elif mode == "video-edit":
            workflow, caps = "Video edit", ["audio-input", "edit", "image-references", "video-edit", "video-input"]  # fmt: skip
            del props["duration"]
            props["prompt"] = prompt(20000, "What to change in @video1; images and audio can be cited too.")
            props["video_url"] = url("Video to edit (4 to 30 s); the result keeps its length and framing.")
            props["image_urls"] = images
            props["audio_urls"] = audios
            required.append("video_url")
            notes += ["The source video seconds are billed twice: as input and as output.", WITH_VIDEO]
        else:
            workflow, caps = (
                "Video extend",
                ["audio-input", "image-references", "video-extend", "video-input"],
            )
            props["prompt"] = prompt(20000, "What happens after the end of @video1.")
            props["video_url"] = url("Video to continue (up to 30 s).")
            props["duration"] = {**common["duration"], "description": "Length of the new video in seconds."}
            props["image_urls"] = images
            props["audio_urls"] = audios
            required.append("video_url")
            notes.append(WITH_VIDEO)
        entry = model(
            _id(mode), name=NAME, workflow=workflow, family=FAMILY, output="video", capabilities=caps,
            properties=props, required=required, docs_url=DOCS, notes=notes,
        )  # fmt: skip
        if mode == "reference-to-video":
            entry["input_schema"]["if"] = {"required": ["image_urls"]}
            entry["input_schema"]["else"] = {
                "if": {"required": ["video_urls"]},
                "else": {"required": ["audio_urls"]},
            }
        found.append(entry)
    return found


MODELS = _models()


def _check(provider: str, mode: str):
    """Los videos de entrada suman a lo más 30 s; el que se edita dura al menos 4 s."""

    def check(source: dict[str, Any], hints: dict[str, Any]) -> None:
        seconds = video_seconds(hints)
        if seconds is None:
            return
        if seconds > MAX_VIDEO_SECONDS:
            raise unsupported(
                provider, f"Seedance 2.5 Flash takes at most {MAX_VIDEO_SECONDS} s of input video"
            )
        if mode == "video-edit" and seconds < MIN_EDIT_SECONDS:
            raise unsupported(provider, f"Seedance 2.5 Flash edits videos of {MIN_EDIT_SECONDS} s or more")

    return check


def _apimart_video(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out["video_urls"] = [out.pop("video_url")]
    return out


def apimart() -> dict[str, Route]:
    keep = ("prompt", "duration", "resolution", "generate_audio")
    media = ("image_urls", "audio_urls")
    price, reserve = _seedance_price(APIMART), _seedance_reserve(APIMART)
    hold = ("APIMart first holds 30 s of output and refunds the difference after generating",)

    def route(spec: Spec, mode: str, notes: tuple[str, ...] = ()) -> Route:
        return Route(
            "apimart", APIMART, spec, price, reserve=reserve, settles_later=True, notes=notes,
            check=_check("apimart", mode) if mode in ("reference-to-video", "video-edit", "video-extend") else None,
        )  # fmt: skip

    return {
        _id("text-to-video"): route(
            Spec("apimart", APIMART, keep=keep, rename={"aspect_ratio": "size"}), "text-to-video"
        ),
        _id("image-to-video"): route(
            Spec(
                "apimart",
                APIMART,
                keep=(*keep, "image_url", "end_image_url"),
                fixed={"size": "adaptive"},
                build=_frames,
            ),
            "image-to-video",
        ),
        _id("reference-to-video"): route(
            Spec(
                "apimart",
                APIMART,
                keep=(*keep, *media, "video_urls"),
                rename={"aspect_ratio": "size"},
                fixed={"omni_reference_task_type": "reference"},
            ),
            "reference-to-video",
        ),
        _id("video-edit"): route(
            Spec(
                "apimart",
                APIMART,
                keep=("prompt", "resolution", "generate_audio", "video_url", *media),
                fixed={"omni_reference_task_type": "edit", "duration": -1, "size": "adaptive"},
                build=_apimart_video,
            ),
            "video-edit",
            hold,
        ),
        _id("video-extend"): route(
            Spec(
                "apimart",
                APIMART,
                keep=(*keep, "video_url", *media),
                fixed={"omni_reference_task_type": "extend", "size": "adaptive"},
                build=_apimart_video,
            ),
            "video-extend",
        ),
    }


def _kie_video(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out["reference_video_urls"] = [out.pop("video_url")]
    return out


def kie() -> dict[str, Route]:
    keep = ("prompt", "duration", "resolution", "aspect_ratio", "generate_audio")
    refs = {"image_urls": SEEDANCE_REFS["image_urls"], "audio_urls": SEEDANCE_REFS["audio_urls"]}
    price = _kie_seedance_price(KIE, "with video")

    def route(spec: Spec, mode: str) -> Route:
        check = _check("kie", mode) if mode in ("reference-to-video", "video-edit", "video-extend") else None
        return Route("kie", KIE, spec, price, check=check)

    return {
        _id("text-to-video"): route(Spec("kie", KIE, keep=keep), "text-to-video"),
        _id("image-to-video"): route(
            Spec("kie", KIE, keep=keep, rename=SEEDANCE_FRAMES, fixed={"aspect_ratio": "adaptive"}),
            "image-to-video",
        ),
        _id("reference-to-video"): route(
            Spec(
                "kie", KIE, keep=keep, rename=SEEDANCE_REFS, fixed={"omni_reference_task_type": "reference"}
            ),
            "reference-to-video",
        ),
        _id("video-edit"): route(
            Spec(
                "kie",
                KIE,
                keep=("prompt", "resolution", "generate_audio", "video_url"),
                rename=refs,
                fixed={"omni_reference_task_type": "edit", "aspect_ratio": "adaptive", "duration": -1},
                build=_kie_video,
            ),
            "video-edit",
        ),
        _id("video-extend"): route(
            Spec(
                "kie",
                KIE,
                keep=(*keep, "video_url"),
                rename=refs,
                fixed={"omni_reference_task_type": "extend", "aspect_ratio": "adaptive"},
                build=_kie_video,
            ),
            "video-extend",
        ),
    }
