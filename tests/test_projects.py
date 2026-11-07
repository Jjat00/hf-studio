"""Proyectos y carpetas de la biblioteca, y su uso en Supercomputer (brief como contexto, tope automático)."""

from __future__ import annotations

from .test_routing import T2V, VIDEO, env  # noqa: F401  (fixture)
from .test_supercomputer import env as chat_env  # noqa: F401
from .test_supercomputer import send


async def test_projects_folders_and_moving_generations(env):  # noqa: F811
    _, http, _ = env
    made = (await http.post("/v1/projects", json={"name": "Spot Frostbyte"})).json()
    assert made["brief"].startswith("# Spot Frostbyte") and "## Visuales" in made["brief"]
    assert made["folders"] == [] and made["generations"] == 0
    folder = (await http.post(f"/v1/projects/{made['id']}/folders", json={"name": "Tomas"})).json()

    job = await http.post(
        "/v1/generations",
        json={"model": T2V, "input": VIDEO, "max_usd": 0.71, "folder_id": folder["id"]},
    )
    job = job.json()
    assert job["project_id"] == made["id"] and job["folder_id"] == folder["id"]
    listed = (await http.get("/v1/generations", params={"project": made["id"]})).json()["generations"]
    assert [g["id"] for g in listed] == [job["id"]]
    assert (await http.get("/v1/generations", params={"project": "none"})).json()["generations"] == []

    other = (await http.post("/v1/projects", json={"name": "Otro"})).json()
    moved = await http.post("/v1/generations/move", json={"ids": [job["id"]], "project_id": other["id"]})
    assert moved.json()["changed"] == [job["id"]]
    again = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert again["project_id"] == other["id"] and again["folder_id"] is None
    bad = await http.post(
        "/v1/generations/move",
        json={"ids": [job["id"]], "project_id": other["id"], "folder_id": folder["id"]},
    )
    assert bad.json()["error"]["code"] == "folder_mismatch"

    patched = await http.patch(f"/v1/projects/{other['id']}", json={"brief": "Tono noir", "description": "x"})
    assert patched.json()["brief"] == "Tono noir"
    assert (await http.patch(f"/v1/folders/{folder['id']}", json={"name": "B-roll"})).json()[
        "name"
    ] == "B-roll"
    assert (await http.delete(f"/v1/projects/{other['id']}")).status_code == 204
    assert (await http.get(f"/v1/generations/{job['id']}")).json()["project_id"] is None
    names = [p["name"] for p in (await http.get("/v1/projects")).json()["projects"]]
    assert names == ["Spot Frostbyte"]
    missing = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "project_id": "nope"})
    assert missing.json()["error"]["code"] == "project_not_found"


async def test_a_project_chat_sends_the_brief_and_the_auto_budget(chat_env):  # noqa: F811
    _, http, claude = chat_env
    project = (await http.post("/v1/projects", json={"name": "Café", "brief": "Paleta cálida, 9:16"})).json()
    chat = (await http.post("/v1/chats", json={"project_id": project["id"]})).json()
    assert chat["project_id"] == project["id"]
    patched = (await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 3})).json()
    assert patched["auto_budget_usd"] == 3 and patched["auto_spent_usd"] == 0
    await send(http, chat["id"], "haz un reel")
    head = claude.requests[0]["messages"][0]["content"][0]["text"]
    assert '<studio_project name="Café">\nPaleta cálida, 9:16' in head
    assert 'remaining_usd="3.00"' in head
    off = (await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 0, "project_id": ""})).json()
    assert off["auto_budget_usd"] is None and off["project_id"] is None
