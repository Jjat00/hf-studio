"""Seedance 1.0, 1.5 Pro y 2.0 Fast/Mini en las tiendas (`store/seedance.py`). Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import seedance as s

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
IMG, END, VID = "https://cdn.test/a.png", "https://cdn.test/b.png", "https://cdn.test/r.mp4"
ROUTES = {"apimart": s.apimart(), "kie": s.kie()}


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def body(provider: str, model_id: str, **extra) -> dict:
    return ROUTES[provider][model_id].translate(logical(model_id, **extra))


def price(provider: str, model_id: str, hints: dict | None = None, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), hints or {}, PRICES[provider])


def refused(provider: str, model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, model_id, **extra)
    assert info.value.kind == "unsupported"


def test_models_and_routes():
    ids = {m["id"] for m in s.MODELS}
    assert len(ids) == 14
    assert not any(i.startswith(("bytedance/seedance-2.0/", "bytedance/seedance-2.5/")) for i in ids)
    only_kie = {"bytedance/seedance-1.0-lite/text-to-video", "bytedance/seedance-1.0-lite/image-to-video"}
    assert set(ROUTES["apimart"]) == ids - only_kie
    assert set(ROUTES["kie"]) == ids - {"bytedance/seedance-1.0-pro-fast/text-to-video"}


def test_seedance_1_0():
    pro = "bytedance/seedance-1.0-pro/image-to-video"
    assert body("apimart", pro, image_url=IMG, end_image_url=END, duration=7) == {
        "prompt": "a fox", "duration": 7, "resolution": "720p",
        "image_with_roles": [{"url": IMG, "role": "first_frame"}, {"url": END, "role": "last_frame"}],
    }  # fmt: skip
    assert price("apimart", pro, image_url=IMG) == pytest.approx(0.22)
    assert body("kie", pro, image_url=IMG, camera_fixed=True, seed=3) == {
        "prompt": "a fox", "duration": "5", "resolution": "720p", "image_url": IMG, "camera_fixed": True, "seed": 3,
    }  # fmt: skip
    assert price("kie", pro, image_url=IMG, resolution="1080p", duration=10) == pytest.approx(0.7)
    # KIE: solo 5 o 10 s y, en pro, sin último fotograma; APIMart no fija la cámara
    refused("kie", pro, image_url=IMG, duration=7)
    refused("kie", pro, image_url=IMG, end_image_url=END)
    refused("apimart", pro, image_url=IMG, camera_fixed=True)
    lite = "bytedance/seedance-1.0-lite/text-to-video"
    assert body("kie", lite, aspect_ratio="9:21")["aspect_ratio"] == "9:21"
    fast = "bytedance/seedance-1.0-pro-fast/image-to-video"
    assert body("kie", fast, image_url=IMG, duration=10, resolution="1080p") == {
        "prompt": "a fox", "duration": "10", "resolution": "1080p", "image_url": IMG,
    }  # fmt: skip
    assert price("kie", fast, image_url=IMG, duration=10, resolution="1080p") == 0.36
    refused("kie", fast, image_url=IMG, resolution="480p")
    refused("apimart", fast, image_url=IMG, end_image_url=END)


def test_seedance_1_5_pro():
    mid = "bytedance/seedance-1.5-pro/image-to-video"
    assert body("apimart", mid, image_url=IMG, camera_fixed=True) == {
        "prompt": "a fox", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "audio": True,
        "camerafixed": True, "image_with_roles": [{"url": IMG, "role": "first_frame"}],
    }  # fmt: skip
    assert body("kie", mid, image_url=IMG, end_image_url=END) == {
        "prompt": "a fox", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "generate_audio": True,
        "fixed_lens": False, "input_urls": [IMG, END],
    }  # fmt: skip
    assert price("kie", mid, image_url=IMG) == pytest.approx(0.175)
    assert price("kie", mid, image_url=IMG, generate_audio=False) == pytest.approx(0.0875)
    assert price("apimart", mid, image_url=IMG, resolution="1080p") == pytest.approx(0.54)
    refused("kie", "bytedance/seedance-1.5-pro/text-to-video", seed=9)


def test_seedance_2_0_fast_and_mini():
    t2v = "bytedance/seedance-2.0-fast/text-to-video"
    assert body("apimart", t2v, aspect_ratio="9:16") == {
        "prompt": "a fox", "duration": 5, "resolution": "720p", "generate_audio": True, "size": "9:16",
    }  # fmt: skip
    assert body("kie", t2v) == {
        "prompt": "a fox", "duration": 5, "resolution": "720p", "generate_audio": True, "aspect_ratio": "16:9",
    }  # fmt: skip
    assert price("apimart", t2v) == pytest.approx(0.428)
    assert price("kie", t2v, resolution="480p") == pytest.approx(0.2925)
    i2v = "bytedance/seedance-2.0-mini/image-to-video"
    assert body("kie", i2v, image_url=IMG, end_image_url=END) == {
        "prompt": "a fox", "duration": 5, "resolution": "720p", "generate_audio": True,
        "first_frame_url": IMG, "last_frame_url": END, "aspect_ratio": "adaptive",
    }  # fmt: skip
    assert body("apimart", i2v, image_url=IMG)["size"] == "adaptive"
    ref = "bytedance/seedance-2.0-mini/reference-to-video"
    assert body("kie", ref, image_urls=[IMG], video_urls=[VID]) == {
        "prompt": "a fox", "duration": 5, "resolution": "720p", "generate_audio": True, "aspect_ratio": "16:9",
        "reference_image_urls": [IMG], "reference_video_urls": [VID],
    }  # fmt: skip
    # Con video de referencia se cobra la entrada más la salida, a la tarifa «with video»
    assert price("kie", ref, {"input_video_seconds": 4}, video_urls=[VID]) == pytest.approx(0.025 * 9)
    assert price("apimart", ref, {"input_video_seconds": 4}, video_urls=[VID]) == pytest.approx(
        0.02376 * 9, abs=1e-4
    )
    assert price("kie", ref, video_urls=[VID]) is None  # sin la duración del video no hay precio
    refused("apimart", t2v, seed=1)
    refused("kie", i2v, image_url=IMG, image_urls=[IMG])
