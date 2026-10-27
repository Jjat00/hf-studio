from hf_studio.pricing import approximate, fill_placeholders, normalize

SEEDANCE = (
    "Token-metered pricing. Billable video tokens = ceil(generated video seconds × output width × output height"
    " × 24 fps / 1024). Image and audio references do not count as video input. Per 1,000 video tokens:"
    " 480p/720p/1080p $0.014, 4K $0.008. Rates shown are before any applicable customer discount."
)
EDIT = (
    "Token-metered pricing. Billable video tokens = ceil((input video seconds + generated video seconds) × output"
    " width × output height × 24 fps / 1024). Image and audio references do not count as video input. Per 1,000"
    " video tokens: without video input — 480p/720p/1080p $0.014, 4K $0.008; with video input — 480p/720p/1080p"
    " $0.0084, 4K $0.0048 (0.6× the standard rate). Rates shown are before any applicable customer discount."
)
PER_SECOND = "Priced per generated second by resolution: 480p $0.05, 720p $0.10, or 1080p $0.20. Rates shown are before any applicable customer discount."
INPUT_SECOND = "Per-second pricing. Each second of input video costs $0.318 at 480p or $0.681 at 720p. Input duration is rounded up to the nearest whole second."


def test_seedance_text_to_video_matches_published_formula():
    r = approximate(SEEDANCE, {"duration": 5, "resolution": "720p", "aspect_ratio": "16:9"}, {})
    # ceil(5 × 1280 × 720 × 24 / 1024) = 108000 tokens × $0.014/1K
    assert round(r["usd"], 3) == 1.512 and r["missing"] == []


def test_video_input_uses_discounted_rate_and_needs_duration():
    args = {"duration": 5, "resolution": "480p", "aspect_ratio": "16:9", "video_url": "https://x/v.mp4"}
    assert approximate(EDIT, args, {})["missing"] == ["input video duration"]
    r = approximate(EDIT, args, {"input_video_seconds": 5})
    assert "$0.0084" in r["basis"] and r["usd"] > approximate(EDIT, args, {})["usd"]


def test_per_second_and_input_second_formulas():
    assert approximate(PER_SECOND, {"duration": 8, "resolution": "1080p"}, {})["usd"] == 1.6
    assert approximate(INPUT_SECOND, {"resolution": "720p"}, {})["usd"] is None
    assert approximate(INPUT_SECOND, {"resolution": "720p"}, {"input_video_seconds": 4.2})["usd"] == 5 * 0.681


def test_placeholders_follow_conditional_schema():
    schema = {
        "if": {"required": ["image_urls"]},
        "else": {"required": ["video_urls"]},
        "required": [],
        "properties": {"image_urls": {"type": "array"}, "video_urls": {"type": "array"}},
    }
    filled, added = fill_placeholders(schema, {})
    assert added == ["video_urls"] and filled["video_urls"][0].endswith(".mp4")
    filled, added = fill_placeholders(schema, {"image_urls": ["https://x/a.png"]})
    assert added == []


def test_exact_estimate_keeps_discount():
    raw = {"type": "estimate", "credits": "8.568", "usd": "0.536", "discount": {"percentage": "15.00"}}
    r = normalize(raw, {}, {}, ["image_url"])
    assert r["kind"] == "exact" and r["credits"] == 8.568 and r["discount_pct"] == 15.0


def test_rate_at_end_of_sentence_ignores_the_period():
    # Seedance 2.5 video-edit/extend: el precio cierra la frase («$0.01284.»); antes daba un 500.
    desc = (
        "Token-metered pricing. Billable video tokens = ceil((input video seconds + generated video seconds) × output"
        " width × output height × 24 fps / 1024). Video input is required. At 480p or 720p, each 1,000 video tokens"
        " cost $0.01284. Both input and generated video durations are billable."
    )
    args = {"duration": 5, "resolution": "480p", "aspect_ratio": "16:9", "video_url": "https://x/v.mp4"}
    r = approximate(desc, args, {"input_video_seconds": 5})
    assert "$0.01284/1K" in r["basis"] and r["usd"] > 0


