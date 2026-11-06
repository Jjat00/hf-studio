"""Skills de Supercomputer: CRUD, importar un SKILL.md y usarlas en el chat (con /nombre o por el agente)."""

from __future__ import annotations

import json

import pytest

from hf_studio.skills import SkillError, invoked, parse_skill_md

from .test_supercomputer import env, send, tool  # noqa: F401  (fixture)

SKILL_MD = """---
name: Ads UGC
description: Guion de anuncio UGC en 3 actos para TikTok y Reels.
---
# Cómo hacerlo
1. Gancho en 2 s.
"""


def test_parse_skill_md_and_mentions():
    assert parse_skill_md(SKILL_MD) == (
        "ads-ugc",
        "Guion de anuncio UGC en 3 actos para TikTok y Reels.",
        "# Cómo hacerlo\n1. Gancho en 2 s.",
    )
    with pytest.raises(SkillError):
        parse_skill_md("sin frontmatter")
    assert invoked("hazlo con /ads-ugc y /nada, otra vez /ads-ugc. ruta a/b /x", {"ads-ugc", "x"}) == [
        "ads-ugc",
        "x",
    ]
    assert invoked("http://web.test/ads-ugc", {"ads-ugc"}) == []


async def test_skills_crud_and_import(env):  # noqa: F811
    _, http, _ = env
    made = await http.post("/v1/skills", json={"skill_md": SKILL_MD})
    assert made.status_code == 201 and made.json()["slug"] == "ads-ugc"
    assert (await http.post("/v1/skills", json={"skill_md": SKILL_MD})).json()["error"][
        "code"
    ] == "skill_exists"
    bad = await http.post("/v1/skills", json={"slug": "Mal Nombre", "description": "x", "body": "y"})
    assert bad.json()["error"]["code"] == "invalid_slug"
    listed = (await http.get("/v1/skills")).json()["skills"]
    assert listed == [
        {"slug": "ads-ugc", "description": listed[0]["description"], "updated_at": listed[0]["updated_at"]}
    ]
    edited = await http.put(
        "/v1/skills/ads-ugc", json={"slug": "ugc", "description": "Otra", "body": "Pasos"}
    )
    assert edited.json()["slug"] == "ugc" and (await http.get("/v1/skills/ugc")).json()["body"] == "Pasos"
    assert (await http.delete("/v1/skills/ugc")).status_code == 204
    assert (await http.get("/v1/skills/ugc")).status_code == 404


async def test_a_slash_skill_goes_with_the_message_and_the_agent_can_load_one(env):  # noqa: F811
    _, http, claude = env
    await http.post("/v1/skills", json={"skill_md": SKILL_MD})
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "/ads-ugc anuncio para mi michelada")
    content = claude.requests[0]["messages"][0]["content"]
    assert any(
        b["text"].startswith('<skill name="ads-ugc">\n# Cómo hacerlo') for b in content if b["type"] == "text"
    )
    assert content[-1]["text"] == "/ads-ugc anuncio para mi michelada"
    assert (
        events[-1]["chat"]["messages"][0]["text"] == "/ads-ugc anuncio para mi michelada"
    )  # se ve como se escribió

    claude.script = [([tool("list_skills", {}), tool("use_skill", {"name": "/ads-ugc"}, 2)], "tool_use")]
    await send(http, chat["id"], "otro anuncio")
    results = claude.requests[2]["messages"][-1]["content"]
    assert json.loads(results[0]["content"])["skills"][0]["name"] == "ads-ugc"
    assert json.loads(results[1]["content"])["instructions"].startswith("# Cómo hacerlo")
