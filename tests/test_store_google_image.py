"""Imágenes de Google en las tiendas (`store/google_image.py`): Nano Banana e Imagen 4. Sin gastar créditos."""

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
from hf_studio.store import google_image as g
from tests.test_providers import KEYS, mock, settings

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
IMG = "https://cdn.test/a.png"
ROUTES = {"apimart": g.apimart(), "kie": g.kie()}


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def body(provider: str, model_id: str, **extra) -> dict:
    return ROUTES[provider][model_id].translate(logical(model_id, **extra))


def price(provider: str, model_id: str, **extra) -> float | None:
    return ROUTES[provider][model_id].price(logical(model_id, **extra), {}, PRICES[provider])


def refused(provider: str, model_id: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, model_id, **extra)
    assert info.value.kind == "unsupported"


def test_every_model_is_in_the_catalog_with_a_route():
    ids = {m["id"] for m in g.MODELS}
    assert len(ids) == 13
    for model_id in ids:
        assert get_catalog().get(model_id)["store"] is True
        assert model_id in ROUTES["apimart"] or model_id in ROUTES["kie"]
    # Imagen 4 Fast y Ultra solo están en KIE; el resto, en las dos tiendas
    assert set(ROUTES["kie"]) == ids
    assert set(ROUTES["apimart"]) == ids - {
        "google/imagen-4/fast/text-to-image",
        "google/imagen-4/ultra/text-to-image",
    }
    assert all(not r.official for r in ROUTES["apimart"].values())
    assert g.APIMART_IMAGE_MODELS == {r.model for r in ROUTES["apimart"].values()}
    for model in g.APIMART_IMAGE_MODELS:
        assert APIMartProvider._submit_path(model) == "/v1/images/generations"


@pytest.mark.parametrize(
    ("model_id", "apimart", "kie"),
    [
        ("google/nano-banana/text-to-image",
         {"prompt": "a fox", "size": "1:1"},
         {"prompt": "a fox", "aspect_ratio": "1:1"}),
        ("google/nano-banana-2/text-to-image",
         {"prompt": "a fox", "size": "1:1", "resolution": "1K"},
         {"prompt": "a fox", "aspect_ratio": "1:1", "resolution": "1K"}),
        ("google/nano-banana-2.1/text-to-image",
         {"prompt": "a fox", "size": "1:1", "resolution": "1K"},
         {"prompt": "a fox", "aspect_ratio": "1:1", "resolution": "1K"}),
        ("google/nano-banana-2-lite/text-to-image",
         {"prompt": "a fox", "size": "1:1", "n": 1},
         {"prompt": "a fox", "aspect_ratio": "1:1"}),
        ("google/nano-banana-pro/text-to-image",
         {"prompt": "a fox", "size": "1:1", "resolution": "1K"},
         {"prompt": "a fox", "aspect_ratio": "1:1", "resolution": "1K"}),
        ("google/imagen-4/text-to-image",
         {"prompt": "a fox", "size": "1:1"},
         {"prompt": "a fox", "aspect_ratio": "1:1"}),
    ],
)  # fmt: skip
def test_text_to_image_bodies(model_id, apimart, kie):
    assert body("apimart", model_id) == apimart
    assert body("kie", model_id) == kie


def test_edit_bodies_name_the_images_as_each_model_expects():
    for family in (
        "nano-banana",
        "nano-banana-2",
        "nano-banana-2.1",
        "nano-banana-2-lite",
        "nano-banana-pro",
    ):
        model_id = f"google/{family}/edit"
        sent = body("apimart", model_id, image_urls=[IMG])
        assert sent["image_urls"] == [IMG] and sent["size"] == "auto"
    assert body("kie", "google/nano-banana/edit", image_urls=[IMG]) == {
        "prompt": "a fox", "aspect_ratio": "auto", "image_urls": [IMG],
    }  # fmt: skip
    assert body("kie", "google/nano-banana-2-lite/edit", image_urls=[IMG])["image_urls"] == [IMG]
    for family in ("nano-banana-2", "nano-banana-2.1", "nano-banana-pro"):
        sent = body("kie", f"google/{family}/edit", image_urls=[IMG], resolution="4k")
        assert sent == {"prompt": "a fox", "aspect_ratio": "auto", "resolution": "4K", "image_input": [IMG]}
    assert ROUTES["kie"]["google/nano-banana/edit"].model == "google/nano-banana-edit"
    assert ROUTES["kie"]["google/nano-banana/text-to-image"].model == "google/nano-banana"


