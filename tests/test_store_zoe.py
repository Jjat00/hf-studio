"""APIMart Zoe (`store/zoe.py`): traducción por modo y precio por segundo, con y sin video. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio import store
from hf_studio.catalog import CATALOG_PATH
from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from tests.test_routes import _prices, route_of, sample

MODES = ("text-to-video", "image-to-video", "reference-to-video", "video-edit")


def test_zoe_ids_are_apimart_only_and_do_not_clash():
    higgsfield = {m["id"] for m in json.loads(Path(CATALOG_PATH).read_text())["models"]}
    for mode in MODES:
        mid = f"apimart/zoe/{mode}"
        assert mid in store.models() and mid not in higgsfield
        assert mid not in PROVIDERS["kie"].routes()
        assert route_of("apimart", mid).model == "apimart-zoe"


def test_text_to_video_body_and_price_by_resolution():
    mid = "apimart/zoe/text-to-video"
    route = route_of("apimart", mid)
    logical = sample(mid)
    assert route.translate(logical) == {"prompt": "a red fox running through snow", "resolution": "720p",
                                        "duration": 5, "aspect_ratio": "adaptive", "audio": True,
                                        "enhance_prompt": False, "output_format": "mp4"}  # fmt: skip
    prices = _prices("apimart")
    assert route.price(logical, {}, prices) == 0.918  # 5 × 0.1836
    assert route.price({**logical, "resolution": "4k", "duration": 10}, {}, prices) == 12.308


def test_image_to_video_sends_the_frames():
    mid = "apimart/zoe/image-to-video"
    out = route_of("apimart", mid).translate({**sample(mid), "end_image_url": "https://x/end.png"})
    assert out["first_frame_image"] and out["last_frame_image"] == "https://x/end.png"
    assert "image_url" not in out


def test_reference_videos_use_the_input_rate():
    mid = "apimart/zoe/reference-to-video"
    route = route_of("apimart", mid)
    logical = {**sample(mid), "duration": 8, "resolution": "1080p"}
    out = route.translate(logical)
    assert out["omni_reference_task_type"] == "reference" and out["video_urls"] == [
        "https://cdn.test/ref.mp4"
    ]
    prices = _prices("apimart")
    # D = 8, R = floor(6.6) = 6 → 8 + max(6, ceil(16/3) = 6) = 14 s a 0.272
    assert route.price(logical, {"input_video_seconds": 6.6}, prices) == 3.808
    # R = 12 manda: 8 + 12 = 20 s
    assert route.price(logical, {"input_video_seconds": 12.4}, prices) == 5.44
    assert route.price(logical, {}, prices) is None
    images_only = {**logical, "video_urls": [], "image_urls": ["https://x/a.png"]}
    assert "video_urls" not in route.translate(images_only)
    assert route.price(images_only, {}, prices) == 3.6448  # 8 × 0.4556, sin recargo
    with pytest.raises(ProviderError):
        route.translate({**logical, "video_urls": [], "audio_urls": ["https://x/a.mp3"]})
    with pytest.raises(ProviderError):
        route.check(logical, {"input_video_seconds": 16})


def test_edit_follows_the_source_and_holds_thirty_seconds():
    mid = "apimart/zoe/video-edit"
    route = route_of("apimart", mid)
    logical = sample(mid)
    out = route.translate(logical)
    assert out["omni_reference_task_type"] == "edit" and len(out["video_urls"]) == 1
    assert "duration" not in out and "aspect_ratio" not in out
    prices = _prices("apimart")
    # D = round(10.6) = 11, R = 10 → 11 + max(10, 8) = 21 s a 0.1088
    assert route.price(logical, {"input_video_seconds": 10.6}, prices) == 2.2848
    assert route.reserve(logical, {"input_video_seconds": 10.6}, prices) == 5.44  # 30 + max(10, 20) = 50 s
    assert route.settles_later
    for seconds in (3, 31):
        with pytest.raises(ProviderError):
            route.check(logical, {"input_video_seconds": seconds})
