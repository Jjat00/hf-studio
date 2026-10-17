"""Grok Imagine Video por modo en las tiendas (`store/grok_video.py`): base y 1.5, con el canal no oficial."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import grok_video

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
MODELS = {m["id"]: m for m in grok_video.MODELS}
APIMART, KIE = grok_video.apimart(), grok_video.kie()
IMG, IMG2 = "https://cdn.test/a.png", "https://cdn.test/b.png"
V1, V15 = "xai/grok-imagine-video/v1", "xai/grok-imagine-video/v1.5"


def sample(model_id: str, **extra) -> dict:
    return with_defaults(MODELS[model_id]["input_schema"], {"prompt": "a fox in the snow", **extra})


def channel(model_id: str, name: str):
    return next(r for r in routes_for(APIMART, model_id) if r.model == name)


def unsupported(route, logical):
    with pytest.raises(ProviderError) as info:
        route.translate(logical)
    assert info.value.kind == "unsupported"


def test_base_text_to_video_on_both_stores():
    logical = sample(f"{V1}/text-to-video")
    am = APIMART[f"{V1}/text-to-video"]
    assert am.translate(logical) == {"prompt": "a fox in the snow", "duration": 8, "resolution": "480p",
                                     "aspect_ratio": "16:9"}  # fmt: skip
    assert am.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.04 * 8)
    kie = KIE[f"{V1}/text-to-video"]
    assert kie.translate(logical) == {"prompt": "a fox in the snow", "duration": 8, "resolution": "480p",
                                      "aspect_ratio": "16:9", "mode": "normal"}  # fmt: skip
    assert kie.price(logical, {}, PRICES["kie"]) == pytest.approx(0.012 * 8)
    unsupported(am, {**logical, "mode": "spicy"})  # APIMart no tiene modos
    unsupported(am, {**logical, "duration": 20})  # APIMart: 1–15 s
    unsupported(kie, {**logical, "aspect_ratio": "auto"})  # KIE base: sin auto
    unsupported(kie, {**logical, "duration": 3})  # KIE: 6–30 s


def test_base_image_to_video():
    one = sample(f"{V1}/image-to-video", image_urls=[IMG])
    kie = KIE[f"{V1}/image-to-video"]
    assert kie.translate(one) == {"prompt": "a fox in the snow", "image_urls": [IMG], "duration": "8",
                                  "resolution": "480p", "mode": "normal"}  # fmt: skip
    am = APIMART[f"{V1}/image-to-video"]
    assert am.translate(one)["aspect_ratio"] == "auto"
    assert am.price(one, {}, PRICES["apimart"]) == pytest.approx(0.04 * 8 + 0.0016)
    # Una imagen manda el formato en KIE; con varias el formato es explícito.
    unsupported(kie, {**one, "aspect_ratio": "16:9"})
    two = {**one, "image_urls": [IMG, IMG2], "aspect_ratio": "9:16"}
    assert kie.translate(two)["aspect_ratio"] == "9:16"
    unsupported(kie, {**two, "aspect_ratio": "auto"})
    unsupported(kie, {**two, "resolution": "1080p"})  # a 1080p, una sola imagen


def test_base_video_edit_on_apimart():
    route = APIMART[f"{V1}/video-edit"]
    logical = sample(f"{V1}/video-edit", video_url="https://cdn.test/v.mp4")
    assert route.translate(logical) == {
        "prompt": "a fox in the snow",
        "video": {"url": "https://cdn.test/v.mp4"},
    }
    assert route.price(logical, {"input_video_seconds": 6}, PRICES["apimart"]) == pytest.approx(
        (0.056 + 0.008) * 6
    )
    assert route.price(logical, {}, PRICES["apimart"]) is None
    assert f"{V1}/video-edit" not in KIE


def test_v15_text_to_video_channels():
    logical = sample(f"{V15}/text-to-video", resolution="720p")
    official = channel(f"{V15}/text-to-video", "grok-imagine-video-1.5")
    assert official.official and official.translate(logical)["aspect_ratio"] == "16:9"
    assert official.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.112 * 8)
    ext = channel(f"{V15}/text-to-video", "grok-imagine-1.5-video-ext")
    assert not ext.official
    assert ext.translate(logical) == {"prompt": "a fox in the snow", "duration": 8, "resolution": "720p",
                                      "size": "16:9"}  # fmt: skip
    assert ext.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.01912 * 8, abs=1e-3)
    unsupported(ext, {**logical, "aspect_ratio": "auto"})  # sin imágenes, `size` explícito
    unsupported(ext, {**logical, "duration": 5})  # mínimo 6 s
    kie = KIE[f"{V15}/text-to-video"]
    assert kie.model == "grok-imagine-video-1-5-preview" and not kie.official
    assert kie.price(logical, {}, PRICES["kie"]) == pytest.approx(0.0225 * 8)
    unsupported(kie, {**logical, "aspect_ratio": "4:3"})


def test_v15_image_to_video_channels():
    logical = sample(f"{V15}/image-to-video", image_urls=[IMG, IMG2])
    official = channel(f"{V15}/image-to-video", "grok-imagine-video-1.5")
    assert official.translate(logical)["image_urls"] == [IMG, IMG2]
    assert official.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.064 * 8 + 0.008 * 2)
    ext = channel(f"{V15}/image-to-video", "grok-imagine-1.5-video-ext")
    assert "size" not in ext.translate(logical)  # el formato sale de las imágenes
    unsupported(ext, {**logical, "aspect_ratio": "1:1"})
    kie = KIE[f"{V15}/image-to-video"]
    assert kie.translate(logical) == {"prompt": "a fox in the snow", "image_urls": [IMG, IMG2], "duration": 8,
                                      "resolution": "480p", "aspect_ratio": "auto"}  # fmt: skip
    assert kie.price(logical, {}, PRICES["kie"]) == pytest.approx(0.012 * 8)
    assert "aspect_ratio" not in kie.translate({**logical, "image_urls": [IMG]})
