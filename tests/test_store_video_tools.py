"""Escalador de video de Topaz en KIE (`store/video_tools.py`). Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import video_tools as t

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = json.loads((FIXTURES / "prices_kie.json").read_text())
ROUTE = t.kie()["topaz/video-upscale"]
VID = "https://cdn.test/v.mp4"


def logical(**extra) -> dict:
    return with_defaults(get_catalog().get("topaz/video-upscale")["input_schema"], extra)


def test_topaz_video_upscale():
    assert get_catalog().get("topaz/video-upscale")["store"] is True
    assert ROUTE.model == "topaz/video-upscale"
    assert ROUTE.translate(logical(video_url=VID)) == {"video_url": VID, "upscale_factor": "2"}
    assert ROUTE.translate(logical(video_url=VID, upscale_factor=4))["upscale_factor"] == "4"
    # por segundo del video de entrada
    assert ROUTE.price(logical(video_url=VID), {}, PRICES) is None
    assert ROUTE.price(logical(video_url=VID), {"input_video_seconds": 10}, PRICES) == 0.4
    assert ROUTE.price(logical(video_url=VID, upscale_factor=4), {"input_video_seconds": 10}, PRICES) == 0.7
    with pytest.raises(ProviderError) as info:  # no tiene prompt
        ROUTE.translate(logical(video_url=VID, prompt="sharper"))
    assert info.value.kind == "unsupported"
