"""Adaptadores de APIMart y KIE contra servidores falsos (httpx.MockTransport): no gastan créditos.

Las respuestas imitan las reales comprobadas el 2026-10-03 (KIE responde HTTP 200 con el error en
`code`; APIMart rechaza todo con 402 si el saldo es menor de 0,05 USD)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hf_studio.config import Settings
from hf_studio.db import Job
from hf_studio.providers import ProviderError
from hf_studio.providers.apimart import APIMartProvider
from hf_studio.providers.kie import KIEProvider
from hf_studio.providers.registry import PROVIDERS, build, configured

KEYS = {"APIMART_API_KEY": "am-key", "KIE_API_KEY": "kie-key"}


def settings(**keys) -> Settings:
    return Settings(_env_file=None, hf_api_key="kid:ksecret", provider_keys=keys)


def mock(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# --- Registro ---------------------------------------------------------------------------------


def test_registry_declares_links_and_keys():
    assert list(PROVIDERS) == ["higgsfield", "apimart", "kie"]
    for cls in PROVIDERS.values():
        assert cls.env_var and cls.key_url.startswith("https://") and cls.signup_url.startswith("https://")
    assert [name for name, cls in PROVIDERS.items() if cls.required] == ["higgsfield"]
    assert configured(settings()) == ["higgsfield"]
    assert configured(settings(**KEYS)) == ["higgsfield", "apimart", "kie"]


def test_provider_keys_ignore_dotenv_when_disabled():
    assert Settings(_env_file=None).secret("KIE_API_KEY") == ""


# --- APIMart ----------------------------------------------------------------------------------


async def test_apimart_balance_below_minimum_is_a_valid_key():
    def handler(request):
        assert request.headers["authorization"] == "Bearer am-key"
        return httpx.Response(402, json={"error": {"message": "[token_id=1] insufficient balance "
                              "(current: 0.000000 USD, required: 0.050000 USD). Please top up"}})  # fmt: skip

    provider = APIMartProvider(settings(**KEYS), mock(handler))
    check = await provider.check_key()
    assert check.valid is True and check.balance_usd == 0.0


async def test_apimart_invalid_key_and_balance():
    def handler(request):
        if request.headers["authorization"] == "Bearer bad":
            return httpx.Response(401, json={"error": {"message": "invalid API key (request id: x)"}})
        return httpx.Response(200, json={"success": True, "remain_balance": 12.5, "remain_credits": 125})

    assert (await APIMartProvider(settings(APIMART_API_KEY="bad"), mock(handler)).check_key()).valid is False
    ok = await APIMartProvider(settings(**KEYS), mock(handler)).check_key()
    assert ok.valid is True and ok.balance_usd == 12.5


async def test_apimart_submit_poll_and_outputs():
    sent = []

    def handler(request):
        if request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(
                200, json={"code": 200, "data": [{"status": "submitted", "task_id": "task_1"}]}
            )
        assert request.url.path == "/v1/tasks/task_1"
        return httpx.Response(200, json={"code": 200, "data": {
            "id": "task_1", "status": "completed", "progress": 100,
            "result": {"videos": [{"url": ["https://cdn.apimart.test/out.mp4"]}]}}})  # fmt: skip

    provider = APIMartProvider(settings(**KEYS), mock(handler))
    submitted = await provider.submit_job("seedance-2.0", {"prompt": "x", "duration": 5}, "https://hook")
    assert submitted.request_id == "task_1" and submitted.status == "queued"
    assert sent == [{"prompt": "x", "duration": 5, "model": "seedance-2.0", "webhook": "https://hook"}]
    polled = await provider.poll_job("task_1")
    assert polled.status == "completed"
    assert polled.outputs == [
        {"kind": "video", "url": "https://cdn.apimart.test/out.mp4", "content_type": None}
    ]


@pytest.mark.parametrize(
    ("status", "message", "kind"),
    [(402, "insufficient balance (current: 0.01 USD)", "credits"), (400, "duration must be 4-15", "validation"),
     (400, "nsfw_content_detected", "moderation"), (429, "too many requests", "concurrency")],
)  # fmt: skip
async def test_apimart_submit_errors_are_fallback_safe(status, message, kind):
    provider = APIMartProvider(
        settings(**KEYS), mock(lambda r: httpx.Response(status, json={"error": {"message": message}}))
    )
    with pytest.raises(ProviderError) as info:
        await provider.submit_job("seedance-2.0", {"prompt": "x"})
    assert info.value.kind == kind and info.value.fallback_safe and info.value.provider == "apimart"


async def test_apimart_timeout_is_ambiguous_and_never_fallback():
    def handler(request):
        raise httpx.ReadTimeout("no answer", request=request)

    with pytest.raises(ProviderError) as info:
        await APIMartProvider(settings(**KEYS), mock(handler)).submit_job("seedance-2.0", {"prompt": "x"})
    assert info.value.kind == "ambiguous" and not info.value.fallback_safe and not info.value.retryable


async def test_apimart_failed_task_by_moderation_is_nsfw():
    body = {"data": {"status": "failed", "error": {"code": "content_policy", "message": "sensitive content"}}}
    polled = await APIMartProvider(settings(**KEYS), mock(lambda r: httpx.Response(200, json=body))).poll_job(
        "t"
    )
    assert polled.status == "nsfw" and polled.error == "sensitive content"


# --- KIE --------------------------------------------------------------------------------------


async def test_kie_credit_balance_and_invalid_key():
    def handler(request):
        if request.headers["authorization"] == "Bearer bad":
            return httpx.Response(200, json={"code": 401, "msg": "Unauthorized"})
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": 80.0})

    ok = await KIEProvider(settings(**KEYS), mock(handler)).check_key()
    assert ok.valid is True and ok.balance_usd == 0.4
    assert (await KIEProvider(settings(KIE_API_KEY="bad"), mock(handler)).check_key()).valid is False


async def test_kie_errors_come_inside_http_200():
    def handler(request):
        return httpx.Response(
            200, json={"code": 500, "msg": "resolution is not within the range", "data": None}
        )

    with pytest.raises(ProviderError) as info:
        await KIEProvider(settings(**KEYS), mock(handler)).submit_job("bytedance/seedance-2-mini", {})
    assert info.value.kind == "validation" and info.value.fallback_safe


async def test_kie_submit_poll_success_and_failure():
    sent = []
    state = {"value": "generating"}

    def handler(request):
        if request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "k1"}})
        assert request.url.params["taskId"] == "k1"
        data = {"taskId": "k1", "state": state["value"]}
        if state["value"] == "success":
            data["resultJson"] = json.dumps({"resultUrls": ["https://tempfile.kie.test/a.mp4"]})
        if state["value"] == "fail":
            data["failMsg"] = "Upstream generation error"
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": data})

    provider = KIEProvider(settings(**KEYS), mock(handler))
    submitted = await provider.submit_job("kling-3.0/video", {"prompt": "x", "sound": False}, "https://hook")
    assert submitted.request_id == "k1"
    assert sent == [
        {"model": "kling-3.0/video", "input": {"prompt": "x", "sound": False}, "callBackUrl": "https://hook"}
    ]
    assert (await provider.poll_job("k1")).status == "in_progress"
    state["value"] = "success"
    done = await provider.poll_job("k1")
    assert done.status == "completed" and done.outputs[0]["url"] == "https://tempfile.kie.test/a.mp4"
    state["value"] = "fail"
    failed = await provider.poll_job("k1")
    assert failed.status == "failed" and failed.error == "Upstream generation error"


async def test_kie_unknown_task_is_not_found():
    body = {"code": 422, "msg": "recordInfo is null", "data": None}
    with pytest.raises(ProviderError) as info:
        await KIEProvider(settings(**KEYS), mock(lambda r: httpx.Response(200, json=body))).poll_job("nope")
    assert info.value.kind == "not_found"


# --- Worker con un proveedor que no es Higgsfield -----------------------------------------------


async def test_worker_dispatches_by_job_provider(tmp_path):
    from hf_studio.db import init_db, make_engine, make_sessionmaker
    from hf_studio.worker import Worker

    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "cdn.kie.test":
            return httpx.Response(200, content=b"MP4", headers={"content-type": "video/mp4"})
        if request.method == "POST":
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "k9"}})
        data = {"state": "success", "resultJson": json.dumps({"resultUrls": ["https://cdn.kie.test/o.mp4"]})}
        return httpx.Response(200, json={"code": 200, "data": data})

    conf = Settings(_env_file=None, hf_api_key="kid:ksecret", provider_keys=KEYS,
                    database_url=f"sqlite+aiosqlite:///{tmp_path}/w.db", storage_dir=tmp_path / "f",
                    worker_enabled=False)  # fmt: skip
    engine = make_engine(conf.database_url)
    await init_db(engine)
    sessions = make_sessionmaker(engine)
    providers = build(conf, mock(handler))
    from hf_studio.db import ApiClient

    async with sessions() as s:
        owner = ApiClient(name="a", key_hash="h", key_prefix="p")
        s.add(owner)
        await s.flush()
        job = Job(owner_id=owner.id, model="kling-3.0/video", provider="kie", input={"prompt": "x"},
                  input_hash="h")  # fmt: skip
        s.add(job)
        await s.commit()
        job_id = job.id
    worker = Worker(sessions, providers, conf)
    await worker.tick()
    async with sessions() as s:
        job = await s.get(Job, job_id)
        assert job.hf_request_id == "k9" and job.status == "queued"
        job.next_check_at = None
        await worker.refresh(s, job)
        await s.commit()
        assert job.status == "completed" and job.files[0]["size"] == 3
    assert "api.higgsfield.ai" not in calls
    for provider in providers.values():
        await provider.aclose()
    await engine.dispose()


async def test_providers_route_lists_links_and_balance(tmp_path):
    from hf_studio.api import create_app
    from hf_studio.db import ApiClient, hash_token

    def handler(request):
        if request.url.host == "api.kie.ai":
            return httpx.Response(200, json={"code": 200, "data": 200})
        return httpx.Response(404, json={"detail": "not found"})  # Higgsfield: clave válida

    conf = Settings(_env_file=None, hf_api_key="kid:ksecret", provider_keys={"KIE_API_KEY": "k"},
                    database_url=f"sqlite+aiosqlite:///{tmp_path}/p.db", worker_enabled=False)  # fmt: skip
    app = create_app(conf, transport=mock(handler))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="a", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            assert (await http.get("/health")).json()["providers_configured"] == ["higgsfield", "kie"]
            items = {p["name"]: p for p in (await http.get("/v1/providers")).json()["providers"]}
    assert items["kie"]["valid"] is True and items["kie"]["balance_usd"] == 1.0
    assert items["higgsfield"]["valid"] is True and items["higgsfield"]["required"] is True
    assert items["apimart"]["configured"] is False and "valid" not in items["apimart"]
    assert items["apimart"]["key_url"] == "https://apimart.ai/keys"


async def test_duration_is_measured_locally_without_network(tmp_path):
    """Un MPD que pasara como medio propio no llega a ffprobe, y ffprobe solo lee el archivo local."""
    from hf_studio.media import local_duration

    mpd = b'<?xml version="1.0"?><MPD><BaseURL>https://127.0.0.1/internal.mp4</BaseURL></MPD>'
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=mpd)

    async with httpx.AsyncClient(transport=mock(handler)) as client:
        assert await local_duration("https://cdn.test/uploaded.mp4", client, 10_000) is None
        assert await local_duration("http://cdn.test/plain.mp4", client, 10_000) is None
    assert requested == ["https://cdn.test/uploaded.mp4"]


async def test_remote_sources_are_copied_locally_only_if_they_are_media(tmp_path):
    """Revisión 29: voz, aislamiento y conservar audio ya no pasan URLs a ffmpeg."""
    from hf_studio.media import cached_source

    mpd = b'<?xml version="1.0"?><MPD><BaseURL>https://127.0.0.1/internal.mp4</BaseURL></MPD>'
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
    bodies = {"/old.mp4": mpd, "/ok.mp4": mp4}

    async with httpx.AsyncClient(
        transport=mock(lambda r: httpx.Response(200, content=bodies[r.url.path]))
    ) as c:
        assert await cached_source("https://cdn.test/old.mp4", tmp_path, c, 10_000) is None
        local = await cached_source("https://cdn.test/ok.mp4", tmp_path, c, 10_000)
    assert local and Path(local).read_bytes() == mp4 and "://" not in local


def test_every_ffmpeg_input_is_guarded():
    from hf_studio.voice import VoiceChangeIn, mix_command

    body = VoiceChangeIn(source_url="https://cdn.test/v.mp4", voice_id="v")
    cmd = mix_command("/tmp/src.mp4", Path("/tmp/voice.mp3"), Path("/tmp/out.mp4"), 1.0, 2.0, body, 1.0, 3.0)
    assert cmd.count("-i") == 2 and cmd.count("-protocol_whitelist") == 2
    assert all(
        cmd[i - 1] != "file" or cmd[i - 2] == "-protocol_whitelist" for i, a in enumerate(cmd) if a == "-i"
    )


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503, text="Service Unavailable"), httpx.Response(200, text="<html>oops</html>"),
     httpx.Response(200, json={"code": 200, "data": ["broken"]}), httpx.Response(200, json=[])],
)  # fmt: skip
async def test_unclear_submissions_are_ambiguous_on_every_provider(response):
    """Revisión 29: 503 genérico y cuerpos malformados tras el POST pudieron crear la tarea."""
    from hf_studio.higgsfield import HiggsfieldClient

    for cls in (APIMartProvider, KIEProvider, HiggsfieldClient):
        provider = cls(settings(**KEYS), mock(lambda r: response))
        with pytest.raises(ProviderError) as info:
            await provider.submit_job("m", {"prompt": "x"})
        assert info.value.kind == "ambiguous", (cls.name, info.value.kind, info.value.message)
        assert not info.value.fallback_safe and not info.value.retryable


async def test_concurrent_downloads_of_the_same_source_do_not_clash(tmp_path):
    """Revisión 30: dos descargas simultáneas de la misma URL usan temporales distintos."""
    import asyncio

    from hf_studio.media import cached_source

    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
    both_open = asyncio.Event()
    opened = 0

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal opened
            opened += 1
            if opened == 2:
                both_open.set()
            await both_open.wait()
            yield mp4

    async def handler(request):
        return httpx.Response(200, stream=Slow())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await asyncio.gather(
            *(cached_source("https://cdn.test/same.mp4", tmp_path, client, 10_000) for _ in range(2)),
            return_exceptions=True,
        )
    assert all(isinstance(r, str) and Path(r).read_bytes() == mp4 for r in results), results
    assert not list((tmp_path / "sources").glob("*.part"))
