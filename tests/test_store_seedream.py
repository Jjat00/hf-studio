"""Seedream (ByteDance) en APIMart y KIE: cuerpos traducidos, precios y casos sin equivalente. Sin gastar créditos."""

from __future__ import annotations

import json

import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import seedream
from tests.test_routes import FIXTURES

PRICES = {p: json.loads((FIXTURES / f"prices_{p}.json").read_text()) for p in ("apimart", "kie")}
SCHEMAS = {m["id"]: m["input_schema"] for m in seedream.MODELS}
IMG = ["https://cdn.test/a.png", "https://cdn.test/b.png"]


def run(provider: str, model_id: str, **fields):
    """(modelo en el proveedor, cuerpo traducido, precio) de una entrada con los valores por defecto."""
    (route,) = routes_for(PROVIDERS[provider].routes(), model_id)
    logical = with_defaults(SCHEMAS[model_id], {"prompt": "a fox", **fields})
    return (
        route.model,
        route.translate(logical, frozenset({"prompt", *fields})),
        route.price(logical, {}, PRICES[provider]),
    )


def unsupported(provider: str, model_id: str, **fields) -> None:
    with pytest.raises(ProviderError) as info:
        run(provider, model_id, **fields)
    assert info.value.kind == "unsupported"


def test_every_version_and_mode_is_listed():
    assert sorted(SCHEMAS) == sorted(
        [f"bytedance/seedream-{v}/{m}" for v in ("4.0", "4.5", "5.0-lite", "5.0-flash", "5.0-pro")
         for m in ("text-to-image", "edit")] + ["bytedance/seedream-3.0/text-to-image"]
    )  # fmt: skip
    assert seedream.APIMART_IMAGE_MODELS == {
        "seedream-4-0", "seedream-4-5", "seedream-5-0-lite", "seedream-5-0-flash", "seedream-5-0-pro",
    }  # fmt: skip
    for model in seedream.APIMART_IMAGE_MODELS:
        assert APIMartProvider._submit_path(model) == "/v1/images/generations"


def test_seedream_3_runs_on_kie_only_with_its_size_presets():
    mid = "bytedance/seedream-3.0/text-to-image"
    assert not routes_for(PROVIDERS["apimart"].routes(), mid)
    assert run("kie", mid, aspect_ratio="9:16", seed=7) == (
        "bytedance/seedream",
        {"prompt": "a fox", "image_size": "portrait_16_9", "guidance_scale": 2.5, "seed": 7},
        0.0175,
    )


def test_seedream_4_on_both_stores():
    mid = "bytedance/seedream-4.0/edit"
    assert run("apimart", mid, image_urls=IMG, aspect_ratio="16:9", resolution="4k") == (
        "seedream-4-0",
        {"prompt": "a fox", "size": "16:9", "resolution": "4K", "image_urls": IMG},
        0.0195,
    )
    assert run("kie", mid, image_urls=IMG, aspect_ratio="2:3") == (
        "bytedance/seedream-v4-edit",
        {"prompt": "a fox", "image_size": "portrait_3_2", "image_resolution": "2K", "image_urls": IMG},
        0.025,
    )
    t2i = "bytedance/seedream-4.0/text-to-image"
    assert run("kie", t2i)[2] == 0.025
    # La semilla y los prompts largos solo los toma KIE; 2:1 y más de 10 imágenes solo APIMart.
    unsupported("apimart", t2i, seed=3)
    unsupported("apimart", t2i, prompt="x" * 1001)
    unsupported("kie", t2i, aspect_ratio="2:1")
    unsupported("kie", mid, image_urls=[f"https://cdn.test/{n}.png" for n in range(11)])
    unsupported("kie", mid, image_urls=IMG, aspect_ratio="auto")


def test_seedream_4_5_and_lite_map_resolution_to_kie_quality():
    assert run("kie", "bytedance/seedream-4.5/text-to-image", resolution="4k") == (
        "seedream/4.5-text-to-image", {"prompt": "a fox", "aspect_ratio": "1:1", "quality": "high"}, 0.0325
    )  # fmt: skip
    assert run("kie", "bytedance/seedream-5.0-lite/edit", image_urls=IMG, resolution="3k") == (
        "seedream/5-lite-image-to-image",
        {
            "prompt": "a fox",
            "aspect_ratio": "1:1",
            "quality": "high",
            "output_format": "jpeg",
            "image_urls": IMG,
        },
        0.0275,
    )
    assert run("apimart", "bytedance/seedream-5.0-lite/text-to-image", output_format="png") == (
        "seedream-5-0-lite",
        {"prompt": "a fox", "size": "1:1", "resolution": "2K", "output_format": "png"},
        0.028,
    )
    unsupported("apimart", "bytedance/seedream-5.0-lite/text-to-image", aspect_ratio="9:21")


def test_seedream_5_pro_prices_by_tier_and_extra_references():
    mid = "bytedance/seedream-5.0-pro/edit"
    _, body, usd = run("kie", mid, image_urls=IMG, resolution="2k")
    assert body == {"prompt": "a fox", "aspect_ratio": "1:1", "quality": "high", "output_format": "jpeg",
                    "image_urls": IMG}  # fmt: skip
    assert usd == round(0.07 + 0.0025, 4)  # la segunda referencia tiene recargo
    assert run("apimart", mid, image_urls=IMG, resolution="1.5k")[1:] == (
        {"prompt": "a fox", "size": "1:1", "resolution": "1.5K", "output_format": "jpeg", "image_urls": IMG},
        0.0293,  # 1.5K cuesta como 1K
    )
    assert run("apimart", mid, image_urls=IMG, resolution="2k")[2] == 0.0585
    unsupported("kie", mid, image_urls=IMG, resolution="1.5k")


def test_seedream_5_flash_sends_kie_size():
    assert run(
        "kie", "bytedance/seedream-5.0-flash/text-to-image", resolution="1.5k", aspect_ratio="21:9"
    ) == (
        "seedream/5-flash-text-to-image",
        {"prompt": "a fox", "aspect_ratio": "21:9", "size": "1.5K", "output_format": "jpeg"},
        0.0162,
    )
    assert run("apimart", "bytedance/seedream-5.0-flash/edit", image_urls=IMG, aspect_ratio="auto")[1:] == (
        {"prompt": "a fox", "size": "auto", "resolution": "1K", "output_format": "jpeg", "image_urls": IMG},
        0.0137,
    )
    unsupported("apimart", "bytedance/seedream-5.0-flash/text-to-image", aspect_ratio="auto")
