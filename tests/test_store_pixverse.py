"""PixVerse V6 Max en las tiendas (`store/pixverse.py`): modelo propio (no V6), traducción fiel y precio con
las tablas de tests/fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import pixverse

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
ROUTES = {"apimart": pixverse.apimart(), "kie": pixverse.kie()}
T2V, I2V = pixverse.T2V, pixverse.I2V
IMG = "https://cdn.test/a.png"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(
        get_catalog().get(model_id)["input_schema"], {"prompt": "a fox in the snow", **extra}
    )


def body(provider: str, model_id: str, **extra) -> dict:
    return ROUTES[provider][model_id].translate(logical(model_id, **extra), frozenset({"prompt", *extra}))


def price(provider: str, model_id: str, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), {}, PRICES[provider])


def test_v6_max_is_a_store_model_apart_from_v6():
    for model_id in (T2V, I2V):
        model = get_catalog().get(model_id)
        assert model["store"] is True and model["family"] == "pixverse-v6-max"
        for provider in ("apimart", "kie"):
            assert routes_for(PROVIDERS[provider].routes(), model_id)
    # V6 sigue en sus propios ids de las tiendas.
    assert PROVIDERS["apimart"].routes()["pixverse/v6/text-to-video"].model == "pixverse-v6"
    assert PROVIDERS["kie"].routes()["pixverse/v6/text-to-video"].model == "pixverse-v6/text-to-video"


def test_text_to_video_bodies():
    assert body("apimart", T2V, aspect_ratio="21:9", seed=7) == {
        "prompt": "a fox in the snow", "duration": 5, "resolution": "720p", "audio": False, "seed": 7,
        "aspect_ratio": "21:9"}  # fmt: skip
    assert ROUTES["apimart"][T2V].model == "pixverse-v6-max"
    assert body("kie", T2V, generate_audio=True) == {
        "prompt": "a fox in the snow", "duration": 5, "quality": "720p", "generate_audio_switch": True,
        "aspect_ratio": "16:9"}  # fmt: skip
    assert ROUTES["kie"][T2V].model == "pixverse-v6-max/text-to-video"


def test_image_to_video_bodies_and_limits():
    out = body("apimart", I2V, image_url=IMG, resolution="1080p")
    assert out["image_urls"] == [IMG] and "aspect_ratio" not in out and "image_url" not in out
    kie = body("kie", I2V, image_url=IMG)
    assert kie["image_urls"] == [IMG] and kie["quality"] == "720p"
    assert ROUTES["kie"][I2V].model == "pixverse-v6-max/image-to-video"
    long_prompt = "x" * 3000  # APIMart: hasta 2048 caracteres en imagen a video; KIE: hasta 5000
    with pytest.raises(ProviderError) as info:
        body("apimart", I2V, image_url=IMG, prompt=long_prompt)
    assert info.value.kind == "unsupported"
    assert body("kie", I2V, image_url=IMG, prompt=long_prompt)["prompt"] == long_prompt
    with pytest.raises(ProviderError):  # ni último fotograma ni nada que el esquema no tenga
        ROUTES["apimart"][I2V].translate({**logical(I2V, image_url=IMG), "end_image_url": IMG})


def test_prices_per_second_by_resolution_and_audio():
    assert price("apimart", T2V, generate_audio=True) == round(0.0533336 * 5, 4)
    assert price("kie", T2V, generate_audio=True) == round(0.06 * 5, 4)
    assert price("apimart", I2V, image_url=IMG, resolution="1080p", duration=10) == round(0.0782224 * 10, 4)
    assert price("kie", I2V, image_url=IMG, resolution="1080p", duration=10) == round(0.088 * 10, 4)
    assert price("kie", T2V, resolution="360p", duration=1) == 0.024
    # Más caro que V6 a la misma resolución y audio: no se hace pasar por V6.
    v6 = with_defaults(get_catalog().get("pixverse/v6/text-to-video")["input_schema"],
                       {"prompt": "x", "generate_audio": True})  # fmt: skip
    v6_price = PROVIDERS["kie"].routes()["pixverse/v6/text-to-video"].price(v6, {}, PRICES["kie"])
    assert price("kie", T2V, generate_audio=True) > v6_price
