"""FLUX (Black Forest Labs) en APIMart y KIE: cuerpos traducidos, precios y casos sin equivalente. Sin gastar créditos."""

from __future__ import annotations

import json

import httpx
import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.kie import KIEProvider
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import flux
from tests.test_providers import KEYS, mock, settings
from tests.test_routes import FIXTURES

PRICES = {p: json.loads((FIXTURES / f"prices_{p}.json").read_text()) for p in ("apimart", "kie")}
SCHEMAS = {m["id"]: m["input_schema"] for m in flux.MODELS}
IMG = ["https://cdn.test/a.png", "https://cdn.test/b.png"]
BFL = "black-forest-labs"


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


def test_image_models_go_to_the_apimart_image_endpoint_and_video_does_not():
    assert flux.APIMART_IMAGE_MODELS == {
        "flux-2-flex", "flux-2-pro", "flux-2-max", "flux-3-image", "flux-kontext-pro", "flux-kontext-max",
    }  # fmt: skip
    for model in flux.APIMART_IMAGE_MODELS:
        assert APIMartProvider._submit_path(model) == "/v1/images/generations"
    assert APIMartProvider._submit_path("flux-3-video") == "/v1/videos/generations"
    assert {m["output"] for m in flux.MODELS if "/flux-3/" in m["id"] and m["id"].endswith("video")} == {
        "video"
    }


def test_flux_2_runs_on_apimart_only():
    mid = f"{BFL}/flux-2-pro/edit"
    assert run("apimart", mid, image_urls=IMG, resolution="4mp", seed=9) == (
        "flux-2-pro",
        {"prompt": "a fox", "size": "auto", "resolution": "4MP", "image_urls": IMG, "seed": 9},
        0.06,
    )
    # KIE no publica cuántos megapíxeles son sus 1K/2K: FLUX.2 no se ruta allí (revisión 87).
    for tier in ("pro", "flex"):
        for mode in ("text-to-image", "edit"):
            assert not routes_for(PROVIDERS["kie"].routes(), f"{BFL}/flux-2-{tier}/{mode}")


def test_flux_2_max_runs_on_apimart_only():
    mid = f"{BFL}/flux-2-max/text-to-image"
    assert not routes_for(PROVIDERS["kie"].routes(), mid)
    assert run("apimart", mid, resolution="2mp")[2] == 0.08
    unsupported("apimart", mid, negative_prompt="blur")


def test_flux_3_image_prices_by_tier():
    assert run("apimart", f"{BFL}/flux-3/edit", image_urls=IMG, resolution="4k") == (
        "flux-3-image",
        {"prompt": "a fox", "aspect_ratio": "auto", "resolution": "4K", "image_urls": IMG},
        0.4856,
    )
    assert run("apimart", f"{BFL}/flux-3/text-to-image", resolution="768sq")[2] == 0.0328
    unsupported("apimart", f"{BFL}/flux-3/text-to-image", seed=1)


def test_flux_3_video_modes_and_per_second_prices():
    assert run(
        "apimart", f"{BFL}/flux-3/text-to-video", duration=8, resolution="1080p", aspect_ratio="9:16"
    ) == (
        "flux-3-video",
        {
            "prompt": "a fox",
            "duration": 8,
            "resolution": "fhd",
            "aspect_ratio": "9:16",
            "audio": True,
            "mode": "t2v",
        },
        round(0.232 * 8, 4),
    )
    _, body, usd = run(
        "apimart",
        f"{BFL}/flux-3/image-to-video",
        image_url=IMG[0],
        end_image_url=IMG[1],
        generate_audio=False,
    )
    assert body == {"prompt": "a fox", "duration": 5, "resolution": "hd", "aspect_ratio": "auto", "audio": False,
                    "mode": "i2v", "image_urls": IMG}  # fmt: skip
    assert usd == round(0.136 * 5, 4)
    _, body, usd = run("apimart", f"{BFL}/flux-3/video-extend", video_url="https://cdn.test/v.mp4")
    assert body == {"prompt": "a fox", "duration": 5, "resolution": "hd", "audio": True, "mode": "v2v",
                    "video_url": "https://cdn.test/v.mp4"}  # fmt: skip
    assert usd == round(0.328 * 5, 4)
    unsupported("apimart", f"{BFL}/flux-3/text-to-video", resolution="4k")


def test_kontext_on_apimart_and_on_kie_unified_api():
    mid = f"{BFL}/flux-kontext-max/edit"
    assert run("apimart", mid, image_urls=IMG) == (
        "flux-kontext-max",
        {"prompt": "a fox", "size": "auto", "output_format": "png", "image_urls": IMG},
        0.064,
    )
    # KIE: una sola imagen en `input_image`; auto es no enviar relación (KIE conserva la de la imagen).
    assert run("kie", mid, image_urls=IMG[:1]) == (
        "flux1-kontext",
        {"prompt": "a fox", "output_format": "png", "input_image": IMG[0], "model": "flux-kontext-max"},
        0.05,
    )
    assert run("kie", f"{BFL}/flux-kontext-pro/text-to-image", aspect_ratio="21:9")[1:] == (
        {"prompt": "a fox", "aspect_ratio": "21:9", "output_format": "png", "model": "flux-kontext-pro"},
        0.025,
    )
    unsupported("kie", mid, image_urls=IMG)
    unsupported("kie", f"{BFL}/flux-kontext-pro/text-to-image", aspect_ratio="3:2")
    unsupported("kie", f"{BFL}/flux-kontext-pro/text-to-image", seed=4)


async def test_kontext_is_sent_to_kie_create_task():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task12345"}})

    _, body, _ = run("kie", f"{BFL}/flux-kontext-pro/edit", image_urls=IMG[:1], aspect_ratio="16:9")
    kie = KIEProvider(settings(**KEYS), mock(handler))
    submitted = await kie.submit_job("flux1-kontext", body, "https://cb")
    assert submitted.request_id == "task12345" and submitted.status_url is None
    assert sent == [("/api/v1/jobs/createTask", {
        "model": "flux1-kontext", "callBackUrl": "https://cb",
        "input": {"prompt": "a fox", "aspect_ratio": "16:9", "output_format": "png", "input_image": IMG[0],
                  "model": "flux-kontext-pro"},
    })]  # fmt: skip
