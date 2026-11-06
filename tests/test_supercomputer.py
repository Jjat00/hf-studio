"""Supercomputer: chat con un agente (Claude simulado en streaming) que busca modelos, lee su esquema y deja
propuestas cotizadas sin generar nada; el usuario genera desde la propuesta y el agente se entera del resultado."""

from __future__ import annotations

import itertools
import json

import httpx
import httpx2
import pytest
from sqlalchemy import func, select

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Element, Job, Upload, hash_token
from hf_studio.supercomputer import visible_messages

from .test_routing import FIXTURES, T2V, VIDEO, Fakes

PROPOSAL = {"model_id": T2V, "title": "Barco de papel", "input": VIDEO}


def sse_message(content: list[dict], stop: str) -> str:
    """Una respuesta de la API de mensajes en eventos de streaming."""
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1}}}),
    ]  # fmt: skip
    for i, block in enumerate(content):
        if block["type"] == "text":
            events += [
                ("content_block_start", {"type": "content_block_start", "index": i,
                                         "content_block": {"type": "text", "text": ""}}),
                ("content_block_delta", {"type": "content_block_delta", "index": i,
                                         "delta": {"type": "text_delta", "text": block["text"]}}),
            ]  # fmt: skip
        else:
            events += [
                ("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                    "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}),
                ("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {
                    "type": "input_json_delta", "partial_json": json.dumps(block["input"])}}),
            ]  # fmt: skip
        events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    events += [
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                           "usage": {"output_tokens": 500}}),
        ("message_stop", {"type": "message_stop"}),
    ]  # fmt: skip
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def tool(name: str, args: dict, n: int = 1) -> dict:
    return {"type": "tool_use", "id": f"toolu_{name}_{n}", "name": name, "input": args}


class FakeClaude:
    """Responde en orden a lo que el test guiona; guarda cada petición."""

    def __init__(self):
        self.requests: list[dict] = []
        self.script: list[tuple[list[dict], str]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        content, stop = self.script.pop(0) if self.script else ([{"type": "text", "text": "Ok"}], "end_turn")
        return httpx2.Response(
            200, text=sse_message(content, stop), headers={"content-type": "text/event-stream"}
        )


@pytest.fixture
async def env(tmp_path):
    claude, fakes = FakeClaude(), Fakes()
    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        provider_keys={"APIMART_API_KEY": "am", "KIE_API_KEY": "kie", "ANTHROPIC_API_KEY": "sk-test",
                       "ANTHROPIC_BASE_URL": "https://api.anthropic.test"},
        database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(fakes))
    async with app.router.lifespan_context(app):
        app.state.assistant_jobs.http_client_factory = lambda: httpx2.AsyncClient(
            transport=httpx2.MockTransport(claude)
        )
        for name in ("apimart", "kie"):
            app.state.prices.store(name, json.loads((FIXTURES / f"prices_{name}.json").read_text()))
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, claude


async def send(http, chat_id: str, text: str, **extra) -> list[dict]:
    res = await http.post(f"/v1/chats/{chat_id}/messages", json={"text": text, **extra})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


async def test_the_agent_searches_reads_and_proposes_without_generating(env):
    app, http, claude = env
    claude.script = [
        ([{"type": "text", "text": "Busco modelos. "}, tool("find_models", {"task": "cinematic video", "output": "video"})], "tool_use"),
        ([tool("get_model", {"model_id": T2V})], "tool_use"),
        ([tool("propose_generation", PROPOSAL)], "tool_use"),
        ([{"type": "text", "text": "Ahí tienes la propuesta."}], "end_turn"),
    ]  # fmt: skip
    listed = (await http.get("/v1/chats")).json()
    assert listed["available"] and listed["default_model"] == "claude-opus-5-5"
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "un video de un barco de papel", mode="auto")

    kinds = [e["type"] for e in events]
    assert kinds[0] == "text" and "proposal" in kinds and kinds[-1] == "done"
    assert [e["name"] for e in events if e["type"] == "tool"] == [
        "find_models",
        "get_model",
        "propose_generation",
    ]
    proposal = next(e["proposal"] for e in events if e["type"] == "proposal")
    assert proposal["model"] == T2V and proposal["input"] == VIDEO and proposal["estimate"]["usd"] > 0

    # Lo que vio Claude: catálogo con precios, el esquema y la cotización; modo, pensamiento y caché.
    first = claude.requests[0]
    assert first["model"] == "claude-opus-5-5" and first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "medium"} and first["cache_control"] == {"type": "ephemeral"}
    assert "<studio_mode>auto</studio_mode>" in first["messages"][0]["content"][0]["text"]
    found = json.loads(claude.requests[1]["messages"][-1]["content"][0]["content"])
    assert found["models"] and all("usd" in m for m in found["models"])
    schema = json.loads(claude.requests[2]["messages"][-1]["content"][0]["content"])
    assert schema["id"] == T2V and "input_schema" in schema
    quoted = json.loads(claude.requests[3]["messages"][-1]["content"][0]["content"])
    assert quoted["ok"] and quoted["price"]["usd"] == proposal["estimate"]["usd"]

    done = events[-1]["chat"]
    assert done["title"] == "un video de un barco de papel" and done["cost_usd"] > 0
    assert done["messages"][0] == {"role": "user", "text": "un video de un barco de papel", "attachments": []}
    parts = done["messages"][1]["parts"]  # las cuatro rondas, un solo mensaje del agente
    assert [p["type"] for p in parts] == ["text", "proposal", "text"]
    async with app.state.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(Job)) == 0  # nada generado

    again = (await http.get(f"/v1/chats/{chat['id']}")).json()
    assert again["messages"] == done["messages"]


