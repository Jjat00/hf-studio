"""Modelos del catálogo que APIMart ofrece, con su traducción y su precio.

Fuente: docs.apimart.ai (páginas `.md`) y la tabla pública de precios, revisadas el 2026-10-03. Las claves
de precio son `modelo|clave` (`apimart.parse_prices`), en USD por segundo salvo que se diga otra cosa.
APIMart apaga por defecto el audio de Kling y PixVerse y usa 1080P por defecto en Wan y HappyHorse: por eso
la entrada llega completa (`routes.with_defaults`) y se envía todo explícito.
"""

from __future__ import annotations

from typing import Any

from .routes import (
    Route,
    Routes,
    Spec,
    kling_elements,
    only_default,
    per_second,
    per_unit,
    unsupported,
    video_seconds,
)

P = "apimart"


def _upper(value: str) -> str:
    return value.upper()


def _no_list(field_name: str):
    def check(value):
        if value:
            raise unsupported(P, f"{field_name} has no equivalent on APIMart")

    return check


def _res_price(model: str, default_key: str | None = None):
    """`modelo|RES` por segundo de salida; `default_key` para tablas cuya fila 720p se llama `default`."""

    def price(i: dict, hints: dict, prices: dict) -> float | None:
        res = str(i.get("resolution", "720p")).upper()
        key = f"{model}|{res}"
        if key not in prices and default_key and res == "720P":
            key = f"{model}|{default_key}"
        return per_second(prices, key, i.get("duration"))

    return price


def _frames(source: dict, out: dict) -> dict:
    """Primer y último fotograma como `image_with_roles` (Seedance, Wan 3.0)."""
    roles = [{"url": source["image_url"], "role": "first_frame"}]
    if source.get("end_image_url"):
        roles.append({"url": source["end_image_url"], "role": "last_frame"})
    out["image_with_roles"] = roles
    out.pop("image_url", None)
    out.pop("end_image_url", None)
    return out


# --- Seedance ------------------------------------------------------------------------------------


