"""Modelos de tienda (`hf_studio/store`): solo APIMart y KIE, nunca Higgsfield. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from hf_studio import store
from hf_studio.catalog import CATALOG_PATH, get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.base import Polled
from hf_studio.providers.kie import KIEEndpoint, KIEProvider
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for
from tests.test_providers import KEYS, mock, settings
from tests.test_routing import env, tick  # noqa: F401  (fixture)

HIGGSFIELD_IDS = {m["id"] for m in json.loads(Path(CATALOG_PATH).read_text())["models"]}
STORE = store.models()


def test_store_models_are_in_the_catalog_and_never_shadow_higgsfield():
    assert STORE, "no store models"
    catalog = get_catalog()
    for model_id, model in STORE.items():
        assert model_id not in HIGGSFIELD_IDS, f"{model_id} is also a Higgsfield id"
        assert catalog.get(model_id)["store"] is True
        Draft202012Validator.check_schema(model["input_schema"])
        for key in ("title", "summary", "workflow", "family", "output", "capabilities", "notes", "docs_url"):
            assert model[key] is not None, f"{model_id}: {key}"
        assert " — " in model["title"] and model["output"] in ("image", "video", "audio")


@pytest.mark.parametrize("model_id", sorted(STORE))
def test_every_store_model_has_a_store_route(model_id):
    routes = [r for name in ("apimart", "kie") for r in routes_for(PROVIDERS[name].routes(), model_id)]
    assert routes, f"{model_id} has no route on APIMart or KIE"


def test_apimart_sends_store_image_models_to_the_image_endpoint():
    for model in store.apimart_image_models():
        assert APIMartProvider._submit_path(model) == "/v1/images/generations"
    assert APIMartProvider._submit_path("seedance-2.0") == "/v1/videos/generations"


async def test_higgsfield_is_left_out_of_store_models(env):  # noqa: F811
    _, http, fakes = env
    body = (await http.post("/v1/estimate", json={
        "model": "openai/gpt-image-2.5/flare/text-to-image", "input": {"prompt": "a lighthouse at dawn"},
    })).json()  # fmt: skip
    assert {o["provider"] for o in body["options"]} == {"apimart", "kie"}
    assert any(e["provider"] == "higgsfield" for e in body["excluded"])
    assert body["savings_vs_higgsfield"] is None
    job = (await http.post("/v1/generations", json={
        "model": "openai/gpt-image-2.5/flare/text-to-image", "input": {"prompt": "a lighthouse at dawn"},
        "max_usd": 0.05,
    })).json()  # fmt: skip
    await tick(env[0])
    assert job["provider"] == "apimart" and not fakes.sent["higgsfield"]
    assert fakes.sent["apimart"][-1] == {"model": "gpt-image-2.5-ext", "version": "flare",
                                         "prompt": "a lighthouse at dawn", "size": "auto", "resolution": "1K",
                                         "n": 1}  # fmt: skip


async def test_forcing_higgsfield_on_a_store_model_finds_no_option(env):  # noqa: F811
    _, http, _ = env
    r = await http.post("/v1/estimate", json={
        "model": "openai/gpt-image-2.5/flare/text-to-image", "input": {"prompt": "x"}, "provider": "higgsfield",
    })  # fmt: skip
    body = r.json()
    assert not body.get("options")
    assert any("does not offer" in e["reason"] for e in body.get("excluded", []))


async def test_kie_endpoint_models_use_their_own_submit_and_poll_paths(monkeypatch):
    seen = []

    def parse(data: dict) -> Polled:
        return Polled("completed", [{"kind": "video", "url": data["url"], "content_type": None}])

    endpoint = KIEEndpoint(
        "fake", "/api/v1/fake/generate", "/api/v1/fake/record-info",
        lambda model, args, callback: {"model": model, **args, "callBackUrl": callback}, parse,
    )  # fmt: skip
    monkeypatch.setattr(store, "kie_endpoints", lambda: {"fake-model": endpoint})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.url.params.get("taskId")))
        if request.method == "POST":
            assert json.loads(request.content) == {
                "model": "fake-model",
                "prompt": "p",
                "callBackUrl": "https://cb",
            }
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "t-1"}})
        return httpx.Response(200, json={"code": 200, "data": {"url": "https://cdn.test/v.mp4"}})

    kie = KIEProvider(settings(**KEYS), mock(handler))
    submitted = await kie.submit_job("fake-model", {"prompt": "p"}, "https://cb")
    assert submitted.status_url == "kie:fake"
    polled = await kie.poll_job(submitted.request_id, submitted.status_url)
    assert polled.outputs[0]["url"] == "https://cdn.test/v.mp4"
    assert seen == [("POST", "/api/v1/fake/generate", None), ("GET", "/api/v1/fake/record-info", "t-1")]
    # Un endpoint que ya no existe no se confunde con la API unificada.
    with pytest.raises(ProviderError) as info:
        await kie.poll_job("t-1", "kie:gone")
    assert info.value.kind == "not_found"
