"""Wan 2.7 Image y Wan 2.7 Image Pro en las tiendas (`store/wan_image.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from tests.test_routes import _prices, route_of, sample


def _unsupported(route, logical: dict) -> None:
    with pytest.raises(ProviderError) as info:
        route.translate(logical, frozenset(logical))
    assert info.value.kind == "unsupported"


def test_wan_image_text_to_image_on_both_stores_is_explicit():
    mid = "wan/v2.7-image/text-to-image"
    logical = sample(mid)
    am = route_of("apimart", mid).translate(logical)
    assert am == {"prompt": "a red fox running through snow", "resolution": "2K", "n": 1, "enable_sequential": False,
                  "size": "1:1", "thinking_mode": True, "watermark": False}  # fmt: skip
    kie = route_of("kie", mid).translate(logical)
    assert kie == {"prompt": "a red fox running through snow", "resolution": "2K", "n": 1,
                   "enable_sequential": False, "aspect_ratio": "1:1", "thinking_mode": True,
                   "watermark": False}  # fmt: skip
    assert route_of("apimart", mid).price({**logical, "num_images": 3}, {}, _prices("apimart")) == 0.0648
    assert route_of("kie", mid).price(logical, {}, _prices("kie")) == 0.024
    assert "wan2.7-image-pro" in store.apimart_image_models()


def test_wan_image_edit_sends_the_images_with_each_store_name():
    mid = "wan/v2.7-image-pro/edit"
    logical = {**sample(mid), "image_urls": ["https://x/a.png", "https://x/b.png"]}
    assert route_of("apimart", mid).translate(logical)["image_urls"] == ["https://x/a.png", "https://x/b.png"]
    out = route_of("kie", mid).translate(logical)
    assert out["input_urls"] == ["https://x/a.png", "https://x/b.png"] and "image_urls" not in out
    assert route_of("kie", mid).price(logical, {}, _prices("kie")) == 0.06


def test_wan_image_values_without_equivalent_are_unsupported():
    mid = "wan/v2.7-image-pro/text-to-image"
    logical = sample(mid)
    _unsupported(route_of("apimart", mid), {**logical, "aspect_ratio": "21:9"})
    _unsupported(route_of("kie", mid), {**logical, "aspect_ratio": "3:2"})
    _unsupported(route_of("kie", mid), {**logical, "negative_prompt": "blur"})
    for name in ("apimart", "kie"):
        route = route_of(name, mid)
        _unsupported(route, {**logical, "num_images": 6})  # más de 4 sin modo secuencial
        _unsupported(route, {**logical, "enable_sequential": True, "resolution": "4k"})
        assert route.translate({**logical, "enable_sequential": True, "num_images": 8})["n"] == 8
