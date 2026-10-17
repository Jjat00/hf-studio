"""Variantes de video de Wan (Alibaba) que solo venden las tiendas: 2.2 A14B Turbo, 2.2 Animate, 2.5, 2.6 Flash
y la edición de video de 2.7. Higgsfield solo trae Wan 2.6, 2.7 (t2v, i2v, referencias) y 3.0.

Fuentes (revisadas el 2026-10-17):
- KIE, API unificada (`jobs/createTask`), un id por modo:
  https://docs.kie.ai/market/wan/2-2-a14b-text-to-video-turbo.md, .../2-2-a14b-image-to-video-turbo.md y
  .../2-2-a14b-speech-to-video-turbo.md (480p/720p, en voz también 580p, `num_frames` y `frames_per_second`);
  .../2-2-animate-move.md y .../2-2-animate-replace.md (video + imagen, sin prompt);
  .../2-5-text-to-video.md y .../2-5-image-to-video.md (5 o 10 s, 720p/1080p, prompt hasta 800 caracteres);
  .../2-6-flash-image-to-video.md y .../2-6-flash-video-to-video.md (`audio` con o sin sonido);
  .../2-7-videoedit.md (un video de 2 a 10 s, una imagen de referencia, `audio_setting`).
  Tabla pública `api.kie.ai/client/v1/model-pricing/page`: 2.2 Turbo, Speech to Video, Animate y 2.7 videoedit
  por segundo; 2.5 y 2.6 Flash por video según duración y resolución.
- APIMart, `POST /v1/videos/generations`:
  https://docs.apimart.ai/en/api-reference/videos/wan2.5/generation.md (`wan2.5-preview`, t2v o i2v según
  `image_urls`, 480p/720p/1080p, siempre con audio), .../wan2.6/i2v-flash-generation.md (`wan2.6-i2v-flash`,
  2–15 s, `audio`), .../wan2.7-videoedit/generation.md (`wan2.7-videoedit`, `metadata.audio_setting`).
  Precio por segundo de salida: `<id>|<RES>` (`|default` es 720P en 2.7) y `wan2.6-i2v-flash|<RES>-audio`.

Wan 2.2 Turbo (texto e imagen) no publica la duración de salida: se cotiza un clip de unos 5 s (81 fotogramas a
16 fps) a la tarifa por segundo de la tabla; la página de KIE dice «por video» en 480p, así que el precio es
aproximado (`settles_later`) y por lo alto.
"""

from __future__ import annotations

from typing import Any

from ..providers.routes import Route, Spec, only_default, per_second, per_unit, unsupported, video_seconds
from ._common import choice, model, prompt, upper, url, urls

KIE_DOCS = "https://docs.kie.ai/market/wan"
TURBO_SECONDS = 5  # 81 fotogramas a 16 fps: la duración típica de Wan 2.2 A14B
RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"]


# --- Piezas del esquema y de los traductores -------------------------------------------------------


def _seed_field() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": -1,
        "maximum": 2147483647,
        "description": "Seed; -1 or empty for random.",
    }


def _flag(default: bool, description: str) -> dict[str, Any]:
    return {"type": "boolean", "default": default, "description": description}


def _negative(max_length: int = 500) -> dict[str, Any]:
    return {"type": "string", "default": "", "maxLength": max_length, "description": "What to avoid."}


def _seed(value: Any) -> Any:
    """-1 es aleatoria: no se envía (las dos tiendas eligen una al omitirla)."""
    return None if value is None or value < 0 else value


def _str(value: Any) -> str:
    return str(value)


def _empty(value: Any) -> Any:
    return value or None


def _max_chars(provider: str, field_name: str, limit: int):
    def check(value: Any) -> Any:
        if value and len(str(value)) > limit:
            raise unsupported(provider, f"{provider} allows {limit} characters in {field_name}")
        return value or None

    return check


def _no_value(provider: str, field_name: str):
    def check(value: Any) -> Any:
        if value:
            raise unsupported(provider, f"{field_name} has no equivalent on {provider}")
        return None

    return check


def _one(value: str) -> list[str]:
    return [value]


# --- Modelos --------------------------------------------------------------------------------------


