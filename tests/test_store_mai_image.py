"""MAI Image 2.6 y 2.6 Flash en APIMart (`store/mai_image.py`): precio por tokens, desconocido. Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.registry import PROVIDERS
from tests.test_routes import _prices, route_of, sample
from tests.test_routing import env  # noqa: F401  (fixture)

TOKENS = "Billed by tokens: the price is only known after generating."
IDS = [
    f"microsoft/{t}/{m}" for t in ("mai-image-2.6", "mai-image-2.6-flash") for m in ("text-to-image", "edit")
]


@pytest.mark.parametrize("mid", IDS)
def test_mai_routes_have_no_price_and_warn_about_tokens(mid):
    route = route_of("apimart", mid)
    assert route.price(sample(mid), {}, _prices("apimart")) is None
    assert route.reserve is None and TOKENS in route.notes
    assert TOKENS in store.models()[mid]["notes"]
    assert APIMartProvider._submit_path(route.model) == "/v1/images/generations"
    assert mid not in PROVIDERS["kie"].routes()


def test_mai_text_to_image_body():
    mid = "microsoft/mai-image-2.6-flash/text-to-image"
    route = route_of("apimart", mid)
    logical = {**sample(mid), "aspect_ratio": "21:9", "resolution": "2k", "web_grounding": True}
    assert route.model == "mai-image-2.6-flash"
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "size": "21:9",
                                        "resolution": "2K", "web_grounding": True, "n": 1}  # fmt: skip


def test_mai_edit_lets_the_model_pick_the_size():
    mid = "microsoft/mai-image-2.6/edit"
    route = route_of("apimart", mid)
    out = route.translate(sample(mid))
    assert out == {"prompt": "a red fox running through snow", "web_grounding": False, "n": 1,
                   "image_urls": ["https://example.com/hf-studio-placeholder.png"]}  # fmt: skip
    assert store.models()[mid]["input_schema"]["properties"]["image_urls"]["maxItems"] == 5
    for extra in ({"aspect_ratio": "16:9"}, {"resolution": "2k"}, {"seed": 1}):
        with pytest.raises(ProviderError):
            route.translate({**sample(mid), **extra})


async def test_mai_estimate_is_unavailable_without_missing_hints(env):  # noqa: F811
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={
        "model": "microsoft/mai-image-2.6/text-to-image", "input": {"prompt": "a lighthouse at dawn"},
    })).json()  # fmt: skip
    option = next(o for o in body["options"] if o["provider"] == "apimart")
    assert option["usd"] is None and option["kind"] == "unavailable" and not option["missing"]
    assert TOKENS in option["notes"]
