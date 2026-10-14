"""Los presets de serie deben producir una entrada válida para su modelo con valores de ejemplo."""

import pytest

from hf_studio.catalog import get_catalog
from hf_studio.presets import BUILTIN, render, resolve_values, variables_in

SAMPLE = {
    "image": "https://cdn.test/a.png",
    "images": ["https://cdn.test/a.png"],
    "video": "https://cdn.test/a.mp4",
    "text": "a red scarf",
    "textarea": "a red scarf",
}


@pytest.mark.parametrize("preset", BUILTIN, ids=lambda p: p["slug"])
def test_builtin_preset_matches_its_model(preset):
    catalog = get_catalog()
    assert catalog.get(preset["model"]), preset["model"]
    declared = {v["key"] for v in preset["variables"]}
    assert variables_in(preset["template"]) <= declared
    given = {v["key"]: SAMPLE[v["type"]] for v in preset["variables"] if v["type"] in SAMPLE}
    for v in preset["variables"]:
        if v["type"] == "select":
            assert v.get("default") in v["options"]
    values, missing = resolve_values(preset, given)
    assert missing == []
    assert catalog.validate(preset["model"], render(preset["template"], values)) == []