def test_google_search_only_runs_on_apimart():
    model_id = "google/nano-banana-2/text-to-image"
    assert body("apimart", model_id, google_search=True, google_image_search=True) == {
        "prompt": "a fox", "size": "1:1", "resolution": "1K", "google_search": True, "google_image_search": True,
    }  # fmt: skip
    refused("kie", model_id, google_search=True)


def test_imagen_seed_and_negative_prompt():
    kie = body("kie", "google/imagen-4/text-to-image", seed=42, negative_prompt="blur", aspect_ratio="auto")
    assert kie == {"prompt": "a fox", "negative_prompt": "blur", "aspect_ratio": "auto", "seed": "42"}
    assert body("kie", "google/imagen-4/fast/text-to-image", seed=42)["seed"] == 42  # entero en fast
    assert ROUTES["kie"]["google/imagen-4/ultra/text-to-image"].model == "google/imagen4-ultra"
    refused("apimart", "google/imagen-4/text-to-image", seed=42)
    refused("apimart", "google/imagen-4/text-to-image", negative_prompt="blur")
    refused("apimart", "google/imagen-4/text-to-image", aspect_ratio="auto")  # APIMart caería en 16:9


@pytest.mark.parametrize(
    ("provider", "model_id", "extra"),
    [
        ("apimart", "google/nano-banana/text-to-image", {"prompt": "x" * 1001}),
        ("apimart", "google/nano-banana/edit", {"image_urls": [IMG] * 15}),
        ("kie", "google/nano-banana/edit", {"image_urls": [IMG] * 11}),
        ("kie", "google/nano-banana-2/text-to-image", {"resolution": "0.5k"}),
        ("kie", "google/nano-banana-2/edit", {"image_urls": [IMG] * 11}),
        ("kie", "google/nano-banana-2.1/edit", {"image_urls": [IMG] * 11}),
        ("apimart", "google/nano-banana-2-lite/text-to-image", {"aspect_ratio": "1:8"}),
        ("kie", "google/nano-banana-2-lite/text-to-image", {"num_images": 2}),
        ("kie", "google/nano-banana-pro/edit", {"image_urls": [IMG] * 9}),
    ],
)  # fmt: skip
def test_requests_without_an_exact_equivalent_are_unsupported(provider, model_id, extra):
    refused(provider, model_id, **extra)


def test_prices_follow_resolution_and_count():
    assert price("apimart", "google/nano-banana/text-to-image") == 0.0125
    assert price("apimart", "google/nano-banana-2/text-to-image", resolution="0.5k") == 0.015
    assert price("apimart", "google/nano-banana-2/text-to-image", resolution="4k") == 0.025
    assert price("apimart", "google/nano-banana-2.1/text-to-image", resolution="2k") == 0.025
    assert price("apimart", "google/nano-banana-2-lite/text-to-image", num_images=3) == 0.0375
    # Pro en APIMart: `default` vale para 1K y 2K
    assert price("apimart", "google/nano-banana-pro/text-to-image", resolution="2k") == 0.03
    assert price("apimart", "google/nano-banana-pro/text-to-image", resolution="4k") == 0.04
    assert price("apimart", "google/imagen-4/text-to-image") == 0.04
    assert price("kie", "google/nano-banana/edit", image_urls=[IMG]) == 0.02
    assert price("kie", "google/nano-banana-2/text-to-image", resolution="2k") == 0.06
    assert price("kie", "google/nano-banana-2.1/text-to-image", resolution="4k") == 0.045
    assert price("kie", "google/nano-banana-pro/text-to-image", resolution="2k") == 0.09
    assert price("kie", "google/nano-banana-pro/text-to-image", resolution="4k") == 0.12
    assert price("kie", "google/nano-banana-2-lite/text-to-image") == 0.02
    assert price("kie", "google/imagen-4/fast/text-to-image") == 0.02
    assert price("kie", "google/imagen-4/ultra/text-to-image") == 0.06


async def test_kie_sends_nano_banana_2_through_the_unified_api():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"code": 200, "data": {"taskId": "t-1"}})

    kie = KIEProvider(settings(**KEYS), mock(handler))
    route = ROUTES["kie"]["google/nano-banana-2/edit"]
    args = route.translate(logical("google/nano-banana-2/edit", image_urls=[IMG]))
    submitted = await kie.submit_job(route.model, args, "https://cb")
    assert submitted.request_id == "t-1" and submitted.status_url is None
    assert sent == [("/api/v1/jobs/createTask", {
        "model": "nano-banana-2", "callBackUrl": "https://cb",
        "input": {"prompt": "a fox", "aspect_ratio": "auto", "resolution": "1K", "image_input": [IMG]},
    })]  # fmt: skip
