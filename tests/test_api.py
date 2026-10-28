"""Pruebas de extremo a extremo contra un Higgsfield falso (httpx.MockTransport): no gastan créditos."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, Upload, hash_token, utcnow

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
T2V = "bytedance/seedance-2.0/text-to-video"
I2V = "bytedance/seedance-2.0/image-to-video"
RESTYLE = "higgsfield/genjutsu/restyle/v1.0"
STYLE = "c2143317-f28d-4c3c-a0b8-39bd547e08a7"
VIDEO = {"prompt": "A cinematic tracking shot along a sunlit coastal road", "resolution": "720p",
         "generate_audio": True, "duration": 5, "aspect_ratio": "16:9"}  # fmt: skip


class FakeHiggsfield:
    def __init__(self):
        self.submits: list[httpx.Request] = []
        self.remote: dict[str, dict] = {}
        self.submit_mode = "ok"
        self.upload_failures = 0  # cuántas veces responde 500 a generate-upload-url antes de funcionar
        self.styles = [{"id": STYLE, "name": "Cel-Shaded CG Anime", "preview_url": "https://cdn.test/s.webp"}]
        self.style_calls = 0
        self.option_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, path = str(request.url), request.url.path
        if url.startswith("https://cdn.test/"):
            return httpx.Response(200, content=b"MP4DATA", headers={"content-type": "video/mp4"})
        if url.startswith("https://storage.test/"):
            return httpx.Response(200)
        assert request.headers["authorization"] == "Key kid:ksecret"
        if path == "/files/generate-upload-url":
            if self.upload_failures:
                self.upload_failures -= 1
                return httpx.Response(500, json={"detail": "Internal Server Error"})
            return httpx.Response(200, json={"public_url": "https://cdn.test/in.png",
                                             "upload_url": "https://storage.test/put",
                                             "upload_headers": {"Content-Type": "image/png"}})  # fmt: skip
        if path.startswith("/requests/") and path.endswith("/status"):
            return httpx.Response(200, json=self.remote[path.split("/")[2]])
        if path.startswith("/requests/") and path.endswith("/cancel"):
            return httpx.Response(202)
        if path == "/models/higgsfield/genjutsu/restyle/v1.0/presets":
            self.style_calls += 1
            return httpx.Response(
                200, json={"model": "higgsfield/genjutsu/restyle/v1.0", "items": self.styles}
            )
        if path == "/models/higgsfield/ai-influencer/options":
            self.option_calls += 1
            return httpx.Response(200, json={"config_revision": "r1", "categories": [
                {"key": "gender", "label": "Gender", "tiers": ["normal"], "max": 1,
                 "options": [{"key": "female", "label": "Female", "img": None, "tiers": None}]}]})  # fmt: skip
        if path.startswith("/estimate/"):
            return httpx.Response(
                200, json={"type": "estimate", "credits": "1.000", "usd": "0.060", "discount": None}
            )
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
    r = await http.post("/v1/uploads", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201 and r.json()["url"] == "https://cdn.test/in.png"
    r = await http.post("/v1/uploads", files={"file": ("a.txt", b"hola", "text/plain")})
    assert r.status_code == 415


async def test_upload_retries_transient_higgsfield_errors(env, monkeypatch):
    _, http, fake = env
    real_sleep = asyncio.sleep
    monkeypatch.setattr("hf_studio.higgsfield.asyncio.sleep", lambda s: real_sleep(0))
    fake.upload_failures = 2
    r = await http.post("/v1/uploads", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201 and fake.upload_failures == 0
    fake.upload_failures = 5
    r = await http.post("/v1/uploads", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 502 and fake.upload_failures == 2


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


async def test_delete_generation(env):
    _, http, _ = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    assert (await http.delete(f"/v1/generations/{job_id}")).status_code == 409  # aún activa
    await http.post(f"/v1/generations/{job_id}/cancel")
    other = {"Authorization": "Bearer hfs_b"}
    assert (await http.delete(f"/v1/generations/{job_id}", headers=other)).status_code == 404
    assert (await http.delete(f"/v1/generations/{job_id}")).status_code == 204
    assert (await http.get(f"/v1/generations/{job_id}")).status_code == 404


async def test_batch_dry_run_quotes_without_submitting(env):
    _, http, fake = env
    body = {
        "items": [{"model": T2V, "input": VIDEO, "count": 2}, {"model": I2V, "input": {"duration": 5}}],
        "dry_run": True,
    }
    r = (await http.post("/v1/generations/batch", json=body)).json()
    assert r["total"] == {"usd": 0.18, "credits": 3.0, "complete": True, "reserve_usd": None}
    assert fake.submits == []


async def test_negative_or_infinite_hints_are_rejected(env):
    _, http, _ = env
    for bad in (-4, 0):
        r = await http.post(
            "/v1/estimate", json={"model": T2V, "input": VIDEO, "hints": {"input_video_seconds": bad}}
        )
        assert r.status_code == 422
    item = {"model": T2V, "input": VIDEO, "hints": {"input_video_seconds": -1}}
    r = await http.post("/v1/generations/batch", json={"items": [item], "dry_run": True})
    assert r.status_code == 422


async def test_batch_creates_variants_and_waits_for_all(env):
    app, http, fake = env
    body = {"items": [{"model": T2V, "input": VIDEO, "count": 2}]}
    r = await http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "b1"})
    ids = [g["id"] for g in r.json()["generations"]]
    assert r.status_code == 202 and len(set(ids)) == 2
    again = await http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "b1"})
    assert [g["id"] for g in again.json()["generations"]] == ids  # reintento seguro
    await app.state.worker.tick()
    for rid in list(fake.remote):
        fake.remote[rid] = {
            "status": "completed",
            "request_id": rid,
            "video": {"url": "https://cdn.test/o.mp4"},
        }
    await make_due(app)
    await app.state.worker.tick()
    r = (await http.get("/v1/generations", params={"ids": ",".join(ids), "wait": 5})).json()
    assert r["all_terminal"] and {g["status"] for g in r["generations"]} == {"completed"}
    too_many = {"items": [{"model": T2V, "input": {**VIDEO, "prompt": "x"}, "count": 8}]}
    assert (await http.post("/v1/generations/batch", json=too_many)).status_code == 429


async def test_builtin_preset_renders_and_prices(env):
    _, http, fake = env
    names = {p["slug"] for p in (await http.get("/v1/presets")).json()["presets"]}
    assert {"hero-shot", "morph", "dance-transfer"} <= names
    dry = {"variables": {"product": "red sneakers"}, "dry_run": True}
    r = (await http.post("/v1/presets/hero-shot/run", json=dry)).json()
    assert "red sneakers" in r["input"]["prompt"] and r["input"]["aspect_ratio"] == "4:3"
    assert r["estimate"]["kind"] == "exact" and fake.submits == []
    missing = await http.post("/v1/presets/hero-shot/run", json={"variables": {}})
    assert missing.status_code == 422 and missing.json()["error"]["details"][0]["path"] == "product"
    frames = {"start": "https://cdn.test/a.png", "end": "https://cdn.test/b.png"}
    run = await http.post("/v1/presets/morph/run", json={"variables": frames})
    assert run.status_code == 202 and run.json()["input"]["end_image_url"] == "https://cdn.test/b.png"


async def test_preset_from_generation_is_private(env):
    _, http, _ = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    r = await http.post(f"/v1/presets/from-generation/{job_id}", json={"slug": "my-road", "title": "My road"})
    assert r.status_code == 201 and r.json()["template"]["prompt"] == "{{prompt}}"
    dry = {"variables": {"prompt": "a desert road"}, "dry_run": True}
    run = (await http.post("/v1/presets/my-road/run", json=dry)).json()
    assert run["input"]["prompt"] == "a desert road" and run["input"]["duration"] == 5
    other = {"Authorization": "Bearer hfs_b"}
    assert (await http.get("/v1/presets/my-road", headers=other)).status_code == 404
    assert (await http.delete("/v1/presets/hero-shot")).status_code == 404  # los de serie no se borran


async def test_sees_all_client_reads_every_generation(env):
    app, http, _ = env
    job_id = (await http.post("/v1/generations", json={"model": T2V, "input": VIDEO})).json()["id"]
    async with app.state.sessions() as s:
        await s.execute(update(ApiClient).where(ApiClient.name == "otro").values(sees_all=True))
        await s.commit()
    ui = {"Authorization": "Bearer hfs_b"}
    listed = (await http.get("/v1/generations", headers=ui)).json()["generations"]
    assert [(g["id"], g["source"]) for g in listed] == [(job_id, "agente")]
    assert (await http.get(f"/v1/generations/{job_id}", headers=ui)).json()["source"] == "agente"
    # El dueño sigue viendo lo suyo sin el campo de origen.
    assert "source" not in (await http.get(f"/v1/generations/{job_id}")).json()


EDIT = "bytedance/seedance-2.5/video-edit"


async def test_keep_source_audio_only_for_video_inputs(env):
    app, http, _ = env
    bad = await http.post("/v1/generations", json={"model": T2V, "input": VIDEO, "keep_source_audio": True})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "source_audio_unsupported"
    body = {"prompt": "swap the jacket", "video_url": "https://cdn.test/src.mp4", "generate_audio": False}
    # Una URL que no es una subida propia no se abre con ffmpeg (SSRF).
    untrusted = await http.post(
        "/v1/generations", json={"model": EDIT, "input": body, "keep_source_audio": True}
    )
    assert untrusted.json()["error"]["code"] == "untrusted_source"
    async with app.state.sessions() as s:
        owner = await s.scalar(select(ApiClient).where(ApiClient.name == "agente"))
        s.add(
            Upload(
                owner_id=owner.id, filename="src.mp4", content_type="video/mp4", size=1, url=body["video_url"]
            )
        )
        await s.commit()
    plain = (await http.post("/v1/generations", json={"model": EDIT, "input": body})).json()
    kept = await http.post("/v1/generations", json={"model": EDIT, "input": body, "keep_source_audio": True})
    # La opción cambia el resultado: no se deduplica contra la misma entrada sin ella.
    assert kept.status_code == 202
    assert kept.json()["id"] != plain["id"]
    assert kept.json()["keep_source_audio"] is True and plain["keep_source_audio"] is False


async def test_studio_notes_warn_about_silent_edits(env):
    _, http, _ = env
    notes = (await http.get(f"/v1/models/{EDIT}")).json()["studio_notes"]
    assert any("SILENT" in n for n in notes) and any("keep_source_audio" in n for n in notes)
    assert (await http.get(f"/v1/models/{T2V}")).json()["studio_notes"] == []


async def test_model_detail_says_whether_keep_source_audio_is_accepted(env):
    """La UI ofrece «Conservar audio» con este campo: debe coincidir con lo que acepta create_generation."""
    _, http, _ = env
    assert (await http.get(f"/v1/models/{EDIT}")).json()["keep_source_audio"] is True
    assert (await http.get(f"/v1/models/{T2V}")).json()["keep_source_audio"] is False
    for model in ("higgsfield/genjutsu/restyle/v1.0", "higgsfield/genjutsu-light/motion-transfer/v1.0"):
        assert (await http.get(f"/v1/models/{model}")).json()["keep_source_audio"] is False


async def test_upload_rejects_content_that_is_not_the_declared_type(env):
    """Revisión 28: un manifiesto DASH subido como video/mp4 haría que ffmpeg abriera sus URLs."""
    _, http, _ = env
    mpd = b'<?xml version="1.0"?><MPD><BaseURL>https://127.0.0.1/internal.mp4</BaseURL></MPD>'
    r = await http.post("/v1/uploads", files={"file": ("a.mp4", mpd, "video/mp4")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "content_mismatch"


async def test_influencer_options_are_listed_and_cached(env):
    _, http, fake = env
    r = await http.get("/v1/model-options/higgsfield/ai-influencer")
    assert r.status_code == 200 and r.json()["revision"] == "r1"
    assert r.json()["categories"][0]["options"][0]["key"] == "female"
    await http.get("/v1/model-options/higgsfield/ai-influencer")
    assert fake.option_calls == 1  # 10 min en memoria
    assert (await http.get(f"/v1/model-options/{RESTYLE}")).json()["error"]["code"] == "no_options"


async def test_restyle_styles_are_listed_cached_and_checked_before_quoting(env):
    _, http, fake = env
    r = await http.get(f"/v1/model-styles/{RESTYLE}")
    assert r.status_code == 200 and r.json()["styles"][0]["id"] == STYLE
    await http.get(f"/v1/model-styles/{RESTYLE}")
    assert fake.style_calls == 1  # 10 min en memoria
    assert (await http.get(f"/v1/model-styles/{T2V}")).json()["error"]["code"] == "no_styles"
    body = {"model": RESTYLE, "input": {"video_url": "https://cdn.test/v.mp4", "preset_id": STYLE},
            "hints": {"input_video_seconds": 5}}  # fmt: skip
    assert (await http.post("/v1/estimate", json=body)).status_code == 200
    gone = {**body, "input": {**body["input"], "preset_id": "00000000-0000-0000-0000-000000000000"}}
    r = await http.post("/v1/estimate", json=gone)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_style"
    assert r.json()["error"]["details"][0]["path"] == "preset_id"  # la UI lo marca en el selector
    assert fake.style_calls == 2  # un id desconocido fuerza una recarga antes de rechazarlo


async def test_renamed_genjutsu_id_resolves_to_the_new_one(env):
    _, http, _ = env
    r = await http.get("/v1/models/higgsfiled/genjutsu/motion-transfer/v1.0")
    assert r.status_code == 200 and r.json()["id"] == "higgsfield/genjutsu/motion-transfer/v1.0"


OLD_SWAP, NEW_SWAP = "higgsfiled/genjutsu/object-swap/v1.0", "higgsfield/genjutsu/object-swap/v1.0"
SWAP_INPUT = {"video_url": "https://cdn.test/v.mp4", "image_urls": ["https://cdn.test/i.png"]}


async def test_retrying_with_a_renamed_id_keeps_idempotency(env):
    """Revisión 83 de Codex: el reintento con el id viejo y la misma clave daba 409 (lotes y trabajos guardados
    antes del renombre, cuya huella usa el id viejo)."""
    app, http, _ = env
    body = {"items": [{"model": OLD_SWAP, "input": SWAP_INPUT}]}
    first = await http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "legacy-batch"})
    again = await http.post("/v1/generations/batch", json=body, headers={"Idempotency-Key": "legacy-batch"})
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["generations"][0]["id"] == first.json()["generations"][0]["id"]

    from hf_studio.service import _digest

    one = {"model": NEW_SWAP, "input": SWAP_INPUT, "allow_duplicate": True}
    job = (await http.post("/v1/generations", json=one, headers={"Idempotency-Key": "legacy-one"})).json()
    async with app.state.sessions() as s:  # como lo guardó una versión anterior: huella con el id viejo
        await s.execute(update(Job).where(Job.id == job["id"]).values(
            input_hash=_digest(OLD_SWAP, SWAP_INPUT, False, None)))  # fmt: skip
        await s.commit()
    for model in (OLD_SWAP, NEW_SWAP):
        r = await http.post(
            "/v1/generations", json={**one, "model": model}, headers={"Idempotency-Key": "legacy-one"}
        )
        assert r.status_code == 200 and r.json()["id"] == job["id"]


async def test_a_stored_plan_with_a_renamed_id_can_be_requoted(env):
    from hf_studio.routing import requote

    app, _, _ = env
    model = app.state.router.catalog.get(NEW_SWAP)
    option = {
        "provider": "higgsfield",
        "model": OLD_SWAP,
        "input": SWAP_INPUT,
        "hints": {"input_video_seconds": 5},
    }
    fresh = await requote(app.state.router, model, SWAP_INPUT, option)
    assert fresh is not None and fresh["model"] == NEW_SWAP


async def test_generations_can_be_filtered_by_model_or_input_text(env):
    """El historial de AI Influencer pide sus generaciones aunque haya cientos más recientes."""
    _, http, _ = env
    base = {"input": {"prompt": "a cat"}, "confirm_unknown_cost": True}
    for i, prompt in enumerate(["Traits: gender: male", "a dog", "50% off"]):
        body = {**base, "model": T2V, "input": {"prompt": prompt}, "idempotency_key": f"f{i}"}
        assert (await http.post("/v1/generations", json=body)).status_code in (200, 201, 202)
    found = (await http.get("/v1/generations", params={"text": ["Traits:"], "limit": 100})).json()[
        "generations"
    ]
    assert [g["input"]["prompt"] for g in found] == ["Traits: gender: male"]
    # % y _ se buscan literales, no como comodines de LIKE.
    found = (await http.get("/v1/generations", params={"text": ["50%"]})).json()["generations"]
    assert [g["input"]["prompt"] for g in found] == ["50% off"]
    assert len((await http.get("/v1/generations", params={"model": [T2V]})).json()["generations"]) == 3
    assert (await http.get("/v1/generations", params={"model": ["x/y"]})).json()["generations"] == []


async def test_hidden_generations_leave_the_lists_but_not_their_links(env):
    app, http, _ = env
    ids = []
    for i in range(3):
        body = {
            "model": T2V,
            "input": {"prompt": f"p{i}"},
            "confirm_unknown_cost": True,
            "idempotency_key": f"h{i}",
        }
        ids.append((await http.post("/v1/generations", json=body)).json()["id"])
    async with app.state.sessions() as s:
        await s.execute(
            update(Job).where(Job.id.in_(ids[:2])).values(status="completed", version=Job.version + 1)
        )
        await s.commit()
    # La tercera sigue en curso: no se oculta.
    res = (await http.post("/v1/generations/hide", json={"ids": ids})).json()
    assert res == {"changed": sorted(ids[:2]), "skipped": [ids[2]]}
    listed = [g["id"] for g in (await http.get("/v1/generations")).json()["generations"]]
    assert listed == [ids[2]]
    hidden = (await http.get("/v1/generations", params={"hidden": "true"})).json()["generations"]
    assert sorted(g["id"] for g in hidden) == sorted(ids[:2]) and all(g["hidden"] for g in hidden)
    # Por id (un lienzo, el detalle) se siguen viendo.
    assert (await http.get(f"/v1/generations/{ids[0]}")).json()["hidden"] is True
    by_ids = (await http.get("/v1/generations", params={"ids": ids[0]})).json()["generations"]
    assert [g["id"] for g in by_ids] == [ids[0]]
    await http.post("/v1/generations/hide", json={"ids": [ids[0]], "hidden": False})
    assert len((await http.get("/v1/generations")).json()["generations"]) == 2


async def test_favorites_are_marked_in_bulk_and_listed_on_their_own(env):
    _, http, _ = env
    ids = []
    for i in range(3):
        body = {
            "model": T2V,
            "input": {"prompt": f"f{i}"},
            "confirm_unknown_cost": True,
            "idempotency_key": f"fav{i}",
        }
        ids.append((await http.post("/v1/generations", json=body)).json()["id"])
    res = (await http.post("/v1/generations/favorite", json={"ids": [*ids[:2], "nope"]})).json()
    assert res == {"changed": sorted(ids[:2]), "skipped": ["nope"]}
    favs = (await http.get("/v1/generations", params={"favorite": "true"})).json()["generations"]
    assert sorted(g["id"] for g in favs) == sorted(ids[:2]) and all(g["favorite"] for g in favs)
    assert len((await http.get("/v1/generations")).json()["generations"]) == 3  # siguen en la biblioteca
    await http.post("/v1/generations/favorite", json={"ids": [ids[0]], "favorite": False})
    favs = (await http.get("/v1/generations", params={"favorite": "true"})).json()["generations"]
    assert [g["id"] for g in favs] == [ids[1]]


async def test_a_library_flag_does_not_break_a_worker_writing_the_same_job(env):
    """Marcar favorita u ocultar no sube Job.version: el worker que ya leyó el trabajo (p. ej. mientras lo
    envía al proveedor) guarda igual su resultado, y su escritura no pisa la marca."""
    app, http, _ = env
    body = {
        "model": T2V,
        "input": {"prompt": "race"},
        "confirm_unknown_cost": True,
        "idempotency_key": "race",
    }
    job_id = (await http.post("/v1/generations", json=body)).json()["id"]
    async with app.state.sessions() as worker:
        job = await worker.get(Job, job_id)  # el worker lo leyó antes de que llegue la estrella
        assert (await http.post("/v1/generations/favorite", json={"ids": [job_id]})).status_code == 200
        job.status, job.hf_request_id = "queued", "req-race"
        await worker.commit()  # sin StaleDataError
    async with app.state.sessions() as s:
        saved = await s.get(Job, job_id)
        assert saved.status == "queued" and saved.hf_request_id == "req-race" and saved.favorite is True


async def test_the_library_reads_its_whole_window_in_order(env):
    app, http, _ = env
    ids = []
    for i in range(5):
        body = {
            "model": T2V,
            "input": {"prompt": f"c{i}"},
            "confirm_unknown_cost": True,
            "idempotency_key": f"c{i}",
        }
        ids.append((await http.post("/v1/generations", json=body)).json()["id"])
        async with app.state.sessions() as s:  # terminada: no ocupa cupo de trabajos activos
            await s.execute(
                update(Job).where(Job.id == ids[-1]).values(status="completed", version=Job.version + 1)
            )
            await s.commit()
    # Dos creadas en el mismo instante: el desempate por id da un orden estable entre lecturas.
    async with app.state.sessions() as s:
        same = (await s.get(Job, ids[1])).created_at
        await s.execute(update(Job).where(Job.id == ids[2]).values(created_at=same, version=Job.version + 1))
        await s.commit()
    # La ventana de la Biblioteca crece con el scroll más allá de las 100 de antes.
    whole = [
        g["id"] for g in (await http.get("/v1/generations", params={"limit": 500})).json()["generations"]
    ]
    assert sorted(whole) == sorted(ids)
    tied = sorted(ids[1:3], reverse=True)
    assert [i for i in whole if i in tied] == tied
    assert (await http.get("/v1/generations", params={"limit": 2001})).status_code == 422
