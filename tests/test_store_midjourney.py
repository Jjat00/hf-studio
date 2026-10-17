"""Midjourney en APIMart: ruta de envío propia, versiones niji y precio por versión y velocidad."""

from __future__ import annotations

import json

import httpx

from hf_studio.providers.apimart import APIMartProvider
from hf_studio.store.midjourney import MODEL_ID, apimart
from tests.test_providers import KEYS, mock, settings
from tests.test_routes import _prices, sample

ROUTE = apimart()[MODEL_ID]


def test_typical_request_and_price():
    logical = sample(MODEL_ID)
    out = ROUTE.translate(logical, frozenset({"prompt"}))
    assert out == {"prompt": "a red fox running through snow", "version": "7", "size": "1:1", "speed": "fast"}
    assert ROUTE.price(logical, {}, _prices("apimart")) == 0.055


def test_niji_raw_and_relax():
    logical = {**sample(MODEL_ID), "version": "niji 6", "raw": True, "speed": "relax", "stylize": 250}
    out = ROUTE.translate(logical, frozenset(logical))
    assert out["niji"] is True and out["version"] == "6" and out["style"] == "raw" and "raw" not in out
    assert out["stylize"] == 250
    assert ROUTE.price(logical, {}, _prices("apimart")) == 0.045


async def test_submits_to_the_midjourney_route_and_polls_the_unified_task():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            assert json.loads(request.content)["prompt"] == "p"
            return httpx.Response(200, json={"code": 200, "data": [{"status": "submitted", "task_id": "t1"}]})
        images = [{"url": [f"https://cdn.test/mj_{n}.png"]} for n in range(4)]
        return httpx.Response(
            200, json={"code": 200, "data": {"status": "completed", "result": {"images": images}}}
        )

    provider = APIMartProvider(settings(**KEYS), mock(handler))
    submitted = await provider.submit_job("midjourney", {"prompt": "p", "version": "7"})
    polled = await provider.poll_job(submitted.request_id)
    assert seen == [("POST", "/v1/midjourney/generations"), ("GET", "/v1/tasks/t1")]
    assert len(polled.outputs) == 4 and polled.outputs[0]["kind"] == "image"
