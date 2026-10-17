"""GPT Image 2, GPT Image 1.5 y GPT-4o Image en APIMart y KIE (`store/openai_image.py`). Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.kie import KIEProvider
from hf_studio.providers.routes import with_defaults
from hf_studio.store import openai_image
from tests.test_providers import KEYS, mock, settings

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {p: json.loads((FIXTURES / f"prices_{p}.json").read_text()) for p in ("apimart", "kie")}
IMG = "https://cdn.test/a.png"


def logical(model_id: str, **values) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **values})


def translate(provider: str, model_id: str, **values) -> dict:
    route = getattr(openai_image, provider)()[model_id]
    return route.translate(logical(model_id, **values), frozenset({"prompt", *values}))


def price(provider: str, model_id: str, **values) -> float | None:
    route = getattr(openai_image, provider)()[model_id]
    return route.price(logical(model_id, **values), {}, PRICES[provider])


def unsupported(provider: str, model_id: str, **values) -> None:
    with pytest.raises(ProviderError) as info:
        translate(provider, model_id, **values)
    assert info.value.kind == "unsupported"


# --- GPT Image 2 ----------------------------------------------------------------------------------


def test_gpt_image_2_on_apimart():
    assert translate("apimart", "openai/gpt-image-2/text-to-image") == {
        "prompt": "a fox", "size": "1:1", "resolution": "1k", "n": 1,
    }  # fmt: skip
    unsupported("apimart", "openai/gpt-image-2/text-to-image", aspect_ratio="auto")  # APIMart lo vuelve 1:1
    assert translate("apimart", "openai/gpt-image-2/edit", image_urls=[IMG], aspect_ratio="9:21",
                     resolution="4k") == {
        "prompt": "a fox", "size": "9:21", "resolution": "4k", "image_urls": [IMG], "n": 1,
    }  # fmt: skip
    assert price("apimart", "openai/gpt-image-2/text-to-image") == 0.0085
    assert price("apimart", "openai/gpt-image-2/text-to-image", resolution="4k") == 0.022
    route = openai_image.apimart()["openai/gpt-image-2/text-to-image"]
    assert route.model == "gpt-image-2" and route.official is False
    assert APIMartProvider._submit_path("gpt-image-2") == "/v1/images/generations"


def test_gpt_image_2_apimart_limits():
    unsupported("apimart", "openai/gpt-image-2/text-to-image", background="transparent")
    unsupported("apimart", "openai/gpt-image-2/edit", image_urls=[IMG] * 16)


def test_gpt_image_2_on_kie():
    assert translate("kie", "openai/gpt-image-2/text-to-image") == {
        "prompt": "a fox", "aspect_ratio": "1:1", "resolution": "1K",
    }  # fmt: skip
    assert translate("kie", "openai/gpt-image-2/edit", image_urls=[IMG] * 16, background="transparent") == {
        "prompt": "a fox", "aspect_ratio": "auto", "resolution": "1K", "background": "transparent",
        "input_urls": [IMG] * 16,
    }  # fmt: skip
    routes = openai_image.kie()
    assert routes["openai/gpt-image-2/text-to-image"].model == "gpt-image-2-text-to-image"
    assert routes["openai/gpt-image-2/edit"].model == "gpt-image-2-image-to-image"
    assert price("kie", "openai/gpt-image-2/text-to-image") == 0.03
    assert price("kie", "openai/gpt-image-2/edit", image_urls=[IMG], resolution="2k") == 0.05


def test_gpt_image_2_kie_limits():
    unsupported("kie", "openai/gpt-image-2/text-to-image", resolution="2k", background="opaque")
    unsupported("kie", "openai/gpt-image-2/text-to-image", resolution="2k", aspect_ratio="4:5")
    unsupported("kie", "openai/gpt-image-2/text-to-image", resolution="4k", aspect_ratio="9:21")
    # 5:4 sí existe en 4K y cualquier relación en 1K.
    assert translate("kie", "openai/gpt-image-2/text-to-image", resolution="4k", aspect_ratio="5:4")
    assert translate("kie", "openai/gpt-image-2/text-to-image", aspect_ratio="1:3")


# --- GPT Image 1.5 --------------------------------------------------------------------------------


def test_gpt_image_1_5_on_kie():
    assert translate("kie", "openai/gpt-image-1.5/text-to-image") == {
        "prompt": "a fox", "aspect_ratio": "1:1", "quality": "medium",
    }  # fmt: skip
    assert translate("kie", "openai/gpt-image-1.5/edit", image_urls=[IMG], quality="high") == {
        "prompt": "a fox", "aspect_ratio": "1:1", "quality": "high", "input_urls": [IMG],
    }  # fmt: skip
    routes = openai_image.kie()
    assert routes["openai/gpt-image-1.5/text-to-image"].model == "gpt-image/1.5-text-to-image"
    assert routes["openai/gpt-image-1.5/edit"].model == "gpt-image/1.5-image-to-image"
    assert price("kie", "openai/gpt-image-1.5/text-to-image") == 0.02
    assert price("kie", "openai/gpt-image-1.5/edit", image_urls=[IMG], quality="high") == 0.11
    unsupported("kie", "openai/gpt-image-1.5/text-to-image", aspect_ratio="16:9")
    assert "openai/gpt-image-1.5/text-to-image" not in openai_image.apimart()


# --- GPT-4o Image ---------------------------------------------------------------------------------


def test_gpt_4o_image_on_kie():
    assert translate("kie", "openai/gpt-4o-image/text-to-image") == {"prompt": "a fox", "size": "1:1"}
    assert translate("kie", "openai/gpt-4o-image/edit", image_urls=[IMG], aspect_ratio="3:2") == {
        "prompt": "a fox", "size": "3:2", "files_url": [IMG],
    }  # fmt: skip
    assert price("kie", "openai/gpt-4o-image/text-to-image") == 0.03
    assert price("kie", "openai/gpt-4o-image/edit", image_urls=[IMG]) == 0.03
    unsupported("kie", "openai/gpt-4o-image/text-to-image", aspect_ratio="16:9")
    unsupported("kie", "openai/gpt-4o-image/text-to-image", seed=7)


async def test_gpt_4o_image_uses_the_unified_kie_api():
    """La versión nueva de 4o Image va por `jobs/createTask` con `model: 4o-image-api` (doc de KIE)."""
    assert "4o-image-api" not in getattr(openai_image, "KIE_ENDPOINTS", {})
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.method == "POST":
            assert json.loads(request.content) == {
                "model": "4o-image-api",
                "input": {"prompt": "A beautiful sunset over the mountains", "size": "1:1"},
            }
            return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task12345"}})
        return httpx.Response(200, json={"code": 200, "data": {
            "taskId": "task12345", "state": "success",
            "resultJson": json.dumps({"resultUrls": ["https://example.com/result/image1.png"]}),
        }})  # fmt: skip

    kie = KIEProvider(settings(**KEYS), mock(handler))
    body = translate("kie", "openai/gpt-4o-image/text-to-image")
    submitted = await kie.submit_job(
        "4o-image-api", {**body, "prompt": "A beautiful sunset over the mountains"}
    )
    polled = await kie.poll_job(submitted.request_id, submitted.status_url)
    assert polled.status == "completed"
    assert polled.outputs[0]["url"] == "https://example.com/result/image1.png"
    assert seen == ["/api/v1/jobs/createTask", "/api/v1/jobs/recordInfo"]
    await kie.aclose()
