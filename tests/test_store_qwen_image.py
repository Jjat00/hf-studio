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


def test_qwen_2_0_does_not_run_on_kie():
    # KIE no tiene resolución ni publica su tamaño de salida: no garantiza el 1k del esquema (revisión 88).
    for mode in ("text-to-image", "edit"):
        assert f"alibaba/qwen-image-2.0/{mode}" not in store.routes("kie")


def test_qwen_2_0_pro_runs_only_on_apimart():
    from hf_studio.providers.registry import PROVIDERS

    assert "alibaba/qwen-image-2.0-pro/text-to-image" not in PROVIDERS["kie"].routes()
    route = route_of("apimart", "alibaba/qwen-image-2.0-pro/text-to-image")
    assert route.translate(sample("alibaba/qwen-image-2.0-pro/text-to-image"))["resolution"] == "1K"


def test_qwen_image_1_image_to_image_on_kie_and_no_per_megapixel_models():
    mid = "alibaba/qwen-image/image-to-image"
    route = route_of("kie", mid)
    out = route.translate(sample(mid))
    assert out["image_url"] and out["strength"] == 0.8 and out["num_inference_steps"] == 30
    assert route.price(sample(mid), {}, _prices("kie")) == 0.02
    _unsupported(route, {**sample(mid), "image_urls": ["https://x/a.png"]})
    # KIE cobra Qwen Image texto a imagen y Qwen Image Edit por megapíxel sin publicar el tamaño de cada preset.
    assert "alibaba/qwen-image/text-to-image" not in store.models()
    assert "alibaba/qwen-image-edit/edit" not in store.models()


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
