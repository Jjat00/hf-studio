"""Modelos del catálogo que KIE ofrece, con su traducción y su precio.

Fuente: el endpoint de esquema de KIE (`GET /api/v1/models/{model}/schema`) y su tabla pública de
precios, revisados el 2026-10-03. Las claves de precio son `modelDescription` normalizado
(`kie.price_key`) y el valor es USD por unidad (créditos × 0,005).
"""

from __future__ import annotations

from typing import Any

from .routes import Route, Spec, only_default, per_second, per_unit, unsupported, video_seconds

P = "kie"


def _str(value: Any) -> str:
    return str(value)


def _upper_p(value: str) -> str:
    return value.upper() if value.endswith("p") else value


def _no_list(field_name: str):
    def check(value):
        if value:
            raise unsupported(P, f"{field_name} has no equivalent on KIE")

    return check


def _need_prompt(source: dict, out: dict) -> dict:
    if not source.get("prompt"):
        raise unsupported(P, "KIE requires a prompt for this model")
    return out


# --- Seedance 2.0 y 2.5 -------------------------------------------------------------------------

SEEDANCE_REFS = {"image_urls": "reference_image_urls", "video_urls": "reference_video_urls",
                 "audio_urls": "reference_audio_urls"}  # fmt: skip
SEEDANCE_FRAMES = {"image_url": "first_frame_url", "end_image_url": "last_frame_url"}