FLARE = (
    "Per 1M tokens: text input $5, cached text input $1.25, text output $10; image input $8, cached image input"
    " $2, image output $30. Quality defaults to high. Final cost uses actual token usage."
)


def test_token_priced_image_is_quoted_high_from_quality_resolution_and_references():
    """Marketing Studio 2.5 Flare/Sunburst: se cotiza por lo alto (no se sabe el uso real hasta terminar)."""
    one_k = approximate(
        FLARE, {"prompt": "x", "quality": "medium", "resolution": "1k", "image_urls": ["a", "b"]}, {}
    )
    # 1.056 tokens de salida × $30/1M + 2 referencias × 600 × $8/1M + el prompt.
    assert round(one_k["usd"], 4) == round((1056 * 30 + 2 * 600 * 8 + 1 * 5) / 1e6, 4)
    assert "upper estimate" in one_k["basis"]
    default = approximate(FLARE, {"prompt": "x"}, {})  # alta y 2k por defecto
    assert round(default["usd"], 4) == round((4160 * 4 * 30 + 5) / 1e6, 4)
    # Calidades sin tabla no se inventan: quedan sin precio.
    assert approximate(FLARE, {"prompt": "x", "quality": "max"}, {})["usd"] is None


# Textos de /estimate a 2026-10-15 (Higgsfield cambió la redacción y añadió 1080p).
SEEDANCE_25 = (
    "For 16:9 video without video input, your request costs roughly $0.2056 per second of generated video at 480p,"
    " $0.4622 at 720p, and $1.1372 at 1080p. Each 1,000 video tokens costs $0.0214 at 480p or 720p and $0.0234 at"
    " 1080p. If video inputs are provided, the token rate is multiplied by 0.6: $0.01284 per 1,000 tokens at 480p or"
    " 720p and $0.01404 at 1080p. Both input and generated video durations are billable. Billable video tokens ="
    " ceil(output height × output width × (input video duration + generated video duration) × 24 / 1024)."
)
SEEDANCE_25_EDIT = (
    "Video input is required. Each 1,000 video tokens costs $0.01284 at 480p or 720p and $0.01404 at 1080p (0.6× the"
    " no-video-input rate). Billable video tokens = ceil(output height × output width × (input video duration +"
    " generated video duration) × 24 / 1024)."
)
GENJUTSU = (
    "Per-second pricing. Each second of input video costs $0.318 at 480p, $0.681 at 720p, $1.632 at 1080p. Input"
    " duration is rounded up to the nearest whole second. Rates shown are before any applicable customer discount."
)
RESTYLE = "Roughly costs $0.318 per second at 480p, $0.681 per second at 720p, or $1.632 per second at 1080p."
WAN3_R2V = (
    "Priced per total video second: 480p $0.05/s, 720p $0.10/s, 1080p $0.20/s. Total billable duration = output"
    " video duration + the sum of all input reference video durations."
)
VIDEO = {"video_url": "https://x/v.mp4"}


def test_seedance_25_rates_by_resolution_and_video_input():
    t2v = approximate(SEEDANCE_25, {"duration": 5, "resolution": "720p", "aspect_ratio": "16:9"}, {})
    assert round(t2v["usd"], 4) == 2.3112  # = 5 s × $0.4622/s publicado
    hd = approximate(SEEDANCE_25, {"duration": 5, "resolution": "1080p", "aspect_ratio": "16:9"}, {})
    assert "$0.0234/1K" in hd["basis"]
    refs = {"duration": 5, "resolution": "720p", "aspect_ratio": "16:9", "video_urls": ["https://x/v.mp4"]}
    assert approximate(SEEDANCE_25, refs, {})["missing"] == ["input video duration"]
    with_video = approximate(SEEDANCE_25, refs, {"input_video_seconds": 5})
    assert "$0.01284/1K" in with_video["basis"] and "10s" in with_video["basis"]
    edit = approximate(SEEDANCE_25_EDIT, {"duration": 5, "resolution": "1080p", "aspect_ratio": "16:9", **VIDEO},
                       {"input_video_seconds": 5})  # fmt: skip
    assert "$0.01404/1K" in edit["basis"]


