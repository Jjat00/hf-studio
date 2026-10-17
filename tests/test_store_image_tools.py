"""Quitar el fondo y ampliar imágenes en KIE (`store/image_tools.py`). Sin gastar créditos."""

from __future__ import annotations

import json

import httpx
import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.kie import KIEProvider
from tests.test_providers import KEYS, mock, settings
from tests.test_routes import _prices, route_of

IMAGE = "https://x/photo.png"


def test_recraft_tools_send_the_image_field():
    for mid, usd in (("recraft/remove-background", 0.005), ("recraft/crisp-upscale", 0.0025)):
        route = route_of("kie", mid)
        assert route.translate({"image_url": IMAGE}) == {"image": IMAGE}
        assert route.price({"image_url": IMAGE}, {}, _prices("kie")) == usd
        assert "prompt" not in get_catalog().get(mid)["input_schema"]["properties"]


def test_topaz_upscale_factor_goes_as_text_and_is_quoted_at_4k():
    route = route_of("kie", "topaz/image-upscale")
    logical = {"image_url": IMAGE, "upscale_factor": 4}
    assert route.translate(logical) == {"image_url": IMAGE, "upscale_factor": "4"}
    assert route.price(logical, {}, _prices("kie")) == 0.1 and route.settles_later
    with pytest.raises(ProviderError) as info:
        route.translate({**logical, "mask_url": IMAGE}, frozenset(logical) | {"mask_url"})
    assert info.value.kind == "unsupported"


async def test_kie_wraps_the_tool_input_in_the_unified_task():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_recraft_1"}})

    kie = KIEProvider(settings(**KEYS), mock(handler))
    route = route_of("kie", "recraft/remove-background")
    submitted = await kie.submit_job(route.model, route.translate({"image_url": IMAGE}), None)
    assert submitted.request_id == "task_recraft_1"
    assert seen == [{"model": "recraft/remove-background", "input": {"image": IMAGE}}]
