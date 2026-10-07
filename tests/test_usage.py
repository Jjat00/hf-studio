"""Página de uso: suma el costo cotizado de las generaciones terminadas por día, proveedor y modelo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from hf_studio.db import ApiClient, Job, utcnow
from hf_studio.usage import UsageRow, summarize

from .test_api import env  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC).replace(tzinfo=None)  # UTC ingenuo, como la base


def test_summarize_groups_and_fills_empty_days():
    rows = [
        UsageRow("pixverse/v6/image-to-video", "apimart", 0.064, "exact", NOW - timedelta(hours=1)),
        UsageRow("pixverse/v6/image-to-video", "apimart", 0.064, "exact", NOW - timedelta(days=2)),
        UsageRow("marketing-studio/image/flare", "higgsfield", 0.048, "approx", NOW),
        UsageRow("elevenlabs/music", "elevenlabs", None, None, NOW),
    ]
    out = summarize(rows, NOW - timedelta(days=3), NOW)
    assert out["total_usd"] == 0.176
    assert out["approx_usd"] == 0.048
    assert (out["generations"], out["unpriced"]) == (4, 1)
    assert [(p["provider"], p["usd"], p["generations"]) for p in out["providers"]] == [
        ("apimart", 0.128, 2),
        ("higgsfield", 0.048, 1),
        ("elevenlabs", 0.0, 1),
    ]
    assert out["models"][0] == {
        "model": "pixverse/v6/image-to-video", "provider": "apimart", "usd": 0.128, "generations": 2, "unpriced": 0,
    }  # fmt: skip
    # Cuatro días seguidos, con el vacío en cero: la gráfica no salta huecos.
    assert [(d["date"], d["usd"]) for d in out["days"]] == [
        ("2026-10-04", 0.0),
        ("2026-10-05", 0.064),
        ("2026-10-06", 0.0),
        ("2026-10-07", 0.112),
    ]


def test_summarize_buckets_by_local_day():
    """Las 02:00 UTC del 8 son aún el 7 en Bogotá (UTC-5)."""
    late = datetime(2026, 10, 8, 2, 0, tzinfo=UTC).replace(tzinfo=None)
    out = summarize([UsageRow("m", "kie", 0.1, "exact", late)], None, late, utc_offset_minutes=-300)
    assert out["days"] == [{"date": "2026-10-07", "usd": 0.1}]


def _job(owner_id: str, model: str, provider: str, usd: float | None, status: str = "completed", **kw) -> Job:
    plan = [{"provider": provider, "model": model, "usd": usd, "kind": "exact"}] if usd is not None else []
    return Job(owner_id=owner_id, model=model, input={}, input_hash="h", provider=provider, plan=plan,
               status=status, **kw)  # fmt: skip


async def test_usage_counts_only_finished_jobs_of_the_owner(env):  # noqa: F811
    app, http, _ = env
    async with app.state.sessions() as s:
        mine = await s.scalar(select(ApiClient.id).where(ApiClient.name == "agente"))
        other = await s.scalar(select(ApiClient.id).where(ApiClient.name == "otro"))
        s.add_all([
            _job(mine, "pixverse/v6/image-to-video", "apimart", 0.064),
            # Plan con respaldo: cuenta la opción que corrió, no la primera.
            Job(owner_id=mine, model="kling-video/v3.0/std/image-to-video", input={}, input_hash="h",
                provider="higgsfield", status="completed", plan_index=1,
                plan=[{"provider": "apimart", "usd": 0.2}, {"provider": "higgsfield", "usd": 0.215}]),
            _job(mine, "elevenlabs/music", "higgsfield", None),  # audio sin precio guardado
            _job(mine, "pixverse/v6/image-to-video", "apimart", 0.064, status="failed"),
            _job(mine, "pixverse/v6/image-to-video", "apimart", 9.0, created_at=utcnow() - timedelta(days=40)),
            _job(other, "pixverse/v6/image-to-video", "apimart", 5.0),
        ])  # fmt: skip
        await s.commit()

    body = (await http.get("/v1/usage", params={"days": 30})).json()
    assert body["total_usd"] == 0.279
    assert (body["generations"], body["unpriced"]) == (3, 1)
    assert {p["provider"]: p["usd"] for p in body["providers"]} == {
        "higgsfield": 0.215,
        "apimart": 0.064,
        "elevenlabs": 0.0,
    }
    assert len(body["days"]) == 30

    everything = (await http.get("/v1/usage", params={"days": 0})).json()
    assert everything["total_usd"] == 9.279

    # Un cliente que ve todo (la UI) suma también lo de los demás.
    async with app.state.sessions() as s:
        await s.execute(update(ApiClient).where(ApiClient.name == "otro").values(sees_all=True))
        await s.commit()
    ui = (await http.get("/v1/usage", params={"days": 30}, headers={"Authorization": "Bearer hfs_b"})).json()
    assert ui["total_usd"] == 5.279
