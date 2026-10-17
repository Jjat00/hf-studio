"""Kling 2.1 y Kling AI Avatar en KIE (`store/kling_extra.py`). Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import kling_extra as k

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = json.loads((FIXTURES / "prices_kie.json").read_text())
ROUTES = k.kie()
IMG, END, WAV = "https://cdn.test/a.png", "https://cdn.test/z.png", "https://cdn.test/s.wav"


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


def test_every_model_is_in_the_catalog_on_kie_only():
    ids = {m["id"] for m in k.MODELS}
    assert len(ids) == 6 and set(ROUTES) == ids
    assert not hasattr(k, "apimart")  # APIMart no vende Kling 2.1 ni AI Avatar
    for model_id in ids:
        assert get_catalog().get(model_id)["store"] is True


def test_kling21_bodies_and_prices():
    t2v = "kling-video/v2.1/master/text-to-video"
    assert body(t2v, prompt="a fox", negative_prompt="") == {
        "prompt": "a fox", "duration": "5", "aspect_ratio": "16:9", "cfg_scale": 0.5}  # fmt: skip
    assert ROUTES[t2v].model == "kling/v2-1-master-text-to-video"
    assert price(t2v, prompt="x", duration=10) == 1.6
    pro = "kling-video/v2.1/pro/image-to-video"
    out = body(pro, prompt="runs", image_url=IMG, end_image_url=END, negative_prompt="blur", duration=10)
    assert out == {"prompt": "runs", "image_url": IMG, "tail_image_url": END, "negative_prompt": "blur",
                   "duration": "10", "cfg_scale": 0.5}  # fmt: skip
    assert price(pro, prompt="x", image_url=IMG) == 0.25
    assert price("kling-video/v2.1/standard/image-to-video", prompt="x", image_url=IMG, duration=10) == 0.25
    assert price("kling-video/v2.1/master/image-to-video", prompt="x", image_url=IMG) == 0.8
    # Solo Pro tiene último fotograma; cfg_scale en pasos de 0,1
    refused("kling-video/v2.1/standard/image-to-video", prompt="x", image_url=IMG, end_image_url=END)
    refused(t2v, prompt="x", cfg_scale=0.55)
    assert body(t2v, prompt="x", cfg_scale=0.3)["cfg_scale"] == 0.3


def test_ai_avatar_is_priced_by_the_audio():
    for tier, rate in (("standard", 0.04), ("pro", 0.08)):
        mid = f"kling/ai-avatar/{tier}"
        assert ROUTES[mid].model == f"kling/ai-avatar-{tier}"
        assert body(mid, image_url=IMG, audio_url=WAV, prompt="talks") == {
            "image_url": IMG, "audio_url": WAV, "prompt": "talks"}  # fmt: skip
        assert price(mid, image_url=IMG, audio_url=WAV, prompt="x") is None  # sin la duración del audio
        assert price(mid, {"input_audio_seconds": 12}, image_url=IMG, audio_url=WAV, prompt="x") == round(
            rate * 12, 4
        )
        refused(mid, image_url=IMG, audio_url=WAV, prompt="x", resolution="720p")
        with pytest.raises(ProviderError):  # más de 5 minutos de audio
            ROUTES[mid].check({}, {"input_audio_seconds": 301})
        ROUTES[mid].check({}, {"input_audio_seconds": 300})