def _turbo_models() -> list[dict[str, Any]]:
    turbo_notes = [
        "Wan 2.2 A14B Turbo: fast open-weights Wan. Higgsfield does not sell it; it runs on KIE.",
        "KIE does not publish the clip length; the quote assumes about 5 s at its per-second rate.",
    ]
    common = {
        "prompt": prompt(5000),
        "resolution": choice(["480p", "720p"], "720p", "Output resolution."),
        "prompt_extend": _flag(False, "Let an LLM expand the prompt."),
        "acceleration": choice(["none", "regular"], "none", "Faster generation at lower quality."),
        "seed": _seed_field(),
    }
    t2v = model(
        "wan/v2.2-turbo/text-to-video", name="Wan 2.2 Turbo", workflow="Text to video", family="wan-2.2-turbo",
        output="video", capabilities=["text-to-video"],
        properties={**common, "aspect_ratio": choice(["16:9", "9:16"], "16:9", "Output aspect ratio.")},
        required=["prompt"], docs_url=f"{KIE_DOCS}/2-2-a14b-text-to-video-turbo", notes=turbo_notes,
    )  # fmt: skip
    i2v = model(
        "wan/v2.2-turbo/image-to-video", name="Wan 2.2 Turbo", workflow="Image to video", family="wan-2.2-turbo",
        output="video", capabilities=["image-to-video"],
        properties={**common, "image_url": url("First frame (JPEG, PNG or WEBP, up to 10 MB).")},
        required=["prompt", "image_url"], docs_url=f"{KIE_DOCS}/2-2-a14b-image-to-video-turbo", notes=turbo_notes,
    )  # fmt: skip
    s2v = model(
        "wan/v2.2-turbo/speech-to-video", name="Wan 2.2 Turbo", workflow="Speech to video",
        family="wan-2.2-turbo", output="video", capabilities=["image-to-video", "audio-input"],
        properties={
            "prompt": prompt(5000, "What the person does while speaking."),
            "image_url": url("The person or character (JPEG, PNG or WEBP, up to 10 MB)."),
            "audio_url": url("Speech or song that drives the video (up to 10 MB)."),
            "resolution": choice(["480p", "580p", "720p"], "480p", "Output resolution."),
            "num_frames": {"type": "integer", "minimum": 40, "maximum": 120, "multipleOf": 4, "default": 80,
                           "description": "Frames to generate (40–120, multiple of 4)."},
            "frames_per_second": {"type": "integer", "minimum": 4, "maximum": 60, "default": 16,
                                  "description": "Output frame rate; length = num_frames / frames_per_second."},
            "negative_prompt": _negative(),
            "num_inference_steps": {"type": "integer", "minimum": 2, "maximum": 40, "default": 27,
                                    "description": "Sampling steps; more is slower and better."},
            "guidance_scale": {"type": "number", "minimum": 1, "maximum": 10, "default": 3.5,
                               "description": "Prompt adherence."},
            "shift": {"type": "number", "minimum": 1, "maximum": 10, "default": 5, "description": "Shift value."},
            "seed": _seed_field(),
        },
        required=["prompt", "image_url", "audio_url"], docs_url=f"{KIE_DOCS}/2-2-a14b-speech-to-video-turbo",
        notes=["Image + audio to a talking or singing video. Runs on KIE only.",
               "Billed per second of output; the quote uses num_frames / frames_per_second."],
    )  # fmt: skip
    return [t2v, i2v, s2v]


def _animate_models() -> list[dict[str, Any]]:
    found = []
    for mode, workflow, caps, what in (
        ("move", "Animate move", ["motion-transfer", "image-to-video", "video-input"],
         "The character in the image performs the motion and expressions of the video."),
        ("replace", "Animate replace", ["video-edit", "video-input"],
         "The character in the image replaces the person in the video, keeping its scene and lighting."),
    ):  # fmt: skip
        found.append(
            model(
                f"wan/v2.2-animate/{mode}",
                name="Wan 2.2 Animate",
                workflow=workflow,
                family="wan-2.2-animate",
                output="video",
                capabilities=caps,
                properties={
                    "video_url": url("Driving video (MP4, MOV or MKV, up to 10 MB)."),
                    "image_url": url("Character image (JPEG, PNG or WEBP, up to 10 MB)."),
                    "resolution": choice(["480p", "580p", "720p"], "480p", "Output resolution."),
                },
                required=["video_url", "image_url"],
                docs_url=f"{KIE_DOCS}/2-2-animate-{mode}",
                notes=[what, "No prompt. Runs on KIE only, billed per second of the driving video."],
            )
        )
    return found


