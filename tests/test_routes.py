"""Mapa de modelos: cada ruta apunta a un modelo del catálogo, traduce una entrada típica sin perder
campos y tiene precio en la tabla del proveedor (copias en tests/fixtures, 2026-10-03)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.pricing import fill_placeholders
from hf_studio.providers import ProviderError
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import Spec, routes_for, with_defaults

FIXTURES = Path(__file__).parent / "fixtures"
# Entradas típicas que a propósito no tienen equivalente exacto en ese proveedor.
EXPECTED_UNSUPPORTED = {
    ("apimart", "minimax/h3/text-to-video"),  # aspect_ratio "auto" por defecto
    ("kie", "minimax/h3/text-to-video"),
    ("kie", "xai/grok-imagine-video/v1.5/reference-to-video"),  # KIE exige al menos una imagen
    # canal -ext: sin imágenes pide una relación explícita, y la duración por defecto (5 s) es menor que su mínimo
    ("apimart", "xai/grok-imagine-video/v1.5/reference-to-video", "grok-imagine-1.5-video-ext"),
}
ROUTED = [
    (name, mid, route.model)
    for name, cls in PROVIDERS.items()
    for mid in sorted(cls.routes())
    for route in routes_for(cls.routes(), mid)
]


def route_of(provider: str, model_id: str, channel: str | None = None):
    """La ruta de un modelo en un proveedor; con varios canales, la de `channel` (o la primera)."""
    routes = routes_for(PROVIDERS[provider].routes(), model_id)
    return next(r for r in routes if channel in (None, r.model))


def requested(model_id: str) -> dict:
    """Lo que pone el usuario: prompt, medios obligatorios y, en referencias, un video."""
    schema = get_catalog().get(model_id)["input_schema"]
    filled, _ = fill_placeholders(schema, {"prompt": "a red fox running through snow"})
    if "video_urls" in schema["properties"] and "reference" in model_id:
        filled["video_urls"] = ["https://cdn.test/ref.mp4"]
    return filled


def sample(model_id: str) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], requested(model_id))


def chosen(model_id: str, *extra: str) -> frozenset:
    return frozenset(requested(model_id)) | frozenset(extra)


@pytest.mark.parametrize(("provider", "model_id", "channel"), ROUTED)
def test_route_translates_and_prices_a_typical_request(provider, model_id, channel):
    assert get_catalog().get(model_id), f"{model_id} is not in the catalog"
    route = route_of(provider, model_id, channel)
    prices = json.loads((FIXTURES / f"prices_{provider}.json").read_text())
    logical = sample(model_id)
    if {(provider, model_id), (provider, model_id, channel)} & EXPECTED_UNSUPPORTED:
        with pytest.raises(ProviderError) as info:
            route.translate(logical, chosen(model_id))
        assert info.value.kind == "unsupported"
        return
    out = route.translate(logical, chosen(model_id))
    assert out and None not in out.values()
    usd = route.price(logical, {"input_video_seconds": 5}, prices)
    assert usd is not None and 0 < usd < 10, f"{provider} {model_id}: {usd}"


def test_kling_audio_defaults_on_everywhere():
    """KIE y APIMart apagan el audio de Kling por defecto; Higgsfield lo enciende."""
    logical = sample("kling-video/v3.0/std/text-to-video")
    assert PROVIDERS["kie"].routes()["kling-video/v3.0/std/text-to-video"].translate(logical)["sound"] is True
    assert (
        PROVIDERS["apimart"].routes()["kling-video/v3.0/std/text-to-video"].translate(logical)["audio"]
        is True
    )
    quiet = {**logical, "sound": "off"}
    assert (
        PROVIDERS["apimart"].routes()["kling-video/v3.0/std/text-to-video"].translate(quiet)["audio"] is False
    )


def test_values_without_exact_equivalent_are_unsupported():
    kie = PROVIDERS["kie"].routes()
    with pytest.raises(ProviderError):  # Wan 2.6 no tiene 480p en KIE
        kie["wan/v2.6/image-to-video"].translate({**sample("wan/v2.6/image-to-video"), "resolution": "480p"})
    with pytest.raises(ProviderError):  # cfg_scale distinto del valor por defecto
        kie["kling-video/v3.0/pro/text-to-video"].translate({**sample("kling-video/v3.0/pro/text-to-video"),
                                                             "cfg_scale": 0.9})  # fmt: skip
    with pytest.raises(ProviderError):  # elementos de Kling: ids que KIE no entiende
        kie["kling-video/v3.0/std/text-to-video"].translate({**sample("kling-video/v3.0/std/text-to-video"),
                                                             "elements": ["el_1"]})  # fmt: skip


def test_unknown_field_is_never_dropped_silently():
    spec = Spec("x", "m")
    with pytest.raises(ProviderError) as info:
        spec({"prompt": "p", "brand_new_field": 1})
    assert info.value.kind == "unsupported" and "brand_new_field" in info.value.message


def test_seedance_edit_puts_the_source_video_first():
    logical = sample("bytedance/seedance-2.5/video-edit")
    logical["video_url"] = "https://cdn.test/source.mp4"
    logical["video_urls"] = ["https://cdn.test/extra.mp4"]
    asked = chosen("bytedance/seedance-2.5/video-edit", "video_urls")
    am = PROVIDERS["apimart"].routes()["bytedance/seedance-2.5/video-edit"].translate(logical, asked)
    assert am["video_urls"] == ["https://cdn.test/source.mp4", "https://cdn.test/extra.mp4"]
    assert am["omni_reference_task_type"] == "edit" and am["duration"] == -1 and "video_url" not in am
    assert "bytedance/seedance-2.5/video-edit" not in PROVIDERS["kie"].routes()  # sin modo de edición fiel


def test_video_input_price_needs_the_input_length():
    route = PROVIDERS["apimart"].routes()["bytedance/seedance-2.5/video-edit"]
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    logical = sample("bytedance/seedance-2.5/video-edit")
    assert route.price(logical, {}, prices) is None
    # 8 s de entrada + 8 s de salida (duration -1 = largo de la entrada) a la tarifa 720P-input
    assert route.price(logical, {"input_video_seconds": 8}, prices) == round(
        prices["seedance-2.5|720P-input"] * 16, 4
    )


def test_explicit_choices_without_equivalent_exclude_the_provider():
    """Revisión 28: una semilla fija o un bitrate elegido no se descartan en silencio."""
    kie, am = PROVIDERS["kie"].routes(), PROVIDERS["apimart"].routes()
    mid = "bytedance/seedance-2.5/text-to-video"
    logical = sample(mid)
    assert "bitrate_mode" not in am[mid].translate(logical, chosen(mid))  # valor por defecto: se omite
    for value in ("high", "standard"):
        with pytest.raises(ProviderError):
            am[mid].translate({**logical, "bitrate_mode": value}, chosen(mid, "bitrate_mode"))
    for mid in ("wan/v2.6/text-to-video", "alibaba/happy-horse/v1.1/text-to-video"):
        with pytest.raises(ProviderError):
            kie[mid].translate({**sample(mid), "seed": 123}, chosen(mid, "seed"))
    assert "seed" not in kie["wan/v2.6/text-to-video"].translate(
        {**sample("wan/v2.6/text-to-video"), "seed": -1}, chosen("wan/v2.6/text-to-video", "seed")
    )


def test_grok_ext_channel_keeps_the_request_exact():
    """Canal -ext de APIMart: 6 a 15 s, 480p o 720p, y formato explícito sin imágenes o el de la imagen."""
    mid = "xai/grok-imagine-video/v1.5/reference-to-video"
    route = route_of("apimart", mid, "grok-imagine-1.5-video-ext")
    assert route.official is False
    base = {**sample(mid), "duration": 6}
    out = route.translate({**base, "aspect_ratio": "9:16"}, chosen(mid, "duration", "aspect_ratio"))
    assert out["size"] == "9:16" and "aspect_ratio" not in out and "image_urls" not in out
    with_image = {**base, "image_url": "https://cdn.test/a.png"}
    out = route.translate(with_image, chosen(mid, "duration", "image_url"))
    assert out["image_urls"] == ["https://cdn.test/a.png"] and "size" not in out
    for bad in ({**base}, {**with_image, "aspect_ratio": "16:9"}, {**base, "duration": 5, "aspect_ratio": "1:1"},
                {**base, "resolution": "1080p", "aspect_ratio": "1:1"}, {**base, "aspect_ratio": "4:3"}):  # fmt: skip
        with pytest.raises(ProviderError) as info:
            route.translate(bad, chosen(mid, *bad))
        assert info.value.kind == "unsupported"
