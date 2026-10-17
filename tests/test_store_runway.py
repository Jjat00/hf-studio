"""Runway Gen-4 Turbo en KIE (`store/runway.py`): API unificada, sin marca de agua."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hf_studio.providers import ProviderError
from hf_studio.providers.kie import KIEProvider
from hf_studio.providers.routes import with_defaults
from hf_studio.store import kie_endpoints, runway
from tests.test_providers import KEYS, mock, settings

PRICES = json.loads((Path(__file__).parent / "fixtures" / "prices_kie.json").read_text())
MODELS = {m["id"]: m for m in runway.MODELS}
KIE = runway.kie()
IMG = "https://cdn.test/a.png"


def sample(model_id: str, **extra) -> dict:
    return with_defaults(MODELS[model_id]["input_schema"], {"prompt": "a fox in the snow", **extra})


def test_text_to_video():
    route = KIE["runway/gen4-turbo/text-to-video"]
    logical = sample("runway/gen4-turbo/text-to-video", aspect_ratio="9:16", duration=10)
    assert route.model == "runway"
    assert route.translate(logical) == {"prompt": "a fox in the snow", "duration": 10, "quality": "720p",
                                        "aspect_ratio": "9:16", "watermark": ""}  # fmt: skip
    assert route.price(logical, {}, PRICES) == 0.15


def test_image_to_video_takes_the_ratio_from_the_image():
    route = KIE["runway/gen4-turbo/image-to-video"]
    logical = sample("runway/gen4-turbo/image-to-video", image_url=IMG, resolution="1080p")
    assert route.translate(logical) == {"prompt": "a fox in the snow", "image_url": IMG, "duration": 5,
                                        "quality": "1080p", "watermark": ""}  # fmt: skip
    assert route.price(logical, {}, PRICES) == 0.15
    assert "aspect_ratio" not in MODELS["runway/gen4-turbo/image-to-video"]["input_schema"]["properties"]


def test_1080p_only_makes_5_second_videos():
    with pytest.raises(ProviderError) as info:
        KIE["runway/gen4-turbo/text-to-video"].translate(
            sample("runway/gen4-turbo/text-to-video", resolution="1080p", duration=10)
        )
    assert info.value.kind == "unsupported"


async def test_runway_goes_through_the_unified_task_api():
    """Runway ya no tiene API propia en KIE: `jobs/createTask` y `jobs/recordInfo` con `resultJson`."""
    assert "runway" not in kie_endpoints()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.method == "POST":
            assert json.loads(request.content)["model"] == "runway"
            return httpx.Response(200, json={"code": 200, "msg": "success",
                                             "data": {"taskId": "ee603959-debb-48d1-98c4-a6d1c717eba6"}})  # fmt: skip
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {
            "taskId": "ee603959-debb-48d1-98c4-a6d1c717eba6", "model": "runway", "state": "success",
            "resultJson": '{"resultUrls":["https://tempfile.aiquickdraw.com/p/c036_1_1791218754_8541.mp4"]}',
        }})  # fmt: skip

    kie = KIEProvider(settings(**KEYS), mock(handler))
    body = KIE["runway/gen4-turbo/text-to-video"].translate(sample("runway/gen4-turbo/text-to-video"))
    submitted = await kie.submit_job("runway", body)
    polled = await kie.poll_job(submitted.request_id, submitted.status_url)
    assert polled.status == "completed" and polled.outputs[0]["url"].endswith(".mp4")
    assert seen == ["/api/v1/jobs/createTask", "/api/v1/jobs/recordInfo"]