def _wan25_models() -> list[dict[str, Any]]:
    common = {
        "prompt": prompt(description="What happens in the video (up to 800 characters on KIE)."),
        "negative_prompt": _negative(),
        "duration": choice([5, 10], 5, "Length in seconds."),
        "resolution": choice(["480p", "720p", "1080p"], "720p", "Output resolution (480p only on APIMart)."),
        "prompt_extend": _flag(True, "Let an LLM rewrite the prompt."),
        "audio_url": url("Your own soundtrack (wav/mp3, 3–30 s); only on APIMart."),
        "seed": _seed_field(),
    }
    notes = ["Wan 2.5 always generates its own audio (dialogue, ambience) unless audio_url is given.",
             "Higgsfield does not sell it; it runs on APIMart (wan2.5-preview) or KIE."]  # fmt: skip
    t2v = model(
        "wan/v2.5/text-to-video", name="Wan 2.5", workflow="Text to video", family="wan-2.5", output="video",
        capabilities=["text-to-video", "audio-input"],
        properties={**common, "aspect_ratio": choice(RATIOS, "16:9", "Output aspect ratio (4:3 and 3:4 not at 480p).")},
        required=["prompt"], docs_url=f"{KIE_DOCS}/2-5-text-to-video",
        notes=[*notes, "KIE takes 16:9, 9:16 or 1:1 at 720p or 1080p."],
    )  # fmt: skip
    i2v = model(
        "wan/v2.5/image-to-video", name="Wan 2.5", workflow="Image to video", family="wan-2.5", output="video",
        capabilities=["image-to-video", "audio-input"],
        properties={**common, "image_url": url("First frame; it sets the aspect ratio.")},
        required=["prompt", "image_url"], docs_url=f"{KIE_DOCS}/2-5-image-to-video", notes=notes,
    )  # fmt: skip
    return [t2v, i2v]


def _flash_models() -> list[dict[str, Any]]:
    common = {
        "prompt": prompt(description="What happens in the video (up to 1500 characters on KIE)."),
        "resolution": choice(["720p", "1080p"], "1080p", "Output resolution."),
        "generate_audio": _flag(True, "Generate sound; silent videos cost less."),
        "multi_shots": _flag(False, "Several shots with transitions instead of one continuous shot."),
    }
    i2v = model(
        "wan/v2.6-flash/image-to-video", name="Wan 2.6 Flash", workflow="Image to video", family="wan-2.6-flash",
        output="video", capabilities=["image-to-video", "audio-input"],
        properties={
            **common,
            "image_url": url("First frame (at least 256×256)."),
            "duration": {"type": "integer", "minimum": 2, "maximum": 15, "default": 5,
                         "description": "Length in seconds (KIE: 5, 10 or 15)."},
            "audio_url": url("Your own soundtrack (wav/mp3, 3–30 s); only on APIMart, needs generate_audio."),
            "negative_prompt": _negative(),
            "prompt_extend": _flag(False, "Let an LLM rewrite the prompt (APIMart only; multi_shots needs it there)."),
            "seed": _seed_field(),
        },
        required=["prompt", "image_url"], docs_url=f"{KIE_DOCS}/2-6-flash-image-to-video",
        notes=["Fast, cheaper Wan 2.6. Runs on APIMart (wan2.6-i2v-flash) or KIE.",
               "KIE takes 5, 10 or 15 s and has no seed, negative prompt or custom audio."],
    )  # fmt: skip
    r2v = model(
        "wan/v2.6-flash/reference-to-video", name="Wan 2.6 Flash", workflow="Reference to video",
        family="wan-2.6-flash", output="video", capabilities=["reference-to-video", "video-input"],
        properties={
            **common,
            "video_urls": urls(1, 3, "One to three reference videos of the characters (MP4, MOV or MKV, up to 10 MB)."),
            "duration": choice([5, 10], 5, "Length in seconds."),
        },
        required=["prompt", "video_urls"], docs_url=f"{KIE_DOCS}/2-6-flash-video-to-video",
        notes=["New video with the characters of the reference videos. Runs on KIE only, priced per video."],
    )  # fmt: skip
    return [i2v, r2v]


