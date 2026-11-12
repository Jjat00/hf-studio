"""APIMart Zoe (`apimart-zoe`), el modelo de video propio de APIMart. Higgsfield y KIE no lo venden.

Fuente (revisada el 2026-11-12): https://docs.apimart.ai/en/api-reference/videos/apimart-zoe/generation.md
- Un solo id para todo, `POST /v1/videos/generations`; el modo sale de los medios: solo texto, fotogramas
  (`first_frame_image` y `last_frame_image` opcional), referencias (hasta 30 imágenes, 10 videos y 10 audios; el
  audio exige una imagen o un video) o edición (`omni_reference_task_type: edit` con un video fuente de 4 a 30 s:
  la duración y la relación siguen al video). Los fotogramas no se combinan con referencias.
- 480p, 720p (por defecto), 1080p, 2k y 4k; de 4 a 30 s (5 por defecto); relación 21:9, 16:9, 4:3, 1:1, 3:4, 9:16
  o `adaptive` (por defecto: la decide el modelo o los medios); `audio` (si se omite lo decide el modelo: aquí va
  siempre explícito), `seed`, `enhance_prompt` (apagado por defecto), `output_format` mp4 o mov.
- Precio por segundo `apimart-zoe|<RES>` (tabla pública, `per_second` por resolución). Con videos de referencia
  (sección «Billing rules») se cobra a la tarifa `|<RES>-input` por `D + max(R, ceil(D × 2/3))` segundos, con `D`
  la duración de salida y `R` la suma de los videos de entrada redondeada hacia abajo. Las imágenes y el audio de
  referencia no cambian la tarifa. En la edición `D` es la duración real del resultado (sigue al video fuente,
  redondeada al segundo): APIMart retiene 30 s de salida al enviar y luego liquida, así que el precio es
  aproximado y la retención va en `reserve`.

Fuera a propósito: el borrador a 480p y su final a 1080p (`draft` / `draft_task_id`, como Seedance 2.5 Draft en
`store/seedance_draft.py`), `duration: -1` fuera de la edición (el modelo elige la duración y la liquida después),
`return_last_frame` (devuelve una imagen aparte que el flujo de resultados no recoge) y `nsfw_check`.
"""

from __future__ import annotations

import math
from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported, video_seconds
from ._common import choice, model, prompt, url, urls

P = "apimart"
NAME = "apimart-zoe"
DOCS = "https://docs.apimart.ai/en/api-reference/videos/apimart-zoe/generation"
BASE = "apimart/zoe"
RATIOS = ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
MODES = {
    "text-to-video": ("Text to video", ["text-to-video"]),
    "image-to-video": ("Image to video", ["image-to-video", "first-last-frame"]),
    "reference-to-video": ("Reference to video", ["reference-to-video", "image-references", "video-input"]),
    "video-edit": ("Edit video", ["video-edit", "video-input"]),
}
EDIT_RESERVE = 30  # segundos de salida que APIMart retiene al enviar una edición


def _models() -> list[dict[str, Any]]:
    found = []
    for mode, (workflow, caps) in MODES.items():
        edit = mode == "video-edit"
        properties: dict[str, Any] = {
            "prompt": prompt(description="What happens in the video or, when editing, what to change."),
            "resolution": choice(["480p", "720p", "1080p", "2k", "4k"], "720p", "Output resolution."),
            "generate_audio": {"type": "boolean", "default": True, "description": "Generate sound with the video."},
            "enhance_prompt": {"type": "boolean", "default": False,
                               "description": "Let the model rewrite the prompt before generating."},
            "output_format": choice(["mp4", "mov"], "mp4", "Video container."),
            "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647, "description": "Fixed seed."},
        }  # fmt: skip
        required = ["prompt"]
        notes = ["Runs on APIMart only: APIMart's own video model."]
        if not edit:
            properties["duration"] = {"type": "integer", "minimum": 4, "maximum": 30, "default": 5,
                                      "description": "Video length in seconds (4–30)."}  # fmt: skip
            properties["aspect_ratio"] = choice(
                RATIOS, "adaptive", "Output aspect ratio; adaptive lets the model or the media decide."
            )
        if mode == "image-to-video":
            properties["image_url"] = url("First frame.")
            properties["end_image_url"] = url("Optional last frame.")
            required.append("image_url")
        elif mode == "reference-to-video":
            properties["image_urls"] = urls(0, 30, "Up to 30 reference images (subjects, style, scene).")
            properties["video_urls"] = urls(0, 10, "Up to 10 reference videos, 2 to 15 s each (MP4 or MOV).")
            properties["audio_urls"] = urls(
                0, 10, "Up to 10 reference audio clips (WAV or MP3, 2 to 15 s each, 30 s in total)."
            )
            notes.append("Needs at least one reference image or video; audio alone is not accepted.")
            notes.append(
                "With reference videos the per-second rate changes and APIMart also bills the input: "
                "output + max(input seconds, two thirds of the output)."
            )
        elif edit:
            properties["video_url"] = url(
                "Video to edit, 4 to 30 s; the result keeps its length and aspect ratio."
            )
            properties["image_urls"] = urls(0, 30, "Optional reference images for the edit.")
            required.append("video_url")
            notes.append(
                "Billed for the real output length plus the source video (approximate until it finishes); "
                "APIMart holds 30 s of output when it starts and refunds the difference."
            )
        found.append(model(
            f"{BASE}/{mode}", name="APIMart Zoe", workflow=workflow, family=NAME, output="video",
            capabilities=caps, properties=properties, required=required, docs_url=DOCS, notes=notes,
            summary=f"{workflow} with APIMart Zoe, APIMart's own video model (not offered by Higgsfield or KIE).",
        ))  # fmt: skip
    return found


