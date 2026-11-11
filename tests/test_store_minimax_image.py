"""MiniMax H3 Image en KIE (`store/minimax_image.py`). Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio import store
from hf_studio.catalog import CATALOG_PATH
from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from tests.test_routes import _prices, route_of, sample


def test_minimax_h3_image_ids_do_not_clash_with_the_higgsfield_video():
    higgsfield = {m["id"] for m in json.loads(Path(CATALOG_PATH).read_text())["models"]}
    for mode in ("text-to-image", "edit"):
        assert f"minimax/h3-image/{mode}" in store.models()
        assert f"minimax/h3-image/{mode}" not in higgsfield
        assert f"minimax/h3-image/{mode}" not in PROVIDERS["apimart"].routes()


def test_text_to_image_body_and_price_by_tier():
    mid = "minimax/h3-image/text-to-image"
    route = route_of("kie", mid)
    logical = sample(mid)
    assert route.model == "minimax-h3/text-to-image"
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "aspect_ratio": "1:1",
                                        "resolution": "2K", "expand_prompt": True,
                                        "output_format": "png"}  # fmt: skip
    assert route.price(logical, {}, _prices("kie")) == 0.009
    assert route.price({**logical, "resolution": "1k"}, {}, _prices("kie")) == 0.009
    assert route.price({**logical, "resolution": "4k"}, {}, _prices("kie")) == 0.0275


def test_edit_charges_every_reference_image():
    mid = "minimax/h3-image/edit"
    route = route_of("kie", mid)
    refs = ["https://x/a.png", "https://x/b.png", "https://x/c.png"]
    logical = {**sample(mid), "image_urls": refs, "resolution": "4k"}
    out = route.translate(logical)
    assert route.model == "minimax-h3/image-edit"
    assert out["image_urls"] == refs and out["aspect_ratio"] == "auto" and out["resolution"] == "4K"
    assert route.price(logical, {}, _prices("kie")) == 0.035  # 0.0275 + 3 × 0.0025
    assert route.price({**logical, "image_urls": refs[:1], "resolution": "2k"}, {}, _prices("kie")) == 0.0115
    assert route.price(logical, {}, {}) is None


def test_fields_without_an_equivalent_are_unsupported():
    mid = "minimax/h3-image/text-to-image"
    with pytest.raises(ProviderError) as info:
        route_of("kie", mid).translate({**sample(mid), "width": 1920, "height": 1080})
    assert info.value.kind == "unsupported"
