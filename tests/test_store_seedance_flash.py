"""Seedance 2.5 Flash (`store/seedance_flash.py`): cuerpos y precios en APIMart y KIE. Sin gastar créditos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio import store
from hf_studio.catalog import CATALOG_PATH, get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.routes import with_defaults
from hf_studio.store import seedance_flash as sf
from tests.test_routes import _prices, route_of

IMG, END = "https://cdn.test/a.png", "https://cdn.test/b.png"
VID, AUD = "https://cdn.test/clip.mp4", "https://cdn.test/a.mp3"
MODES = ("text-to-video", "image-to-video", "reference-to-video", "video-edit", "video-extend")


def logical(mode: str, **extra) -> dict:
    schema = get_catalog().get(f"{sf.FAMILY}/{mode}")["input_schema"]
    return with_defaults(schema, {"prompt": "a fox", **extra})


def body(provider: str, mode: str, **extra) -> dict:
    return route_of(provider, f"{sf.FAMILY}/{mode}").translate(logical(mode, **extra))


def price(provider: str, mode: str, hints: dict | None = None, **extra) -> float | None:
    route = route_of(provider, f"{sf.FAMILY}/{mode}")
    return route.price(logical(mode, **extra), hints or {}, _prices(provider))


def test_ids_are_store_only_on_both_stores():
    higgsfield = {m["id"] for m in json.loads(Path(CATALOG_PATH).read_text())["models"]}
    for mode in MODES:
        mid = f"bytedance/seedance-2.5-flash/{mode}"
        assert mid in store.models() and mid not in higgsfield
        assert route_of("apimart", mid).model == "seedance-2-5-flash"
        assert route_of("kie", mid).model == "bytedance/seedance-2-5-flash"
        assert route_of("apimart", mid).settles_later and not route_of("kie", mid).settles_later


def test_apimart_bodies():
    assert body("apimart", "text-to-video", aspect_ratio="9:16", duration=12) == {
        "prompt": "a fox", "duration": 12, "resolution": "720p", "generate_audio": True, "size": "9:16",
    }  # fmt: skip
    frames = body("apimart", "image-to-video", image_url=IMG, end_image_url=END)
    assert frames["image_with_roles"] == [
        {"url": IMG, "role": "first_frame"},
        {"url": END, "role": "last_frame"},
    ]
    assert frames["size"] == "adaptive" and "image_url" not in frames
    ref = body("apimart", "reference-to-video", audio_urls=[AUD])
    assert ref["audio_urls"] == [AUD] and ref["omni_reference_task_type"] == "reference"
    assert body("apimart", "video-edit", video_url=VID, image_urls=[IMG]) == {
        "prompt": "a fox", "resolution": "720p", "generate_audio": True, "image_urls": [IMG],
        "video_urls": [VID], "omni_reference_task_type": "edit", "duration": -1, "size": "adaptive",
    }  # fmt: skip
    extend = body("apimart", "video-extend", video_url=VID, duration=6)
    assert extend["omni_reference_task_type"] == "extend" and extend["video_urls"] == [VID]
    assert extend["duration"] == 6 and extend["size"] == "adaptive"
    resolution = get_catalog().get(f"{sf.FAMILY}/text-to-video")["input_schema"]["properties"]["resolution"]
    assert resolution["enum"] == ["480p", "720p"]  # Flash no tiene 1080p


def test_kie_bodies():
    assert body("kie", "text-to-video") == {
        "prompt": "a fox", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9", "generate_audio": True,
    }  # fmt: skip
    frames = body("kie", "image-to-video", image_url=IMG, end_image_url=END)
    assert frames["first_frame_url"] == IMG and frames["last_frame_url"] == END
    assert frames["aspect_ratio"] == "adaptive"
    ref = body("kie", "reference-to-video", image_urls=[IMG], video_urls=[VID])
    assert ref["reference_image_urls"] == [IMG] and ref["reference_video_urls"] == [VID]
    assert body("kie", "video-edit", video_url=VID, audio_urls=[AUD]) == {
        "prompt": "a fox", "resolution": "720p", "generate_audio": True, "reference_audio_urls": [AUD],
        "reference_video_urls": [VID], "omni_reference_task_type": "edit", "aspect_ratio": "adaptive",
        "duration": -1,
    }  # fmt: skip
    extend = body("kie", "video-extend", video_url=VID, duration=6)
    assert extend["omni_reference_task_type"] == "extend" and extend["reference_video_urls"] == [VID]


def test_prices():
    # APIMart: 5 s × 0,14192 a 720p; KIE: 5 s × 0,205
    assert price("apimart", "text-to-video") == pytest.approx(0.7096)
    assert price("kie", "text-to-video", resolution="480p", duration=10) == pytest.approx(0.925)
    # Con video de referencia: tarifa de entrada × (salida + referencia)
    hints = {"input_video_seconds": 6}
    assert price("apimart", "reference-to-video", hints, video_urls=[VID], duration=8) == pytest.approx(
        1.2096
    )
    assert price("kie", "reference-to-video", hints, video_urls=[VID], duration=8) == pytest.approx(1.785)
    assert price("apimart", "reference-to-video", video_urls=[VID]) is None  # falta la duración del video
    # Edición: el video cuenta como entrada y como salida
    assert price("apimart", "video-edit", {"input_video_seconds": 10}, video_url=VID) == pytest.approx(1.728)
    assert price("kie", "video-edit", {"input_video_seconds": 10}, video_url=VID) == pytest.approx(2.55)
    # Extensión: entrada más los segundos nuevos
    assert price(
        "kie", "video-extend", {"input_video_seconds": 10}, video_url=VID, duration=5
    ) == pytest.approx(1.9125)
    edit = route_of("apimart", f"{sf.FAMILY}/video-edit")
    entry = logical("video-edit", video_url=VID)
    assert edit.reserve(entry, {"input_video_seconds": 10}, _prices("apimart")) == pytest.approx(
        3.456
    )  # 10 + 30 s


def test_input_video_limits():
    for provider in ("apimart", "kie"):
        edit = route_of(provider, f"{sf.FAMILY}/video-edit")
        edit.check({}, {"input_video_seconds": 30})
        for seconds in (3, 31):
            with pytest.raises(ProviderError):
                edit.check({}, {"input_video_seconds": seconds})
        ref = route_of(provider, f"{sf.FAMILY}/reference-to-video")
        ref.check({}, {"input_video_seconds": 2})
        with pytest.raises(ProviderError):
            ref.check({}, {"input_video_seconds": 31})


def test_reference_needs_some_media():
    schema = get_catalog().get(f"{sf.FAMILY}/reference-to-video")["input_schema"]
    assert schema["if"] == {"required": ["image_urls"]}
    assert schema["else"]["else"] == {"required": ["audio_urls"]}
