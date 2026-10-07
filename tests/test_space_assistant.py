"""Nodo Assistant (Claude): cotización con cota superior, llamada a la API simulada y su texto como prompt."""

from __future__ import annotations

import asyncio
import json

import httpx
import httpx2
import pytest

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, SpaceRun, hash_token

from .test_routing import FIXTURES, VIDEO, Fakes, tick

T2V = "bytedance/seedance-2.0/text-to-video"
SETTINGS = {k: v for k, v in VIDEO.items() if k != "prompt"}


class FakeClaude:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.refuse = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        body = json.loads(request.content)
        if self.refuse:
            content, stop = [], "refusal"
        else:
            content, stop = (
                [{"type": "text", "text": "A paper boat drifts down a rainy street at dusk"}],
                "end_turn",
            )
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "content": content,
            "stop_reason": stop, "stop_sequence": None, "stop_details": None,
            "usage": {"input_tokens": 12, "output_tokens": 40},
        })  # fmt: skip


async def _env(tmp_path, key: str):
    claude, fakes = FakeClaude(), Fakes()

    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        provider_keys={"APIMART_API_KEY": "am", "KIE_API_KEY": "kie", "ANTHROPIC_API_KEY": key,
                       "ANTHROPIC_BASE_URL": "https://api.anthropic.test"},
        database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    return create_app(settings, transport=httpx.MockTransport(fakes)), claude


@pytest.fixture
async def claude_env(tmp_path):
    app, claude = await _env(tmp_path, "sk-test")
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


async def finish(app, job_id):
    await tick(app)
    for _ in range(100):
        await asyncio.sleep(0.05)
        await tick(app)
        async with app.state.sessions() as s:
            job = await s.get(Job, job_id)
            if job.status in ("completed", "failed"):
                return job
    raise AssertionError("did not finish")


async def test_the_assistant_is_quoted_with_its_upper_bound_and_writes_text(claude_env):
    app, http, claude = claude_env
    body = {"model": "claude/assistant", "input": {"prompt": "Write a cinematic prompt about a paper boat"}}
    est = (await http.post("/v1/estimate", json=body)).json()
    assert est["provider"] == "anthropic" and est["kind"] == "approx"
    prompt_bytes = len(body["input"]["prompt"].encode())
    assert est["usd"] == pytest.approx(
        ((prompt_bytes + 200) * 4 + 6000 * 20) / 1_000_000, rel=0.01
    )  # bytes + estructura (cota de tokens) + tope de salida, Opus 5.5
    job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
    done = await finish(app, job["id"])
    assert done.status == "completed", done.error
    assert done.files[0]["kind"] == "text"
    text = (app.state.settings.storage_dir / "outputs" / done.id / done.files[0]["name"]).read_text()
    assert text.startswith("A paper boat")
    sent = json.loads(claude.requests[-1].content)
    assert sent["model"] == "claude-opus-5-5" and "fallbacks" not in sent  # sin respaldo a otro modelo
    assert sent["output_config"] == {"effort": "medium"} and sent["max_tokens"] == 6000


async def test_haiku_sends_no_effort_and_a_refusal_fails_visibly(claude_env):
    app, http, claude = claude_env
    body = {"model": "claude/assistant", "input": {"prompt": "hi", "model_id": "claude-haiku-4-5"}}
    est = (await http.post("/v1/estimate", json=body)).json()
    await finish(app, (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()["id"])
    sent = json.loads(claude.requests[-1].content)
    assert "output_config" not in sent and "fallbacks" not in sent
    claude.refuse = True
    body = {"model": "claude/assistant", "input": {"prompt": "something else"}}
    est = (await http.post("/v1/estimate", json=body)).json()
    failed = await finish(
        app, (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()["id"]
    )
    assert failed.status == "failed" and "declined" in failed.error


async def test_the_assistant_text_becomes_the_next_prompt_in_a_run(claude_env):
    app, http, _ = claude_env
    graph = {
        "nodes": [
            {"id": "a", "type": "generator", "position": {"x": 0, "y": 0},
             "data": {"model": "claude/assistant", "values": {"prompt": "Write a video prompt"}, "runs": []}},
            {"id": "v", "type": "generator", "position": {"x": 400, "y": 0}, "data": {"model": T2V, "values": SETTINGS, "runs": []}},
        ],
        "edges": [{"id": "e", "source": "a", "target": "v", "sourceHandle": "out", "targetHandle": "prompt"}],
    }  # fmt: skip
    space = (await http.post("/v1/spaces", json={"graph": graph})).json()
    run = (
        await http.post(
            f"/v1/spaces/{space['id']}/runs",
            json={"mode": "workflow", "version": space["version"], "max_total_usd": 5},
        )
    ).json()
    runner = app.state.space_runner
    await runner.tick(run["id"])
    async with app.state.sessions() as s:
        a_job = (await s.get(SpaceRun, run["id"])).nodes["a"]["job_id"]
    await finish(app, a_job)
    await runner.tick(run["id"])
    async with app.state.sessions() as s:
        state = await s.get(SpaceRun, run["id"])
        video = await s.get(Job, state.nodes["v"]["job_id"])
    assert video.input["prompt"] == "A paper boat drifts down a rainy street at dusk"


async def test_the_assistant_needs_a_key(tmp_path):
    app, _ = await _env(tmp_path, "")
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            res = await http.post(
                "/v1/estimate", json={"model": "claude/assistant", "input": {"prompt": "x"}}
            )
    assert res.status_code == 503 and res.json()["error"]["code"] == "anthropic_not_configured"


async def test_a_lost_response_is_not_resent(claude_env):
    """Revisión 69 (H2): sin reintentos del SDK, una respuesta perdida no reenvía la petición pagada."""
    app, http, claude = claude_env
    real = claude.__call__

    def lose_first(request):
        if not claude.requests:
            claude.requests.append(request)
            raise httpx2.ReadError("response lost", request=request)
        return real(request)

    app.state.assistant_jobs.http_client_factory = lambda: httpx2.AsyncClient(
        transport=httpx2.MockTransport(lose_first)
    )
    body = {"model": "claude/assistant", "input": {"prompt": "hi"}}
    est = (await http.post("/v1/estimate", json=body)).json()
    done = await finish(
        app, (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()["id"]
    )
    assert done.status == "failed" and len(claude.requests) == 1


def test_the_quote_bounds_any_valid_input():
    """Revisión 69 (H3): la cota cubre el peor caso admitido (texto multibyte e imágenes)."""
    from hf_studio.space_assistant import IMAGE_TOKENS, MAX_TOKENS, assistant_quote

    prompt = "語" * 20000  # 3 bytes por carácter: más tokens que caracteres
    q = assistant_quote({"prompt": prompt, "image_urls": ["https://x.test/a.png"] * 4})
    assert q["usd"] >= ((60000 + 4 * IMAGE_TOKENS) * 4 + MAX_TOKENS * 20) / 1_000_000
    assert assistant_quote({"prompt": "hi"})["usd"] > MAX_TOKENS * 20 / 1_000_000
