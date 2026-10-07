"""Ruteo al proveedor más barato y respaldo entre proveedores, con Higgsfield, APIMart y KIE falsos.

Precios: copias reales de las tablas (tests/fixtures, 2026-10-03). Seedance 2.0 a 720p y 5 s cuesta 0,71 USD
en APIMart, 1,025 en KIE y 1,51 en Higgsfield (aquí Higgsfield cotiza lo que diga el falso)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update

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
        self.apimart_submit = "ok"  # ok | credits | timeout | no_id | bad_gateway
        self.apimart_task = "processing"  # processing | completed | failed
        self.kie_task = "generating"
        self.kie_credits = 1000.0
        self.apimart_balance = 50.0
        self.hf_usd = "1.510"
        self.upload_down = False  # Higgsfield responde 503 a las subidas
        self.uploads: list[bytes] = []  # bytes subidos a Higgsfield (cada uno con su URL cdn.test/up-N)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "cdn.test":
            if path.startswith("/up-"):
                return httpx.Response(200, content=self.uploads[int(path[4:].split(".")[0])])
            return httpx.Response(200, content=b"MP4", headers={"content-type": "video/mp4"})
        if host == "storage.test":
            self.uploads.append(request.content)
            return httpx.Response(200)
        if host == "api.higgsfield.test":
            if path.startswith("/estimate/"):
                return httpx.Response(200, json={"type": "estimate", "credits": "24", "usd": self.hf_usd})
            if path.startswith("/requests/") and path.endswith("/status"):
                return httpx.Response(404, json={"detail": "not found"})
            if path == "/files/generate-upload-url":
                if self.upload_down:
                    return httpx.Response(503, json={"detail": "Service Unavailable"})
                n = len(self.uploads)
                return httpx.Response(200, json={"public_url": f"https://cdn.test/up-{n}.png",
                                                 "upload_url": f"https://storage.test/put-{n}"})  # fmt: skip
            self.sent["higgsfield"].append(json.loads(request.content))
            return httpx.Response(200, json={"status": "queued", "request_id": "hf-1"})
        if host == "api.apimart.ai":
            if path == "/v1/user/balance":
                return httpx.Response(200, json={"success": True, "remain_balance": self.apimart_balance})
            if request.method == "POST":
                self.sent["apimart"].append(json.loads(request.content))
                if self.apimart_submit == "credits":
                    return httpx.Response(
                        402, json={"error": {"message": "insufficient balance (current: 0.01 USD)"}}
                    )
                if self.apimart_submit == "timeout":
                    raise httpx.ReadTimeout("no answer", request=request)
                if self.apimart_submit == "no_id":
                    return httpx.Response(200, json={"code": 200, "data": []})
                if self.apimart_submit == "bad_gateway":
                    return httpx.Response(502, text="Bad gateway")
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
    assert state["status"] == "awaiting_approval" and "KIE can do it for 1.0250 USD" in state["error"]
    assert state["provider"] == "kie" and state["cost_usd"] == 1.025
    assert fakes.sent["kie"] == []
    r = await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.0})
    assert r.status_code == 409  # cuesta 1,025: más de lo que se aprueba
    approved = (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.03})).json()
    assert approved["status"] == "pending" and approved["provider"] == "kie" and approved["max_usd"] == 1.03
    assert (
        await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.03})
    ).status_code == 409
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
    assert job["provider"] == "higgsfield"
    assert job["plan"] == [{"provider": "higgsfield", "model": T2V, "official": True, "usd": 1.51, "kind": "exact",
                            "reserve_usd": None}]  # fmt: skip
    await tick(app)
    assert fakes.sent["higgsfield"][0] == VIDEO  # Higgsfield recibe la entrada tal cual


async def test_models_only_higgsfield_has_stay_there(env):
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={"model": "higgsfiled/genjutsu/object-swap/v1.0", "input": {
        "video_url": "https://cdn.test/v.mp4", "image_urls": ["https://cdn.test/a.png"]}})).json()  # fmt: skip
    assert [o["provider"] for o in body["options"]] == ["higgsfield"]


# --- Revisión 28 de Codex -------------------------------------------------------------------------


async def test_a_late_result_cannot_send_the_fallback_twice(env):
    """Sondeo y webhook aplican el mismo fallo en dos sesiones: un solo envío al respaldo."""
    from hf_studio.providers.base import Polled

    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 2})).json()
    await tick(app)
    worker = app.state.worker
    async with app.state.sessions() as a, app.state.sessions() as b:
        ja, jb = await a.get(Job, job["id"]), await b.get(Job, job["id"])
        await worker.apply_polled(a, ja, Polled("failed", error="upstream error"))
        assert await worker.commit(a, job["id"])
        await worker.submit(job["id"])
        await worker.apply_polled(b, jb, Polled("failed", error="upstream error"))
        assert not await worker.commit(b, job["id"])  # resultado viejo: se descarta
    await worker.submit(job["id"])
    assert len(fakes.sent["kie"]) == 1
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["provider"] == "kie" and state["request_id"] == "kie-1"


async def test_a_late_result_cannot_undo_a_cancel(env):

    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()
    await tick(app)  # queda esperando aprobación de KIE
    async with app.state.sessions() as old:
        stale_job = await old.get(Job, job["id"])
        assert (await http.post(f"/v1/generations/{job['id']}/cancel")).json()["status"] == "canceled"
        stale_job.status = "pending"
        assert not await app.state.worker.commit(old, job["id"])
    assert (await http.get(f"/v1/generations/{job['id']}")).json()["status"] == "canceled"


@pytest.mark.parametrize("mode", ["no_id", "bad_gateway"])
async def test_an_accepted_but_unclear_submission_is_ambiguous(env, mode):
    app, http, fakes = env
    fakes.apimart_submit = mode
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 5})).json()
    await tick(app, polls=3)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "failed" and state["error_kind"] == "submission_ambiguous"
    assert len(fakes.sent["apimart"]) == 1 and fakes.sent["kie"] == []


async def test_unknown_price_under_a_ceiling_is_refused(env):
    app, http, _ = env
    app.state.prices.store("apimart", {})
    r = await http.post(
        "/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart", "max_usd": 0.71}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_unknown"
    r = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.7099})
    assert r.status_code == 409  # sin tolerancia: 0,71 > 0,7099


async def test_approval_requotes_the_fallback(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()
    await tick(app)
    prices = json.loads((FIXTURES / "prices_kie.json").read_text())
    prices["bytedance/seedance-2, 720p no video input"] = 0.5  # sube a 2,50 USD
    app.state.prices.store("kie", prices)
    r = await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.025})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_changed"
    ok = (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 2.5})).json()
    assert ok["status"] == "pending" and ok["cost_usd"] == 2.5


async def test_a_stale_quote_is_requoted_before_sending(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 1.1})).json()
    async with app.state.sessions() as s:
        row = await s.get(Job, job["id"])
        row.plan = [{**o, "quoted_at": 0} for o in row.plan]  # cotizado hace mucho
        await s.commit()
    prices = json.loads((FIXTURES / "prices_kie.json").read_text())
    prices["bytedance/seedance-2, 720p no video input"] = 0.5
    app.state.prices.store("kie", prices)
    await tick(app)  # APIMart sin saldo → KIE, que ahora cuesta 2,50: no se envía
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    # El plan se rehízo con las tarifas de ahora: tras APIMart, el respaldo más barato es Higgsfield (1,51),
    # no KIE (2,50); como supera lo aprobado (1,10), espera aprobación y KIE no recibe nada.
    assert state["status"] == "awaiting_approval" and fakes.sent["kie"] == []
    assert state["provider"] == "higgsfield" and state["cost_usd"] == 1.51


async def test_a_batch_keeps_the_approved_total(env):
    app, http, _ = env
    items = [{"model": T2V, "input": VIDEO, "count": 1}]
    quoted = (await http.post("/v1/generations/batch", json={"items": items, "dry_run": True})).json()
    assert quoted["total"]["usd"] == 0.71
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.0|720P"] = 0.3  # APIMart sube: el más barato pasa a KIE (1,025)
    app.state.prices.store("apimart", prices)
    r = await http.post("/v1/generations/batch", json={"items": items, "max_total_usd": 0.71})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_changed"
    async with app.state.sessions() as s:
        assert (await s.scalars(select(Job))).all() == []  # ningún trabajo creado


async def test_seedance_edit_shows_the_initial_hold_and_checks_balance_against_it(env):
    """Revisión 28: APIMart retiene 30 s de salida con duration -1; el saldo debe cubrir esa reserva."""
    app, http, fakes = env
    edit = {
        "prompt": "Remove the passers-by from video 1",
        "video_url": "https://cdn.test/in.mp4",
        "resolution": "720p",
    }
    body = {"model": "bytedance/seedance-2.5/video-edit", "input": edit, "hints": {"input_video_seconds": 8}}
    am = next(
        o
        for o in (await http.post("/v1/estimate", json=body)).json()["options"]
        if o["provider"] == "apimart"
    )
    assert am["usd"] == 2.0736 and am["reserve_usd"] == 4.9248 and am["kind"] == "approx"
    fakes.apimart_balance = 3.0
    app.state.router.forget_balance("apimart")
    est = (await http.post("/v1/estimate", json=body)).json()
    assert "apimart" not in [o["provider"] for o in est["options"]]
    assert any(e["provider"] == "apimart" and "insufficient" in e["reason"] for e in est["excluded"])


async def test_a_known_price_change_blocks_sending_even_within_15_minutes(env):
    """Revisión 29: con tabla local se recotiza siempre antes de enviar."""
    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart",
                                                    "max_usd": 0.71})).json()  # fmt: skip
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.0|720P"] = 0.3  # 1,50 USD
    app.state.prices.store("apimart", prices)
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "awaiting_approval" and fakes.sent["apimart"] == [] and state["cost_usd"] == 1.5


async def test_the_reserve_survives_the_plan_and_needs_approval(env):
    """Revisión 29: la retención inicial se guarda, se publica y se aprueba aparte en los respaldos."""
    app, http, fakes = env
    edit = {
        "prompt": "Remove the passers-by from video 1",
        "video_url": "https://cdn.test/in.mp4",
        "resolution": "720p",
    }
    body = {"model": "bytedance/seedance-2.5/video-edit", "input": edit, "hints": {"input_video_seconds": 8}}
    fakes.hf_usd = "0.100"  # Higgsfield es el más barato; APIMart (con reserva) queda de respaldo
    est = (await http.post("/v1/estimate", json=body)).json()
    assert est["provider"] == "higgsfield" and est["options"][1]["reserve_usd"] == 4.9248
    job = (await http.post("/v1/generations", json={**body, "max_usd": 3.0})).json()
    assert job["plan"][1] == {"provider": "apimart", "model": "seedance-2.5", "official": True, "usd": 2.0736,
                              "kind": "approx", "reserve_usd": 4.9248}  # fmt: skip
    async with app.state.sessions() as s:  # Higgsfield rechaza el envío sin cobrar
        row = await s.get(Job, job["id"])
        app.state.worker.fallback(row, "unavailable", "model locked")
        await s.commit()
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert (
        state["status"] == "awaiting_approval" and "holds 4.9248 USD" in state["error"]
    )  # cabe en 3 USD, la reserva no
    r = await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 2.0736})
    assert r.status_code == 409 and r.json()["error"]["code"] == "reserve_not_approved"
    ok = await http.post(
        f"/v1/generations/{job['id']}/approve", json={"max_usd": 2.0736, "max_reserve_usd": 4.9248}
    )
    assert ok.status_code == 200 and ok.json()["max_reserve_usd"] == 4.9248


async def test_a_rejected_approval_shows_the_new_price(env):
    """Revisión 29: tras cost_changed la generación muestra el precio actual (no el viejo para siempre)."""
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()
    await tick(app)
    prices = json.loads((FIXTURES / "prices_kie.json").read_text())
    prices["bytedance/seedance-2, 720p no video input"] = 0.5
    app.state.prices.store("kie", prices)
    r = await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.025})
    assert r.status_code == 409
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "awaiting_approval" and state["cost_usd"] == 2.5
    assert (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 2.5})).status_code == 200


# --- Revisión 30 ----------------------------------------------------------------------------------


async def test_accepting_an_unknown_total_still_requires_the_hold(env):
    app, http, fakes = env
    fakes.hf_usd = "9.000"  # APIMart (con retención) es el más barato
    edit = {
        "prompt": "Remove the passers-by from video 1",
        "video_url": "https://cdn.test/in.mp4",
        "resolution": "720p",
    }
    items = [{"model": "bytedance/seedance-2.5/video-edit", "input": edit, "hints": {"input_video_seconds": 8}},
             {"model": T2V, "input": VIDEO, "provider": "apimart"}]  # fmt: skip
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.5|720P-input"] *= 2  # la retención sube a 9,85 USD
    app.state.prices.store("apimart", prices)
    r = await http.post("/v1/generations/batch", json={"items": items[:1], "accept_unknown_cost": True,
                                                        "max_total_reserve_usd": 4.9248})  # fmt: skip
    assert r.status_code == 409 and r.json()["error"]["code"] == "reserve_not_approved"
    async with app.state.sessions() as s:
        assert (await s.scalars(select(Job))).all() == []


async def test_an_accepted_unknown_price_is_honored_for_that_option(env):
    app, http, fakes = env
    app.state.prices.store("apimart", {})
    r = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart",
                                                  "accept_unknown_cost": True})  # fmt: skip
    assert r.status_code == 202 and r.json()["cost_usd"] is None
    await tick(app)
    assert len(fakes.sent["apimart"]) == 1
    assert (await http.get(f"/v1/generations/{r.json()['id']}")).json()["status"] == "queued"


async def test_the_cheapest_provider_is_reconsidered_before_the_first_send(env):
    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 2})).json()
    assert job["provider"] == "apimart"
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.0|720P"] = 0.3  # APIMart pasa a 1,50; KIE (1,025) es ahora el más barato
    app.state.prices.store("apimart", prices)
    await tick(app)
    assert fakes.sent["apimart"] == [] and len(fakes.sent["kie"]) == 1
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["provider"] == "kie" and state["cost_usd"] == 1.025


async def test_forcing_another_provider_is_not_deduplicated(env):
    """Prueba real F0 (2026-10-03): la misma entrada forzada en otro proveedor devolvía el trabajo anterior."""
    _, http, _ = env
    a = (
        await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart"})
    ).json()
    b = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "kie"})).json()
    c = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "kie"})).json()
    assert a["id"] != b["id"] and b["provider"] == "kie" and c["id"] == b["id"]


# --- Revisión 31 ----------------------------------------------------------------------------------


async def test_a_numeric_cap_still_rules_when_an_unknown_price_becomes_known(env):
    app, http, fakes = env
    real = json.loads((FIXTURES / "prices_apimart.json").read_text())
    app.state.prices.store("apimart", {})
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart",
                                                    "max_usd": 0.71, "accept_unknown_cost": True})).json()  # fmt: skip
    assert job["max_usd"] == 0.71
    app.state.prices.store("apimart", {**real, "seedance-2.0|720P": 0.3})  # ahora 1,50 > 0,71
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "awaiting_approval" and fakes.sent["apimart"] == []


async def test_approving_an_unknown_fallback_with_a_cap_keeps_the_cap(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.71})).json()
    await tick(app)  # APIMart sin saldo → KIE espera aprobación
    real = json.loads((FIXTURES / "prices_kie.json").read_text())
    app.state.prices.store("kie", {})
    assert (
        await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 0.71})
    ).status_code == 409
    ok = await http.post(
        f"/v1/generations/{job['id']}/approve", json={"max_usd": 0.71, "accept_unknown_cost": True}
    )
    assert ok.status_code == 200 and ok.json()["max_usd"] == 0.71
    app.state.prices.store("kie", {**real, "bytedance/seedance-2, 720p no video input": 0.5})  # 2,50 > 0,71
    await tick(app)
    assert fakes.sent["kie"] == []
    assert (await http.get(f"/v1/generations/{job['id']}")).json()["status"] == "awaiting_approval"


async def test_approving_an_unknown_fallback_without_a_cap_sends_it(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.71})).json()
    await tick(app)
    app.state.prices.store("kie", {})
    assert (await http.post(f"/v1/generations/{job['id']}/approve", json={})).status_code == 422
    ok = await http.post(f"/v1/generations/{job['id']}/approve", json={"accept_unknown_cost": True})
    assert ok.status_code == 200 and ok.json()["max_usd"] is None
    await tick(app)
    assert len(fakes.sent["kie"]) == 1


# --- Revisión 32 ----------------------------------------------------------------------------------


async def test_a_rejected_approval_adds_no_permission(env):
    app, http, fakes = env
    fakes.apimart_submit = "credits"
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 0.71})).json()
    await tick(app)  # KIE espera aprobación a 1,025
    r = await http.post(
        f"/v1/generations/{job['id']}/approve", json={"max_usd": 1, "accept_unknown_cost": True}
    )
    assert r.status_code == 409
    ok = await http.post(
        f"/v1/generations/{job['id']}/approve", json={"max_usd": 1.025, "accept_unknown_cost": False}
    )
    assert ok.status_code == 200
    app.state.prices.store("kie", {})  # la tarifa desaparece antes del envío
    await tick(app)
    assert fakes.sent["kie"] == []
    assert (await http.get(f"/v1/generations/{job['id']}")).json()["status"] == "awaiting_approval"


async def test_an_uncapped_acceptance_survives_a_price_that_reappears(env):
    app, http, fakes = env
    real = json.loads((FIXTURES / "prices_apimart.json").read_text())
    # Cotizado sin precio; al crear ya hay tarifa (0,71) y luego sube a 1,50: la aceptación sin tope manda.
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "provider": "apimart",
                                                    "accept_unknown_cost": True})).json()  # fmt: skip
    assert job["max_usd"] is None
    app.state.prices.store("apimart", {**real, "seedance-2.0|720P": 0.3})
    await tick(app)
    assert len(fakes.sent["apimart"]) == 1


async def test_a_batch_cannot_mix_a_total_cap_with_an_unknown_acceptance(env):
    """Revisión 33: aceptar desconocidos borraba el tope total; la combinación se rechaza sin crear nada."""
    app, http, _ = env
    items = [{"model": T2V, "input": VIDEO}]
    r = await http.post(
        "/v1/generations/batch", json={"items": items, "max_total_usd": 0.71, "accept_unknown_cost": True}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "conflicting_approval"
    async with app.state.sessions() as s:
        assert (await s.scalars(select(Job))).all() == []


@pytest.mark.parametrize("message", ["Internal server error", "Internal error: invalid parameter cache",
                                     "moderation service timeout"])  # fmt: skip
async def test_a_kie_internal_error_never_falls_back(env, message):
    """Revisión 34: KIE con HTTP 200 y code 500 genérico: un solo POST y ningún respaldo."""
    app, http, fakes = env
    original = fakes.__call__

    def kie_internal(request):
        if request.url.host == "api.kie.ai" and request.method == "POST":
            fakes.sent["kie"].append(json.loads(request.content))
            return httpx.Response(200, json={"code": 500, "msg": message, "data": None})
        return original(request)

    app.state.providers["kie"]._api._transport = httpx.MockTransport(kie_internal)
    app.state.prices.store(
        "apimart", {}
    )  # KIE (1,025) es el más barato; Higgsfield (1,51) cabe como respaldo
    job = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "max_usd": 5})).json()
    assert job["provider"] == "kie" and [o["provider"] for o in job["plan"]][:2] == ["kie", "higgsfield"]
    await tick(app, polls=3)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "failed" and state["error_kind"] == "submission_ambiguous"
    assert len(fakes.sent["kie"]) == 1 and fakes.sent["apimart"] == [] and fakes.sent["higgsfield"] == []


GROK = "xai/grok-imagine-video/v1.5/reference-to-video"
GROK_INPUT = {
    "prompt": "A neon koi swimming through fog",
    "duration": 6,
    "resolution": "480p",
    "aspect_ratio": "16:9",
}


async def test_an_unofficial_channel_is_its_own_cheaper_option(env):
    """APIMart tiene Grok 1.5 oficial y un canal -ext seis veces más barato: son dos opciones del plan."""
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={"model": GROK, "input": GROK_INPUT})).json()
    apimart = [o for o in body["options"] if o["provider"] == "apimart"]
    assert [(o["model"], o["official"]) for o in apimart] == [
        ("grok-imagine-1.5-video-ext", False),
        ("grok-imagine-video-1.5", True),
    ]
    assert body["options"][0]["model"] == "grok-imagine-1.5-video-ext" and body["usd"] == 0.0612
    assert apimart[1]["usd"] == 0.384
    assert any(e["provider"] == "kie" for e in body["excluded"])  # KIE pide al menos una imagen


async def test_a_failed_unofficial_channel_falls_back_to_the_official_one_with_approval(env):
    """Si el canal -ext falla, el oficial del mismo proveedor es el respaldo; cuesta más, así que pide permiso,
    y la aprobación recotiza ese canal (no vuelve en silencio al -ext más barato)."""
    app, http, fakes = env
    job = (await http.post("/v1/generations", json={"model": GROK, "input": GROK_INPUT})).json()
    assert job["plan"][0]["model"] == "grok-imagine-1.5-video-ext" and job["plan"][0]["official"] is False
    await tick(app)
    sent = fakes.sent["apimart"][0]
    assert (
        sent["model"] == "grok-imagine-1.5-video-ext"
        and sent["size"] == "16:9"
        and "aspect_ratio" not in sent
    )
    fakes.apimart_task = "failed"
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert (
        state["status"] == "awaiting_approval"
        and state["provider"] == "apimart"
        and state["cost_usd"] == 0.384
    )
    fakes.apimart_task = "processing"
    approved = (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 0.4})).json()
    assert approved["status"] == "pending" and approved["cost_usd"] == 0.384
    await tick(app)
    assert fakes.sent["apimart"][1]["model"] == "grok-imagine-video-1.5"


async def test_an_approved_channel_is_sent_even_if_another_gets_cheaper(env):
    """Revisión 41: el replan del primer envío pide aprobar el oficial; aprobado, se envía ese canal aunque el
    -ext vuelva a ser más barato antes del envío."""
    app, http, fakes = env
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    job = (await http.post("/v1/generations", json={"model": GROK, "input": GROK_INPUT})).json()
    app.state.prices.store("apimart", {**prices, "grok-imagine-1.5-video-apimart|480P": 0.1})
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "awaiting_approval" and state["provider_model"] == "grok-imagine-video-1.5"
    approved = (await http.post(f"/v1/generations/{job['id']}/approve", json={"max_usd": 0.384})).json()
    assert approved["provider_model"] == "grok-imagine-video-1.5"
    app.state.prices.store("apimart", prices)  # el -ext vuelve a su tarifa barata
    await tick(app)
    assert [s["model"] for s in fakes.sent["apimart"]] == ["grok-imagine-video-1.5"]


async def test_a_partial_batch_retry_counts_what_it_already_committed(env):
    """Revisión 70 (H1): al recuperar un lote parcial, lo ya creado cuenta con su tope persistido, no con su
    precio de hoy; si el total supera lo aprobado, no se crea el resto."""
    app, http, _ = env
    a = {"model": T2V, "input": VIDEO}
    b = {"model": T2V, "input": {**VIDEO, "prompt": "A kite over a beach"}}
    first = await http.post("/v1/generations/batch", json={"items": [a], "max_total_usd": 0.71},
                            headers={"Idempotency-Key": "k"})  # fmt: skip
    assert first.status_code == 202  # k:0 creado con 0,71 comprometidos
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.0|720P"] = prices["seedance-2.0|720P"] / 2  # baja el precio
    app.state.prices.store("apimart", prices)
    quoted = (await http.post("/v1/generations/batch", json={"items": [a, b], "dry_run": True})).json()
    cheap = quoted["total"]["usd"]
    assert cheap < 1.42
    r = await http.post("/v1/generations/batch", json={"items": [a, b], "max_total_usd": cheap},
                        headers={"Idempotency-Key": "k"})  # fmt: skip
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_changed"
    async with app.state.sessions() as s:
        assert len((await s.scalars(select(Job))).all()) == 1


async def test_a_partial_batch_is_requoted_with_its_key_and_then_recovered(env):
    """Revisión 71 (H1): la cotización en seco con la clave cuenta lo ya creado con su compromiso de entonces;
    con ese total, el reintento recupera el primero y crea solo el segundo."""
    app, http, _ = env
    a = {"model": T2V, "input": VIDEO}
    b = {"model": T2V, "input": {**VIDEO, "prompt": "A kite over a beach"}}
    await http.post("/v1/generations/batch", json={"items": [a], "max_total_usd": 0.71},
                    headers={"Idempotency-Key": "k"})  # fmt: skip
    prices = json.loads((FIXTURES / "prices_apimart.json").read_text())
    prices["seedance-2.0|720P"] = prices["seedance-2.0|720P"] / 2
    app.state.prices.store("apimart", prices)
    plain = (await http.post("/v1/generations/batch", json={"items": [a, b], "dry_run": True})).json()[
        "total"
    ]
    keyed = (
        await http.post(
            "/v1/generations/batch", json={"items": [a, b], "dry_run": True}, headers={"Idempotency-Key": "k"}
        )
    ).json()["total"]
    assert keyed["recovered"] == 1 and keyed["usd"] == pytest.approx(0.71 + plain["usd"] / 2, abs=1e-4)
    r = await http.post("/v1/generations/batch", json={"items": [a, b], "max_total_usd": keyed["usd"]},
                        headers={"Idempotency-Key": "k"})  # fmt: skip
    assert r.status_code == 202 and len(r.json()["generations"]) == 2
    async with app.state.sessions() as s:
        assert len((await s.scalars(select(Job))).all()) == 2


async def test_recovering_a_batch_does_not_requote_what_it_already_created(env):
    """Revisión 71 (H2): una posición ya creada no se vuelve a cotizar (su proveedor puede no estar ya)."""
    from hf_studio.service import request_digest

    app, http, _ = env
    assistant = {"model": "claude/assistant", "input": {"prompt": "Write a prompt"}}
    video = {"model": T2V, "input": VIDEO}
    async with app.state.sessions() as s:  # creado en un intento anterior; hoy no hay ANTHROPIC_API_KEY
        owner = await s.scalar(select(ApiClient))
        s.add(Job(owner_id=owner.id, model=assistant["model"], input=assistant["input"], status="completed",
                  provider="anthropic", idempotency_key="m:0", max_usd=0.12,
                  input_hash=request_digest(assistant["model"], assistant["input"])))  # fmt: skip
        await s.commit()
    dry = (
        await http.post(
            "/v1/generations/batch",
            json={"items": [assistant, video], "dry_run": True},
            headers={"Idempotency-Key": "m"},
        )
    ).json()
    assert dry["total"]["usd"] == pytest.approx(0.12 + 0.71)
    r = await http.post("/v1/generations/batch", json={"items": [assistant, video], "max_total_usd": 0.83},
                        headers={"Idempotency-Key": "m"})  # fmt: skip
    assert r.status_code == 202, r.text
    other = await http.post("/v1/generations/batch", json={"items": [video, video], "max_total_usd": 2},
                            headers={"Idempotency-Key": "m"})  # fmt: skip
    assert other.status_code == 409 and other.json()["error"]["code"] == "idempotency_conflict"


async def test_two_retries_of_the_same_batch_key_run_one_after_the_other(env):
    """Revisión 72 (H1): dos reintentos simultáneos de la misma clave no cotizan ni crean a la vez: el segundo
    espera al primero y ve lo que creó (así no suman dos fotos distintas del presupuesto)."""
    import asyncio

    app, http, _ = env
    router = app.state.router
    real_plan = router.plan
    entered, release = asyncio.Event(), asyncio.Event()
    planning = 0

    async def slow_plan(*args, **kwargs):
        nonlocal planning
        planning += 1
        entered.set()
        await release.wait()
        return await real_plan(*args, **kwargs)

    router.plan = slow_plan
    body = {"items": [{"model": T2V, "input": VIDEO}], "max_total_usd": 0.71}
    first = asyncio.create_task(
        http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "same"})
    )
    await entered.wait()
    second = asyncio.create_task(
        http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "same"})
    )
    await asyncio.sleep(0.2)
    assert planning == 1  # el segundo espera el candado, no cotiza en paralelo
    release.set()
    a, b = await asyncio.gather(first, second)
    router.plan = real_plan
    assert a.status_code == 202 and b.status_code == 200
    assert a.json()["generations"][0]["id"] == b.json()["generations"][0]["id"] and planning == 1
