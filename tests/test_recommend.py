from hf_studio.recommend import parse_task


def test_spanish_two_photos_cheap():
    t = parse_task("quiero un video barato que vaya entre dos fotos")
    assert t["output"] == "video" and "first-last-frame" in t["capabilities"] and t["cheap"]


def test_dance_swap_and_image():
    assert "motion-transfer" in parse_task("make my character dance like this video")["capabilities"]
    assert "object-swap" in parse_task("replace the bottle in my ad with my product")["capabilities"]
    img = parse_task("a poster for a jazz night, best quality")
    assert img["output"] == "image" and img["quality"]