def _edit_model() -> dict[str, Any]:
    return model(
        "wan/v2.7/video-edit", name="Wan 2.7", workflow="Video edit", family="wan-2.7", output="video",
        capabilities=["video-edit", "video-input", "image-references"],
        properties={
            "prompt": prompt(5000, "What to change: style, outfit, background, added elements."),
            "video_url": url("Video to edit: MP4 or MOV, 2–10 s, up to 100 MB."),
            "image_urls": urls(0, 4, "Reference images for style or appearance (KIE takes one)."),
            "negative_prompt": _negative(),
            "resolution": choice(["720p", "1080p"], "1080p", "Output resolution."),
            "aspect_ratio": {"type": "string", "enum": RATIOS,
                             "description": "Output aspect ratio; empty keeps the source video's."},
            "duration": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0,
                         "description": "0 keeps the whole source; 2–10 cuts the output to that many seconds."},
            "audio_setting": choice(["auto", "origin"], "auto", "auto regenerates sound; origin keeps the source audio."),
            "prompt_extend": _flag(True, "Let an LLM rewrite the prompt."),
            "seed": _seed_field(),
        },
        required=["video_url"], docs_url=f"{KIE_DOCS}/2-7-videoedit",
        notes=["Edits an existing 2–10 s video. Runs on APIMart or KIE, billed per second of output.",
               "Without duration the output is as long as the source video."],
    )  # fmt: skip


MODELS = [*_turbo_models(), *_animate_models(), *_wan25_models(), *_flash_models(), _edit_model()]


# --- KIE ------------------------------------------------------------------------------------------

K = "kie"


def _kie_turbo() -> dict[str, Route]:
    routes = {}
    for kind, label in (("text-to-video", "text to video"), ("image-to-video", "image to video")):
        name = f"wan/2-2-a14b-{kind}-turbo"
        routes[f"wan/v2.2-turbo/{kind}"] = Route(
            K, name,
            Spec(K, name, keep=("prompt", "resolution", "aspect_ratio", "acceleration", "image_url"),
                 rename={"prompt_extend": "enable_prompt_expansion"}, convert={"seed": _seed}),
            lambda i, h, p, lb=label: per_second(
                p, f"wan 2.2 a14b turbo api {lb}, {i.get('resolution', '720p')}", TURBO_SECONDS),
            settles_later=True,
            notes=("Quoted for a clip of about 5 s; KIE does not publish the exact length",),
        )  # fmt: skip
    name = "wan/2-2-a14b-speech-to-video-turbo"
    routes["wan/v2.2-turbo/speech-to-video"] = Route(
        K, name,
        Spec(K, name,
             keep=("prompt", "image_url", "audio_url", "resolution", "num_frames", "frames_per_second",
                   "num_inference_steps", "guidance_scale", "shift"),
             convert={"seed": _seed, "negative_prompt": _empty}),
        lambda i, h, p: per_second(
            p, f"wan 2.2 a14b turbo api speech to video, {i.get('resolution', '480p')}",
            i.get("num_frames", 80) / i.get("frames_per_second", 16)),
        settles_later=True,
        notes=("Quoted as num_frames / frames_per_second seconds at KIE's per-second rate",),
    )  # fmt: skip
    return routes


def _kie_animate() -> dict[str, Route]:
    routes = {}
    for mode in ("move", "replace"):
        name = f"wan/2-2-animate-{mode}"
        routes[f"wan/v2.2-animate/{mode}"] = Route(
            K, name,
            Spec(K, name, keep=("video_url", "image_url", "resolution"), convert={"prompt": _no_value(K, "prompt")}),
            lambda i, h, p, m=mode: per_second(
                p, f"wan 2.2 animate, 2.2 animate {m}, 1.0s-{i.get('resolution', '480p')}", video_seconds(h)),
            notes=("Billed by the length of the driving video",),
        )  # fmt: skip
    return routes


