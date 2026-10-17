"""Qwen Image 1, 2.0, 2.0 Pro y 2.1 en las tiendas (`store/qwen_image.py`). Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from tests.test_routes import _prices, chosen, route_of, sample


def _unsupported(route, logical: dict, asked: frozenset | None = None) -> None:
    with pytest.raises(ProviderError) as info:
        route.translate(logical, asked if asked is not None else frozenset(logical))
    assert info.value.kind == "unsupported"


def test_qwen_2_0_on_apimart_sends_the_image_endpoint_body():
    mid = "alibaba/qwen-image-2.0/edit"
    route = route_of("apimart", mid)
    logical = {**sample(mid), "num_images": 3, "aspect_ratio": "16:9"}
    out = route.translate(logical, chosen(mid, "num_images", "aspect_ratio"))
    assert out == {"prompt": "a red fox running through snow", "size": "16:9", "resolution": "1K", "n": 3,
                   "image_urls": ["https://example.com/hf-studio-placeholder.png"]}  # fmt: skip
    assert route.price(logical, {}, _prices("apimart")) == 0.06
    assert "qwen-image-2.0-pro" in store.apimart_image_models()
    _unsupported(route, {**logical, "aspect_ratio": "21:9"})  # solo en KIE
    _unsupported(route, {**logical, "seed": 7})  # APIMart no tiene semilla


def test_qwen_2_0_on_kie_keeps_only_what_it_can_reproduce():
    mid = "alibaba/qwen-image-2.0/text-to-image"
    route = route_of("kie", mid)
    logical = {**sample(mid), "seed": 5}
    out = route.translate(logical, chosen(mid, "seed"))
    assert out == {"prompt": "a red fox running through snow", "image_size": "1:1", "seed": 5,
                   "output_format": "png"}  # fmt: skip
    assert route.price(logical, {}, _prices("kie")) == 0.028
    _unsupported(
        route, {**logical, "resolution": "2k"}, chosen(mid, "resolution")
    )  # tamaño desconocido en KIE
    _unsupported(route, logical, chosen(mid, "resolution"))  # 1k elegido a mano tampoco se garantiza
    _unsupported(route, {**logical, "num_images": 2})
    _unsupported(route, {**logical, "aspect_ratio": "3:2"})
    _unsupported(route, {**logical, "negative_prompt": "text"})
    edit = route_of("kie", "alibaba/qwen-image-2.0/edit")
    out = edit.translate(sample("alibaba/qwen-image-2.0/edit"), chosen("alibaba/qwen-image-2.0/edit"))
    assert (
        out["image_url"] == ["https://example.com/hf-studio-placeholder.png"] and out["image_size"] == "1:1"
    )


def test_qwen_2_0_pro_runs_only_on_apimart():
    from hf_studio.providers.registry import PROVIDERS

    assert "alibaba/qwen-image-2.0-pro/text-to-image" not in PROVIDERS["kie"].routes()
    route = route_of("apimart", "alibaba/qwen-image-2.0-pro/text-to-image")
    assert route.translate(sample("alibaba/qwen-image-2.0-pro/text-to-image"))["resolution"] == "1K"


def test_qwen_image_1_and_edit_send_kie_diffusion_parameters():
    route = route_of("kie", "alibaba/qwen-image/text-to-image")
    out = route.translate(sample("alibaba/qwen-image/text-to-image"))
    assert out == {"prompt": "a red fox running through snow", "image_size": "square_hd", "num_inference_steps": 30,
                   "guidance_scale": 2.5, "acceleration": "none", "output_format": "png"}  # fmt: skip
    edit = route_of("kie", "alibaba/qwen-image-edit/edit")
    logical = {**sample("alibaba/qwen-image-edit/edit"), "num_images": 2}
    out = edit.translate(logical)
    assert out["num_images"] == "2" and out["image_url"].endswith(".png") and out["num_inference_steps"] == 25
    assert edit.price(logical, {}, _prices("kie")) == 0.05
    _unsupported(route_of("kie", "alibaba/qwen-image/image-to-image"),
                 {**sample("alibaba/qwen-image/image-to-image"), "image_urls": ["https://x/a.png"]})  # fmt: skip


def test_qwen_2_1_checks_masks_and_transparency():
    mid = "alibaba/qwen-image-2.1/edit"
    route = route_of("kie", mid)
    logical = {**sample(mid), "resolution": "2k", "mask_url": "https://x/mask.png"}
    out = route.translate(logical)
    assert (
        out["resolution"] == "2K"
        and out["aspect_ratio"] == "auto"
        and out["mask_url"] == "https://x/mask.png"
    )
    assert route.price(logical, {}, _prices("kie")) == 0.04
    _unsupported(route, {**logical, "image_urls": ["https://x/a.png", "https://x/b.png"]})
    _unsupported(route, {**logical, "background": "transparent", "output_format": "jpeg"})
