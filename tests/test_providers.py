"""Adaptadores de APIMart y KIE contra servidores falsos (httpx.MockTransport): no gastan créditos.

Las respuestas imitan las reales comprobadas el 2026-10-03 (KIE responde HTTP 200 con el error en
`code`; APIMart rechaza todo con 402 si el saldo es menor de 0,05 USD)."""

from __future__ import annotations

import json

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
     (400, "nsfw_content_detected", "moderation"), (429, "too many requests", "concurrency"),
     (503, "upstream unavailable", "unavailable")],
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
