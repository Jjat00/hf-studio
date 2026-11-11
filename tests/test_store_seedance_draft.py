"""Seedance 2.5 Draft (`store/seedance_draft.py`): borrador a 480p y final a 1080p en la misma tienda. Sin gastar."""

from __future__ import annotations

from sqlalchemy import update

from hf_studio.db import Job
from hf_studio.store import seedance_draft as sd
from tests.test_routing import env, tick  # noqa: F401  (fixture)

T2V, REF, FINAL = sd.draft_id("text-to-video"), sd.draft_id("reference-to-video"), sd.FINAL_ID


async def draft(http, app, fakes, provider: str | None = None, **extra) -> dict:
    body = {"model": T2V, "input": {"prompt": "a fox in the snow", "duration": 8, **extra}, "max_usd": 5}
    job = (
        await http.post("/v1/generations", json={**body, **({"provider": provider} if provider else {})})
    ).json()
    await tick(app)
    if provider == "kie":
        fakes.kie_task = "success"
    else:
        fakes.apimart_task = "completed"
    await tick(app)
    async with app.state.sessions() as s:  # la tienda simulada da siempre el mismo id de tarea
        await s.execute(
            update(Job).where(Job.id == job["id"]).values(hf_request_id=f"{provider or 'apimart'}-draft")
        )
        await s.commit()
    done = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert done["status"] == "completed", done
    return done


async def test_the_draft_is_seedance_25_at_480p_with_draft_on(env):  # noqa: F811
    app, http, fakes = env
    quote = (
        await http.post("/v1/estimate", json={"model": T2V, "input": {"prompt": "x", "duration": 8}})
    ).json()
    assert [o["provider"] for o in quote["options"]] == ["apimart", "kie"]  # Higgsfield no lo ofrece
    assert quote["usd"] == round(8 * 0.09608, 4)
    await draft(http, app, fakes)
    sent = fakes.sent["apimart"][0]
    assert sent["model"] == "seedance-2.5" and sent["draft"] is True and sent["resolution"] == "480p"


async def test_the_final_goes_to_the_store_that_made_the_draft(env):  # noqa: F811
    app, http, fakes = env
    done = await draft(http, app, fakes)
    quote = (
        await http.post("/v1/estimate", json={"model": FINAL, "input": {"draft_generation_id": done["id"]}})
    ).json()
    assert [o["provider"] for o in quote["options"]] == ["apimart"]
    assert quote["kind"] == "approx" and quote["usd"] == round(8 * 0.5346, 4)
    job = (await http.post("/v1/generations", json={
        "model": FINAL, "input": {"draft_generation_id": done["id"], "output_format": "mov"}, "max_usd": quote["usd"],
    })).json()  # fmt: skip
    await tick(app)
    assert job["provider"] == "apimart"
    assert fakes.sent["apimart"][-1] == {
        "model": "seedance-2.5",
        "draft_task_id": "apimart-draft",
        "output_format": "mov",
    }


async def test_a_kie_draft_is_finished_on_kie(env):  # noqa: F811
    app, http, fakes = env
    fakes.kie_credits = 5000.0  # 25 USD: el final a 1080p cuesta más que el saldo simulado por defecto
    done = await draft(http, app, fakes, provider="kie")
    assert (
        fakes.sent["kie"][0]["input"]["draft"] is True
        and fakes.sent["kie"][0]["input"]["resolution"] == "480p"
    )
    quote = (
        await http.post("/v1/estimate", json={"model": FINAL, "input": {"draft_generation_id": done["id"]}})
    ).json()
    assert [o["provider"] for o in quote["options"]] == ["kie"]
    assert quote["usd"] == round(8 * 0.79, 4)
    await http.post("/v1/generations", json={
        "model": FINAL, "input": {"draft_generation_id": done["id"]}, "max_usd": quote["usd"],
    })  # fmt: skip
    await tick(app)
    assert fakes.sent["kie"][-1] == {
        "model": "bytedance/seedance-2-5-draft",
        "input": {"draft_task_id": "kie-draft", "resolution": "1080p", "output_format": "mp4"},
    }


async def test_only_your_finished_drafts_can_be_finished(env):  # noqa: F811
    _, http, _ = env

    async def code(generation_id: str) -> str:
        r = await http.post(
            "/v1/estimate", json={"model": FINAL, "input": {"draft_generation_id": generation_id}}
        )
        return r.json()["error"]["code"]

    assert await code("nope") == "draft_not_found"
    pending = (await http.post("/v1/generations", json={
        "model": T2V, "input": {"prompt": "x"}, "max_usd": 5,
    })).json()  # fmt: skip
    assert await code(pending["id"]) == "draft_not_ready"
    other = (await http.post("/v1/generations", json={
        "model": "bytedance/seedance-2.5/text-to-video", "input": {"prompt": "x"}, "max_usd": 5,
    })).json()  # fmt: skip
    assert await code(other["id"]) == "not_a_draft"
