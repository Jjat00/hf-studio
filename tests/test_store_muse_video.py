"""Muse Video en APIMart (`store/muse_video.py`): cobra por segundo de salida. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.routes import with_defaults
from hf_studio.store import muse_video as m

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = json.loads((FIXTURES / "prices_apimart.json").read_text())
ROUTES = m.apimart()
T2V, REF = "muse/muse-video/text-to-video", "muse/muse-video/reference-to-video"
IMG = "https://cdn.test/a.png"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "waves at sunset", **extra})


def body(model_id: str, **extra) -> dict:
    return ROUTES[model_id].translate(logical(model_id, **extra))


def refused(model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(model_id, **extra)
    assert info.value.kind == "unsupported"


def test_models_and_routes():
    assert {x["id"] for x in m.MODELS} == set(ROUTES) == {T2V, REF}
    for model_id, route in ROUTES.items():
        assert get_catalog().get(model_id)["store"] is True
        assert route.provider == "apimart" and route.model == "muse-video-ext"
        assert APIMartProvider._submit_path(route.model) == "/v1/videos/generations"


def test_bodies():
    assert body(T2V) == {
        "prompt": "waves at sunset", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "n": 1,
    }  # fmt: skip
    # Con referencias, `auto` no se envía: el formato sigue a las imágenes
    assert body(REF, image_urls=[IMG], duration=10) == {
        "prompt": "waves at sunset", "duration": 10, "image_urls": [IMG], "resolution": "720p", "n": 1,
    }  # fmt: skip
    assert body(REF, image_urls=[IMG], aspect_ratio="9:16")["aspect_ratio"] == "9:16"
    refused(T2V, seed=3)
    refused(T2V, image_url=IMG)


def test_price_per_second_of_output():
    """Una sola tarifa por segundo (720P) desde el 2026-11-12: la fila `default` ya no está."""
    assert "muse-video-ext|default" not in PRICES
    assert ROUTES[T2V].price(logical(T2V), {}, PRICES) == 0.0118  # 5 s × 0,002352, redondeado
    assert ROUTES[REF].price(logical(REF, image_urls=[IMG], duration=10), {}, PRICES) == 0.0235
    for model_id, route in ROUTES.items():
        assert not route.notes
        assert not any("cannot be known" in n for n in get_catalog().get(model_id)["notes"])
