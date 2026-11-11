"""PixVerse V6 Max en las tiendas: texto a video e imagen a video. Higgsfield no lo vende.

No es PixVerse V6 (`pixverse/v6/…`, que sí está en Higgsfield): APIMart lo presenta como «the higher-quality
version of PixVerse V6», con su propio id y su propia tarifa, y KIE como un modelo afinado para cine, publicidad
y diálogo. Por eso va con id lógico propio y no como un canal más barato de V6.

Fuentes (revisadas el 2026-11-11):
- APIMart, `POST /v1/videos/generations` con `pixverse-v6-max` (un id para los dos modos; con una imagen en
  `image_urls` es imagen a video): https://docs.apimart.ai/en/api-reference/videos/pixverse-v6-max/generation.md.
  Duración 1 a 15 s, 360p/540p/720p/1080p (por defecto 540p), audio apagado por defecto (`audio`), `seed`, 8
  relaciones solo en texto a video. Prompt hasta 5000 caracteres en texto a video y hasta 2048 en imagen a video
  (allí es opcional). Precio por segundo de salida: `pixverse-v6-max|720P` y `|720P-audio`.
- KIE, API unificada (`jobs/createTask`): https://docs.kie.ai/market/pixverse/v6-max-text-to-video.md
  (`pixverse-v6-max/text-to-video`) y .../v6-max-image-to-video.md (`pixverse-v6-max/image-to-video`, una imagen
  en `image_urls`, sin `aspect_ratio`). `quality` en vez de resolución, `generate_audio_switch`, `seed`, prompt
  obligatorio de hasta 5000 caracteres. Precio por segundo (`creditUnit`: per second), la misma fila para los
  dos modos: `pixverse-v6-max, text /image to video, 720p(with audio)`.

Fuera a propósito: primer y último fotograma, fusión de varias imágenes y extensión de video; ninguna de las dos
tiendas los ofrece en V6 Max (APIMart remite a V6 para eso).
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, per_second, unsupported
from ._common import choice, model, prompt, url

DOCS = "https://docs.kie.ai/market/pixverse/v6-max-{}"
RESOLUTIONS = ["360p", "540p", "720p", "1080p"]
RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"]
APIMART_I2V_PROMPT_MAX = 2048
T2V, I2V = "pixverse/v6-max/text-to-video", "pixverse/v6-max/image-to-video"


def _models() -> list[dict[str, Any]]:
    found = []
    for model_id, workflow in ((T2V, "Text to video"), (I2V, "Image to video")):
        text = model_id == T2V
        properties: dict[str, Any] = {
            "prompt": prompt(5000, "What happens in the video." if text else "How the image comes to life."),
            "duration": {"type": "integer", "minimum": 1, "maximum": 15, "default": 5,
                         "description": "Length in seconds (1 to 15)."},
            "resolution": choice(RESOLUTIONS, "720p", "Output resolution."),
            "generate_audio": {"type": "boolean", "default": False,
                               "description": "Generate native audio synced to the picture (costs more per second)."},
            "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647,
                     "description": "Seed for reproducible results; omit for a random one."},
        }  # fmt: skip
        notes = [
            "PixVerse V6 Max, the higher-quality version of PixVerse V6. Not sold by Higgsfield: APIMart or KIE.",
            "Billed per second of output; audio has its own, higher rate.",
        ]
        if text:
            properties["aspect_ratio"] = choice(RATIOS, "16:9", "Output aspect ratio.")
        else:
            properties["image_url"] = url(
                "First frame (JPEG, PNG or WebP, up to 20 MB, sides up to 10000 px)."
            )
            notes.append("No aspect_ratio: the output follows the image.")
            notes.append(f"Prompts over {APIMART_I2V_PROMPT_MAX} characters only run on KIE.")
        found.append(
            model(
                model_id,
                name="PixVerse V6 Max",
                workflow=workflow,
                family="pixverse-v6-max",
                output="video",
                capabilities=["text-to-video"] if text else ["image-to-video"],
                properties=properties,
                required=["prompt"] if text else ["prompt", "image_url"],
                docs_url=DOCS.format("text-to-video" if text else "image-to-video"),
                notes=notes,
            )
        )
    return found


MODELS = _models()


# --- APIMart ----------------------------------------------------------------------------------------

A = "apimart"
A_MODEL = "pixverse-v6-max"


def _apimart_price(i: dict, hints: dict, prices: dict) -> float | None:
    res = str(i.get("resolution", "720p")).upper()
    return per_second(
        prices, f"{A_MODEL}|{res}{'-audio' if i.get('generate_audio') else ''}", i.get("duration")
    )


def _apimart_i2v_prompt(source: dict, out: dict) -> dict:
    if len(source.get("prompt") or "") > APIMART_I2V_PROMPT_MAX:
        raise unsupported(
            A, f"APIMart takes image-to-video prompts of up to {APIMART_I2V_PROMPT_MAX} characters"
        )
    return out


def apimart() -> dict[str, Route]:
    keep = ("prompt", "duration", "resolution", "seed")
    return {
        T2V: Route(A, A_MODEL, Spec(A, A_MODEL, keep=(*keep, "aspect_ratio"), rename={"generate_audio": "audio"}),
                   _apimart_price),
        I2V: Route(A, A_MODEL,
                   Spec(A, A_MODEL, keep=keep, rename={"generate_audio": "audio", "image_url": "image_urls"},
                        convert={"image_url": lambda v: [v]}, build=_apimart_i2v_prompt),
                   _apimart_price),
    }  # fmt: skip


# --- KIE --------------------------------------------------------------------------------------------

K = "kie"


def _kie_price(i: dict, hints: dict, prices: dict) -> float | None:
    audio = "with audio" if i.get("generate_audio") else "no audio"
    key = f"pixverse-v6-max, text /image to video, {i.get('resolution', '720p')}({audio})"
    return per_second(prices, key, i.get("duration"))


def kie() -> dict[str, Route]:
    rename = {"resolution": "quality", "generate_audio": "generate_audio_switch"}
    t2v, i2v = "pixverse-v6-max/text-to-video", "pixverse-v6-max/image-to-video"
    return {
        T2V: Route(K, t2v, Spec(K, t2v, keep=("prompt", "duration", "aspect_ratio", "seed"), rename=rename),
                   _kie_price),
        I2V: Route(K, i2v,
                   Spec(K, i2v, keep=("prompt", "duration", "seed"), rename={**rename, "image_url": "image_urls"},
                        convert={"image_url": lambda v: [v]}),
                   _kie_price),
    }  # fmt: skip
