"""GPT Image 2.6 en las tiendas (`store/gpt_image_2_6.py`): APIMart (canal ext) y KIE (Economy). Sin gastar."""

from __future__ import annotations

import json
from pathlib import Path

from hf_studio.catalog import get_catalog
from hf_studio.providers.routes import with_defaults
from hf_studio.store import apimart_image_models
from hf_studio.store import gpt_image_2_6 as g

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
IMG = "https://cdn.test/a.png"
ROUTES = {"apimart": g.apimart(), "kie": g.kie()}
BASE = "openai/gpt-image-2.6"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a lighthouse", **extra})


def body(provider: str, model_id: str, **extra) -> dict:
    return ROUTES[provider][model_id].translate(logical(model_id, **extra))


def price(provider: str, model_id: str, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), {}, PRICES[provider])


def test_models_and_routes():
    ids = {m["id"] for m in g.MODELS}
    assert ids == {
        f"{BASE}/{v}/{m}" for v in ("flare", "sunburst", "economy") for m in ("text-to-image", "edit")
    }
    assert set(ROUTES["apimart"]) == {i for i in ids if "/economy/" not in i}
    assert set(ROUTES["kie"]) == {i for i in ids if "/economy/" in i}
    assert all(get_catalog().get(i)["store"] for i in ids)
    assert "gpt-image-2.6-ext" in apimart_image_models()


def test_apimart_ext():
    assert body("apimart", f"{BASE}/sunburst/edit", image_urls=[IMG], aspect_ratio="16:9", quality="high") == {
        "prompt": "a lighthouse", "size": "16:9", "quality": "high", "complexity": "high",
        "output_format": "png", "image_urls": [IMG], "version": "sunburst", "resolution": "1k", "n": 1,
    }  # fmt: skip
    assert ROUTES["apimart"][f"{BASE}/flare/text-to-image"].official is False
    assert price("apimart", f"{BASE}/flare/text-to-image") == 0.0085
    assert price("apimart", f"{BASE}/sunburst/edit", image_urls=[IMG]) == 0.0085


def test_kie_economy():
    assert body("kie", f"{BASE}/economy/edit", image_urls=[IMG], background="transparent") == {
        "prompt": "a lighthouse", "aspect_ratio": "auto", "background": "transparent", "input_urls": [IMG],
    }  # fmt: skip
    assert ROUTES["kie"][f"{BASE}/economy/text-to-image"].model == "gpt-image-2-6/economy-text-to-image"
    assert price("kie", f"{BASE}/economy/text-to-image") == 0.025
    assert price("kie", f"{BASE}/economy/edit", image_urls=[IMG]) == 0.025
