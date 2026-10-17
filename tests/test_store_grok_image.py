"""Grok Imagine (imagen) en canales que no son Grok Imagine 2.0 (`store/grok_image.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from tests.test_routes import _prices, route_of, sample


def _unsupported(route, logical: dict) -> None:
    with pytest.raises(ProviderError) as info:
        route.translate(logical, frozenset(logical))
    assert info.value.kind == "unsupported"


def test_official_grok_image_on_apimart_body_and_input_surcharge():
    mid = "xai/grok-imagine-image/edit"
    route = route_of("apimart", mid)
    logical = {
        **sample(mid),
        "resolution": "2k",
        "num_images": 2,
        "image_urls": ["https://x/a.png", "https://x/b.png"],
    }
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "aspect_ratio": "auto",
                                        "resolution": "2k", "n": 2,
                                        "image_urls": ["https://x/a.png", "https://x/b.png"]}  # fmt: skip
    assert route.price(logical, {}, _prices("apimart")) == round(0.016 * 2 + 0.0016 * 2, 4)
    quality = route_of("apimart", "xai/grok-imagine-image-quality/text-to-image")
    assert (
        quality.price(sample("xai/grok-imagine-image-quality/text-to-image"), {}, _prices("apimart")) == 0.04
    )
    assert {"grok-imagine-image", "grok-imagine-image-quality"} <= store.apimart_image_models()


def test_grok_1_5_ext_channel_is_unofficial():
    mid = "xai/grok-imagine-image/v1.5/text-to-image"
    route = route_of("apimart", mid)
    assert route.official is False and route.model == "grok-imagine-1.5-apimart"
    logical = {**sample(mid), "num_images": 4}
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "size": "1:1", "n": 4}
    assert route.price(logical, {}, _prices("apimart")) == 0.06
    edit = route_of("apimart", "xai/grok-imagine-image/v1.5/edit")
    assert edit.translate(sample("xai/grok-imagine-image/v1.5/edit"))["image_urls"]
    _unsupported(route, {**logical, "resolution": "2k"})


def test_grok_imagine_on_kie_maps_quality_mode():
    mid = "xai/grok-imagine/text-to-image"
    route = route_of("kie", mid)
    logical = sample(mid)
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "aspect_ratio": "1:1",
                                        "enable_pro": False}  # fmt: skip
    assert route.price(logical, {}, _prices("kie")) == 0.02
    assert route.translate({**logical, "mode": "quality"})["enable_pro"] is True
    assert route.price({**logical, "mode": "quality"}, {}, _prices("kie")) == 0.025
    _unsupported(route, {**logical, "num_images": 2})
    i2i = route_of("kie", "xai/grok-imagine/image-to-image")
    assert i2i.translate(sample("xai/grok-imagine/image-to-image"))["image_urls"]
    _unsupported(i2i, {**sample("xai/grok-imagine/image-to-image"), "aspect_ratio": "1:1"})
