"""AI Director: skills de dirección incluidas, lista de tomas enlazada a las propuestas, documentos del proyecto,
brief por secciones, revisión de resultados con fotogramas, encadenar tomas, presupuesto y elementos con clic."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from sqlalchemy import select, update

from hf_studio.db import ApiClient, Element, Job
from hf_studio.director import frame_times, replace_section

from .test_routing import T2V, VIDEO
from .test_supercomputer import PROPOSAL, env, send, tool  # noqa: F401  (fixture)

DIRECTOR_SKILLS = {
    "lista-de-tomas", "biblia-continuidad", "tratamiento", "desglose-guion", "plan-de-cobertura", "look-y-color",
    "spot-publicitario", "revision-dailies", "puesta-en-escena", "trailer-teaser", "videoclip",
    "entregables-plataforma",
}  # fmt: skip
FFMPEG = shutil.which("ffmpeg") is not None


def result_of(claude, n: int = 1) -> dict:
    """Resultado JSON de la herramienta que vio Claude en la petición `n`."""
    content = claude.requests[n]["messages"][-1]["content"][0]["content"]
    return json.loads(content if isinstance(content, str) else content[0]["text"])


async def project_chat(http, name: str = "Corto") -> tuple[dict, dict]:
    project = (await http.post("/v1/projects", json={"name": name})).json()
    chat = (await http.post("/v1/chats", json={"project_id": project["id"]})).json()
    return project, chat


async def finished_job(
    app, kind: str = "image", data: bytes | None = None, project_id: str | None = None
) -> str:
    ext, ctype = ("mp4", "video/mp4") if kind == "video" else ("png", "image/png")
    async with app.state.sessions() as s:
        owner = await s.scalar(select(ApiClient))
        job = Job(owner_id=owner.id, model=T2V, input={"prompt": "fox"}, input_hash="h", status="completed",
                  outputs=[{"kind": kind, "url": f"https://cdn.test/out.{ext}"}], project_id=project_id,
                  files=[{"name": f"0.{ext}", "kind": kind, "size": 1, "content_type": ctype, "index": 0}])  # fmt: skip
        s.add(job)
        await s.commit()
    folder = app.state.settings.storage_dir / "outputs" / job.id
    folder.mkdir(parents=True, exist_ok=True)
    if data is not None:
        (folder / f"0.{ext}").write_bytes(data)
    return job.id


def make_media(tmp_path, kind: str) -> bytes:
    out = tmp_path / ("clip.mp4" if kind == "video" else "still.png")
    source = "testsrc=size=320x180:rate=10:duration=2" if kind == "video" else "testsrc=size=64x64"
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source]
    args += ["-pix_fmt", "yuv420p", str(out)] if kind == "video" else ["-frames:v", "1", str(out)]
    subprocess.run(args, check=True)
    return out.read_bytes()


async def test_the_director_skills_ship_with_the_studio(env):  # noqa: F811
    _, http, _ = env
    listed = {s["slug"] for s in (await http.get("/v1/skills")).json()["skills"]}
    assert DIRECTOR_SKILLS <= listed
    shots = (await http.get("/v1/skills/lista-de-tomas")).json()
    assert [f["path"] for f in shots["files"]] == ["references/cinema-studio.md"]
    ref = (await http.get("/v1/skills/lista-de-tomas/files/references/cinema-studio.md")).json()["content"]
    assert "neon-rain-at-midnight" in ref and "f11-deep-focus" in ref
    assert "upsert_shots" in shots["body"]


async def test_project_tools_need_a_project(env):  # noqa: F811
    _, http, claude = env
    claude.script = [([tool("upsert_shots", {"shots": [{"scene": "1", "number": "1.1"}]})], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    await send(http, chat["id"], "haz la lista de tomas")
    assert "no project" in result_of(claude)["error"]
    system = str(claude.requests[0]["system"])
    assert "# Director" in system and "upsert_shots" in {t["name"] for t in claude.requests[0]["tools"]}


async def test_a_shot_list_follows_its_takes(env):  # noqa: F811
    app, http, claude = env
    project, chat = await project_chat(http)
    shots = [
        {"scene": "1", "number": "1.1", "purpose": "Barco entra", "shot_size": "WS", "model_id": T2V,
         "params": {k: v for k, v in VIDEO.items() if k != "prompt"}, "prompt": VIDEO["prompt"]},
        {"scene": "1", "number": "1.2", "purpose": "Detalle", "shot_size": "insert"},
    ]  # fmt: skip
    claude.script = [([tool("upsert_shots", {"shots": shots})], "tool_use")]
    await send(http, chat["id"], "lista de tomas")
    saved = result_of(claude)["shots"]
    assert [s["number"] for s in saved] == ["1.1", "1.2"] and all(s["status"] == "planned" for s in saved)
    first, second = saved[0]["shot_id"], saved[1]["shot_id"]

    # Mismo número sin id: se actualiza, no se duplica.
    claude.script = [([tool("upsert_shots", {"shots": [{"scene": "1", "number": "1.2", "notes": "macro"}]}, 2)], "tool_use")]  # fmt: skip
    events = await send(http, chat["id"], "nota")
    assert [e["label"] for e in events if e["type"] == "tool"] == ["shots"]
    listed = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"]
    assert len(listed) == 2 and listed[1]["notes"] == "macro"

    items = [
        {"title": "1.1", "input": VIDEO, "shot_id": first},
        {"title": "1.2", "input": VIDEO, "shot_id": second},
    ]
    claude.script = [([tool("propose_generation", {"model_id": T2V, "title": "Escena 1", "items": items}, 3)], "tool_use")]  # fmt: skip
    events = await send(http, chat["id"], "propón")
    proposal = next(e["proposal"] for e in events if e["type"] == "proposal")
    assert [link["shot_id"] for link in proposal["shots"]] == [first, second]
    listed = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"]
    assert {s["status"] for s in listed} == {"proposed"}

    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 5},
                           headers={"Idempotency-Key": "s1"})).json()  # fmt: skip
    await http.post(
        f"/v1/chats/{chat['id']}/proposals/{proposal['tool_use_id']}/job", json={"job_id": job["id"]}
    )
    listed = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"]
    assert listed[0]["status"] == "generating" and listed[0]["take_job_ids"] == [job["id"]]
    assert listed[1]["status"] == "proposed"

    async with app.state.sessions() as s:
        await s.execute(update(Job).where(Job.id == job["id"]).values(status="completed", outputs=[{"kind": "video", "url": "https://cdn.test/t.mp4"}]))  # fmt: skip
        await s.commit()
    listed = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"]
    assert listed[0]["status"] == "review" and listed[0]["takes"][0]["url"] == "https://cdn.test/t.mp4"

    bad = await http.patch(f"/v1/shots/{first}", json={"selected_job_id": "nope"})
    assert bad.json()["error"]["code"] == "not_a_take"
    picked = (
        await http.patch(f"/v1/shots/{first}", json={"selected_job_id": job["id"], "status": "approved"})
    ).json()
    assert picked["selected"]["job_id"] == job["id"] and picked["status"] == "approved"

    claude.script = [([tool("get_shot_list", {"status": "approved"}, 4)], "tool_use")]
    await send(http, chat["id"], "¿qué hay aprobado?")
    got = result_of(claude, -1)["shots"]
    assert [s["shot_id"] for s in got] == [first] and got[0]["takes"][0]["job_id"] == job["id"]
    head = claude.requests[-2]["messages"][-1]["content"][0]["text"]
    assert "<studio_shot_list>2 shots" in head

    assert (await http.delete(f"/v1/shots/{second}")).status_code == 204
    assert len((await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"]) == 1


async def test_auto_generation_links_the_takes_to_their_shot(env):  # noqa: F811
    _, http, claude = env
    project, chat = await project_chat(http)
    claude.script = [([tool("upsert_shots", {"shots": [{"scene": "1", "number": "1.1"}]})], "tool_use")]
    await send(http, chat["id"], "toma")
    shot_id = result_of(claude)["shots"][0]["shot_id"]
    claude.script = [([tool("propose_generation", {**PROPOSAL, "shot_id": shot_id}, 2)], "tool_use")]
    events = await send(http, chat["id"], "propón")
    pid = next(e["proposal"]["tool_use_id"] for e in events if e["type"] == "proposal")
    await http.patch(f"/v1/chats/{chat['id']}", json={"auto_budget_usd": 2})
    done = (await http.post(f"/v1/chats/{chat['id']}/proposals/{pid}/auto")).json()
    shot = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"][0]
    assert shot["status"] == "generating" and shot["take_job_ids"] == done["proposal"]["job_ids"]

    claude.script = [([tool("propose_generation", {**PROPOSAL, "shot_id": "nope"}, 3)], "tool_use")]
    await send(http, chat["id"], "otra")
    assert "Unknown shot" in result_of(claude, -1)["error"]


async def test_documents_and_brief_sections(env):  # noqa: F811
    _, http, claude = env
    project, chat = await project_chat(http)
    claude.script = [
        ([tool("save_document", {"kind": "treatment", "title": "Tratamiento", "markdown": "# Logline\nUn barco."}),
          tool("update_project_brief", {"section": "Visuales", "markdown": "Paleta: gasoline-sunset"})], "tool_use"),
    ]  # fmt: skip
    await send(http, chat["id"], "/tratamiento un barco")
    saved = result_of(claude)
    assert saved["version"] == 1
    brief = (await http.get(f"/v1/projects/{project['id']}")).json()["brief"]
    assert "## Visuales\nPaleta: gasoline-sunset\n" in brief and "Referencias, ambiente" not in brief
    assert "## Producción" in brief

    docs = (await http.get(f"/v1/projects/{project['id']}/documents")).json()["documents"]
    assert (
        docs[0]["title"] == "Tratamiento"
        and docs[0]["updated_by"] == "agent"
        and docs[0]["excerpt"] == "Logline"
    )
    doc_id = docs[0]["id"]
    # El usuario lo edita; el agente con la versión vieja no lo pisa.
    edited = await http.patch(
        f"/v1/documents/{doc_id}", json={"markdown": "# Logline\nUn barco rojo.", "base_version": 1}
    )
    assert edited.json()["version"] == 2
    stale = await http.patch(f"/v1/documents/{doc_id}", json={"markdown": "x", "base_version": 1})
    assert stale.status_code == 409
    claude.script = [
        ([tool("save_document", {"kind": "treatment", "title": "T", "markdown": "y", "document_id": doc_id, "base_version": 1}, 2)], "tool_use"),
    ]  # fmt: skip
    await send(http, chat["id"], "cámbialo")
    assert "version 2" in result_of(claude, -1)["error"]
    head = claude.requests[-2]["messages"][-1]["content"][0]["text"]
    assert f'{doc_id} · treatment · "Tratamiento" (v2)' in head  # índice, no el contenido
    assert "Un barco rojo" not in head

    claude.script = [([tool("read_document", {"document_id": doc_id}, 3)], "tool_use")]
    await send(http, chat["id"], "léelo")
    assert result_of(claude, -1)["markdown"] == "# Logline\nUn barco rojo."
    assert (await http.delete(f"/v1/documents/{doc_id}")).status_code == 204
    assert (await http.get(f"/v1/projects/{project['id']}/documents")).json()["documents"] == []


def test_replace_section_keeps_the_other_sections():
    brief = "# P\n\n## Contexto\nA\n\n## Visuales\nB\n\n## Estado\nC\n"
    out = replace_section(brief, "Visuales", "Nuevo")
    assert "## Visuales\nNuevo\n\n## Estado\nC" in out and "## Contexto\nA" in out
    assert "B\n\nMás" in replace_section(brief, "Visuales", "Más", "append")
    assert replace_section("# P\n", "Estado", "Listo").endswith("## Estado\nListo\n")


def test_frames_are_evenly_spaced_and_capped():
    assert frame_times(10, 4) == [0.0, 3.32, 6.63, 9.95]
    assert len(frame_times(10, 50)) == 8 and frame_times(None, 4) == [0.0]


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
async def test_the_agent_reviews_a_video_with_its_frames(env, tmp_path):  # noqa: F811
    app, http, claude = env
    video = await finished_job(app, "video", make_media(tmp_path, "video"))
    image = await finished_job(app, "image", make_media(tmp_path, "image"))
    claude.script = [([tool("review_generation", {"job_id": video, "frames": 3, "compare_with": [image]})], "tool_use")]  # fmt: skip
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "¿qué tal quedó?")
    assert [e["label"] for e in events if e["type"] == "tool"] == ["reviewing"]
    content = claude.requests[1]["messages"][-1]["content"][0]["content"]
    info = json.loads(content[0]["text"])
    assert info["input"] == {"prompt": "fox"} and info["images"] == 4
    assert info["outputs"][0]["frames_at_s"][0] == 0.0 and len(info["outputs"][0]["frames_at_s"]) == 3
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 4 and all(b["source"]["media_type"] == "image/jpeg" for b in images)
    # El chat guardado sigue mostrándose bien (los bloques de imagen no salen en la UI).
    assert events[-1]["chat"]["messages"][-1]["role"] == "assistant"

    claude.script = [([tool("review_generation", {"job_id": "nope"}, 2)], "tool_use")]
    await send(http, chat["id"], "otra")
    assert "not found" in result_of(claude, -1)["error"]


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
async def test_chain_shot_gives_the_last_frame_to_the_next_shot(env, tmp_path):  # noqa: F811
    app, http, claude = env
    project, chat = await project_chat(http)
    video = await finished_job(app, "video", make_media(tmp_path, "video"), project["id"])
    claude.script = [([tool("upsert_shots", {"shots": [{"scene": "1", "number": "1.2"}]})], "tool_use")]
    await send(http, chat["id"], "toma")
    shot_id = result_of(claude)["shots"][0]["shot_id"]
    claude.script = [([tool("chain_shot", {"from_job_id": video, "to_shot_id": shot_id}, 2)], "tool_use")]
    await send(http, chat["id"], "encadena")
    content = claude.requests[-1]["messages"][-1]["content"][0]["content"]
    chained = json.loads(content[0]["text"])
    assert chained["image_url"].startswith("https://cdn.test/up-") and chained["which"] == "last"
    assert content[1]["type"] == "image"
    shot = (await http.get(f"/v1/projects/{project['id']}/shots")).json()["shots"][0]
    assert shot["start_frame_url"] == chained["image_url"]


async def test_estimate_shot_list_prices_the_plan(env):  # noqa: F811
    _, http, claude = env
    _, chat = await project_chat(http)
    params = {k: v for k, v in VIDEO.items() if k != "prompt"}
    shots = [{"number": "1.1", "model_id": T2V, "params": params, "prompt": "A boat"}, {"number": "1.2"}]
    claude.script = [
        ([tool("upsert_shots", {"shots": shots})], "tool_use"),
        ([tool("estimate_shot_list", {"takes_per_shot": 2})], "tool_use"),
    ]
    await send(http, chat["id"], "presupuesto")
    priced = result_of(claude, 2)
    single = (await http.post("/v1/estimate", json={"model": T2V, "input": VIDEO})).json()["usd"]
    assert priced["total_usd"] == single and priced["total_with_retakes_usd"] == round(single * 2, 4)
    assert priced["unpriced_shots"] == 1 and priced["project_spent_usd"] == 0


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
async def test_an_element_from_a_generation_needs_the_users_click(env, tmp_path):  # noqa: F811
    app, http, claude = env
    still = await finished_job(app, "image", make_media(tmp_path, "image"))
    video = await finished_job(app, "video", make_media(tmp_path, "video"))
    args = {"name": "ana", "category": "character", "description": "Mujer de abrigo rojo",
            "sources": [{"job_id": still}, {"job_id": video, "frame": "first"}]}  # fmt: skip
    claude.script = [([tool("create_element_from_generation", args)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "guárdala como elemento")
    card = next(e["proposal"] for e in events if e["type"] == "proposal")
    assert card["kind"] == "element" and card["element_id"] is None
    async with app.state.sessions() as s:
        assert await s.scalar(select(Element)) is None  # aún nada: falta el clic
    shown = events[-1]["chat"]["messages"][1]["parts"]
    assert shown[0]["type"] == "proposal" and shown[0]["proposal"]["kind"] == "element"

    url = f"/v1/chats/{chat['id']}/proposals/{card['tool_use_id']}/element"
    made = await http.post(url)
    assert made.status_code == 201, made.text
    assert made.json()["name"] == "ana" and len(made.json()["images"]) == 2
    assert (await http.post(url)).json()["error"]["code"] == "element_created"
    claude.script = [([tool("create_element_from_generation", args, 2)], "tool_use")]
    await send(http, chat["id"], "otra vez")
    assert "already an element" in result_of(claude, -1)["error"]
