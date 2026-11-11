"""Kling 4.0 Flash: entradas a mano del catálogo (Higgsfield) y rutas de APIMart y KIE. Sin gastar créditos:
precios con las tablas de tests/fixtures (2026-11-11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.catalog_sync import MANUAL_DOCS
from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for, with_defaults

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {name: json.loads((FIXTURES / f"prices_{name}.json").read_text()) for name in ("apimart", "kie")}
BASE = "kling-video/v4.0-flash"
IMG, IMG2, VID = "https://cdn.test/a.png", "https://cdn.test/b.png", "https://cdn.test/v.mp4"
WORKFLOWS = ("text-to-video", "image-to-video", "reference-to-video", "video-edit")


def logical(workflow: str, **extra) -> dict:
    return with_defaults(get_catalog().get(f"{BASE}/{workflow}")["input_schema"], extra)


def route(provider: str, workflow: str):
    (found,) = routes_for(PROVIDERS[provider].routes(), f"{BASE}/{workflow}")
    return found


def body(provider: str, workflow: str, **extra) -> dict:
    return route(provider, workflow).translate(logical(workflow, **extra), frozenset(extra))


def price(provider: str, workflow: str, seconds: float | None = None, **extra) -> float | None:
    hints = {} if seconds is None else {"input_video_seconds": seconds}
    return route(provider, workflow).price(logical(workflow, **extra), hints, PRICES[provider])


def refused(provider: str, workflow: str, **extra) -> None:
    with pytest.raises(ProviderError) as info:
        body(provider, workflow, **extra)
    assert info.value.kind == "unsupported"


def test_catalog_entries_are_hand_written_higgsfield_models():
    for workflow in WORKFLOWS:
        model = get_catalog().get(f"{BASE}/{workflow}")
        assert model["docs_url"].startswith(MANUAL_DOCS)  # el sync los conserva
        assert not model.get("store") and model["family"] == "kling-4"
        props = model["input_schema"]["properties"]
        assert props["resolution"]["enum"] == ["720p"]
        assert (props["duration"]["minimum"], props["duration"]["maximum"], props["duration"]["default"]) == (
            3,
            20,
            10,
        )
    # Imagen a video: solo el primer fotograma (ni intermedios ni último, a diferencia de Kling 4.0).
    i2v = get_catalog().get(f"{BASE}/image-to-video")["input_schema"]["properties"]
    assert set(i2v) == {"image_url", "prompt", "duration", "resolution"}


def test_text_to_video_on_both_stores():
    assert body("apimart", "text-to-video", prompt="a fox", aspect_ratio="21:9") == {
        "prompt": "a fox", "duration": 10, "resolution": "720p", "aspect_ratio": "21:9"}  # fmt: skip
    assert route("apimart", "text-to-video").model == "kling-v4-flash"
    assert body("kie", "text-to-video", prompt="a fox")["aspect_ratio"] == "16:9"
    assert route("kie", "text-to-video").model == "kling-4.0/flash-keyframe-to-video"
    assert price("apimart", "text-to-video", prompt="x") == round(0.0857144 * 10, 4)
    assert price("kie", "text-to-video", prompt="x", duration=20) == round(0.085 * 20, 4)


def test_image_to_video_takes_only_the_first_frame():
    out = body("apimart", "image-to-video", image_url=IMG)
    assert out == {
        "first_frame_image": IMG,
        "duration": 10,
        "resolution": "720p",
    }  # prompt vacío: no se envía
    assert "aspect_ratio" not in out
    assert body("kie", "image-to-video", image_url=IMG, prompt="@first_frame waves") == {
        "prompt": "@first_frame waves", "first_frame_url": IMG, "duration": 10, "resolution": "720p"}  # fmt: skip
    refused("kie", "image-to-video", image_url=IMG)  # KIE exige prompt
    refused("apimart", "image-to-video", image_url=IMG, end_image_url=IMG2)  # Flash no tiene último fotograma
    assert price("apimart", "image-to-video", image_url=IMG, duration=5) == round(0.0857144 * 5, 4)
    assert price("kie", "image-to-video", image_url=IMG, prompt="x", duration=5) == round(0.085 * 5, 4)


def test_references_translate_mentions_and_price_the_input_video():
    refs = {
        "prompt": "@image_1 dances like @video_1",
        "image_urls": [IMG],
        "video_urls": [VID],
        "aspect_ratio": "adaptive",
    }
    out = body("apimart", "reference-to-video", **refs)
    assert out["prompt"] == "@Image1 dances like @Video1" and out["aspect_ratio"] == "auto"
    assert out["omni_reference_task_type"] == "reference"
    kie = body("kie", "reference-to-video", **refs)
    assert kie["prompt"] == refs["prompt"] and kie["aspect_ratio"] == "auto"  # KIE cita igual que Higgsfield
    assert route("kie", "reference-to-video").model == "kling-4.0/flash-reference-to-video"
    # Salida + max(salida, entrada redondeada hacia arriba), a la tarifa con video de entrada.
    assert price("apimart", "reference-to-video", 8, **refs) == round(0.0571432 * 20, 4)
    assert price("apimart", "reference-to-video", 12.2, **refs) == round(0.0571432 * (10 + 13), 4)
    assert price("kie", "reference-to-video", 8, **refs) == round(0.0565 * 20, 4)
    assert price("kie", "reference-to-video", None, **refs) is None  # falta la duración de la entrada
    # Solo imágenes: tarifa sin video de entrada.
    images = {"prompt": "@image_1 smiles", "image_urls": [IMG]}
    assert price("apimart", "reference-to-video", None, **images) == round(0.0857144 * 10, 4)
    assert price("kie", "reference-to-video", None, **images) == round(0.085 * 10, 4)


def test_reference_video_lengths_follow_each_store():
    one = logical("reference-to-video", prompt="x", video_urls=[VID])
    two = logical("reference-to-video", prompt="x", video_urls=[VID, VID])
    apimart, kie = route("apimart", "reference-to-video"), route("kie", "reference-to-video")
    apimart.check(one, {"input_video_seconds": 20})
    kie.check(one, {"input_video_seconds": 2})
    for check, source, seconds in ((apimart.check, one, 2.5), (apimart.check, one, 21), (apimart.check, two, 5),
                                   (kie.check, one, 1.5), (kie.check, two, 21)):  # fmt: skip
        with pytest.raises(ProviderError):
            check(source, {"input_video_seconds": seconds})


def test_video_edit_runs_on_apimart_only():
    out = body("apimart", "video-edit", prompt="make it snow on @video_1", video_url=VID, image_urls=[IMG])
    assert out == {"prompt": "make it snow on @Video1", "video_url": VID, "image_urls": [IMG], "duration": 10,
                   "resolution": "720p", "aspect_ratio": "16:9", "omni_reference_task_type": "edit"}  # fmt: skip
    assert "aspect_ratio" not in body(
        "apimart", "video-edit", prompt="x", video_url=VID, aspect_ratio="adaptive"
    )
    refused("apimart", "video-edit", prompt="x", video_url=VID, video_urls=[VID])  # sin videos de referencia
    edit = logical("video-edit", prompt="x", video_url=VID)
    for seconds in (2.5, 20.5):
        with pytest.raises(ProviderError):
            route("apimart", "video-edit").check(edit, {"input_video_seconds": seconds})
    assert price("apimart", "video-edit", 12.2, prompt="x", video_url=VID) == round(0.0571432 * 23, 4)
    assert not routes_for(PROVIDERS["kie"].routes(), f"{BASE}/video-edit")


def test_flash_is_cheaper_than_kling4_on_the_stores():
    k4 = with_defaults(get_catalog().get("kling-video/v4.0/text-to-video")["input_schema"],
                       {"prompt": "x", "duration": 10, "resolution": "720p"})  # fmt: skip
    for provider in ("apimart", "kie"):
        (full,) = routes_for(PROVIDERS[provider].routes(), "kling-video/v4.0/text-to-video")
        assert price(provider, "text-to-video", prompt="x") < full.price(k4, {}, PRICES[provider])