async def test_the_agent_lists_saved_elements_to_cite_them(env):
    app, http, claude = env
    async with app.state.sessions() as s:
        ui = await s.scalar(select(ApiClient))
        s.add(Element(id="el_000000000001", created_by=ui.id, name="zorro", description="Zorro rojo de peluche", images=[{"file": "a.png"}, {"file": "b.png"}]))  # fmt: skip
        await s.commit()
    claude.script = [([tool("list_elements", {})], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "usa mi zorro")
    assert [e["name"] for e in events if e["type"] == "tool"] == ["list_elements"]
    listed = json.loads(claude.requests[1]["messages"][-1]["content"][0]["content"])
    assert listed["elements"][0] == {
        "id": "el_000000000001", "name": "zorro", "mention": "@zorro", "description": "Zorro rojo de peluche", "images": 2,
    }  # fmt: skip
    assert "list_elements" in {t["name"] for t in claude.requests[0]["tools"]}
    assert "# References" in str(claude.requests[0]["system"])


async def test_questions_come_one_at_a_time_with_clickable_options(env):
    _, http, claude = env
    ask = {
        "question": "¿Qué formato?",
        "options": [{"label": "Historia 9:16", "detail": "Recomendado"}, {"label": "Feed 4:5"}],
    }
    claude.script = [([{"type": "text", "text": "Buena foto. "}, tool("ask_user", ask)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "mejora la imagen")
    assert len(claude.requests) == 1  # la vuelta termina en la pregunta, sin otra llamada a Claude
    question = next(e["question"] for e in events if e["type"] == "question")
    assert question["question"] == "¿Qué formato?" and [o["label"] for o in question["options"]] == [
        "Historia 9:16",
        "Feed 4:5",
    ]
    parts = events[-1]["chat"]["messages"][1]["parts"]
    assert [p["type"] for p in parts] == ["text", "question"]

    events = await send(http, chat["id"], "Historia 9:16")
    last = claude.requests[1]["messages"][-1]
    assert (
        last["role"] == "user" and last["content"][0]["type"] == "tool_result"
    )  # respuesta y resultado juntos
    assert last["content"][-1] == {"type": "text", "text": "Historia 9:16"}
    roles = [m["role"] for m in claude.requests[1]["messages"]]
    assert all(a != b for a, b in itertools.pairwise(roles))  # nunca dos mensajes seguidos del mismo rol
    shown = events[-1]["chat"]["messages"]
    assert [m["role"] for m in shown] == ["user", "assistant", "user", "assistant"]
    assert shown[2] == {"role": "user", "text": "Historia 9:16", "attachments": []}


async def test_a_bad_question_goes_back_to_claude(env):
    _, http, claude = env
    claude.script = [
        ([tool("ask_user", {"question": "¿Formato?", "options": [{"label": "Solo una"}]})], "tool_use")
    ]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "hola")
    assert not [e for e in events if e["type"] == "question"] and len(claude.requests) == 2
    assert claude.requests[1]["messages"][-1]["content"][0]["is_error"]


async def test_an_invalid_proposal_goes_back_to_claude_as_an_error(env):
    _, http, claude = env
    bad = {**PROPOSAL, "input": {**VIDEO, "duration": 999}}
    claude.script = [([tool("propose_generation", bad)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "hazlo")
    assert not [e for e in events if e["type"] == "proposal"]
    result = claude.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and json.loads(result["content"])["errors"]


async def test_the_agent_hears_how_a_generation_from_its_proposal_ended(env):
    app, http, claude = env
    claude.script = [([tool("propose_generation", PROPOSAL)], "tool_use")]
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "propón")
    pid = next(e["proposal"]["tool_use_id"] for e in events if e["type"] == "proposal")
    async with app.state.sessions() as s:
        owner = (await s.execute(select(ApiClient))).scalar_one()
        job = Job(owner_id=owner.id, model=T2V, input=VIDEO, input_hash="h", status="completed",
                  outputs=[{"kind": "video", "url": "https://cdn.test/boat.mp4"}])  # fmt: skip
        s.add(job)
        await s.commit()
        job_id = job.id
    assert (
        await http.post(f"/v1/chats/{chat['id']}/proposals/nope/job", json={"job_id": job_id})
    ).status_code == 404
    linked = await http.post(f"/v1/chats/{chat['id']}/proposals/{pid}/job", json={"job_id": job_id})
    assert linked.json()["job_id"] == job_id

    await send(http, chat["id"], "¿qué tal quedó?")
    head = claude.requests[-1]["messages"][-1]["content"][0]["text"]
    assert "<studio_update>" in head and "completed" in head and "https://cdn.test/boat.mp4" in head
    await send(http, chat["id"], "otra cosa")  # ya contado: no se repite
    assert "<studio_update>" not in claude.requests[-1]["messages"][-1]["content"][0]["text"]
    shown = (await http.get(f"/v1/chats/{chat['id']}")).json()["messages"][1]["parts"][0]
    assert shown["proposal"]["job_id"] == job_id


async def test_attachments_must_be_your_own_files_and_images_are_shown_to_claude(env):
    app, http, claude = env
    chat = (await http.post("/v1/chats", json={})).json()
    url = "https://cdn.test/ref.png"
    att = {"url": url, "content_type": "image/png", "filename": "ref.png"}
    res = await http.post(f"/v1/chats/{chat['id']}/messages", json={"text": "usa esto", "attachments": [att]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "untrusted_source"
    async with app.state.sessions() as s:
        owner = (await s.execute(select(ApiClient))).scalar_one()
        s.add(Upload(owner_id=owner.id, filename="ref.png", content_type="image/png", size=10, url=url))
        await s.commit()
    events = await send(http, chat["id"], "usa esto", attachments=[att])
    content = claude.requests[-1]["messages"][0]["content"]
    assert {"type": "image", "source": {"type": "url", "url": url}} in content
    assert events[-1]["chat"]["messages"][0]["attachments"] == [url]


async def test_a_claude_error_is_reported_and_the_user_message_is_kept(env):
    app, http, _ = env
    app.state.assistant_jobs.http_client_factory = lambda: httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda r: httpx2.Response(
                400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
            )
        )
    )
    chat = (await http.post("/v1/chats", json={})).json()
    events = await send(http, chat["id"], "hola")
    assert events[-2]["type"] == "error" and "400" in events[-2]["message"]
    assert events[-1]["chat"]["messages"] == [{"role": "user", "text": "hola", "attachments": []}]
    assert not app.state.chats_busy


async def test_without_a_key_the_chat_says_how_to_enable_it(tmp_path):
    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(Fakes()))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            assert (await http.get("/v1/chats")).json()["available"] is False
            chat = (await http.post("/v1/chats", json={})).json()
            res = await http.post(f"/v1/chats/{chat['id']}/messages", json={"text": "hola"})
            assert res.status_code == 503 and res.json()["error"]["code"] == "anthropic_not_configured"


def test_the_visible_chat_hides_thinking_and_tool_traffic():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "<studio_mode>ask</studio_mode>"},
                                     {"type": "text", "text": "hola"}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                          {"type": "text", "text": "Busco"},
                                          {"type": "tool_use", "id": "t1", "name": "find_models", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Listo"}]},
    ]  # fmt: skip
    assert visible_messages(messages, {}) == [
        {"role": "user", "text": "hola", "attachments": []},
        {
            "role": "assistant",
            "parts": [{"type": "text", "text": "Busco"}, {"type": "text", "text": "Listo"}],
        },
    ]