def _seedance_price(model: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        res = str(i.get("resolution", "720p")).upper()
        if i.get("video_urls") or i.get("video_url"):
            seconds = video_seconds(hints)
            if seconds is None:
                return None
            output = seconds if i.get("duration", -1) == -1 else i["duration"]
            return per_second(prices, f"{model}|{res}-input", seconds + output)
        return per_second(prices, f"{model}|{res}", i.get("duration"))

    return price


def _seedance_reserve(model: str):
    """`duration=-1` retiene 30 s de salida al enviar (docs de Seedance 2.5, «Billing») y luego liquida."""

    def reserve(i: dict, hints: dict, prices: dict) -> float | None:
        if i.get("duration", -1) != -1 or not (i.get("video_urls") or i.get("video_url")):
            return None
        seconds = video_seconds(hints)
        res = str(i.get("resolution", "720p")).upper()
        return None if seconds is None else per_second(prices, f"{model}|{res}-input", min(seconds, 30) + 30)

    return reserve


def _videos_first(source: dict, out: dict) -> dict:
    videos = [source["video_url"], *(source.get("video_urls") or [])]
    if len(videos) > 10:
        raise unsupported(P, "APIMart accepts at most 10 videos")
    out["video_urls"] = videos
    out.pop("video_url", None)
    return out


def seedance() -> dict[str, Route]:
    routes = {}
    keep = ("prompt", "duration", "resolution", "generate_audio")
    for version in ("2.0", "2.5"):
        model = f"seedance-{version}"
        drop = {"bitrate_mode"} if version == "2.5" else set()
        notes = ("bitrate_mode is not available on APIMart; its default bitrate is used",) if drop else ()
        price = _seedance_price(model)
        later = version == "2.5"  # 2.5 se liquida por tokens tras generar
        t2v_keep = (*keep, "output_format") if version == "2.5" else keep
        routes[f"bytedance/seedance-{version}/text-to-video"] = Route(
            P,
            model,
            Spec(P, model, keep=t2v_keep, rename={"aspect_ratio": "size"}, drop=drop),
            price,
            notes=notes,
        )
        routes[f"bytedance/seedance-{version}/image-to-video"] = Route(
            P, model,
            Spec(P, model, keep=(*keep, "image_url", "end_image_url"), drop=drop, fixed={"size": "adaptive"},
                 build=_frames),
            price, notes=notes, settles_later=later,
        )  # fmt: skip
        fixed = {"omni_reference_task_type": "reference"} if version == "2.5" else {}
        routes[f"bytedance/seedance-{version}/reference-to-video"] = Route(
            P, model,
            Spec(P, model, keep=(*keep, "image_urls", "video_urls", "audio_urls"), rename={"aspect_ratio": "size"},
                 drop=drop, fixed=fixed),
            price, notes=notes, settles_later=later,
        )  # fmt: skip
    edit_keep = (
        "prompt",
        "resolution",
        "generate_audio",
        "video_url",
        "video_urls",
        "image_urls",
        "audio_urls",
    )
    routes["bytedance/seedance-2.5/video-edit"] = Route(
        P, "seedance-2.5",
        Spec(P, "seedance-2.5", keep=edit_keep, drop={"bitrate_mode"}, build=_videos_first,
             fixed={"omni_reference_task_type": "edit", "duration": -1, "size": "adaptive"}),
        _seedance_price("seedance-2.5"),
        notes=("APIMart infers edit from the prompt; a prompt that does not read as an edit fails (refunded)",
               "APIMart first holds 30 s of output and refunds the difference after generating"),
        reserve=_seedance_reserve("seedance-2.5"), settles_later=True,
    )  # fmt: skip
    routes["bytedance/seedance-2.5/video-extend"] = Route(
        P, "seedance-2.5",
        Spec(P, "seedance-2.5", keep=(*edit_keep, "duration"), drop={"bitrate_mode"}, build=_videos_first,
             fixed={"omni_reference_task_type": "extend", "size": "adaptive"}),
        _seedance_price("seedance-2.5"),
        notes=("APIMart infers extend from the prompt; a prompt that does not read as an extension fails (refunded)",),
        settles_later=True,
    )  # fmt: skip
    return routes


# --- Kling 3.0 ----------------------------------------------------------------------------------


def _kling_build(image: bool):
    def build(source: dict, out: dict) -> dict:
        multi = bool(source.get("multi_shots"))
        shots = source.get("multi_prompt") or []
        out["multi_shot"] = multi
        out.pop("multi_prompt", None)
        if multi:
            out["shot_type"] = "customize" if shots else "intelligence"
            if shots:
                out["multi_prompt"] = [{"index": n, **shot} for n, shot in enumerate(shots, 1)]
        elif not source.get("prompt"):
            raise unsupported(P, "APIMart requires a prompt")
        if image:
            urls = [source["image_url"]]
            if source.get("last_image_url"):
                urls.append(source["last_image_url"])
            out["image_urls"] = urls
            out.pop("image_url", None)
            out.pop("last_image_url", None)
        return out

    return build


def _kling_price(tier: str):
    keys = {"std": ("default", "sound"), "pro": ("pro", "pro-sound"), "4k": ("4k", "4k-sound")}[tier]

    def price(i: dict, hints: dict, prices: dict) -> float | None:
        key = keys[1] if i.get("sound", "on") == "on" else keys[0]
        return per_second(prices, f"kling-v3|{key}", i.get("duration"))

    return price


def kling() -> dict[str, Route]:
    routes = {}
    for tier, mode in (("std", "std"), ("pro", "pro"), ("4k", "4k")):
        for kind in ("text-to-video", "image-to-video"):
            image = kind == "image-to-video"
            spec = Spec(
                P, "kling-v3",
                keep=("prompt", "duration", "aspect_ratio", "multi_prompt", "image_url", "last_image_url"),
                rename={"sound": "audio", "elements": "element_list"},
                convert={"sound": lambda v: v == "on", "cfg_scale": only_default("cfg_scale", 0.5),
                         "elements": kling_elements(P), "multi_shots": lambda v: None},
                fixed={"mode": mode}, build=_kling_build(image),
            )  # fmt: skip
            routes[f"kling-video/v3.0/{tier}/{kind}"] = Route(P, "kling-v3", spec, _kling_price(tier))
    turbo = _res_price("kling-3.0-turbo")
    routes["kling-video/v3.0-turbo/text-to-video"] = Route(
        P, "kling-3.0-turbo", Spec(P, "kling-3.0-turbo"), turbo,
        notes=("APIMart documents no audio switch for Kling 3.0 Turbo",),
    )  # fmt: skip
    routes["kling-video/v3.0-turbo/image-to-video"] = Route(
        P, "kling-3.0-turbo", Spec(P, "kling-3.0-turbo", rename={"image_url": "first_frame_image"}), turbo,
        notes=("APIMart documents no audio switch for Kling 3.0 Turbo",),
    )  # fmt: skip
    for tier, key in (("std", "default"), ("pro", "pro")):
        routes[f"kling-video/v3/motion-control/{tier}"] = Route(
            P, "kling-v3-motion-control",
            Spec(P, "kling-v3-motion-control",
                 keep=("prompt", "image_url", "video_url", "keep_original_sound", "character_orientation"),
                 fixed={"mode": tier, "watermark_info": {"enabled": False}}),
            lambda i, h, p, k=key: per_second(p, f"kling-v3-motion-control|{k}", video_seconds(h)),
            notes=("Billed by the length of the motion video",),
        )  # fmt: skip
    return routes


# --- Wan ----------------------------------------------------------------------------------------


def wan() -> dict[str, Route]:
    routes = {}
    seed = {"seed": lambda v: v if v >= 0 else None}
    shot = {"multi_shots": lambda v: "multi" if v else "single"}
    routes["wan/v2.6/text-to-video"] = Route(
        P, "wan2.6",
        Spec(P, "wan2.6", keep=("prompt", "duration", "resolution", "audio_url", "prompt_extend"),
             rename={"multi_shots": "shot_type"}, convert={**seed, **shot}),
        _res_price("wan2.6", "default"),
    )  # fmt: skip
    routes["wan/v2.6/image-to-video"] = Route(
        P, "wan2.6",
        Spec(P, "wan2.6", keep=("prompt", "duration", "resolution", "audio_url", "prompt_extend", "negative_prompt"),
             rename={"multi_shots": "shot_type", "image_url": "image_urls"},
             convert={**seed, **shot, "image_url": lambda v: [v],
                      "negative_prompt": lambda v: v or None},
             allowed={"resolution": {"720p", "1080p"}}),
        _res_price("wan2.6", "default"),
        notes=("APIMart may bill image-to-video under wan2.6-i2v (unverified)",),
    )  # fmt: skip
    wan27 = {"resolution": _upper, "negative_prompt": lambda v: v or None}
    routes["wan/v2.7/text-to-video"] = Route(
        P, "wan2.7",
        Spec(P, "wan2.7", keep=("prompt", "duration", "seed", "prompt_extend", "audio_url"),
             rename={"aspect_ratio": "size"}, convert=wan27),
        _res_price("wan2.7", "default"),
    )  # fmt: skip

    def i2v_images(source: dict, out: dict) -> dict:
        out["image_urls"] = [u for u in (source.get("image_url"), source.get("end_image_url")) if u]
        out.pop("image_url", None)
        out.pop("end_image_url", None)
        return out

    routes["wan/v2.7/image-to-video"] = Route(
        P, "wan2.7",
        Spec(P, "wan2.7", keep=("prompt", "duration", "seed", "prompt_extend", "image_url", "end_image_url"),
             convert={**wan27, "audio_url": _no_list("audio_url")}, build=i2v_images),
        _res_price("wan2.7", "default"),
        notes=("audio_url with an image is not offered: APIMart's docs contradict themselves on it",),
    )  # fmt: skip

    def r2v(source: dict, out: dict) -> dict:
        images = source.get("image_urls") or []
        count = len(images) + len(source.get("video_urls") or [])
        if not 1 <= count <= 5:
            raise unsupported(P, "APIMart needs 1 to 5 reference images and videos in total")
        if images:
            out["image_with_roles"] = [{"url": u, "role": "reference_image"} for u in images]
        out.pop("image_urls", None)
        return out

    routes["wan/v2.7/reference-to-video"] = Route(
        P, "wan2.7-r2v",
        Spec(P, "wan2.7-r2v", keep=("prompt", "duration", "seed", "prompt_extend", "image_urls", "video_urls"),
             rename={"aspect_ratio": "size"}, convert=wan27, build=r2v),
        _res_price("wan2.7-r2v", "default"),
    )  # fmt: skip
    for variant, model in (("wan-3.0", "wan3.0-video"), ("wan-3.0-prime", "wan3.0-video-prime")):
        convert = {"resolution": _upper, "enable_thinking": only_default("enable_thinking", False)}
        rename = {"aspect_ratio": "size", "generate_audio": "audio"}
        price = _res_price(model)
        routes[f"alibaba/{variant}/text-to-video"] = Route(
            P,
            model,
            Spec(P, model, keep=("prompt", "duration", "seed"), rename=rename, convert=convert),
            price,
        )
        routes[f"alibaba/{variant}/image-to-video"] = Route(
            P, model,
            Spec(P, model, keep=("prompt", "duration", "seed", "image_url", "end_image_url"), rename=rename,
                 convert=convert, build=_frames),
            price,
        )  # fmt: skip

        def refs(source: dict, out: dict) -> dict:
            if source.get("file_url") and source.get("link_url"):
                raise unsupported(P, "APIMart takes file_url or link_url, not both")
            return out

        routes[f"alibaba/{variant}/reference-to-video"] = Route(
            P, model,
            Spec(P, model,
                 keep=("prompt", "duration", "seed", "image_urls", "video_urls", "audio_urls", "file_url", "link_url"),
                 rename=rename, convert=convert, fixed={"generation_type": "reference"}, build=refs),
            price,
        )  # fmt: skip
    return routes


# --- HappyHorse, MiniMax, Hailuo, Grok, PixVerse ----------------------------------------------------


def others() -> Routes:
    routes = {}
    for version, model in (("", "happyhorse-1.0"), ("v1.1/", "happyhorse-1.1")):
        price = _res_price(model)
        common: dict[str, Any] = {"convert": {"resolution": _upper}, "allowed": {"duration": range(3, 16)}}
        routes[f"alibaba/happy-horse/{version}text-to-video"] = Route(
            P,
            model,
            Spec(P, model, keep=("prompt", "duration", "seed"), rename={"aspect_ratio": "size"}, **common),
            price,
        )
        routes[f"alibaba/happy-horse/{version}image-to-video"] = Route(
            P, model, Spec(P, model, keep=("prompt", "duration", "seed"), rename={"image_url": "first_frame_image"}, **common),
            price,
        )  # fmt: skip

        def refs(source: dict, out: dict) -> dict:
            if not 1 <= len(source.get("image_urls") or []) <= 9:
                raise unsupported(P, "APIMart needs 1 to 9 reference images")
            return out

        routes[f"alibaba/happy-horse/{version}reference-to-video"] = Route(
            P,
            model,
            Spec(P, model, keep=("prompt", "duration", "seed", "image_urls"), build=refs, **common),
            price,
        )

    def h3_price(i: dict, hints: dict, prices: dict) -> float | None:
        base = per_second(prices, "MiniMax-H3|2K", i.get("duration"))
        if base is None:
            return None
        if i.get("video_urls"):
            seconds = video_seconds(hints)
            if seconds is None:
                return None
            base += per_second(prices, "MiniMax-H3|input:video:2K", min(seconds, 15)) or 0.0
        images = len(i.get("image_urls") or [])
        if images > 5:
            base += per_unit(prices, "MiniMax-H3|input:image", images - 5) or 0.0
        return round(base, 4)

    explicit = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
    routes["minimax/h3/text-to-video"] = Route(
        P, "MiniMax-H3",
        Spec(P, "MiniMax-H3", rename={"aigc_watermark": "watermark"}, allowed={"aspect_ratio": explicit}),
        h3_price,
    )  # fmt: skip
    routes["minimax/h3/image-to-video"] = Route(
        P, "MiniMax-H3",
        Spec(P, "MiniMax-H3", keep=("prompt", "duration", "resolution"),
             rename={"aigc_watermark": "watermark", "image_url": "first_frame_image", "end_image_url": "last_frame_image"},
             convert={"aspect_ratio": lambda v: None}, allowed={"aspect_ratio": {"auto", "adaptive"}}),
        h3_price,
    )  # fmt: skip
    routes["minimax/h3/reference-to-video"] = Route(
        P, "MiniMax-H3",
        Spec(P, "MiniMax-H3", keep=("prompt", "duration", "resolution", "image_urls", "video_urls", "audio_urls"),
             rename={"aigc_watermark": "watermark"},
             convert={"aspect_ratio": lambda v: "adaptive" if v == "auto" else v}),
        h3_price,
    )  # fmt: skip
    hailuo = lambda i, h, p: per_second(p, "MiniMax-Hailuo-2.3|default", i.get("duration"))
    routes["minimax/hailuo-2.3/standard/text-to-video"] = Route(
        P, "MiniMax-Hailuo-2.3",
        Spec(P, "MiniMax-Hailuo-2.3", keep=("prompt", "duration", "prompt_optimizer"), fixed={"resolution": "768P"}),
        hailuo,
    )  # fmt: skip
    routes["minimax/hailuo-2.3/standard/image-to-video"] = Route(
        P, "MiniMax-Hailuo-2.3",
        Spec(P, "MiniMax-Hailuo-2.3", keep=("prompt", "duration", "prompt_optimizer"),
             rename={"image_url": "first_frame_image"}, fixed={"resolution": "768P"}),
        hailuo,
    )  # fmt: skip

    def grok(source: dict, out: dict) -> dict:
        images = [u for u in [source.get("image_url"), *(source.get("image_urls") or [])] if u]
        if images:
            out["image_urls"] = images
        out.pop("image_url", None)
        return out

    def grok_price(i: dict, h: dict, p: dict) -> float | None:
        base = per_second(
            p, f"grok-imagine-video-1.5|{str(i.get('resolution', '480p')).upper()}", i.get("duration")
        )
        images = len([u for u in [i.get("image_url"), *(i.get("image_urls") or [])] if u])
        extra = per_unit(p, "grok-imagine-video-1.5|input:image", images) or 0.0
        return None if base is None else round(base + extra, 4)

    def grok_ext(source: dict, out: dict) -> dict:
        """Canal no oficial (docs «Grok Imagine 1.5 Video Generation»): con imágenes el formato sale de la
        imagen, sin ellas `size` es explícito y su valor por defecto (16:9) no equivale a `auto`."""
        out = grok(source, out)
        ratio = out.pop("aspect_ratio", "auto")
        if len(out.get("image_urls") or []) > 7:
            raise unsupported(P, "APIMart's ext channel accepts at most 7 images")
        if out.get("image_urls"):
            if ratio != "auto":
                raise unsupported(P, "APIMart's ext channel takes the aspect ratio from the image")
        elif ratio == "auto":
            raise unsupported(P, "APIMart's ext channel needs an explicit aspect ratio without images")
        else:
            out["size"] = ratio
        return out

    ext = "grok-imagine-1.5-video-ext"
    routes["xai/grok-imagine-video/v1.5/reference-to-video"] = (
        Route(
            P, "grok-imagine-video-1.5",
            Spec(P, "grok-imagine-video-1.5", keep=("prompt", "duration", "resolution", "aspect_ratio", "image_url",
                                                     "image_urls"),
                 convert={"audio_url": _no_list("audio_url")}, build=grok),
            grok_price,
        ),
        # La tabla lo lista como `grok-imagine-1.5-video-apimart` (alias `-ext`); se envía con el alias.
        Route(
            P, ext,
            Spec(P, ext, keep=("prompt", "duration", "resolution", "aspect_ratio", "image_url", "image_urls"),
                 convert={"audio_url": _no_list("audio_url")},
                 allowed={"duration": range(6, 16), "resolution": {"480p", "720p"},
                          "aspect_ratio": {"auto", "16:9", "9:16", "1:1", "3:2", "2:3"}},
                 build=grok_ext),
            _res_price("grok-imagine-1.5-video-apimart"),
            official=False,
            notes=("Unofficial APIMart channel: much cheaper, may be less stable",),
        ),
    )  # fmt: skip

    def pixverse_price(i: dict, h: dict, p: dict) -> float | None:
        res = str(i.get("resolution", "720p")).upper()
        return per_second(
            p, f"pixverse-v6|{res}{'-audio' if i.get('generate_audio', True) else ''}", i.get("duration")
        )

    def pixverse_frames(source: dict, out: dict) -> dict:
        if source.get("end_image_url"):
            if source.get("duration") not in (5, 8):
                raise unsupported(P, "APIMart's first-last frame mode only allows 5 or 8 seconds")
            out["first_frame_image"] = source["image_url"]
            out["last_frame_image"] = source["end_image_url"]
        else:
            out["image_urls"] = [source["image_url"]]
        out.pop("image_url", None)
        out.pop("end_image_url", None)
        return out

    pix = {
        "keep": ("prompt", "duration", "resolution", "seed", "negative_prompt"),
        "rename": {"generate_audio": "audio"},
    }
    routes["pixverse/v6/text-to-video"] = Route(
        P, "pixverse-v6", Spec(P, "pixverse-v6", keep=pix["keep"], rename={**pix["rename"], "aspect_ratio": "size"}),
        pixverse_price,
    )  # fmt: skip
    routes["pixverse/v6/image-to-video"] = Route(
        P, "pixverse-v6",
        Spec(P, "pixverse-v6", keep=(*pix["keep"], "image_url", "end_image_url"), rename=pix["rename"],
             build=pixverse_frames),
        pixverse_price,
    )  # fmt: skip
    return routes


def apimart_routes() -> Routes:
    return {**seedance(), **kling(), **wan(), **others()}
