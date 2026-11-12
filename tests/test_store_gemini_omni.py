"""Gemini Omni en las tiendas (`store/gemini_omni.py`): APIMart (canal ext) y KIE. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import gemini_omni as g

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"
ROUTES = {"apimart": g.apimart(), "kie": g.kie()}
T2V, I2V, REF = (
    f"google/gemini-omni-1.1-flash/{m}" for m in ("text-to-video", "image-to-video", "reference-to-video")
)


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def body(provider: str, model_id: str, **extra) -> dict:
    return ROUTES[provider][model_id].translate(logical(model_id, **extra))


def price(provider: str, model_id: str, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), {}, PRICES[provider])


def refused(provider: str, model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, model_id, **extra)
    assert info.value.kind == "unsupported"


def test_models_and_routes():
    ids = {m["id"] for m in g.MODELS if "/gemini-omni-1.2-flash/" not in m["id"]}
    assert ids == {
        T2V,
        I2V,
        REF,
        "google/gemini-omni-flash/text-to-video",
        "google/gemini-omni-flash/reference-to-video",
    }
    assert {k for k in ROUTES["kie"] if "/gemini-omni-1.2-flash/" not in k} == ids
    v11 = {k: r for k, r in ROUTES["apimart"].items() if "/gemini-omni-1.2-flash/" not in k}
    assert set(v11) == {T2V, I2V, REF}
    assert all(not r.official and r.model == "gemini-omni-1.1-flash-ext" for r in v11.values())


def test_apimart_ext_bodies_and_prices():
    assert body("apimart", T2V, duration=10, resolution="4k") == {
        "prompt": "a fox", "duration": 10, "aspect_ratio": "16:9", "resolution": "4k",
    }  # fmt: skip
    assert body("apimart", I2V, image_url=IMG) == {
        "prompt": "a fox", "duration": 8, "aspect_ratio": "16:9", "resolution": "720p",
        "image_urls": [IMG], "generation_type": "frame",
    }  # fmt: skip
    assert body("apimart", REF, image_urls=[IMG, IMG, END])["generation_type"] == "reference"
    assert price("apimart", T2V) == 0.35
    assert price("apimart", T2V, duration=4, resolution="360p") == 0.15
    # Sin último fotograma, 2 referencias ni semilla en el canal ext
    refused("apimart", I2V, image_url=IMG, end_image_url=END)
    refused("apimart", REF, image_urls=[IMG, END])
    refused("apimart", T2V, seed=5)


def test_kie_bodies_and_prices():
    assert body("kie", I2V, image_url=IMG, end_image_url=END, seed=5) == {
        "prompt": "a fox", "duration": "8", "aspect_ratio": "16:9", "resolution": "720p",
        "first_frame_url": IMG, "last_frame_url": END, "seed": 5,
    }  # fmt: skip
    assert body("kie", REF, image_urls=[IMG, END])["image_urls"] == [IMG, END]
    assert price("kie", T2V, duration=6, resolution="4k") == 0.84
    v1 = "google/gemini-omni-flash/text-to-video"
    assert ROUTES["kie"][v1].model == "gemini-omni-video"
    assert price("kie", v1) == 0.525


def test_fields_without_equivalent_are_refused():
    refused("kie", T2V, image_url=IMG)
    refused("kie", "google/gemini-omni-flash/reference-to-video", image_urls=[IMG], end_image_url=END)


# --- Gemini Omni 1.2 Flash (APIMart y KIE) ---------------------------------------------------------------

V12 = "google/gemini-omni-1.2-flash"
VID = "https://cdn.test/clip.mp4"


def test_v12_models_and_routes():
    ids = {m["id"] for m in g.MODELS if m["id"].startswith(V12) and m["id"] != g.V12_EXTEND}
    modes = ("text-to-video", "image-to-video", "reference-to-video", "video-edit")
    assert ids == {f"{V12}/{m}" for m in modes}
    assert ids <= set(ROUTES["apimart"]) and ids <= set(ROUTES["kie"])
    for mid in ids:
        route = ROUTES["apimart"][mid]
        assert route.model == "gemini-omni-1.2-flash" and route.official and route.settles_later
        kie = ROUTES["kie"][mid]
        assert kie.model == "google/gemini-omni-flash-1-2" and kie.official and not kie.settles_later


def test_v12_bodies():
    assert body("apimart", f"{V12}/text-to-video", duration=15, resolution="4k", aspect_ratio="9:16") == {
        "prompt": "a fox", "duration": 15, "aspect_ratio": "9:16", "resolution": "4k",
    }  # fmt: skip
    assert body("apimart", f"{V12}/image-to-video", image_url=IMG, end_image_url=END, duration=8) == {
        "prompt": "a fox", "duration": 8, "aspect_ratio": "16:9", "resolution": "720p",
        "first_frame_image": IMG, "last_frame_image": END,
    }  # fmt: skip
    ref = body("apimart", f"{V12}/reference-to-video", image_urls=[IMG, END])
    assert ref["image_urls"] == [IMG, END] and ref["omni_reference_task_type"] == "reference"
    assert body("apimart", f"{V12}/video-edit", video_url=VID) == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "720p",
        "video_urls": [VID], "omni_reference_task_type": "edit",
    }  # fmt: skip
    # Con último fotograma, como mucho 10 s
    refused("apimart", f"{V12}/image-to-video", image_url=IMG, end_image_url=END, duration=12)


def test_v12_prices_and_reserve():
    route = ROUTES["apimart"][f"{V12}/text-to-video"]
    assert price("apimart", f"{V12}/text-to-video") == 0.6  # 10 s × 0,06 a 720p
    assert price("apimart", f"{V12}/text-to-video", duration=4, resolution="4k") == 0.7232
    assert route.reserve(logical(f"{V12}/text-to-video", duration=4), {}, PRICES["apimart"]) == 0.6
    assert route.reserve(logical(f"{V12}/text-to-video", duration=15), {}, PRICES["apimart"]) == 0.9
    edit = ROUTES["apimart"][f"{V12}/video-edit"]
    entry = logical(f"{V12}/video-edit", video_url=VID)
    assert edit.price(entry, {}, PRICES["apimart"]) is None  # sin la duración del video de entrada
    assert edit.price(entry, {"input_video_seconds": 6}, PRICES["apimart"]) == 0.36
    assert edit.reserve(entry, {}, PRICES["apimart"]) == 0.9


def test_v12_kie_bodies():
    assert body("kie", f"{V12}/text-to-video", duration=15, resolution="4k", aspect_ratio="9:16") == {
        "prompt": "a fox", "duration": 15, "aspect_ratio": "9:16", "resolution": "4k",
    }  # fmt: skip
    assert body("kie", f"{V12}/image-to-video", image_url=IMG, end_image_url=END, duration=8) == {
        "prompt": "a fox", "duration": 8, "aspect_ratio": "16:9", "resolution": "720p",
        "first_frame_url": IMG, "last_frame_url": END,
    }  # fmt: skip
    assert body("kie", f"{V12}/reference-to-video", image_urls=[IMG] * 6)["image_urls"] == [IMG] * 6
    assert body("kie", f"{V12}/video-edit", video_url=VID) == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "720p", "video_list": [VID],
    }  # fmt: skip
    # KIE: como mucho 6 referencias y 10 s con último fotograma
    refused("kie", f"{V12}/reference-to-video", image_urls=[IMG] * 7)
    refused("kie", f"{V12}/image-to-video", image_url=IMG, end_image_url=END, duration=12)


def test_v12_kie_prices():
    assert price("kie", f"{V12}/text-to-video") == 0.45  # 10 s × 0,045 a 720p
    assert price("kie", f"{V12}/text-to-video", duration=15, resolution="4k") == 1.65
    assert price("kie", f"{V12}/image-to-video", image_url=IMG, duration=3, resolution="360p") == 0.06
    edit = ROUTES["kie"][f"{V12}/video-edit"]
    entry = logical(f"{V12}/video-edit", video_url=VID, resolution="1080p")
    assert edit.price(entry, {}, PRICES["kie"]) is None  # sin la duración del video de entrada
    assert edit.price(entry, {"input_video_seconds": 6}, PRICES["kie"]) == 0.3
    edit.check({}, {"input_video_seconds": 15})
    with pytest.raises(ProviderError):  # KIE edita videos de hasta 15 s
        edit.check({}, {"input_video_seconds": 16})


def test_v12_extend_only_on_apimart():
    """Extender: APIMart con `video_urls`; KIE pide un id de tarea suyo y no se ofrece."""
    ext = g.V12_EXTEND
    assert ext == f"{V12}/video-extend" and "video-extend" in get_catalog().get(ext)["capabilities"]
    assert ext not in ROUTES["kie"]
    route = ROUTES["apimart"][ext]
    assert route.model == "gemini-omni-1.2-flash" and route.settles_later
    assert body("apimart", ext, video_url=VID, duration=8) == {
        "prompt": "a fox", "duration": 8, "resolution": "720p",
        "video_urls": [VID], "omni_reference_task_type": "extend",
    }  # fmt: skip
    # Solo se cobran los segundos añadidos; con video de entrada retiene 15 s
    entry = logical(ext, video_url=VID, duration=4)
    assert route.price(entry, {"input_video_seconds": 6}, PRICES["apimart"]) == pytest.approx(0.24)
    assert route.reserve(entry, {}, PRICES["apimart"]) == pytest.approx(0.9)
    route.check(entry, {"input_video_seconds": 15})
    with pytest.raises(ProviderError):  # el video de origen, como mucho 15 s
        route.check(entry, {"input_video_seconds": 16})
