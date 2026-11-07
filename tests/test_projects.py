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


async def test_auto_generation_is_checked_and_reserved_on_the_server(chat_env):  # noqa: F811
    from .test_supercomputer import PROPOSAL, tool

    _, http, claude = chat_env
    project = (await http.post("/v1/projects", json={"name": "Barcos"})).json()
    chat = (await http.post("/v1/chats", json={"project_id": project["id"]})).json()
    claude.script = [([tool("propose_generation", {**PROPOSAL, "variations": 2})], "tool_use")]
    events = await send(http, chat["id"], "dos barcos")
    pid = next(e["proposal"]["tool_use_id"] for e in events if e["type"] == "proposal")
    url = f"/v1/chats/{chat['id']}/proposals/{pid}/auto"

    assert (await http.post(url)).json()["error"]["code"] == "auto_off"
    await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 1})
    over = await http.post(url)  # 2 × 0,71 no cabe en 1 USD: no se lanza nada
    assert over.status_code == 409 and over.json()["error"]["code"] == "auto_budget_exceeded"
    assert (await http.get("/v1/generations", params={"project": project["id"]})).json()["generations"] == []

    await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 2})
    done = (await http.post(url)).json()
    jobs = done["proposal"]["job_ids"]
    assert len(jobs) == 2 and done["auto_spent_usd"] == 1.42
    listed = (await http.get("/v1/generations", params={"project": project["id"]})).json()["generations"]
    assert sorted(g["id"] for g in listed) == sorted(jobs)
    again = (await http.post(url)).json()  # repetir no lanza ni cobra otra vez
    assert again["proposal"]["job_ids"] == jobs and again["auto_spent_usd"] == 1.42
    # Vincular a mano el mismo trabajo no suma al tope (el cliente ya no informa importes).
    await http.post(f"/v1/chats/{chat['id']}/proposals/{pid}/job", json={"job_id": jobs[0], "auto_usd": 9})
    assert (await http.get(f"/v1/chats/{chat['id']}")).json()["auto_spent_usd"] == 1.42


async def test_a_link_made_while_the_agent_answers_is_kept(chat_env, tmp_path):  # noqa: F811
    import json
    import sqlite3

    from .test_supercomputer import PROPOSAL, tool

    _, http, claude = chat_env
    claude.script = [([tool("propose_generation", PROPOSAL)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "un barco")
    pid = next(e["proposal"]["tool_use_id"] for e in events if e["type"] == "proposal")

    # Mientras Claude responde el mensaje siguiente, otra petición vincula una generación a la propuesta.
    original = claude.__call__

    def answer_and_link(request):
        with sqlite3.connect(tmp_path / "c.db") as db:
            (raw,) = db.execute("SELECT proposals FROM chats WHERE id = ?", (chat["id"],)).fetchone()
            proposals = json.loads(raw)
            proposals[pid] = {**proposals[pid], "job_id": "job-x", "job_ids": ["job-x"], "reported": None}
            db.execute("UPDATE chats SET proposals = ? WHERE id = ?", (json.dumps(proposals), chat["id"]))
        return original(request)

    claude.__class__ = type("Linking", (claude.__class__,), {"__call__": lambda self, r: answer_and_link(r)})
    await send(http, chat["id"], "otra cosa")
    saved = (await http.get(f"/v1/chats/{chat['id']}")).json()
    proposal = next(
        part["proposal"]
        for m in saved["messages"]
        for part in m.get("parts", [])
        if part.get("type") == "proposal"
    )
    assert proposal["job_ids"] == ["job-x"]


async def test_changing_the_budget_waits_for_an_auto_run_in_progress(chat_env):  # noqa: F811
    import asyncio

    from .test_supercomputer import PROPOSAL, tool

    app, http, claude = chat_env
    claude.script = [([tool("propose_generation", PROPOSAL)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "un barco")
    pid = next(e["proposal"]["tool_use_id"] for e in events if e["type"] == "proposal")
    await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 2})

    router = app.state.router
    original, quoting, release = router.plan, asyncio.Event(), asyncio.Event()

    async def slow_plan(*args, **kwargs):
        quoting.set()
        await release.wait()
        return await original(*args, **kwargs)

    router.plan = slow_plan
    try:
        run = asyncio.create_task(http.post(f"/v1/chats/{chat['id']}/proposals/{pid}/auto"))
        await quoting.wait()
        patch = asyncio.create_task(http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 0}))
        await asyncio.sleep(0.05)
        assert not patch.done()  # espera al candado del chat
        release.set()
        assert (await run).status_code == 200
        assert (await patch).json()["auto_budget_usd"] is None
    finally:
        router.plan = original
    # Orden coherente: primero la generación (con su tope), después el apagado que reinicia lo gastado.
    assert (await http.get(f"/v1/chats/{chat['id']}")).json()["auto_spent_usd"] == 0


async def test_an_upload_can_be_removed_from_the_list(env):  # noqa: F811
    _, http, _ = env
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    up = (await http.post("/v1/uploads", files={"file": ("a.png", png, "image/png")})).json()
    assert any(u["id"] == up["id"] for u in (await http.get("/v1/uploads")).json()["uploads"])
    assert (await http.delete(f"/v1/uploads/{up['id']}")).status_code == 204
    assert all(u["id"] != up["id"] for u in (await http.get("/v1/uploads")).json()["uploads"])
    assert (await http.delete(f"/v1/uploads/{up['id']}")).status_code == 404
