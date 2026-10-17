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
    ids = {m["id"] for m in g.MODELS}
    assert ids == {
        T2V,
        I2V,
        REF,
        "google/gemini-omni-flash/text-to-video",
        "google/gemini-omni-flash/reference-to-video",
    }
    assert set(ROUTES["kie"]) == ids
    assert set(ROUTES["apimart"]) == {T2V, I2V, REF}
    assert all(not r.official and r.model == "gemini-omni-1.1-flash-ext" for r in ROUTES["apimart"].values())


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
