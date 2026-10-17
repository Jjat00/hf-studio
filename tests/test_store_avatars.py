"""Avatares que hablan en KIE (`store/avatars.py`): InfiniteTalk y OmniHuman 1.5. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import avatars as a

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = json.loads((FIXTURES / "prices_kie.json").read_text())
ROUTES = a.kie()
IMG, WAV = "https://cdn.test/a.png", "https://cdn.test/s.wav"
INFINITE, OMNI = "meigen/infinitetalk/image-to-video", "bytedance/omnihuman-1.5/image-to-video"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], extra)


def body(model_id: str, **extra) -> dict:
    return ROUTES[model_id].translate(logical(model_id, **extra), frozenset(extra))


def price(model_id: str, hints: dict | None = None, **extra) -> float | None:
    return ROUTES[model_id].price(logical(model_id, **extra), hints or {}, PRICES)


def refused(model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(model_id, **extra)
    assert info.value.kind == "unsupported"


def test_models_are_in_the_catalog_on_kie():
    assert {m["id"] for m in a.MODELS} == set(ROUTES) == {INFINITE, OMNI}
    for model_id in ROUTES:
        model = get_catalog().get(model_id)
        assert model["store"] is True and "audio-input" in model["capabilities"]


def test_audio_seconds_hint():
    assert a.audio_seconds({"input_audio_seconds": 7}) == 7.0
    assert a.audio_seconds({"input_audio_seconds": 0}) is None
    assert a.audio_seconds({"input_video_seconds": 7}) is None


def test_infinitetalk():
    assert ROUTES[INFINITE].model == "infinitalk/from-audio"
    assert body(INFINITE, image_url=IMG, audio_url=WAV, prompt="talks", seed=-1) == {
        "image_url": IMG, "audio_url": WAV, "prompt": "talks", "resolution": "480p"}  # fmt: skip
    assert body(INFINITE, image_url=IMG, audio_url=WAV, prompt="x", seed=12345)["seed"] == 12345
    refused(INFINITE, image_url=IMG, audio_url=WAV, prompt="x", seed=42)  # KIE: 10000–1000000
    assert price(INFINITE, image_url=IMG, audio_url=WAV, prompt="x") is None
    assert price(INFINITE, {"input_audio_seconds": 10}, image_url=IMG, audio_url=WAV, prompt="x",
                 resolution="720p") == 0.6  # fmt: skip
    with pytest.raises(ProviderError):
        ROUTES[INFINITE].check({}, {"input_audio_seconds": 16})
    ROUTES[INFINITE].check({}, {"input_audio_seconds": 15})
    ROUTES[INFINITE].check({}, {})  # sin la duración no se descarta


def test_omnihuman():
    assert body(OMNI, image_url=IMG, audio_url=WAV) == {
        "image_url": IMG, "audio_url": WAV, "output_resolution": "1080", "pe_fast_mode": False}  # fmt: skip
    out = body(OMNI, image_url=IMG, audio_url=WAV, prompt="smiles", mask_urls=[IMG], resolution="720p",
               fast_mode=True, seed=9)  # fmt: skip
    assert out == {"image_url": IMG, "audio_url": WAV, "prompt": "smiles", "mask_url": [IMG],
                   "output_resolution": "720", "pe_fast_mode": True, "seed": 9}  # fmt: skip
    assert price(OMNI, {"input_audio_seconds": 10}, image_url=IMG, audio_url=WAV) == 1.35
    refused(OMNI, image_url=IMG, audio_url=WAV, duration=5)  # la duración la pone el audio
    with pytest.raises(ProviderError):  # el audio debe durar menos de 60 s
        ROUTES[OMNI].check({}, {"input_audio_seconds": 60})
    ROUTES[OMNI].check({}, {"input_audio_seconds": 59.5})
