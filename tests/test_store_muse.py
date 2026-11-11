"""Muse Image en APIMart (`store/muse.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from tests.test_routes import _prices, route_of, sample


def test_muse_text_to_image_sends_the_ratio_and_one_image():
    assert APIMartProvider._submit_path("muse-image-ext") == "/v1/images/generations"
    mid = "muse/muse-image/text-to-image"
    route = route_of("apimart", mid)
    logical = sample(mid)
    assert route.translate(logical) == {
        "prompt": "a red fox running through snow",
        "aspect_ratio": "1:1",
        "n": 1,
    }
    assert route.price(logical, {}, _prices("apimart")) == 0.0048


def test_muse_edit_omits_auto_and_rejects_fields_it_does_not_take():
    mid = "muse/muse-image/edit"
    route = route_of("apimart", mid)
    out = route.translate(sample(mid))
    assert "aspect_ratio" not in out and out["image_urls"] and out["n"] == 1
    assert route.translate({**sample(mid), "aspect_ratio": "9:16"})["aspect_ratio"] == "9:16"
    assert store.models()[mid]["input_schema"]["properties"]["image_urls"]["maxItems"] == 9
    for extra in ({"seed": 3}, {"negative_prompt": "text"}, {"resolution": "2k"}):
        with pytest.raises(ProviderError):
            route.translate({**sample(mid), **extra})
