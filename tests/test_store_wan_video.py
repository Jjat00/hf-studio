"""Wan en las tiendas (`store/wan_video.py`): 2.2 Turbo y Animate, 2.5, 2.6 Flash y 2.7 Video Edit. Sin créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.routes import with_defaults
from hf_studio.store import wan_video as w

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
ROUTES = {"apimart": w.apimart(), "kie": w.kie()}
IMG, VID, WAV = "https://cdn.test/a.png", "https://cdn.test/v.mp4", "https://cdn.test/s.wav"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], extra)


def body(provider: str, model_id: str, **extra) -> dict:
    data = logical(model_id, **extra)
    return ROUTES[provider][model_id].translate(data, frozenset(extra))


def price(provider: str, model_id: str, hints: dict | None = None, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), hints or {}, PRICES[provider])


def refused(provider: str, model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, model_id, **extra)
    assert info.value.kind == "unsupported"


def test_every_model_is_in_the_catalog_with_a_route():
    ids = {m["id"] for m in w.MODELS}
    assert len(ids) == 10
    for model_id in ids:
        assert get_catalog().get(model_id)["store"] is True
        assert get_catalog().get(model_id)["output"] == "video"
    assert set(ROUTES["kie"]) == ids
    assert set(ROUTES["apimart"]) == {"wan/v2.5/text-to-video", "wan/v2.5/image-to-video",
                                      "wan/v2.6-flash/image-to-video", "wan/v2.7/video-edit"}  # fmt: skip
    for route in ROUTES["apimart"].values():  # videos: nunca al endpoint de imágenes
        assert APIMartProvider._submit_path(route.model) == "/v1/videos/generations"


def test_wan22_turbo_on_kie():
    mid = "wan/v2.2-turbo/text-to-video"
    assert body("kie", mid, prompt="a fox", seed=-1) == {
        "prompt": "a fox", "resolution": "720p", "aspect_ratio": "16:9", "acceleration": "none",
        "enable_prompt_expansion": False,
    }  # fmt: skip
    assert body("kie", mid, prompt="a fox", seed=7)["seed"] == 7
    assert price("kie", mid, prompt="a fox") == round(0.08 * 5, 4)
    assert ROUTES["kie"][mid].settles_later  # duración de salida no publicada: aproximado
    refused("kie", mid, prompt="a fox", negative_prompt="blur")  # campo sin equivalente: nunca se pierde
    i2v = body("kie", "wan/v2.2-turbo/image-to-video", prompt="walks", image_url=IMG, resolution="480p")
    assert i2v["image_url"] == IMG and "aspect_ratio" not in i2v
    assert price("kie", "wan/v2.2-turbo/image-to-video", prompt="x", image_url=IMG, resolution="480p") == 0.2


def test_wan22_speech_to_video_prices_frames_over_fps():
    mid = "wan/v2.2-turbo/speech-to-video"
    out = body("kie", mid, prompt="she sings", image_url=IMG, audio_url=WAV)
    assert out == {"prompt": "she sings", "image_url": IMG, "audio_url": WAV, "resolution": "480p",
                   "num_frames": 80, "frames_per_second": 16, "num_inference_steps": 27,
                   "guidance_scale": 3.5, "shift": 5}  # fmt: skip
    assert price("kie", mid, prompt="x", image_url=IMG, audio_url=WAV) == round(0.06 * 5, 4)
    assert price("kie", mid, prompt="x", image_url=IMG, audio_url=WAV, num_frames=120, frames_per_second=24,
                 resolution="720p") == round(0.12 * 5, 4)  # fmt: skip


def test_wan22_animate_is_priced_by_the_driving_video():
    for mode in ("move", "replace"):
        mid = f"wan/v2.2-animate/{mode}"
        assert body("kie", mid, video_url=VID, image_url=IMG) == {
            "video_url": VID, "image_url": IMG, "resolution": "480p"}  # fmt: skip
        assert ROUTES["kie"][mid].model == f"wan/2-2-animate-{mode}"
        assert price("kie", mid, video_url=VID, image_url=IMG) is None  # sin la duración del video
        assert price("kie", mid, {"input_video_seconds": 8}, video_url=VID, image_url=IMG,
                     resolution="720p") == round(0.0625 * 8, 4)  # fmt: skip
        refused("kie", mid, video_url=VID, image_url=IMG, prompt="dance")  # no tiene prompt


def test_wan25_on_both_stores():
    mid = "wan/v2.5/text-to-video"
    am = body("apimart", mid, prompt="a fox", seed=3)
    assert am == {"prompt": "a fox", "duration": 5, "resolution": "720p", "prompt_extend": True, "size": "16:9",
                  "seed": 3}  # fmt: skip
    kie = body("kie", mid, prompt="a fox", duration=10)
    assert kie == {"prompt": "a fox", "duration": "10", "resolution": "720p", "aspect_ratio": "16:9",
                   "enable_prompt_expansion": True}  # fmt: skip
    assert price("apimart", mid, prompt="x") == round(0.0664 * 5, 4)
    assert price("kie", mid, prompt="x", duration=10, resolution="1080p") == 1.0
    # 480p y 4:3 solo en APIMart, y APIMart no tiene 4:3 en 480p
    refused("kie", mid, prompt="x", resolution="480p")
    refused("kie", mid, prompt="x", aspect_ratio="4:3")
    assert body("apimart", mid, prompt="x", aspect_ratio="4:3")["size"] == "4:3"
    refused("apimart", mid, prompt="x", aspect_ratio="4:3", resolution="480p")
    refused("kie", mid, prompt="x" * 801)
    refused("kie", mid, prompt="x", audio_url=WAV)
    assert body("apimart", mid, prompt="x", audio_url=WAV)["audio_url"] == WAV
    i2v = "wan/v2.5/image-to-video"
    assert body("apimart", i2v, prompt="x", image_url=IMG)["image_urls"] == [IMG]
    assert "size" not in body("apimart", i2v, prompt="x", image_url=IMG)
    assert body("kie", i2v, prompt="x", image_url=IMG)["image_url"] == IMG
    assert price("kie", i2v, prompt="x", image_url=IMG) == 0.3


def test_wan26_flash_image_to_video():
    mid = "wan/v2.6-flash/image-to-video"
    am = body("apimart", mid, prompt="waves", image_url=IMG)
    assert am == {"prompt": "waves", "duration": 5, "resolution": "1080p", "prompt_extend": False,
                  "image_urls": [IMG], "audio": True, "shot_type": "single"}  # fmt: skip
    kie = body("kie", mid, prompt="waves", image_url=IMG, generate_audio=False)
    assert kie == {"prompt": "waves", "image_urls": [IMG], "duration": "5", "resolution": "1080p",
                   "audio": False, "multi_shots": False}  # fmt: skip
    assert price("apimart", mid, prompt="x", image_url=IMG) == round(0.0552 * 5, 4)
    assert price("apimart", mid, prompt="x", image_url=IMG, generate_audio=False, resolution="720p") == round(
        0.0168 * 5, 4
    )
    assert price("kie", mid, prompt="x", image_url=IMG, duration=15, resolution="720p") == 0.6
    refused("kie", mid, prompt="x", image_url=IMG, duration=7)  # KIE: 5, 10 o 15 s
    assert body("apimart", mid, prompt="x", image_url=IMG, duration=7)["duration"] == 7
    refused("kie", mid, prompt="x", image_url=IMG, seed=5)
    refused("kie", mid, prompt="x", image_url=IMG, audio_url=WAV)
    refused("apimart", mid, prompt="x", image_url=IMG, audio_url=WAV, generate_audio=False)
    refused("apimart", mid, prompt="x", image_url=IMG, multi_shots=True)  # pide prompt_extend en APIMart
    multi = body("apimart", mid, prompt="x", image_url=IMG, multi_shots=True, prompt_extend=True)
    assert multi["shot_type"] == "multi"
    refused("kie", mid, prompt="x", image_url=IMG, multi_shots=True, prompt_extend=True)


def test_wan26_flash_reference_to_video_on_kie():
    mid = "wan/v2.6-flash/reference-to-video"
    out = body("kie", mid, prompt="they dance", video_urls=[VID])
    assert out == {"prompt": "they dance", "video_urls": [VID], "duration": "5", "resolution": "1080p",
                   "audio": True, "multi_shots": False}  # fmt: skip
    assert price("kie", mid, prompt="x", video_urls=[VID], duration=10, resolution="720p") == 0.4
    refused("kie", mid, prompt="x" * 1501, video_urls=[VID])


def test_wan27_video_edit_on_both_stores():
    mid = "wan/v2.7/video-edit"
    am = body("apimart", mid, prompt="red gown", video_url=VID, image_urls=[IMG], audio_setting="origin")
    assert am == {"prompt": "red gown", "video_urls": [VID], "image_urls": [IMG], "resolution": "1080P",
                  "duration": 0, "prompt_extend": True, "metadata": {"audio_setting": "origin"}}  # fmt: skip
    kie = body("kie", mid, prompt="red gown", video_url=VID, image_urls=[IMG], aspect_ratio="9:16", seed=-1)
    assert kie == {"prompt": "red gown", "video_url": VID, "reference_image": IMG, "resolution": "1080p",
                   "aspect_ratio": "9:16", "duration": 0, "audio_setting": "auto", "prompt_extend": True,
                   "watermark": False}  # fmt: skip
    assert body("apimart", mid, video_url=VID, aspect_ratio="1:1")["size"] == "1:1"
    # duration 0 = largo del video de origen
    assert price("apimart", mid, video_url=VID) is None
    assert price("apimart", mid, {"input_video_seconds": 6}, video_url=VID) == round(0.1096 * 6, 4)
    assert price("apimart", mid, {"input_video_seconds": 6}, video_url=VID, resolution="720p",
                 duration=4) == round(0.0664 * 4, 4)  # fmt: skip
    assert price("kie", mid, {"input_video_seconds": 6}, video_url=VID, resolution="720p") == round(
        0.08 * 6, 4
    )
    refused("kie", mid, video_url=VID, image_urls=[IMG, IMG])  # KIE: una referencia
    for provider in ("apimart", "kie"):
        refused(provider, mid, video_url=VID, duration=1)
        check = ROUTES[provider][mid].check
        with pytest.raises(ProviderError):
            check(logical(mid, video_url=VID), {"input_video_seconds": 12})
        with pytest.raises(ProviderError):
            check(logical(mid, video_url=VID, duration=8), {"input_video_seconds": 5})
        check(logical(mid, video_url=VID, duration=5), {"input_video_seconds": 5})
