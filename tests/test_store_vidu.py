"""Vidu en las tiendas (`store/vidu.py`): traducción fiel y precio con las tablas de tests/fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import vidu

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
MODELS = {m["id"]: m for m in vidu.MODELS}
APIMART, KIE = vidu.apimart(), vidu.kie()
IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"


def sample(model_id: str, **extra) -> dict:
    return with_defaults(MODELS[model_id]["input_schema"], {"prompt": "a fox in the snow", **extra})


def test_q3_pro_text_to_video_on_apimart():
    logical = sample("vidu/q3-pro/text-to-video", duration=8, resolution="1080p")
    route = APIMART["vidu/q3-pro/text-to-video"]
    assert route.model == "viduq3-pro"
    assert route.translate(logical) == {"prompt": "a fox in the snow", "duration": 8, "resolution": "1080p",
                                        "aspect_ratio": "16:9", "audio": True}  # fmt: skip
    assert route.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.128 * 8)


def test_q3_turbo_first_and_last_frame_go_in_order():
    logical = sample("vidu/q3-turbo/image-to-video", image_url=IMG, end_image_url=END, generate_audio=False)
    out = APIMART["vidu/q3-turbo/image-to-video"].translate(logical)
    assert out["image_urls"] == [IMG, END] and out["audio"] is False
    assert "image_url" not in out and "end_image_url" not in out and "aspect_ratio" not in out


def test_q3_reference_models_and_their_limits():
    logical = sample("vidu/q3-mix/reference-to-video", image_urls=[IMG, END])
    out = APIMART["vidu/q3-mix/reference-to-video"].translate(logical)
    assert out == {"prompt": "a fox in the snow", "image_urls": [IMG, END], "duration": 5, "resolution": "720p",
                   "aspect_ratio": "16:9"}  # fmt: skip
    assert (
        APIMART["vidu/q3/reference-to-video"].price(
            sample("vidu/q3/reference-to-video"), {}, PRICES["apimart"]
        )
        == 0.4
    )
    # Q3 Mix no tiene 540p ni un campo de audio que se pueda apagar.
    assert (
        "540p"
        not in MODELS["vidu/q3-mix/reference-to-video"]["input_schema"]["properties"]["resolution"]["enum"]
    )
    with pytest.raises(ProviderError) as info:
        APIMART["vidu/q3/reference-to-video"].translate({**logical, "generate_audio": False})
    assert info.value.kind == "unsupported"


def test_q4_image_to_video_on_both_stores():
    logical = sample("vidu/q4/image-to-video", image_url=IMG, resolution="4k")
    am = APIMART["vidu/q4/image-to-video"].translate(logical)
    assert am == {"prompt": "a fox in the snow", "first_frame_image": IMG, "duration": 5, "resolution": "4K",
                  "audio": True}  # fmt: skip
    kie = KIE["vidu/q4/image-to-video"]
    assert kie.model == "vidu-q4/image-to-video"
    assert kie.translate(logical) == {"prompt": "a fox in the snow", "image_url": IMG, "duration": 5,
                                      "resolution": "4k", "audio": True}  # fmt: skip
    assert APIMART["vidu/q4/image-to-video"].price(logical, {}, PRICES["apimart"]) == pytest.approx(
        0.3328 * 5
    )
    assert kie.price(logical, {}, PRICES["kie"]) == pytest.approx(0.312 * 5)


def test_q4_reference_to_video_on_both_stores():
    logical = sample("vidu/q4/reference-to-video", image_urls=[IMG], audio_urls=["https://cdn.test/line.mp3"],
                     aspect_ratio="9:16")  # fmt: skip
    am = APIMART["vidu/q4/reference-to-video"].translate(logical)
    # Rol explícito: con una sola imagen sin rol APIMart haría imagen a video.
    assert am["image_with_roles"] == [{"url": IMG, "role": "reference_image"}]
    assert am["audio_urls"] == ["https://cdn.test/line.mp3"] and am["aspect_ratio"] == "9:16"
    kie = KIE["vidu/q4/reference-to-video"].translate(logical)
    assert kie == {"prompt": "a fox in the snow", "reference_image_urls": [IMG],
                   "reference_audio_urls": ["https://cdn.test/line.mp3"], "aspect_ratio": "9:16", "duration": 5,
                   "resolution": "720p", "audio": True}  # fmt: skip
    assert KIE["vidu/q4/reference-to-video"].price(logical, {}, PRICES["kie"]) == pytest.approx(0.38)


def test_q4_fixed_seed_only_runs_on_apimart():
    logical = sample("vidu/q4/image-to-video", image_url=IMG, seed=42)
    assert APIMART["vidu/q4/image-to-video"].translate(logical)["seed"] == 42
    with pytest.raises(ProviderError) as info:
        KIE["vidu/q4/image-to-video"].translate(logical)
    assert info.value.kind == "unsupported"
