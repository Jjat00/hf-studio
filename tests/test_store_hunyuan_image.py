"""HY Image 3.5 Preview (Hunyuan) en APIMart (`store/hunyuan_image.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.registry import PROVIDERS
from tests.test_routes import _prices, route_of, sample


def test_hy_image_goes_to_the_image_endpoint_with_one_image():
    assert APIMartProvider._submit_path("hy-image-v3.5-preview") == "/v1/images/generations"
    mid = "tencent/hy-image-3.5-preview/text-to-image"
    route = route_of("apimart", mid)
    logical = {**sample(mid), "aspect_ratio": "4:5", "seed": 42, "negative_prompt": "text"}
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "size": "4:5",
                                        "resolution": "1K", "seed": 42, "negative_prompt": "text",
                                        "n": 1}  # fmt: skip
    assert route.price(logical, {}, _prices("apimart")) == 0.0192
    assert route.price({**logical, "resolution": "4k"}, {}, _prices("apimart")) == 0.0256
    assert "tencent/hy-image-3.5-preview/text-to-image" not in PROVIDERS["kie"].routes()


def test_hy_image_edit_follows_the_reference_by_default():
    mid = "tencent/hy-image-3.5-preview/edit"
    route = route_of("apimart", mid)
    out = route.translate({**sample(mid), "resolution": "2k"})
    assert out["size"] == "auto" and out["resolution"] == "2K" and len(out["image_urls"]) == 1
    schema = store.models()[mid]["input_schema"]
    assert schema["properties"]["image_urls"]["maxItems"] == 5
    with pytest.raises(ProviderError):
        route.translate({**sample(mid), "num_images": 2})
