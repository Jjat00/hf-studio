"""Pruebas de extremo a extremo contra un Higgsfield falso (httpx.MockTransport): no gastan créditos."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import update

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, hash_token, utcnow

T2V = "bytedance/seedance-2.0/text-to-video"
I2V = "bytedance/seedance-2.0/image-to-video"
VIDEO = {"prompt": "A cinematic tracking shot along a sunlit coastal road", "resolution": "720p",
         "generate_audio": True, "duration": 5, "aspect_ratio": "16:9"}  # fmt: skip


class FakeHiggsfield:
    def __init__(self):
        self.submits: list[httpx.Request] = []
        self.remote: dict[str, dict] = {}
        self.submit_mode = "ok"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, path = str(request.url), request.url.path
        if url.startswith("https://cdn.test/"):
            return httpx.Response(200, content=b"MP4DATA", headers={"content-type": "video/mp4"})
        if url.startswith("https://storage.test/"):
            return httpx.Response(200)
        assert request.headers["authorization"] == "Key kid:ksecret"
        if path == "/files/generate-upload-url":
            return httpx.Response(200, json={"public_url": "https://cdn.test/in.png",
                                             "upload_url": "https://storage.test/put",
                                             "upload_headers": {"Content-Type": "image/png"}})  # fmt: skip
        if path.startswith("/requests/") and path.endswith("/status"):
            return httpx.Response(200, json=self.remote[path.split("/")[2]])
        if path.startswith("/requests/") and path.endswith("/cancel"):
            return httpx.Response(202)
        if request.method == "POST":
            self.submits.append(request)
            if self.submit_mode == "concurrency":
                return httpx.Response(
                    400, json={"detail": "Maximum number of concurrent requests (4) has been reached"}
                )
            if self.submit_mode == "timeout":
                raise httpx.ReadTimeout("sin respuesta", request=request)
            rid = f"00000000-0000-0000-0000-{len(self.submits):012d}"
            self.remote[rid] = {"status": "queued", "request_id": rid}
            return httpx.Response(200, json={
                "status": "queued", "request_id": rid,
                "status_url": f"https://api.higgsfield.test/requests/{rid}/status",
                "cancel_url": f"https://api.higgsfield.test/requests/{rid}/cancel",
            }, headers={"x-correlation-id": "corr-1"})  # fmt: skip
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
async def env(tmp_path):
    fake = FakeHiggsfield()
    settings = Settings(
        _env_file=None,
        hf_api_key_id="kid",
        hf_api_key_secret="ksecret",
        hf_base_url="https://api.higgsfield.test",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db",
        storage_dir=tmp_path / "files",
        public_base_url="https://studio.example.com",
        worker_enabled=False,
        max_active_jobs_per_client=3,
    )
    app = create_app(settings, transport=httpx.MockTransport(fake))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add_all([
                ApiClient(name="agente", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"),
                ApiClient(name="otro", key_hash=hash_token("hfs_b"), key_prefix="hfs_b"),
            ])  # fmt: skip
            await s.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, fake


async def make_due(app):
    async with app.state.sessions() as s:
        await s.execute(update(Job).values(next_check_at=utcnow() - timedelta(seconds=1)))
        await s.commit()


async def test_requires_key(env):
    _, http, _ = env
    assert (await http.get("/v1/models", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await http.get("/health")).json()["higgsfield_configured"] is True


async def test_catalog_lists_first_last_frame_models(env):
    _, http, _ = env
    body = (await http.get("/v1/models", params={"capability": "first-last-frame"})).json()
    ids = {m["id"] for m in body["models"]}
    assert {I2V, "kling-video/o3/first-last-frame"} <= ids
    schema = (await http.get(f"/v1/models/{T2V}")).json()["input_schema"]
    assert schema["properties"]["duration"]["maximum"] == 15


async def test_full_lifecycle_text_to_video(env):
    app, http, fake = env
    r = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    job_id = r.json()["id"]

    await app.state.worker.tick()
    sent = fake.submits[0]
    assert sent.url.path == f"/{T2V}"
    assert json.loads(sent.content) == VIDEO
    assert sent.url.params["hf_webhook"].startswith(
        f"https://studio.example.com/v1/webhooks/higgsfield/{job_id}?token="
    )
    job = (await http.get(f"/v1/generations/{job_id}")).json()
    assert job["status"] == "queued" and job["correlation_id"] == "corr-1"

    rid = job["request_id"]
    fake.remote[rid] = {"status": "in_progress", "request_id": rid}
    await make_due(app)
    await app.state.worker.tick()
    assert (await http.get(f"/v1/generations/{job_id}")).json()["status"] == "in_progress"

    fake.remote[rid] = {
        "status": "completed",
        "request_id": rid,
        "video": {"url": "https://cdn.test/out.mp4"},
    }
    await make_due(app)
    await app.state.worker.tick()
    job = (await http.get(f"/v1/generations/{job_id}")).json()
    assert job["status"] == "completed" and job["terminal"]
    out = job["outputs"][0]
    assert "file_url" in out  # la copia local existe en cuanto el trabajo es `completed`
    assert out["kind"] == "video" and out["url"] == "https://cdn.test/out.mp4"
    assert (await http.get(out["file_url"])).content == b"MP4DATA"
    assert len(fake.submits) == 1


async def test_invalid_input_never_reaches_higgsfield(env):
    _, http, fake = env
    r = await http.post("/v1/generations", json={"model": T2V, "input": {**VIDEO, "duration": 30}})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["path"] == "duration"
    r = await http.post("/v1/generations", json={"model": I2V, "input": {"image_url": "/home/yo/foto.png"}})
    assert r.status_code == 422 and "URL" in r.json()["error"]["details"][0]["message"]
    r = await http.post("/v1/generations", json={"model": "no/existe", "input": {}})
    assert r.status_code == 404
    assert fake.submits == []


async def test_first_and_last_frame_is_accepted(env):
    _, http, _ = env
    body = {
        "image_url": "https://cdn.test/a.png",
        "end_image_url": "https://cdn.test/b.png",
        "prompt": "morph",
    }
    assert (await http.post("/v1/generations", json={"model": I2V, "input": body})).status_code == 202


async def test_ownership_is_enforced(env):
    _, http, _ = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    other = {"Authorization": "Bearer hfs_b"}
    assert (await http.get(f"/v1/generations/{job_id}", headers=other)).status_code == 404
    assert (await http.post(f"/v1/generations/{job_id}/cancel", headers=other)).status_code == 404
    assert (await http.get("/v1/generations", headers=other)).json()["generations"] == []


async def test_duplicates_and_idempotency(env):
    _, http, _ = env
    first = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})
    again = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})
    assert (
        again.status_code == 200 and again.json()["deduplicated"] and again.json()["id"] == first.json()["id"]
    )

    key = {"Idempotency-Key": "k1"}
    a = await http.post(
        "/v1/generations", json={"model": T2V, "input": VIDEO, "allow_duplicate": True}, headers=key
    )
    b = await http.post(
        "/v1/generations", json={"model": T2V, "input": VIDEO, "allow_duplicate": True}, headers=key
    )
    assert a.status_code == 202 and b.json()["id"] == a.json()["id"]
    other = {**VIDEO, "prompt": "otra cosa"}
    assert (
        await http.post("/v1/generations", json={"model": T2V, "input": other}, headers=key)
    ).status_code == 409


async def test_active_job_limit_per_client(env):
    _, http, _ = env
    for i in range(3):
        r = await http.post("/v1/generations", json={"model": T2V, "input": {**VIDEO, "prompt": f"p{i}"}})
        assert r.status_code == 202
    r = await http.post("/v1/generations", json={"model": T2V, "input": {**VIDEO, "prompt": "p9"}})
    assert r.status_code == 429


async def test_concurrency_limit_keeps_job_queued_locally(env):
    app, http, fake = env
    fake.submit_mode = "concurrency"
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    await app.state.worker.tick()
    job = (await http.get(f"/v1/generations/{job_id}")).json()
    assert job["status"] == "pending" and job["error"] is None
    await app.state.worker.tick()  # envíos en pausa: no se martillea la API
    assert len(fake.submits) == 1


async def test_ambiguous_submit_is_not_retried(env):
    app, http, fake = env
    fake.submit_mode = "timeout"
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    await app.state.worker.tick()
    await app.state.worker.tick()
    job = (await http.get(f"/v1/generations/{job_id}")).json()
    assert job["status"] == "failed" and job["error_kind"] == "submission_ambiguous"
    assert len(fake.submits) == 1


async def test_cancel_pending_and_queued(env):
    app, http, _ = env
    a = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    assert (await http.post(f"/v1/generations/{a}/cancel")).json()["status"] == "canceled"
    b = (await http.post("/v1/generations", json={"model": T2V, "input": {**VIDEO, "prompt": "b"}})).json()[
        "id"
    ]
    await app.state.worker.tick()
    assert (await http.post(f"/v1/generations/{b}/cancel")).json()["status"] == "canceled"
    assert (await http.post(f"/v1/generations/{b}/cancel")).status_code == 409


async def test_webhook_triggers_authoritative_refresh(env):
    app, http, fake = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    await app.state.worker.tick()
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
    rid, token = job.hf_request_id, job.webhook_token
    envelope = {
        "request_id": rid,
        "status": "completed",
        "error": None,
        "payload": {"video": {"url": "https://evil.test/x.mp4"}},
    }
    url = f"/v1/webhooks/higgsfield/{job_id}"
    assert (await http.post(url, params={"token": "mal"}, json=envelope)).status_code == 404
    assert (await http.post(url, params={"token": token}, json={"foo": 1})).status_code == 400

    fake.remote[rid] = {
        "status": "completed",
        "request_id": rid,
        "video": {"url": "https://cdn.test/real.mp4"},
    }
    assert (await http.post(url, params={"token": token}, json=envelope)).status_code == 200
    await asyncio.gather(*app.state.tasks)
    job = (await http.get(f"/v1/generations/{job_id}")).json()
    # Se usa la respuesta del endpoint de estado, no la URL que venía en el webhook.
    assert job["status"] == "completed" and job["outputs"][0]["url"] == "https://cdn.test/real.mp4"
    assert (await http.post(url, params={"token": token}, json=envelope)).status_code == 200  # duplicado


async def test_long_poll_wait_returns_when_terminal(env):
    app, http, fake = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    await app.state.worker.tick()

    async def finish_later():
        await asyncio.sleep(1.2)
        rid = next(iter(fake.remote))
        fake.remote[rid] = {"status": "failed", "request_id": rid, "error": "Generation failed"}
        await make_due(app)
        await app.state.worker.tick()

    task = asyncio.create_task(finish_later())
    job = (await http.get(f"/v1/generations/{job_id}", params={"wait": 10})).json()
    await task
    assert job["status"] == "failed" and job["error"] == "Generation failed"


async def test_upload(env):
    _, http, _ = env
    r = await http.post("/v1/uploads", files={"file": ("a.png", b"\x89PNG", "image/png")})
    assert r.status_code == 201 and r.json()["url"] == "https://cdn.test/in.png"
    r = await http.post("/v1/uploads", files={"file": ("a.txt", b"hola", "text/plain")})
    assert r.status_code == 415


def test_single_key_and_split_credentials_build_same_header():
    single = Settings(_env_file=None, hf_api_key="kid:ksecret")
    split = Settings(_env_file=None, hf_api_key_id="kid", hf_api_key_secret="ksecret")
    prefixed = Settings(_env_file=None, hf_api_key="Key kid:ksecret")
    assert single.hf_credential == split.hf_credential == prefixed.hf_credential == "kid:ksecret"
    assert not Settings(_env_file=None).hf_configured


async def test_check_credentials_uses_free_status_probe():
    from hf_studio.higgsfield import HiggsfieldClient

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        ok = request.headers["authorization"] == "Key kid:ksecret"
        return httpx.Response(404 if ok else 401, json={"detail": "x"})

    good = HiggsfieldClient(Settings(_env_file=None, hf_api_key="kid:ksecret"), httpx.MockTransport(handler))
    bad = HiggsfieldClient(Settings(_env_file=None, hf_api_key="otra"), httpx.MockTransport(handler))
    assert await good.check_credentials() is True
    assert await bad.check_credentials() is False
    assert all(m == "GET" and p.endswith("/status") for m, p in seen)  # nunca un POST que cobre
    await good.aclose()
    await bad.aclose()