def test_input_second_pricing_uses_the_rate_of_the_requested_resolution():
    # Antes, todo lo que no fuera 720p salía a la tarifa de 480p: 1080p se cotizaba 5 veces por debajo.
    hint = {"input_video_seconds": 4.2}
    assert approximate(GENJUTSU, {"resolution": "1080p", **VIDEO}, hint)["usd"] == 5 * 1.632
    assert approximate(GENJUTSU, {"resolution": "480p", **VIDEO}, hint)["usd"] == 5 * 0.318
    assert (
        approximate(INPUT_SECOND, {"resolution": "1080p", **VIDEO}, hint)["usd"] is None
    )  # sin tarifa publicada
    # El texto puede terminar en «1080p.» sin espacio detrás.
    assert approximate(GENJUTSU.split(" Input")[0], {"resolution": "720p", **VIDEO}, hint)["usd"] == 5 * 0.681


RS = "higgsfield/genjutsu/restyle/v1.0"


def test_restyle_bills_the_source_seconds_trimmed_to_30():
    assert approximate(RESTYLE, {"resolution": "720p", **VIDEO}, {}, RS)["missing"] == [
        "input video duration"
    ]
    assert (
        approximate(RESTYLE, {"resolution": "720p", **VIDEO}, {"input_video_seconds": 8.1}, RS)["usd"]
        == 9 * 0.681
    )
    assert (
        approximate(RESTYLE, {"resolution": "1080p", **VIDEO}, {"input_video_seconds": 45}, RS)["usd"]
        == 30 * 1.632
    )
    # El recorte a 30 s es de Restyle: otro modelo con un texto parecido no lo hereda.
    assert approximate(RESTYLE, {"resolution": "720p", **VIDEO}, {"input_video_seconds": 45})["usd"] is None


def test_wan3_reference_bills_output_plus_input_videos():
    assert approximate(WAN3_R2V, {"duration": 5, "resolution": "720p"}, {})["usd"] == 0.5
    refs = {"duration": 5, "resolution": "1080p", "video_urls": ["https://x/v.mp4"]}
    assert approximate(WAN3_R2V, refs, {})["missing"] == ["input video duration"]
    assert approximate(WAN3_R2V, refs, {"input_video_seconds": 3})["usd"] == 8 * 0.2


def test_ads_studio_is_quoted_high_per_image_times_the_batch():
    # 2k y calidad alta fijas, como Marketing Studio; el ≈$0.084 de la documentación es un ejemplo, no un tope.
    one = approximate(FLARE, {"prompt": "x"}, {}, "higgsfield/ads-studio/v1.0")
    three = approximate(
        FLARE, {"prompt": "x", "batch_size": 3, "image_urls": ["a"]}, {}, "higgsfield/ads-studio/v1.0"
    )
    assert round(one["usd"], 4) == round((4160 * 4 * 30 + 5) / 1e6, 4)
    assert round(three["usd"], 4) == round(3 * (4160 * 4 * 30 + 600 * 8 + 5) / 1e6, 4)
    assert three["basis"].startswith("3 images × ")


def test_edit_without_duration_bills_an_output_as_long_as_the_input():
    # Seedance 2.5 video-edit no tiene duration: la salida dura lo que la entrada (15 s + 15 s = 30 s).
    args = {"resolution": "720p", "aspect_ratio": "16:9", **VIDEO}
    r = approximate(SEEDANCE_25_EDIT, args, {"input_video_seconds": 15}, output_follows_input=True)
    assert "30s × 1280×720" in r["basis"] and r["missing"] == []
    assert approximate(SEEDANCE_25_EDIT, args, {}, output_follows_input=True)["missing"] == [
        "input video duration"
    ]


