"""Kling Image 4.0 (`store/kling_image.py`): rutas de tienda del modelo de Higgsfield y Long Image. Sin gastar créditos."""

from __future__ import annotations

import pytest

from hf_studio import store
from hf_studio.catalog import get_catalog
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.registry import PROVIDERS
from hf_studio.providers.routes import routes_for, with_defaults
from hf_studio.store import kling_image as k
from tests.test_routes import _prices, route_of

IMG = ["https://cdn.test/a.png", "https://cdn.test/b.png"]


def logical(model_id: str, **extra) -> dict:
    return with_defaults(get_catalog().get(model_id)["input_schema"], {"prompt": "a fox", **extra})


def test_higgsfield_model_gets_cheaper_store_routes():
    t2i, edit = f"{k.HF}/text-to-image", f"{k.HF}/edit"
    assert not get_catalog().get(t2i).get("store")
    kie = route_of("kie", t2i)
    assert kie.translate(logical(t2i, resolution="8k")) == {
        "prompt": "a fox", "resolution": "8k", "aspect_ratio": "auto",
    }  # fmt: skip
    assert kie.price(logical(t2i), {}, _prices("kie")) == 0.0565  # contra 0,063 en Higgsfield
    assert (
        route_of("kie", edit).price(logical(edit, image_urls=IMG), {}, _prices("kie")) == 0.0615
    )  # +2 × 0,0025
    apimart = route_of("apimart", t2i)
    assert apimart.translate(logical(t2i, aspect_ratio="16:9")) == {
        "prompt": "a fox",
        "resolution": "2K",
        "size": "16:9",
    }
    assert (
        apimart.price(logical(t2i, resolution="4k"), {}, _prices("apimart")) == 0.0857
    )  # per_unit redondea a 4 decimales
    with pytest.raises(ProviderError):  # APIMart no tiene 8K
        apimart.translate(logical(t2i, resolution="8k"))
    # APIMart cobra las referencias sin publicar el importe: la edición no va por ahí
    assert not routes_for(PROVIDERS["apimart"].routes(), edit)
    with pytest.raises(ProviderError):  # KIE corta el prompt en 20000 caracteres
        kie.translate(logical(t2i, prompt="x" * 20001))
    assert APIMartProvider._submit_path(k.APIMART_IMAGE) == "/v1/images/generations"


def test_long_image_ecommerce_on_kie():
    assert k.ECOMMERCE in store.models() and k.WEBPAGE in store.models()
    route = route_of("kie", k.ECOMMERCE)
    entry = logical(k.ECOMMERCE, image_urls=IMG, length="long", resolution="1k")
    assert route.translate(entry) == {
        "prompt": "a fox", "image_urls": IMG, "length": "long", "resolution": "1k", "skill": "ecommerce",
    }  # fmt: skip
    assert route.price(entry, {}, _prices("kie")) == 0.71  # 0,705 + 2 fotos × 0,0025
    assert not routes_for(PROVIDERS["apimart"].routes(), k.ECOMMERCE)


def test_long_image_webpage_on_both_stores():
    plain = logical(k.WEBPAGE)
    assert route_of("kie", k.WEBPAGE).price(plain, {}, _prices("kie")) == 0.5375
    apimart = route_of("apimart", k.WEBPAGE)
    assert apimart.translate(plain) == {"prompt": "a fox", "resolution": "2K", "skill": "webpage"}
    assert apimart.price(plain, {}, _prices("apimart")) == 0.5429
    styled = logical(k.WEBPAGE, style_image_url=IMG[0])
    assert route_of("kie", k.WEBPAGE).translate(styled)["style_image"] == IMG[0]
    assert route_of("kie", k.WEBPAGE).price(styled, {}, _prices("kie")) == 0.54
    with pytest.raises(ProviderError):  # con imágenes, APIMart no publica el precio
        apimart.translate(styled)


@pytest.mark.parametrize("variant", ["h3-lite", "h3-highspeed"])
def test_minimax_h3_lite_and_highspeed_schemas_follow_higgsfield(variant):
    """Listas de referencias vacías valen (como en Higgsfield) si alguna trae algo; la marca de agua no se ofrece."""
    mid = f"minimax/{variant}/reference-to-video"
    ok = {"prompt": "a fox", "image_urls": IMG[:1], "video_urls": [], "audio_urls": []}
    assert get_catalog().validate(mid, ok) == []
    assert get_catalog().validate(mid, {"prompt": "a fox", "audio_urls": ["https://cdn.test/a.mp3"]}) == []
    assert get_catalog().validate(
        mid, {"prompt": "a fox", "image_urls": [], "video_urls": [], "audio_urls": []}
    )
    assert get_catalog().validate(mid, {"prompt": "a fox"})
    for mode in ("text-to-video", "image-to-video", "reference-to-video"):
        assert (
            "aigc_watermark"
            not in get_catalog().get(f"minimax/{variant}/{mode}")["input_schema"]["properties"]
        )
    i2v = f"minimax/{variant}/image-to-video"
    assert get_catalog().validate(i2v, {"prompt": "a fox", "end_image_url": IMG[0]}) == []
    assert get_catalog().validate(i2v, {"prompt": "a fox"})
