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
