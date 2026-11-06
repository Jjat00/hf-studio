from hf_studio.recommend import parse_task


def test_spanish_two_photos_cheap():
    t = parse_task("quiero un video barato que vaya entre dos fotos")
    assert t["output"] == "video" and "first-last-frame" in t["capabilities"] and t["cheap"]


def test_dance_swap_and_image():
    assert parse_task("make my character dance like this video")["capabilities"] == ["motion-transfer"]
    assert "object-swap" in parse_task("replace the bottle in my ad with my product")["capabilities"]
    img = parse_task("a poster for a jazz night, best quality")
    assert img["output"] == "image" and img["quality"]


def test_a_named_model_is_found_by_its_name_and_version():
    from hf_studio.catalog import get_catalog
    from hf_studio.recommend import named_models

    pool = [m for m in get_catalog().models.values() if m["output"] in ("video", "image")]
    found = {m["id"] for m in named_models("usa gemini omni 1.2", pool)}
    assert found and all(i.startswith("google/gemini-omni-1.2-flash/") for i in found)
    assert {m["id"] for m in named_models("gpt image 2.6", pool)} >= {
        "openai/gpt-image-2.6/flare/text-to-image"
    }
    assert named_models("un video épico de naves con sonido", pool) == []