MODELS = _models()


def _res(i: dict[str, Any]) -> str:
    return str(i.get("resolution", "720p")).upper()


def _with_input(prices: dict[str, float], res: str, output: int, seconds: float) -> float | None:
    """Docs, «Billing rules»: `D + max(R, ceil(D × 2/3))` a la tarifa con video, con `R` hacia abajo."""
    billable = output + max(math.floor(seconds), math.ceil(output * 2 / 3))
    return per_second(prices, f"{NAME}|{res}-input", billable)


def _price(i: dict[str, Any], hints: dict[str, Any], prices: dict[str, float]) -> float | None:
    output = i.get("duration")
    if output is None:
        return None
    if i.get("video_urls"):
        seconds = video_seconds(hints)
        return None if seconds is None else _with_input(prices, _res(i), output, seconds)
    return per_second(prices, f"{NAME}|{_res(i)}", output)


def _edit_price(i: dict[str, Any], hints: dict[str, Any], prices: dict[str, float]) -> float | None:
    """La salida dura lo que el video fuente (redondeado al segundo más cercano, como liquida APIMart)."""
    seconds = video_seconds(hints)
    return None if seconds is None else _with_input(prices, _res(i), math.floor(seconds + 0.5), seconds)


def _edit_reserve(i: dict[str, Any], hints: dict[str, Any], prices: dict[str, float]) -> float | None:
    seconds = video_seconds(hints)
    return None if seconds is None else _with_input(prices, _res(i), EDIT_RESERVE, seconds)


def _refs(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    if not (source.get("image_urls") or source.get("video_urls")):
        raise unsupported(P, "APIMart Zoe needs at least one reference image or video")
    for key in ("image_urls", "video_urls", "audio_urls"):
        if not out.get(key):
            out.pop(key, None)  # una lista vacía no se envía
    return out


def _refs_length(source: dict[str, Any], hints: dict[str, Any]) -> None:
    """Solo se conoce la suma: con un clip se comprueba exacto; con varios, lo que la suma ya hace imposible."""
    count, seconds = len(source.get("video_urls") or []), video_seconds(hints)
    if count and seconds is not None and not 1.8 * count <= seconds <= 15.2 * count:
        raise unsupported(P, "APIMart Zoe takes reference videos of 2 to 15 s each")


def _edit(source: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out["video_urls"] = [out.pop("video_url")]
    if not out.get("image_urls"):
        out.pop("image_urls", None)
    return out


def _edit_length(source: dict[str, Any], hints: dict[str, Any]) -> None:
    seconds = video_seconds(hints)
    if seconds is not None and not 3.8 <= seconds < 30.2:
        raise unsupported(P, "APIMart Zoe edits videos of 4 to 30 s")


def apimart() -> dict[str, Route]:
    keep = ("prompt", "resolution", "enhance_prompt", "output_format", "seed")
    timed = (*keep, "duration", "aspect_ratio")
    audio = {"generate_audio": "audio"}
    specs = {
        "text-to-video": Spec(P, NAME, keep=timed, rename=audio),
        "image-to-video": Spec(P, NAME, keep=timed, rename={
            **audio, "image_url": "first_frame_image", "end_image_url": "last_frame_image"}),
        "reference-to-video": Spec(P, NAME, keep=(*timed, "image_urls", "video_urls", "audio_urls"), rename=audio,
                                   fixed={"omni_reference_task_type": "reference"}, build=_refs),
        "video-edit": Spec(P, NAME, keep=(*keep, "video_url", "image_urls"), rename=audio,
                           fixed={"omni_reference_task_type": "edit"}, build=_edit),
    }  # fmt: skip
    return {
        f"{BASE}/text-to-video": Route(P, NAME, specs["text-to-video"], _price),
        f"{BASE}/image-to-video": Route(P, NAME, specs["image-to-video"], _price),
        f"{BASE}/reference-to-video": Route(P, NAME, specs["reference-to-video"], _price, check=_refs_length),
        f"{BASE}/video-edit": Route(
            P, NAME, specs["video-edit"], _edit_price, reserve=_edit_reserve, settles_later=True,
            check=_edit_length, notes=("Output length follows the source video: approximate until it finishes",),
        ),
    }  # fmt: skip
