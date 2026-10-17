"""Veo 3.1 en las tiendas (`store/veo.py`): APIMart (oficial y no oficial) y KIE. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.kie import KIEProvider
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import veo
from tests.test_providers import KEYS, mock, settings

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"
ROUTES = {"apimart": veo.apimart(), "kie": veo.kie()}


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def route(provider: str, model_id: str, name: str | None = None):
    return next(r for r in routes_for(ROUTES[provider], model_id) if name in (None, r.model))


def body(provider: str, model_id: str, name: str | None = None, **extra) -> dict:
    return route(provider, model_id, name).translate(logical(model_id, **extra))


def price(provider: str, model_id: str, name: str | None = None, **extra) -> float | None:
    return route(provider, model_id, name).price(logical(model_id, **extra), {}, PRICES[provider])


def refused(provider: str, model_id: str, name: str | None = None, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, model_id, name, **extra)
    assert info.value.kind == "unsupported"


def test_models_and_channels():
    ids = {m["id"] for m in veo.MODELS}
    assert len(ids) == 8 and "google/veo-3.1/quality/reference-to-video" not in ids
    assert set(ROUTES["kie"]) == ids
    # APIMart: lite solo texto (canal no oficial); fast y quality con canal oficial y no oficial
    assert set(ROUTES["apimart"]) == ids - {
        "google/veo-3.1/lite/image-to-video",
        "google/veo-3.1/lite/reference-to-video",
    }
    fast = routes_for(ROUTES["apimart"], "google/veo-3.1/fast/text-to-video")
    assert [(r.model, r.official) for r in fast] == [("veo3.1-fast-official", True), ("veo3.1-fast", False)]
    assert [r.model for r in routes_for(ROUTES["apimart"], "google/veo-3.1/fast/reference-to-video")] == [
        "veo3.1-fast"
    ]
    assert APIMartProvider._submit_path("veo3.1-fast") == "/v1/videos/generations"


def test_apimart_official_body_and_price():
    mid = "google/veo-3.1/quality/image-to-video"
    assert body("apimart", mid, "veo3.1-quality-official", image_url=IMG, end_image_url=END, resolution="4k",
                seed=7, negative_prompt="blur") == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "4K", "duration": 8, "generate_audio": True,
        "first_frame_image": IMG, "last_frame_image": END, "seed": 7, "negative_prompt": "blur",
    }  # fmt: skip
    # Por segundo: quality sin fila 720P-audio usa `audio` (0,32); sin audio, 720P (0,16)
    assert price("apimart", mid, "veo3.1-quality-official", image_url=IMG) == pytest.approx(2.56)
    assert price(
        "apimart", mid, "veo3.1-quality-official", image_url=IMG, generate_audio=False
    ) == pytest.approx(1.28)
    t2v = "google/veo-3.1/fast/text-to-video"
    assert price("apimart", t2v, "veo3.1-fast-official", duration=4, resolution="1080p") == pytest.approx(
        0.384
    )
    refused("apimart", t2v, "veo3.1-fast-official", aspect_ratio="1:1")


def test_apimart_unofficial_body_price_and_limits():
    mid = "google/veo-3.1/fast/image-to-video"
    assert body("apimart", mid, "veo3.1-fast", image_url=IMG, end_image_url=END) == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "720p", "duration": 8,
        "image_urls": [IMG, END], "generation_type": "frame",
    }  # fmt: skip
    ref = "google/veo-3.1/fast/reference-to-video"
    assert body("apimart", ref, image_urls=[IMG])["generation_type"] == "reference"
    assert price("apimart", mid, "veo3.1-fast", image_url=IMG) == 0.14
    assert price("apimart", mid, "veo3.1-fast", image_url=IMG, resolution="4k") == 0.64
    # Solo 8 s, siempre con audio y sin semilla
    refused("apimart", mid, "veo3.1-fast", image_url=IMG, duration=6)
    refused("apimart", mid, "veo3.1-fast", image_url=IMG, generate_audio=False)
    refused("apimart", mid, "veo3.1-fast", image_url=IMG, seed=3)
    assert body("apimart", "google/veo-3.1/lite/text-to-video") == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "720p", "duration": 8,
    }  # fmt: skip


def test_kie_body_price_and_limits():
    assert body("kie", "google/veo-3.1/lite/text-to-video", duration=6) == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "720p", "duration": 6,
        "model": "veo3_lite", "generation_type": "TEXT_2_VIDEO",
    }  # fmt: skip
    i2v = "google/veo-3.1/quality/image-to-video"
    assert body("kie", i2v, image_url=IMG, end_image_url=END, resolution="1080p") == {
        "prompt": "a fox", "aspect_ratio": "16:9", "resolution": "1080p", "duration": 8,
        "image_urls": [IMG, END], "model": "veo3", "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO",
    }  # fmt: skip
    ref = body("kie", "google/veo-3.1/fast/reference-to-video", image_urls=[IMG, END])
    assert (ref["model"], ref["generation_type"], ref["image_urls"]) == (
        "veo3_fast",
        "REFERENCE_2_VIDEO",
        [IMG, END],
    )
    assert price("kie", i2v, image_url=IMG, resolution="1080p") == 1.275
    assert price("kie", "google/veo-3.1/fast/reference-to-video", image_urls=[IMG], resolution="4k") == 0.9
    refused("kie", i2v, image_url=IMG, generate_audio=False)
    refused("kie", i2v, image_url=IMG, seed=1)


def test_kie_endpoint_body_and_parse():
    endpoint = veo.KIE_ENDPOINTS["veo-3-1"]
    args = body("kie", "google/veo-3.1/fast/text-to-video")
    assert endpoint.body("veo-3-1", args, "https://cb") == {
        "model": "veo-3-1",
        "input": args,
        "callBackUrl": "https://cb",
    }
    assert "callBackUrl" not in endpoint.body("veo-3-1", args, None)
    # Ejemplo de la API unificada (`resultJson` con `resultUrls`)
    done = endpoint.parse({"taskId": "t", "state": "success",
                           "resultJson": '{"resultUrls":["https://cdn.test/v.mp4"]}'})  # fmt: skip
    assert done.status == "completed" and done.outputs[0] == {
        "kind": "video", "url": "https://cdn.test/v.mp4", "content_type": None
    }  # fmt: skip
    # 1080p/4k: la doc pone la URL en `resultJson.data.result_urls`
    upscaled = endpoint.parse({"state": "success", "resultJson": json.dumps(
        {"data": {"result_urls": ["https://cdn.test/4k.mp4"], "origin_urls": ["https://cdn.test/720.mp4"]}}
    )})  # fmt: skip
    assert [o["url"] for o in upscaled.outputs] == ["https://cdn.test/4k.mp4"]
    assert endpoint.parse({"state": "generating"}).status == "in_progress"
    failed = endpoint.parse(
        {"state": "fail", "failMsg": "Your prompt was flagged by Website as violating content policies"}
    )
    assert failed.status == "nsfw"


async def test_kie_submits_and_polls_through_the_unified_api():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            sent = json.loads(request.content)
            assert sent["model"] == "veo-3-1" and sent["input"]["model"] == "veo3_fast"
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "veo_task_1"}})
        return httpx.Response(200, json={"code": 200, "data": {
            "state": "success", "resultJson": '{"resultUrls":["https://cdn.test/v.mp4"]}'}})  # fmt: skip

    kie = KIEProvider(settings(**KEYS), mock(handler))
    submitted = await kie.submit_job("veo-3-1", body("kie", "google/veo-3.1/fast/text-to-video"))
    assert submitted.status_url == "kie:veo-3-1"
    polled = await kie.poll_job(submitted.request_id, submitted.status_url)
    assert polled.outputs[0]["url"] == "https://cdn.test/v.mp4"
    assert seen == [("POST", "/api/v1/jobs/createTask"), ("GET", "/api/v1/jobs/recordInfo")]
