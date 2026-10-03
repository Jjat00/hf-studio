"""Ruteo al proveedor más barato y respaldo entre proveedores, con Higgsfield, APIMart y KIE falsos.

Precios: copias reales de las tablas (tests/fixtures, 2026-10-03). Seedance 2.0 a 720p y 5 s cuesta 0,71 USD
en APIMart, 1,025 en KIE y 1,51 en Higgsfield (aquí Higgsfield cotiza lo que diga el falso)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import update

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, hash_token, utcnow

FIXTURES = Path(__file__).parent / "fixtures"
T2V = "bytedance/seedance-2.0/text-to-video"
VIDEO = {"prompt": "A paper boat sailing down a rainy street", "resolution": "720p", "duration": 5,
         "aspect_ratio": "9:16"}  # fmt: skip


class Fakes:
    """Un solo transporte para los tres proveedores; cada uno con su modo de respuesta."""

    def __init__(self):
        self.sent: dict[str, list] = {"higgsfield": [], "apimart": [], "kie": []}
        self.apimart_submit = "ok"  # ok | credits | timeout
        self.apimart_task = "processing"  # processing | completed | failed
        self.kie_task = "generating"
        self.kie_credits = 1000.0
        self.hf_usd = "1.510"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "cdn.test":
            return httpx.Response(200, content=b"MP4", headers={"content-type": "video/mp4"})
        if host == "api.higgsfield.test":
            if path.startswith("/estimate/"):
                return httpx.Response(200, json={"type": "estimate", "credits": "24", "usd": self.hf_usd})
            if path.startswith("/requests/") and path.endswith("/status"):
                return httpx.Response(404, json={"detail": "not found"})
            self.sent["higgsfield"].append(json.loads(request.content))
            return httpx.Response(200, json={"status": "queued", "request_id": "hf-1"})
        if host == "api.apimart.ai":
            if path == "/v1/user/balance":
                return httpx.Response(200, json={"success": True, "remain_balance": 50.0})
            if request.method == "POST":
                self.sent["apimart"].append(json.loads(request.content))
                if self.apimart_submit == "credits":
                    return httpx.Response(
                        402, json={"error": {"message": "insufficient balance (current: 0.01 USD)"}}
                    )
                if self.apimart_submit == "timeout":
                    raise httpx.ReadTimeout("no answer", request=request)
                return httpx.Response(
                    200, json={"code": 200, "data": [{"status": "submitted", "task_id": "am-1"}]}
                )
            data = {"status": self.apimart_task}
            if self.apimart_task == "completed":
                data["result"] = {"videos": [{"url": ["https://cdn.test/am.mp4"]}]}
            if self.apimart_task == "failed":
                data["error"] = {"message": "upstream error"}
            return httpx.Response(200, json={"code": 200, "data": data})
        if host == "api.kie.ai":
            if path == "/api/v1/chat/credit":
                return httpx.Response(200, json={"code": 200, "data": self.kie_credits})
            if request.method == "POST":
                self.sent["kie"].append(json.loads(request.content))
                return httpx.Response(200, json={"code": 200, "data": {"taskId": "kie-1"}})
            data = {"state": self.kie_task}
            if self.kie_task == "success":
                data["resultJson"] = json.dumps({"resultUrls": ["https://cdn.test/kie.mp4"]})
            return httpx.Response(200, json={"code": 200, "data": data})
        return httpx.Response(404)


@pytest.fixture
async def env(tmp_path):
    fakes = Fakes()
    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        provider_keys={"APIMART_API_KEY": "am", "KIE_API_KEY": "kie"},
        database_url=f"sqlite+aiosqlite:///{tmp_path}/r.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(fakes))
    async with app.router.lifespan_context(app):
        for name in ("apimart", "kie"):
            app.state.prices.store(name, json.loads((FIXTURES / f"prices_{name}.json").read_text()))
        async with app.state.sessions() as s:
            s.add(ApiClient(name="agente", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, fakes


async def tick(app, polls: int = 1):
    for _ in range(polls):
        async with app.state.sessions() as s:
            await s.execute(update(Job).values(next_check_at=utcnow() - timedelta(seconds=1)))
            await s.commit()
        await app.state.worker.tick()


async def test_estimate_lists_every_provider_cheapest_first(env):
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={"model": T2V, "input": VIDEO})).json()
    assert [o["provider"] for o in body["options"]] == ["apimart", "kie", "higgsfield"]
    assert body["provider"] == "apimart" and body["usd"] == 0.71 and body["kind"] == "exact"
    assert body["basis"].startswith("APIMart price list")
    assert body["savings_vs_higgsfield"] == {"usd": 0.8, "pct": 53}
    assert body["options"][1]["usd"] == 1.025


async def test_generation_goes_to_the_cheapest_with_translated_input(env):
    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.71})).json()
    assert job["provider"] == "apimart" and job["cost_usd"] == 0.71 and job["max_usd"] == 0.71
    await tick(app)
    sent = fakes.sent["apimart"][0]
    assert sent["model"] == "seedance-2.0" and sent["size"] == "9:16" and "aspect_ratio" not in sent
    assert sent["generate_audio"] is True  # valor por defecto de Higgsfield, enviado explícito
    fakes.apimart_task = "completed"
    await tick(app)
    done = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert done["status"] == "completed" and done["outputs"][0]["url"] == "https://cdn.test/am.mp4"
    assert done["outputs"][0]["file_url"]  # copia local descargada


async def test_price_went_up_since_the_quote(env):
    _, http, _ = env
    r = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.5})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_changed"


async def test_fallback_within_the_approved_price_runs_alone(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 1.2})).json()
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["provider"] == "kie" and state["status"] == "pending"
    assert state["attempts"][0]["provider"] == "apimart" and state["attempts"][0]["error_kind"] == "credits"
    await tick(app)
    assert fakes.sent["kie"][0]["model"] == "bytedance/seedance-2"
    fakes.kie_task = "success"
    await tick(app)
    done = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert done["status"] == "completed" and done["outputs"][0]["url"] == "https://cdn.test/kie.mp4"


async def test_a_more_expensive_fallback_waits_for_approval(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()
    assert job["max_usd"] == 0.71  # sin max_usd se aprueba el precio de la opción elegida
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "awaiting_approval" and "KIE can do it for 1.02 USD" in state["error"]
    assert fakes.sent["kie"] == []
    r = await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.0})
    assert r.status_code == 409  # cuesta 1,025: más de lo que se aprueba
    approved = (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.03})).json()
    assert approved["status"] == "pending" and approved["provider"] == "kie" and approved["max_usd"] == 1.025
    await tick(app)
    assert len(fakes.sent["kie"]) == 1


async def test_failed_task_falls_back_too(env):
    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 2})).json()
    await tick(app)
    fakes.apimart_task = "failed"
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["provider"] == "kie" and state["request_id"] is None
    assert state["attempts"][0]["request_id"] == "am-1" and state["attempts"][0]["error"] == "upstream error"


async def test_ambiguous_submission_never_falls_back(env):
    app, http, fakes = env
    fakes.apimart_submit = "timeout"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 5})).json()
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "failed" and state["error_kind"] == "submission_ambiguous"
    assert fakes.sent["kie"] == [] and fakes.sent["higgsfield"] == []


async def test_provider_without_enough_balance_is_skipped(env):
    _, http, fakes = env
    fakes.kie_credits = 10  # 0,05 USD
    body = (await http.post("/v1/estimate", json={"model": T2V, "input": VIDEO})).json()
    assert [o["provider"] for o in body["options"]] == ["apimart", "higgsfield"]
    assert (
        body["excluded"][0]["provider"] == "kie" and "insufficient balance" in body["excluded"][0]["reason"]
    )


async def test_forcing_a_provider(env):
    app, http, fakes = env
    job = (
        await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "higgsfield"})
    ).json()
    assert job["provider"] == "higgsfield" and job["plan"] == [{"provider": "higgsfield", "usd": 1.51}]
    await tick(app)
    assert fakes.sent["higgsfield"][0] == VIDEO  # Higgsfield recibe la entrada tal cual


async def test_models_only_higgsfield_has_stay_there(env):
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={"model": "higgsfiled/genjutsu/object-swap/v1.0", "input": {
        "video_url": "https://cdn.test/v.mp4", "image_urls": ["https://cdn.test/a.png"]}})).json()  # fmt: skip
    assert [o["provider"] for o in body["options"]] == ["higgsfield"]
