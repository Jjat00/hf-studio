"""MiniMax en las tiendas (`store/minimax.py`): Hailuo 02, Hailuo 2.3 Fast y Pro, H3 Max."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import minimax

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
MODELS = {m["id"]: m for m in minimax.MODELS}
APIMART, KIE = minimax.apimart(), minimax.kie()
IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"


def sample(model_id: str, **extra) -> dict:
    return with_defaults(MODELS[model_id]["input_schema"], {"prompt": "a fox in the snow", **extra})


def unsupported(route, logical):
    with pytest.raises(ProviderError) as info:
        route.translate(logical)
    assert info.value.kind == "unsupported"


def test_hailuo_02_standard_on_kie():
    t2v = KIE["minimax/hailuo-02/standard/text-to-video"]
    logical = sample("minimax/hailuo-02/standard/text-to-video", duration=10)
    assert t2v.model == "hailuo/02-text-to-video-standard"
    assert t2v.translate(logical) == {
        "prompt": "a fox in the snow",
        "duration": "10",
        "prompt_optimizer": True,
    }
    assert t2v.price(logical, {}, PRICES["kie"]) == 0.25
    i2v = KIE["minimax/hailuo-02/standard/image-to-video"]
    logical = sample(
        "minimax/hailuo-02/standard/image-to-video", image_url=IMG, end_image_url=END, resolution="512p"
    )
    assert i2v.translate(logical) == {"prompt": "a fox in the snow", "image_url": IMG, "end_image_url": END,
                                      "duration": "6", "resolution": "512P", "prompt_optimizer": True}  # fmt: skip
    assert i2v.price(logical, {}, PRICES["kie"]) == 0.06


def test_hailuo_02_pro_is_1080p_and_6_seconds_without_those_fields():
    route = KIE["minimax/hailuo-02/pro/image-to-video"]
    logical = sample("minimax/hailuo-02/pro/image-to-video", image_url=IMG)
    assert route.translate(logical) == {
        "prompt": "a fox in the snow",
        "image_url": IMG,
        "prompt_optimizer": True,
    }
    assert route.price(logical, {}, PRICES["kie"]) == 0.285
    assert "duration" not in MODELS["minimax/hailuo-02/pro/text-to-video"]["input_schema"]["properties"]
    # Sin ruta en APIMart: documenta otras duraciones (5 o 10 s).
    assert not any(k.startswith("minimax/hailuo-02/") for k in APIMART)


def test_hailuo_23_fast_on_apimart():
    route = APIMART["minimax/hailuo-2.3/fast/image-to-video"]
    logical = sample("minimax/hailuo-2.3/fast/image-to-video", image_url=IMG, resolution="1080p")
    assert route.translate(logical) == {"prompt": "a fox in the snow", "first_frame_image": IMG, "duration": 6,
                                        "resolution": "1080p", "prompt_optimizer": True, "watermark": False}  # fmt: skip
    assert route.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.0424 * 6)
    assert route.price({**logical, "resolution": "768p"}, {}, PRICES["apimart"]) == pytest.approx(0.0248 * 6)
    unsupported(route, {**logical, "duration": 10})  # 1080p solo a 6 s


def test_hailuo_23_pro_on_kie():
    route = KIE["minimax/hailuo-2.3/pro/image-to-video"]
    logical = sample("minimax/hailuo-2.3/pro/image-to-video", image_url=IMG, duration=10)
    assert route.translate(logical) == {"prompt": "a fox in the snow", "image_url": IMG, "duration": "10",
                                        "resolution": "768P"}  # fmt: skip
    assert route.price(logical, {}, PRICES["kie"]) == 0.45
    unsupported(route, {**logical, "resolution": "1080p"})
    unsupported(route, {**logical, "prompt_optimizer": False})  # KIE Pro no tiene ese interruptor


def test_h3_max_text_and_frames():
    t2v = APIMART["minimax/h3-max/text-to-video"]
    logical = sample("minimax/h3-max/text-to-video", aspect_ratio="9:16", duration=10)
    assert t2v.translate(logical) == {"prompt": "a fox in the snow", "duration": 10, "resolution": "768P",
                                      "aspect_ratio": "9:16", "watermark": False}  # fmt: skip
    assert t2v.price(logical, {}, PRICES["apimart"]) == pytest.approx(0.05712 * 10)
    # A 1080P la marca de agua no se envía (ni en false) y pedirla no se puede reproducir.
    full_hd = {**logical, "resolution": "1080p"}
    assert "watermark" not in t2v.translate(full_hd)
    unsupported(t2v, {**full_hd, "aigc_watermark": True})
    i2v = APIMART["minimax/h3-max/image-to-video"]
    out = i2v.translate(sample("minimax/h3-max/image-to-video", image_url=IMG, end_image_url=END))
    assert out["first_frame_image"] == IMG and out["last_frame_image"] == END and "aspect_ratio" not in out


def test_h3_max_references_and_their_price():
    route = APIMART["minimax/h3-max/reference-to-video"]
    images = [f"https://cdn.test/{n}.png" for n in range(4)]
    logical = sample("minimax/h3-max/reference-to-video", image_urls=images, video_urls=["https://cdn.test/v.mp4"],
                     audio_urls=["https://cdn.test/a.mp3"])  # fmt: skip
    out = route.translate(logical)
    assert out["aspect_ratio"] == "adaptive" and out["image_urls"] == images and out["resolution"] == "768P"
    # 5 s a 768P + 2 imágenes cobradas (las 2 primeras son gratis) + 4 s de video de referencia.
    expected = 0.05712 * 5 + 0.05712 * 2 + 0.11088 * 4
    assert route.price(logical, {"input_video_seconds": 4}, PRICES["apimart"]) == pytest.approx(
        expected, abs=1e-3
    )
    assert route.price(logical, {}, PRICES["apimart"]) is None  # falta la duración del video
    unsupported(route, sample("minimax/h3-max/reference-to-video", audio_urls=["https://cdn.test/a.mp3"]))