def _seedance_price(row: str, with_video: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        res = i.get("resolution", "720p")
        if i.get("video_urls") or i.get("video_url"):
            seconds = video_seconds(hints)
            if seconds is None:
                return None
            output = seconds if i.get("duration", -1) == -1 else i["duration"]
            return per_second(prices, f"{row}, {res} {with_video}", seconds + output)
        return per_second(prices, f"{row}, {res} {'no video input' if row.endswith('-2') else 'no video'}",
                          i.get("duration"))  # fmt: skip

    return price


def _edit_build(source: dict, out: dict) -> dict:
    out["reference_video_urls"] = [source["video_url"], *(source.get("video_urls") or [])]
    out.pop("video_url", None)
    out.pop("video_urls", None)
    if len(out["reference_video_urls"]) > 10:
        raise unsupported(P, "KIE accepts at most 10 reference videos")
    return out


def seedance() -> dict[str, Route]:
    routes = {}
    keep = ("prompt", "duration", "resolution", "aspect_ratio", "generate_audio")
    for version, model in (("2.0", "bytedance/seedance-2"), ("2.5", "bytedance/seedance-2-5")):
        base = f"bytedance/seedance-{version}"
        price = _seedance_price(model, "with video input" if version == "2.0" else "with video")
        drop = {"bitrate_mode"} if version == "2.5" else set()
        notes = ("bitrate_mode is not available on KIE; KIE's default bitrate is used",) if drop else ()
        keep_t2v = (*keep, "output_format") if version == "2.5" else keep
        routes[f"{base}/text-to-video"] = Route(
            P, model, Spec(P, model, keep=keep_t2v, drop=drop), price, notes=notes
        )
        routes[f"{base}/image-to-video"] = Route(
            P, model, Spec(P, model, keep=keep, rename=SEEDANCE_FRAMES, drop=drop, fixed={"aspect_ratio": "adaptive"}),
            price, notes=notes,
        )  # fmt: skip
        routes[f"{base}/reference-to-video"] = Route(
            P, model, Spec(P, model, keep=keep, rename=SEEDANCE_REFS, drop=drop), price, notes=notes
        )
    edit_keep = ("prompt", "resolution", "generate_audio", "video_url")
    edit_refs = {"image_urls": "reference_image_urls", "audio_urls": "reference_audio_urls"}
    routes["bytedance/seedance-2.5/video-edit"] = Route(
        P, "bytedance/seedance-2-5",
        Spec(P, "bytedance/seedance-2-5", keep=(*edit_keep, "video_urls"), rename=edit_refs,
             drop={"bitrate_mode"}, fixed={"duration": -1}, build=_edit_build),
        _seedance_price("bytedance/seedance-2-5", "with video"),
        notes=("KIE has no explicit edit mode: the clip goes as reference video 1 and the prompt says what to change",),
    )  # fmt: skip
    routes["bytedance/seedance-2.5/video-extend"] = Route(
        P, "bytedance/seedance-2-5",
        Spec(P, "bytedance/seedance-2-5", keep=(*edit_keep, "video_urls", "duration"), rename=edit_refs,
             drop={"bitrate_mode"}, build=_edit_build),
        _seedance_price("bytedance/seedance-2-5", "with video"),
        notes=("KIE has no explicit extend mode: the clip goes as reference video 1",),
    )  # fmt: skip
    return routes


# --- Kling 3.0 ----------------------------------------------------------------------------------


def _kling_build(image: bool):
    def build(source: dict, out: dict) -> dict:
        shots = source.get("multi_prompt") or []
        if len(shots) > 5:
            raise unsupported(P, "KIE allows at most 5 shots")
        out["multi_shots"] = bool(source.get("multi_shots"))
        out["multi_prompt"] = shots
        if not out["multi_shots"] and not source.get("prompt"):
            raise unsupported(P, "KIE requires a prompt")
        if image:
            urls = [source["image_url"]]
            if source.get("last_image_url"):
                if out["multi_shots"]:
                    raise unsupported(P, "KIE takes no last frame in multi-shot mode")
                urls.append(source["last_image_url"])
            out["image_urls"] = urls
            out.pop("image_url", None)
            out.pop("last_image_url", None)
        return out

    return build


def _kling_price(tier: str):
    def price(i: dict, hints: dict, prices: dict) -> float | None:
        audio = "with audio" if i.get("sound", "on") == "on" else "without audio"
        return per_second(prices, f"kling 3.0, video, {audio}-{tier}", i.get("duration"))

    return price


def kling() -> dict[str, Route]:
    routes = {}
    for tier, mode, res in (("std", "std", "720p"), ("pro", "pro", "1080p"), ("4k", "4K", "4k")):
        for kind in ("text-to-video", "image-to-video"):
            image = kind == "image-to-video"
            spec = Spec(
                P, "kling-3.0/video",
                keep=("prompt", "aspect_ratio", "multi_shots", "multi_prompt", "image_url", "last_image_url"),
                convert={"sound": lambda v: v == "on", "duration": _str, "cfg_scale": only_default("cfg_scale", 0.5),
                         "elements": _no_list("elements")},
                drop=(), fixed={"mode": mode, **({"aspect_ratio": "16:9"} if image else {})},
                build=_kling_build(image),
            )  # fmt: skip
            routes[f"kling-video/v3.0/{tier}/{kind}"] = Route(P, "kling-3.0/video", (spec), _kling_price(res))
    for kind, model in (("text-to-video", "kling/v3-turbo-text-to-video"),
                        ("image-to-video", "kling/v3-turbo-image-to-video")):  # fmt: skip
        spec = Spec(P, model, convert={"duration": _str}, rename={"image_url": "image_urls"})
        spec.convert["image_url"] = lambda v: [v]
        routes[f"kling-video/v3.0-turbo/{kind}"] = Route(
            P, model, spec,
            lambda i, h, p, k=kind: per_second(p, f"kling 3.0 turbo, {k}, {i.get('resolution', '720p')}", i.get("duration")),
        )  # fmt: skip
    for tier, mode in (("std", "720p"), ("pro", "1080p")):
        spec = Spec(
            P, "kling-3.0/motion-control",
            keep=("prompt", "character_orientation"),
            rename={"image_url": "input_urls", "video_url": "video_urls"},
            convert={"image_url": lambda v: [v], "video_url": lambda v: [v],
                     "keep_original_sound": only_default("keep_original_sound", "yes")},
            fixed={"mode": mode, "background_source": "input_video"},
        )  # fmt: skip
        routes[f"kling-video/v3/motion-control/{tier}"] = Route(
            P, "kling-3.0/motion-control", (spec),
            lambda i, h, p, m=mode: per_second(p, f"kling 3.0 motion control, video-to-video, {m}", video_seconds(h)),
            notes=("Billed by the length of the motion video",),
        )  # fmt: skip
    return routes


# --- Wan ----------------------------------------------------------------------------------------


def wan() -> dict[str, Route]:
    routes = {}
    # 2.6: precio por video según duración y resolución.
    for kind, model, label in (("text-to-video", "wan/2-6-text-to-video", "text to video"),
                               ("image-to-video", "wan/2-6-image-to-video", "image-to-video")):  # fmt: skip
        spec = Spec(
            P, model,
            keep=("prompt", "resolution", "multi_shots"),
            rename={"image_url": "image_urls"},
            convert={"duration": _str, "image_url": lambda v: [v], "seed": lambda v: None,
                     "audio_url": _no_list("audio_url"), "prompt_extend": only_default("prompt_extend", False),
                     "negative_prompt": only_default("negative_prompt", "")},
            allowed={"resolution": {"720p", "1080p"}},
        )  # fmt: skip
        routes[f"wan/v2.6/{kind}"] = Route(
            P, model, (spec),
            lambda i, h, p, lb=label: per_unit(p, f"wan 2.6, {lb}, {i.get('duration', 5)}.0s-{i.get('resolution', '720p')}"),
            notes=("seed is not available on KIE",),
        )  # fmt: skip
    # 2.7
    common = ("prompt", "duration", "resolution", "prompt_extend", "negative_prompt", "seed")
    routes["wan/v2.7/text-to-video"] = Route(
        P, "wan/2-7-text-to-video",
        Spec(P, "wan/2-7-text-to-video", keep=(*common, "audio_url"), rename={"aspect_ratio": "ratio"},
             fixed={"watermark": False}),
        lambda i, h, p: per_second(p, f"wan 2.7 video, text-to-video, {i.get('resolution', '720p')}", i.get("duration")),
    )  # fmt: skip
    routes["wan/v2.7/image-to-video"] = Route(
        P, "wan/2-7-image-to-video",
        Spec(P, "wan/2-7-image-to-video", keep=common,
             rename={"image_url": "first_frame_url", "end_image_url": "last_frame_url", "audio_url": "driving_audio_url"},
             fixed={"watermark": False}, build=_need_prompt),
        lambda i, h, p: per_second(p, f"wan 2.7 video, image-to-video, {i.get('resolution', '720p')}", i.get("duration")),
    )  # fmt: skip

    def r2v(source: dict, out: dict) -> dict:
        count = len(source.get("image_urls") or []) + len(source.get("video_urls") or [])
        if not 1 <= count <= 5:
            raise unsupported(P, "KIE needs 1 to 5 reference images and videos in total")
        return out

    routes["wan/v2.7/reference-to-video"] = Route(
        P, "wan/2-7-r2v",
        Spec(P, "wan/2-7-r2v", keep=(*common, "aspect_ratio"),
             rename={"image_urls": "reference_image", "video_urls": "reference_video"},
             fixed={"watermark": False}, build=r2v),
        lambda i, h, p: per_second(p, f"wan 2.7 video, r2v, {i.get('resolution', '720p')}", i.get("duration")),
    )  # fmt: skip
    # 3.0 y 3.0 prime: mismo modelo para t2v, i2v y referencias; se cobra también el video de entrada.
    for variant, model, row in (("wan-3.0", "wan/3-0-video", "wan 3.0 video"),
                                ("wan-3.0-prime", "wan/3-0-video-prime", "wan3.0 video prime")):  # fmt: skip

        def price(i: dict, h: dict, p: dict, row=row) -> float | None:
            seconds = i.get("duration")
            if i.get("video_urls"):
                extra = video_seconds(h)
                if extra is None:
                    return None
                seconds = seconds + extra
            return per_second(p, f"{row}, {i.get('resolution', '1080p')}, video", seconds)

        for kind in ("text-to-video", "image-to-video", "reference-to-video"):
            routes[f"alibaba/{variant}/{kind}"] = Route(P, model, _wan3_spec(model), price)
    return routes


def _wan3_spec(model: str) -> Spec:
    return Spec(
        P, model,
        keep=("prompt", "duration", "aspect_ratio", "seed"),
        rename={"generate_audio": "audio", "image_url": "first_frame_url", "end_image_url": "last_frame_url",
                "image_urls": "reference_image_urls", "video_urls": "reference_video_urls",
                "audio_urls": "reference_audio_urls", "file_url": "reference_file_urls", "link_url": "reference_link_urls"},
        convert={"resolution": _upper_p, "enable_thinking": only_default("enable_thinking", False),
                 "file_url": lambda v: [v], "link_url": lambda v: [v]},
    )  # fmt: skip


# --- HappyHorse, MiniMax, Hailuo, Grok, PixVerse ----------------------------------------------------


def others() -> dict[str, Route]:
    routes = {}
    for version, prefix, row, seed in (("", "happyhorse", "happyhorse-1.0", True),
                                       ("v1.1/", "happyhorse-1-1", "happyhorse-1.1", False)):  # fmt: skip
        for kind in ("text-to-video", "image-to-video", "reference-to-video"):
            model = f"{prefix}/{kind}"
            convert = {"image_url": lambda v: [v]}
            if not seed:
                convert["seed"] = lambda v: None
            spec = Spec(
                P, model, keep=("prompt", "duration", "resolution", "aspect_ratio", "seed"),
                rename={"image_url": "image_urls", "image_urls": "reference_image"}, convert=convert,
                allowed={"duration": range(3, 16)},
            )  # fmt: skip
            routes[f"alibaba/happy-horse/{version}{kind}"] = Route(
                P, model, (spec),
                lambda i, h, p, r=row, k=kind: per_second(p, f"{r}, {k}, {i.get('resolution', '720p')}", i.get("duration")),
            )  # fmt: skip

    def h3_price(kind: str):
        def price(i: dict, h: dict, p: dict) -> float | None:
            seconds = i.get("duration")
            extra = 0.0
            if i.get("video_urls"):
                video = video_seconds(h)
                if video is None:
                    return None
                seconds += video
            images = len(i.get("image_urls") or [])
            if images > 5:
                extra = per_unit(p, "minimax h3, image input, 768p, 2k", images - 5) or 0.0
            base = per_second(p, f"minimax h3, {kind}, 2k", seconds)
            return None if base is None else round(base + extra, 4)

        return price

    wm = {"aigc_watermark": only_default("aigc_watermark", False)}
    explicit = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
    routes["minimax/h3/text-to-video"] = Route(
        P, "minimax-h3/text-to-video",
        (Spec(P, "minimax-h3/text-to-video", convert=wm, allowed={"aspect_ratio": explicit})),
        h3_price("text to video"),
    )  # fmt: skip
    routes["minimax/h3/image-to-video"] = Route(
        P, "minimax-h3/image-to-video",
        (Spec(P, "minimax-h3/image-to-video", rename=SEEDANCE_FRAMES,
                         convert={**wm, "aspect_ratio": lambda v: None}, allowed={"aspect_ratio": {"auto", "adaptive"}})),
        h3_price("image to video"),
    )  # fmt: skip

    def h3_refs(source: dict, out: dict) -> dict:
        if not (source.get("image_urls") or source.get("video_urls")):
            raise unsupported(P, "KIE needs at least one reference image or video")
        return out

    routes["minimax/h3/reference-to-video"] = Route(
        P, "minimax-h3/reference-to-video",
        (Spec(P, "minimax-h3/reference-to-video", rename=SEEDANCE_REFS,
                         convert={**wm, "aspect_ratio": lambda v: "adaptive" if v == "auto" else v}, build=h3_refs)),
        h3_price("reference to video"),
    )  # fmt: skip
    routes["minimax/hailuo-2.3/standard/image-to-video"] = Route(
        P, "hailuo/2-3-image-to-video-standard",
        (Spec(P, "hailuo/2-3-image-to-video-standard", keep=("prompt", "image_url"),
                         convert={"duration": _str, "prompt_optimizer": only_default("prompt_optimizer", True)},
                         fixed={"resolution": "768P"})),
        lambda i, h, p: per_unit(p, f"hailuo 2.3, image-to-video, standard-{i.get('duration', 6)}.0s-768p"),
        notes=("KIE has no prompt_optimizer switch; its default is assumed to be on, as on Higgsfield",),
    )  # fmt: skip

    def grok(source: dict, out: dict) -> dict:
        images = [u for u in [source.get("image_url"), *(source.get("image_urls") or [])] if u]
        if not images:
            raise unsupported(P, "KIE's Grok 1.5 needs at least one image")
        if len(images) > 7:
            raise unsupported(P, "KIE accepts at most 7 images")
        out["image_urls"] = images
        out.pop("image_url", None)
        return out

    routes["xai/grok-imagine-video/v1.5/reference-to-video"] = Route(
        P, "grok-imagine-video-1-5-preview",
        Spec(P, "grok-imagine-video-1-5-preview", keep=("prompt", "duration", "resolution", "image_url", "image_urls"),
             convert={"audio_url": _no_list("audio_url")},
             allowed={"aspect_ratio": {"auto", "1:1", "16:9", "9:16", "3:2", "2:3"}}, build=grok),
        lambda i, h, p: per_second(p, f"grok-imagine-video-1-5-preview, image-to-video, {i.get('resolution', '480p')}",
                                   i.get("duration")),
        official=False,
    )  # fmt: skip

    def pixverse_price(i: dict, h: dict, p: dict) -> float | None:
        audio = "with audio" if i.get("generate_audio", True) else "no audio"
        res = i.get("resolution", "720p")
        key = f"pixverse-v6, text /image to video, {res} ({audio})"
        return per_second(p, key if key in p else key.replace(" (", "("), i.get("duration"))

    for kind in ("text-to-video", "image-to-video"):
        model = f"pixverse-v6/{kind}"
        routes[f"pixverse/v6/{kind}"] = Route(
            P, model,
            Spec(P, model, keep=("prompt", "duration", "aspect_ratio", "seed"),
                 rename={"resolution": "quality", "generate_audio": "generate_audio_switch", "image_url": "image_urls"},
                 convert={"image_url": lambda v: [v], "end_image_url": _no_list("end_image_url"),
                          "negative_prompt": _no_list("negative_prompt")},
                 fixed={"generate_multi_clip_switch": False}),
            pixverse_price,
        )  # fmt: skip
    return routes


def kie_routes() -> dict[str, Route]:
    return {**seedance(), **kling(), **wan(), **others()}
