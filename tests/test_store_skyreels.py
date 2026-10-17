"""SkyReels V4 en APIMart (`store/skyreels.py`): modos por campos y etiquetas @ en el prompt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import skyreels

PRICES = json.loads((Path(__file__).parent / "fixtures" / "prices_apimart.json").read_text())
MODELS = {m["id"]: m for m in skyreels.MODELS}
APIMART = skyreels.apimart()
IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"


def sample(model_id: str, **extra) -> dict:
    return with_defaults(MODELS[model_id]["input_schema"], {"prompt": "a fox in the snow", **extra})


def test_only_apimart_sells_it():
    assert not hasattr(skyreels, "kie")
    assert set(APIMART) == set(MODELS)


def test_text_to_video():
    route = APIMART["skyreels/v4/std/text-to-video"]
    logical = sample("skyreels/v4/std/text-to-video", resolution="1080p", aspect_ratio="9:16")
    assert route.model == "skyreels-v4-std"
    assert route.translate(logical) == {"prompt": "a fox in the snow", "duration": 5, "resolution": "1080p",
                                        "aspect_ratio": "9:16", "prompt_optimizer": True}  # fmt: skip
    assert route.price(logical, {}, PRICES) == pytest.approx(0.28 * 5)


def test_frames():
    out = APIMART["skyreels/v4/fast/image-to-video"].translate(
        sample("skyreels/v4/fast/image-to-video", image_url=IMG, end_image_url=END)
    )
    assert out["first_frame_image"] == IMG and out["end_frame_image"] == END and "aspect_ratio" not in out


def test_references_are_tagged_and_cited():
    route = APIMART["skyreels/v4/fast/reference-to-video"]
    logical = sample(
        "skyreels/v4/fast/reference-to-video", prompt="@image1 hugs a bear", image_urls=[IMG, END]
    )
    out = route.translate(logical)
    assert out["ref_images"] == [{"tag": "@image1", "type": "image", "image_urls": [IMG]},
                                 {"tag": "@image2", "type": "image", "image_urls": [END]}]  # fmt: skip
    # La etiqueta que el prompt no cita se añade al final; la que ya cita no se repite.
    assert out["prompt"] == "@image1 hugs a bear @image2"
    assert route.price(logical, {}, PRICES) == pytest.approx(0.088 * 5)
    with pytest.raises(ProviderError) as info:
        route.translate({**logical, "image_urls": [IMG] * 4})
    assert info.value.kind == "unsupported"


def test_extend_uses_the_video_input_rate():
    route = APIMART["skyreels/v4/fast/video-extend"]
    logical = sample("skyreels/v4/fast/video-extend", video_url="https://cdn.test/v.mp4", duration=8)
    out = route.translate(logical)
    assert out["ref_videos"] == [{"tag": "@video1", "type": "extend", "video_url": "https://cdn.test/v.mp4"}]
    assert out["prompt"] == "a fox in the snow @video1" and "aspect_ratio" not in out
    assert route.price(logical, {}, PRICES) == pytest.approx(0.16 * 8)


def test_aspect_ratio_has_no_meaning_with_frames():
    with pytest.raises(ProviderError) as info:
        APIMART["skyreels/v4/fast/image-to-video"].translate(
            {**sample("skyreels/v4/fast/image-to-video", image_url=IMG), "aspect_ratio": "1:1"}
        )
    assert info.value.kind == "unsupported"