def _kie_wan25() -> dict[str, Route]:
    routes = {}
    for kind in ("text-to-video", "image-to-video"):
        name = f"wan/2-5-{kind}"
        spec = Spec(
            K, name,
            keep=("resolution", "aspect_ratio", "image_url"),
            rename={"prompt_extend": "enable_prompt_expansion"},
            convert={"prompt": _max_chars(K, "prompt", 800), "duration": _str, "seed": _seed,
                     "negative_prompt": _empty, "audio_url": _no_value(K, "audio_url")},
            allowed={"resolution": {"720p", "1080p"}, "aspect_ratio": {"16:9", "9:16", "1:1"}},
        )  # fmt: skip
        routes[f"wan/v2.5/{kind}"] = Route(
            K, name, spec,
            lambda i, h, p, k=kind: per_unit(
                p, f"wan 2.5, {k}, default-{i.get('duration', 5)}.0s-{i.get('resolution', '720p')}"),
        )  # fmt: skip
    return routes


def _flash_price(kind: str):
    def price(i: dict, h: dict, p: dict) -> float | None:
        sound = "with" if i.get("generate_audio", True) else "without"
        return per_unit(
            p,
            f"wan 2.6 flash, {kind}, {sound} audio-{i.get('duration', 5)}.0s-{i.get('resolution', '1080p')}",
        )

    return price


def _kie_flash() -> dict[str, Route]:
    common = {"prompt": _max_chars(K, "prompt", 1500), "duration": _str}
    i2v = Spec(
        K, "wan/2-6-flash-image-to-video",
        keep=("resolution", "multi_shots"),
        rename={"image_url": "image_urls", "generate_audio": "audio"},
        convert={**common, "image_url": _one, "generate_audio": bool, "seed": _no_seed,
                 "audio_url": _no_value(K, "audio_url"), "negative_prompt": _no_value(K, "negative_prompt"),
                 "prompt_extend": only_default("prompt_extend", False)},
        allowed={"duration": {5, 10, 15}},
    )  # fmt: skip
    r2v = Spec(
        K, "wan/2-6-flash-video-to-video",
        keep=("resolution", "multi_shots", "video_urls"),
        rename={"generate_audio": "audio"},
        convert={**common, "generate_audio": bool},
    )  # fmt: skip
    return {
        "wan/v2.6-flash/image-to-video": Route(
            K, "wan/2-6-flash-image-to-video", i2v, _flash_price("image-to-video")
        ),
        "wan/v2.6-flash/reference-to-video": Route(
            K, "wan/2-6-flash-video-to-video", r2v, _flash_price("video-to-video")
        ),
    }


def _no_seed(value: Any) -> Any:
    if value not in (None, -1):
        raise unsupported(K, "a fixed seed cannot be reproduced on KIE for this model")
    return None


def _edit_seconds(i: dict, h: dict) -> float | None:
    return i["duration"] if i.get("duration") else video_seconds(h)


def _edit_check(provider: str):
    def check(source: dict, hints: dict) -> None:
        seconds = video_seconds(hints)
        if seconds is not None and not 2 <= seconds <= 10.5:
            raise unsupported(provider, f"{provider} edits source videos of 2 to 10 s")
        if seconds is not None and source.get("duration") and source["duration"] > seconds + 0.5:
            raise unsupported(provider, "duration cannot be longer than the source video")

    return check


def _edit_duration(provider: str):
    def check(value: Any) -> Any:
        if value == 1:
            raise unsupported(provider, "duration must be 0 or 2 to 10 seconds")
        return value

    return check


def _kie_edit() -> dict[str, Route]:
    def reference(value: Any) -> Any:
        if not value:
            return None
        if len(value) > 1:
            raise unsupported(K, "KIE takes one reference image for Wan 2.7 video edit")
        return value[0]

    name = "wan/2-7-videoedit"
    spec = Spec(
        K, name,
        keep=("prompt", "video_url", "resolution", "aspect_ratio", "audio_setting", "prompt_extend"),
        rename={"image_urls": "reference_image"},
        convert={"image_urls": reference, "seed": _seed, "negative_prompt": _empty, "duration": _edit_duration(K)},
        fixed={"watermark": False},
    )  # fmt: skip
    return {
        "wan/v2.7/video-edit": Route(
            K,
            name,
            spec,
            lambda i, h, p: per_second(
                p, f"wan 2.7 video, videoedit, {i.get('resolution', '1080p')}", _edit_seconds(i, h)
            ),
            notes=("Billed per second of output (the source length when duration is 0)",),
            check=_edit_check(K),
        )
    }