def test_placeholders_follow_nested_conditions_and_fill_the_restyle_preset():
    # Seedance 2.5 reference-to-video: imágenes, si no videos, si no audios.
    nested = {"if": {"required": ["image_urls"]},
              "else": {"if": {"required": ["video_urls"]}, "else": {"required": ["audio_urls"]}},
              "properties": {"image_urls": {"type": "array"}, "video_urls": {"type": "array"},
                             "audio_urls": {"type": "array"}}}  # fmt: skip
    assert fill_placeholders(nested, {})[1] == ["audio_urls"]
    assert fill_placeholders(nested, {"video_urls": ["https://x/v.mp4"]})[1] == []
    restyle = {"required": ["video_url", "preset_id"],
               "properties": {"video_url": {"type": "string"}, "preset_id": {"type": "string", "format": "uuid"}}}  # fmt: skip
    filled, added = fill_placeholders(restyle, {})
    assert added == ["preset_id", "video_url"] and len(filled["preset_id"]) == 36


KLING4 = (
    "Without input video: 720p $0.157/s, 1080p $0.235/s, charged on output duration. With input video: 720p"
    " $0.094/s, 1080p $0.141/s, charged on output duration + max(total input video duration, output duration)."
    " Input duration includes video elements and explicit videos after the 30-second trim."
)
GENJUTSU_LIGHT = (
    "Priced per total second by resolution: 480p $0.05, 720p $0.10, or 1080p $0.20. Rates shown are before any"
    " applicable customer discount. Billable seconds = output duration + the sum of input reference video durations."
    " Input video durations are measured during preprocessing; without video references, only output duration is"
    " billed. Genjutsu Light trims the source to 15 seconds; output duration is rounded up to whole seconds before"
    " billing."
)


def test_kling4_charges_output_alone_or_plus_the_longer_of_input_and_output():
    assert round(approximate(KLING4, {"duration": 10, "resolution": "1080p"}, {})["usd"], 3) == 2.35
    edit = {"duration": 5, "resolution": "720p", "video_url": "https://x/v.mp4"}
    # Video de 12 s y salida de 5 s: 5 + max(12, 5) = 17 s a la tarifa con video.
    assert round(approximate(KLING4, edit, {"input_video_seconds": 12})["usd"], 3) == round(17 * 0.094, 3)
    assert approximate(KLING4, edit, {})["missing"] == ["input video duration"]


def test_genjutsu_light_bills_output_trimmed_to_15s_plus_input():
    args = {"resolution": "480p", "video_url": "https://x/v.mp4", "image_urls": ["https://x/a.png"]}
    assert approximate(GENJUTSU_LIGHT, args, {})["usd"] is None
    assert approximate(GENJUTSU_LIGHT, args, {"input_video_seconds": 8.2})["usd"] == (9 + 8.2) * 0.05
    assert approximate(GENJUTSU_LIGHT, args, {"input_video_seconds": 20})["usd"] == (15 + 20) * 0.05


def test_quote_prices_text_formulas_with_schema_defaults():
    import asyncio

    from hf_studio.catalog import get_catalog
    from hf_studio.pricing import quote

    class FakeHF:
        async def estimate(self, model, args):
            return {"type": "description", "pricing_description": KLING4}

    catalog = get_catalog()
    model = catalog.get("kling-video/v4.0/reference-to-video")
    r = asyncio.run(
        quote(FakeHF(), catalog, model, {"prompt": "x @image_1", "image_urls": ["https://x/a.png"]}, {})
    )
    # Sin duración ni resolución, Kling 4.0 hace 10 s en 1080p.
    assert round(r["usd"], 3) == 2.35 and "1080p" in r["basis"]
