"""Ideogram V3 e Ideogram Character en KIE (`store/ideogram.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from tests.test_routes import _prices, route_of, sample


def test_ideogram_v3_text_to_image_body_and_price():
    mid = "ideogram/v3/text-to-image"
    route = route_of("kie", mid)
    logical = sample(mid)
    assert route.translate(logical) == {
        "prompt": "a red fox running through snow", "rendering_speed": "BALANCED", "style": "AUTO",
        "expand_prompt": True, "image_size": "square_hd",
    }  # fmt: skip
    assert route.price(logical, {}, _prices("kie")) == 0.035
    assert route.price({**logical, "rendering_speed": "TURBO"}, {}, _prices("kie")) == 0.0175
    assert mid not in PROVIDERS["apimart"].routes()


def test_ideogram_character_sends_the_character_as_a_list_and_counts_as_text():
    mid = "ideogram/v3/character-remix"
    route = route_of("kie", mid)
    logical = {
        **sample(mid),
        "num_images": 2,
        "rendering_speed": "QUALITY",
        "image_urls": ["https://x/style.png"],
    }
    out = route.translate(logical)
    assert out["reference_image_urls"] == ["https://example.com/hf-studio-placeholder.png"]
    assert (
        out["num_images"] == "2" and out["image_urls"] == ["https://x/style.png"] and out["strength"] == 0.8
    )
    assert "character_image_url" not in out
    assert route.price(logical, {}, _prices("kie")) == 0.24
    edit = route_of("kie", "ideogram/v3/character-edit").translate(sample("ideogram/v3/character-edit"))
    assert edit["mask_url"].endswith(".png") and edit["image_url"].endswith(".png")


def test_ideogram_fields_from_other_variants_are_unsupported():
    for mid, extra in (("ideogram/v3/edit", {"num_images": 2}), ("ideogram/v3/text-to-image", {"num_images": 2}),
                       ("ideogram/v3/character-edit", {"image_size": "square"})):  # fmt: skip
        logical = {**sample(mid), **extra}
        with pytest.raises(ProviderError) as info:
            route_of("kie", mid).translate(logical, frozenset(logical))
        assert info.value.kind == "unsupported"
