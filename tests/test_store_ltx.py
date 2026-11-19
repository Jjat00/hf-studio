"""LTX 2.5 en KIE (`store/ltx.py`): ruta más barata de Higgsfield y audio a video. Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import ltx
from tests.test_routes import _prices, route_of

IMG, AUDIO = "https://cdn.test/a.png", "https://cdn.test/a.mp3"


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def test_text_to_video_sends_higgsfields_defaults():
    mid = "lightricks/ltx-2.5/text-to-video/fast"
    route = route_of("kie", mid)
    entry = logical(mid)
    assert route.translate(entry, frozenset({"prompt"})) == {
        "prompt": "a fox", "duration": 6, "resolution": "720p", "fps": 25, "aspect_ratio": "16:9",
    }  # fmt: skip
    assert route.price(entry, {}, _prices("kie")) == pytest.approx(6 * 0.054)
    pro = "lightricks/ltx-2.5/text-to-video/pro"
    assert (
        route_of("kie", pro).price(logical(pro, resolution="1080p", duration=10), {}, _prices("kie")) == 1.02
    )
    for bad in (
        {"resolution": "4k"},
        {"resolution": "2k"},
        {"generate_audio": False},
        {"camera_movement": "jib_up"},
    ):
        with pytest.raises(ProviderError):
            route.translate({**entry, **bad}, frozenset({"prompt", *bad}))


def test_image_to_video_takes_the_format_from_the_image():
    mid = "lightricks/ltx-2.5/image-to-video/pro"
    route = route_of("kie", mid)
    entry = logical(mid, image_url=IMG)
    out = route.translate(entry, frozenset({"prompt", "image_url"}))
    assert out["image_url"] == IMG and "aspect_ratio" not in out
    with pytest.raises(ProviderError):  # una relación elegida no tiene equivalente
        route.translate({**entry, "aspect_ratio": "9:16"}, frozenset({"prompt", "image_url", "aspect_ratio"}))
    with pytest.raises(ProviderError):  # tampoco el último fotograma
        route.translate({**entry, "end_image_url": IMG}, frozenset({"prompt", "image_url", "end_image_url"}))


def test_audio_to_video_is_a_kie_store_model():
    assert ltx.AUDIO_ID in store.models()
    route = route_of("kie", ltx.AUDIO_ID)
    entry = logical(ltx.AUDIO_ID, audio_url=AUDIO, duration=8.5)
    assert route.translate(entry) == {
        "prompt": "a fox", "audio_url": AUDIO, "duration": 8.5, "resolution": "720p", "fps": 25,
    }  # fmt: skip
    assert route.price(entry, {}, _prices("kie")) == pytest.approx(8.5 * 0.054)
    route.translate({**entry, "resolution": "1440p", "duration": 10})
    with pytest.raises(ProviderError):  # 1440p o 48/50 fps, como mucho 10 s
        route.translate({**entry, "fps": 50, "duration": 12})
