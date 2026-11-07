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
    assert listed[0]["slug"] == "ads-ugc" and listed[0]["files"] == [] and "body" not in listed[0]
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


async def test_reference_files_are_read_on_demand(env):  # noqa: F811
    _, http, claude = env
    files = {"references/master.md": "# Máster\nÁngulos…", "references/plantillas/01-chat.md": "Plantilla 1"}
    made = await http.post("/v1/skills", json={"skill_md": SKILL_MD, "files": files})
    assert [f["path"] for f in made.json()["files"]] == sorted(files)
    bad = await http.post(
        "/v1/skills", json={"slug": "x", "description": "d", "body": "b", "files": {"../etc": "x"}}
    )
    assert bad.json()["error"]["code"] == "invalid_file"
    got = await http.get("/v1/skills/ads-ugc/files/references/master.md")
    assert got.json()["content"].startswith("# Máster")
    # Editar sin `files` conserva los archivos
    await http.put("/v1/skills/ads-ugc", json={"slug": "ads-ugc", "description": "d", "body": "b"})
    assert len((await http.get("/v1/skills/ads-ugc")).json()["files"]) == 2

    chat = (await http.post("/v1/chats", json={})).json()
    claude.script = [
        (
            [tool("read_skill_file", {"name": "ads-ugc", "path": "references/plantillas/01-chat.md"})],
            "tool_use",
        )
    ]
    await send(http, chat["id"], "/ads-ugc un anuncio")
    block = next(
        b["text"] for b in claude.requests[0]["messages"][0]["content"] if b["text"].startswith("<skill")
    )
    assert "- references/master.md" in block  # la lista de archivos va con la skill, no su contenido
    result = json.loads(claude.requests[1]["messages"][-1]["content"][0]["content"])
    assert result["content"] == "Plantilla 1"


async def test_builtin_skills_are_installed_once(env):  # noqa: F811
    _, http, _ = env
    listed = [s["slug"] for s in (await http.get("/v1/skills")).json()["skills"]]
    assert "character-sheet" in listed
    sheet = (await http.get("/v1/skills/character-sheet")).json()
    assert (
        "sin la cabeza" in sheet["description"] and "BOTTOM" not in sheet["body"] and "16:9" in sheet["body"]
    )
    await http.delete("/v1/skills/character-sheet")
    listed = [s["slug"] for s in (await http.get("/v1/skills")).json()["skills"]]
    assert "character-sheet" not in listed  # borrada por el usuario: no vuelve