def kie() -> dict[str, Route]:
    return {**_kie_turbo(), **_kie_animate(), **_kie_wan25(), **_kie_flash(), **_kie_edit()}


# --- APIMart --------------------------------------------------------------------------------------

A = "apimart"


def _res_key(model_id: str, res: str, default_720: bool = False) -> str:
    res = res.upper()
    return f"{model_id}|default" if default_720 and res == "720P" else f"{model_id}|{res}"


def _apimart_wan25() -> dict[str, Route]:
    def ratios(source: dict, out: dict) -> dict:
        if source.get("resolution") == "480p" and out.get("size") in ("4:3", "3:4"):
            raise unsupported(A, "APIMart has no 4:3 or 3:4 at 480p")
        return out

    common = {"seed": _seed, "negative_prompt": _empty}
    keep = ("prompt", "duration", "resolution", "prompt_extend", "audio_url")
    price = lambda i, h, p: per_second(
        p, _res_key("wan2.5-preview", i.get("resolution", "720p")), i.get("duration")
    )
    return {
        "wan/v2.5/text-to-video": Route(
            A, "wan2.5-preview",
            Spec(A, "wan2.5-preview", keep=keep, rename={"aspect_ratio": "size"}, convert=common, build=ratios),
            price,
        ),
        "wan/v2.5/image-to-video": Route(
            A, "wan2.5-preview",
            Spec(A, "wan2.5-preview", keep=keep, rename={"image_url": "image_urls"},
                 convert={**common, "image_url": _one}),
            price,
        ),
    }  # fmt: skip


def _apimart_flash() -> dict[str, Route]:
    def build(source: dict, out: dict) -> dict:
        if source.get("audio_url") and not source.get("generate_audio", True):
            raise unsupported(A, "audio_url needs generate_audio on APIMart (silent output ignores it)")
        if source.get("multi_shots") and not source.get("prompt_extend"):
            raise unsupported(A, "APIMart only makes multiple shots with prompt_extend on")
        return out

    def price(i: dict, h: dict, p: dict) -> float | None:
        suffix = "-audio" if i.get("generate_audio", True) else ""
        res = str(i.get("resolution", "1080p")).upper()
        return per_second(p, f"wan2.6-i2v-flash|{res}{suffix}", i.get("duration"))

    name = "wan2.6-i2v-flash"
    spec = Spec(
        A, name,
        keep=("prompt", "duration", "resolution", "prompt_extend", "audio_url"),
        rename={"image_url": "image_urls", "generate_audio": "audio", "multi_shots": "shot_type"},
        convert={"image_url": _one, "generate_audio": bool, "multi_shots": lambda v: "multi" if v else "single",
                 "seed": _seed, "negative_prompt": _empty},
        build=build,
    )  # fmt: skip
    return {"wan/v2.6-flash/image-to-video": Route(A, name, spec, price)}


def _apimart_edit() -> dict[str, Route]:
    def build(source: dict, out: dict) -> dict:
        setting = out.pop("audio_setting", None)
        if setting:
            out["metadata"] = {"audio_setting": setting}
        return out

    name = "wan2.7-videoedit"
    spec = Spec(
        A, name,
        keep=("prompt", "image_urls", "prompt_extend", "audio_setting"),
        rename={"video_url": "video_urls", "aspect_ratio": "size"},
        convert={"video_url": _one, "resolution": upper, "seed": _seed, "negative_prompt": _empty,
                 "duration": _edit_duration(A), "image_urls": _empty},
        build=build,
    )  # fmt: skip
    return {
        "wan/v2.7/video-edit": Route(
            A,
            name,
            spec,
            lambda i, h, p: per_second(
                p, _res_key(name, i.get("resolution", "1080p"), default_720=True), _edit_seconds(i, h)
            ),
            notes=("Billed per second of output (the source length when duration is 0)",),
            check=_edit_check(A),
        )
    }


def apimart() -> dict[str, Route]:
    return {**_apimart_wan25(), **_apimart_flash(), **_apimart_edit()}
