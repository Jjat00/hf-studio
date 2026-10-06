"""Corridas de Spaces en el servidor: orden, entradas encadenadas, tope aprobado, pausas y cancelación."""

from __future__ import annotations

import asyncio

from sqlalchemy import select, update

from hf_studio.db import Job, SpaceRun
from hf_studio.space_runs import ports, run_scope

from .test_routing import T2V, VIDEO, Fakes, env  # noqa: F401  (fixture compartida)

SOUL = "higgsfield-ai/soul/v2/standard"
I2V = "kling-video/v3.0/std/image-to-video"
SETTINGS = {k: v for k, v in VIDEO.items() if k != "prompt"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def node(id_, type_="text", **data):
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "data": data}


def edge(id_, source, target, handle):
    return {"id": id_, "source": source, "target": target, "sourceHandle": "out", "targetHandle": handle}


def gen(id_, model=T2V, **values):
    return node(id_, "generator", model=model, values=values, runs=[])


async def make_space(http, nodes, edges=()):
    space = (await http.post("/v1/spaces", json={"graph": {"nodes": nodes, "edges": list(edges)}})).json()
    return space["id"], space["version"]


async def tick(app, run_id):
    return await app.state.space_runner.tick(run_id)


async def finish(app, job_id, image=False):
    """Marca un trabajo como terminado (con una copia local de imagen si `image`)."""
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
        job.status = "completed"
        if image:
            job.outputs = [{"kind": "image", "url": "https://cdn.test/old.png"}]
            job.files = [
                {
                    "name": "0-image.png",
                    "kind": "image",
                    "size": len(PNG),
                    "content_type": "image/png",
                    "index": 0,
                }
            ]
            folder = app.state.settings.storage_dir / "outputs" / job.id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "0-image.png").write_bytes(PNG)
        await s.commit()


async def run_state(app, run_id) -> SpaceRun:
    async with app.state.sessions() as s:
        return await s.get(SpaceRun, run_id)


def test_ports_follow_the_ui_rules():
    from hf_studio.catalog import get_catalog

    schema = get_catalog().get(I2V)["input_schema"]
    keys = {p.key: (p.kind, p.multiple, p.required) for p in ports(schema)}
    assert keys["image_url"] == ("image", False, True) and keys["prompt"][0] == "text"


def test_scope_is_the_start_and_what_depends_on_it():
    graph = {
        "nodes": [gen("a"), gen("b"), gen("c"), node("t")],
        "edges": [edge("e1", "a", "b", "image_url"), edge("e2", "t", "c", "prompt")],
    }
    assert run_scope(graph, "downstream", "a") == ["a", "b"]
    assert sorted(run_scope(graph, "workflow", None)) == ["a", "b", "c"]


async def test_dry_run_then_budget_pause_and_approval(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(
        http,
        [
            node("t", text=VIDEO["prompt"]),
            gen("g1", **SETTINGS),
            gen("g2", prompt="A kite at dawn", **SETTINGS),
        ],
        [edge("e1", "t", "g1", "prompt")],
    )
    dry = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "dry_run": True}
        )
    ).json()
    assert (
        [s["usd"] for s in dry["steps"]] == [0.71, 0.71] and dry["total_usd"] == 1.42 and dry["pending"] == 0
    )
    assert (
        await http.post(f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version})
    ).status_code == 422
    stale = await http.post(
        f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version + 1, "max_total_usd": 2}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "space_changed"

    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1.0}
        )
    ).json()
    second = await http.post(
        f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1.0}
    )
    assert second.status_code == 409 and second.json()["error"]["code"] == "run_active"

    assert await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert state.nodes["g1"]["status"] == "running" and state.committed_usd == 0.71
    assert state.status == "awaiting_approval" and state.pause["reason"] == "over_budget"
    assert state.pause["needed_total_usd"] == 1.42
    async with app.state.sessions() as s:
        job = await s.get(Job, state.nodes["g1"]["job_id"])
    assert (
        job.input["prompt"] == VIDEO["prompt"] and job.max_usd == 0.71
    )  # el texto conectado llega al prompt

    low = await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"max_total_usd": 1.2})
    assert low.status_code == 422
    ok = await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"max_total_usd": 1.42})
    assert ok.status_code == 200 and ok.json()["status"] == "running"
    await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert state.nodes["g2"]["status"] == "running" and state.committed_usd == 1.42
    for n in ("g1", "g2"):
        await finish(app, state.nodes[n]["job_id"])
    assert not await tick(app, run["id"])
    assert (await run_state(app, run["id"])).status == "completed"


async def test_a_step_waits_for_its_source_and_uses_its_output(env):  # noqa: F811
    app, http, fakes = env
    space_id, version = await make_space(
        http,
        [gen("img", SOUL, prompt="a red fox"), gen("vid", I2V, prompt="the fox runs")],
        [edge("e1", "img", "vid", "image_url")],
    )
    dry = (
        await http.post(
            f"/v1/spaces/{space_id}/runs",
            json={"mode": "downstream", "node_id": "img", "version": version, "dry_run": True},
        )
    ).json()
    assert [s["status"] for s in dry["steps"]] == [
        "ok",
        "later",
    ]  # el video se cotiza cuando exista la imagen
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs",
            json={"mode": "downstream", "node_id": "img", "version": version, "max_total_usd": 10},
        )
    ).json()
    await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert state.nodes["img"]["status"] == "running" and state.nodes["vid"]["status"] == "pending"
    await tick(app, run["id"])  # sin terminar la imagen, el video no empieza
    assert (await run_state(app, run["id"])).nodes["vid"]["status"] == "pending"
    await finish(app, state.nodes["img"]["job_id"], image=True)
    await tick(app, run["id"])
    state = await run_state(app, run["id"])
    if state.status == "awaiting_approval":  # sin precio conocido para este modelo en los fixtures
        assert state.pause["reason"] == "unknown_cost" and state.pause["node"] == "vid"
        bad = await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={})
        assert bad.status_code == 422
        await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"accept_unknown": True})
        await tick(app, run["id"])
        state = await run_state(app, run["id"])
    assert state.nodes["vid"]["status"] == "running"
    async with app.state.sessions() as s:
        job = await s.get(Job, state.nodes["vid"]["job_id"])
    assert job.input["image_url"].startswith("https://cdn.test/up-") and fakes.uploads == [PNG]


async def test_a_failed_step_skips_what_depends_on_it(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(
        http,
        [gen("img", SOUL, prompt="a red fox"), gen("vid", I2V, prompt="the fox runs")],
        [edge("e1", "img", "vid", "image_url")],
    )
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 10}
        )
    ).json()
    await tick(app, run["id"])
    job_id = (await run_state(app, run["id"])).nodes["img"]["job_id"]
    async with app.state.sessions() as s:
        await s.execute(
            update(Job).where(Job.id == job_id).values(status="failed", error="boom", version=Job.version + 1)
        )
        await s.commit()
    assert not await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert (
        state.status == "failed"
        and state.nodes["img"]["error"] == "boom"
        and state.nodes["vid"]["status"] == "skipped"
    )


async def test_a_retried_step_does_not_create_a_second_generation(env):  # noqa: F811
    """Si guardar el estado de la corrida falla tras crear el trabajo, el siguiente paso reutiliza la clave."""
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1}
        )
    ).json()
    await tick(app, run["id"])
    first = (await run_state(app, run["id"])).nodes["g1"]["job_id"]
    async with app.state.sessions() as s:
        r = await s.get(SpaceRun, run["id"])
        r.nodes = {"g1": {"status": "pending"}}
        r.committed_usd = 0
        await s.commit()
    await tick(app, run["id"])
    assert (await run_state(app, run["id"])).nodes["g1"]["job_id"] == first
    async with app.state.sessions() as s:
        assert len((await s.scalars(select(Job))).all()) == 1


async def test_cancel_keeps_what_finished_and_cancels_the_local_queue(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(
        http, [gen("g1", prompt="a kite", **SETTINGS), gen("g2", prompt="a boat", **SETTINGS)]
    )
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs",
            json={"mode": "workflow", "version": version, "max_total_usd": 0.71},
        )
    ).json()
    await tick(app, run["id"])  # g1 enviado, g2 en pausa por tope
    res = (await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/cancel")).json()
    assert res["status"] == "canceled" and res["nodes"]["g2"]["status"] == "canceled"
    async with app.state.sessions() as s:
        assert (
            await s.get(Job, res["nodes"]["g1"]["job_id"])
        ).status == "canceled"  # seguía en la cola local
    assert (await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/cancel")).status_code == 409
    assert not await tick(app, run["id"])
    again = await http.post(
        f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1}
    )
    assert again.status_code == 201  # ya no hay corrida activa


async def test_runs_are_private_and_go_away_with_their_space(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1}
        )
    ).json()
    assert (await http.get(f"/v1/spaces/{space_id}/runs")).json()["runs"][0]["id"] == run["id"]
    assert (await http.get(f"/v1/spaces/other/runs/{run['id']}")).status_code == 404
    assert (await http.delete(f"/v1/spaces/{space_id}")).status_code == 204
    assert await run_state(app, run["id"]) is None


async def test_stopping_while_quoting_leaves_no_payable_generation(env):  # noqa: F811
    """Revisión 55 (H1): si Detener gana mientras se cotiza, el trabajo no llega a existir."""
    app, http, fakes = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1}
        )
    ).json()
    hooks = app.state.space_runner.hooks
    original = hooks.plan

    async def plan_then_stop(*args):
        result = await original(*args)
        assert (await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/cancel")).status_code == 200
        return result

    hooks.plan = plan_then_stop
    try:
        await tick(app, run["id"])
    finally:
        hooks.plan = original
    state = await run_state(app, run["id"])
    assert state.status == "canceled" and state.committed_usd == 0
    async with app.state.sessions() as s:
        assert (await s.scalars(select(Job))).all() == []
    await app.state.worker.tick()
    assert fakes.sent["apimart"] == []


async def test_resuming_adopts_the_existing_generation_without_requoting(env):  # noqa: F811
    """Revisión 55 (H2): el trabajo ya creado se recupera con su precio aprobado, sin volver a cotizar."""
    app, http, _ = env
    space_id, version = await make_space(
        http, [gen("g1", prompt="a kite", **SETTINGS), gen("g2", prompt="a boat", **SETTINGS)]
    )
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1.0}
        )
    ).json()
    await tick(app, run["id"])
    async with app.state.sessions() as s:  # simula un reinicio entre crear el trabajo y guardar la corrida
        r = await s.get(SpaceRun, run["id"])
        job_id = r.nodes["g1"]["job_id"]
        r.nodes, r.committed_usd, r.status, r.pause = (
            {"g1": {"status": "pending"}, "g2": {"status": "pending"}},
            0,
            "running",
            None,
        )
        await s.commit()
    hooks = app.state.space_runner.hooks
    original, quoted = hooks.plan, []

    async def spy(session, owner, model_id, arguments):
        quoted.append(arguments.get("prompt"))
        return await original(session, owner, model_id, arguments)

    hooks.plan = spy
    try:
        await tick(app, run["id"])
    finally:
        hooks.plan = original
    state = await run_state(app, run["id"])
    assert state.nodes["g1"]["job_id"] == job_id and state.nodes["g1"]["spend"] == 0.71
    assert quoted == ["a boat"]  # el primer paso no se recotiza
    assert (
        state.status == "awaiting_approval" and state.pause["needed_total_usd"] == 1.42
    )  # el tope se respeta


async def test_a_pricier_fallback_is_approved_from_the_run_against_its_budget(env):  # noqa: F811
    """Revisión 55 (H3 y H4): el respaldo más caro pausa la corrida; la aprobación suelta se rechaza."""
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1.0}
        )
    ).json()
    await tick(app, run["id"])
    job_id = (await run_state(app, run["id"])).nodes["g1"]["job_id"]
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
        assert [o["provider"] for o in job.plan][:2] == ["apimart", "kie"]
        job.status, job.plan_index = "awaiting_approval", 1  # APIMart falló sin cobrar; KIE cuesta 1.025
        await s.commit()
    await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert state.status == "awaiting_approval" and state.pause["reason"] == "job_approval"
    assert state.pause["needed_total_usd"] == 1.025
    loose = await http.post(f"/v1/generations/{job_id}/approve", json={"max_usd": 1.03})
    assert loose.status_code == 409 and loose.json()["error"]["code"] == "approve_in_run"
    low = await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"max_total_usd": 1.0})
    assert low.status_code == 422
    ok = (
        await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"max_total_usd": 1.03})
    ).json()
    assert ok["status"] == "running" and ok["committed_usd"] == 1.025
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
        assert job.status == "pending" and job.max_usd == 1.025


async def test_stop_cancels_steps_waiting_for_approval(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 1.0}
        )
    ).json()
    await tick(app, run["id"])
    job_id = (await run_state(app, run["id"])).nodes["g1"]["job_id"]
    async with app.state.sessions() as s:
        await s.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="awaiting_approval", plan_index=1, version=Job.version + 1)
        )
        await s.commit()
    assert (await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/cancel")).status_code == 200
    async with app.state.sessions() as s:
        assert (await s.get(Job, job_id)).status == "canceled"


async def test_a_run_rejects_media_that_is_not_yours(env):  # noqa: F811
    """Revisión 55 (H5): una URL de otro cliente (o desconocida) no entra en una corrida."""
    app, http, _ = env
    from hf_studio.db import ApiClient, Upload

    async with app.state.sessions() as s:
        other = ApiClient(name="otro", key_hash="z" * 64, key_prefix="hfs_z")
        s.add(other)
        await s.flush()
        s.add(
            Upload(
                owner_id=other.id,
                filename="p.png",
                content_type="image/png",
                size=1,
                url="https://cdn.test/private.png",
            )
        )
        await s.commit()
    space_id, version = await make_space(
        http,
        [node("m", "media", url="https://cdn.test/private.png", kind="image"), gen("vid", I2V, prompt="go")],
        [edge("e1", "m", "vid", "image_url")],
    )
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 10}
        )
    ).json()
    await tick(app, run["id"])
    state = await run_state(app, run["id"])
    assert state.nodes["vid"]["status"] == "failed" and "not one of your" in state.nodes["vid"]["error"]
    async with app.state.sessions() as s:
        assert (await s.scalars(select(Job))).all() == []


async def test_a_single_port_takes_the_first_connection_and_rejects_other_kinds():
    """Revisión 55 (H6): mismas reglas que el navegador."""
    import pytest

    from hf_studio.catalog import get_catalog
    from hf_studio.space_runs import NodeInputError, resolve_input

    schema = get_catalog().get(I2V)["input_schema"]
    graph = {
        "nodes": [node("a", "media", url="https://x/a.png", kind="image"), node("b", "media", url="https://x/b.png", kind="image"),
                  gen("v", I2V, prompt="go")],
        "edges": [edge("e1", "a", "v", "image_url"), edge("e2", "b", "v", "image_url")],
    }  # fmt: skip

    async def url(job_id):
        return job_id

    args = await resolve_input(graph, "v", schema, lambda m: None, lambda s: None, url)
    assert args["image_url"] == "https://x/a.png"
    graph["nodes"][1]["data"]["kind"] = "video"
    with pytest.raises(NodeInputError, match="does not carry image"):
        await resolve_input(graph, "v", schema, lambda m: None, lambda s: None, url)


async def _fallback_pause(app, http):
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    run = (
        await http.post(
            f"/v1/spaces/{space_id}/runs", json={"mode": "workflow", "version": version, "max_total_usd": 2.0}
        )
    ).json()
    await tick(app, run["id"])
    job_id = (await run_state(app, run["id"])).nodes["g1"]["job_id"]
    return space_id, run["id"], job_id


async def test_approving_a_fallback_aligns_the_job_permissions_with_the_run(env):  # noqa: F811
    """Revisión 56 (H1): una retención vieja mayor no sobrevive a la aprobación desde la corrida."""
    app, http, _ = env
    space_id, run_id, job_id = await _fallback_pause(app, http)
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
        job.status, job.plan_index, job.max_reserve_usd = "awaiting_approval", 1, 2.0  # retenía 2 USD
        r = await s.get(SpaceRun, run_id)
        r.nodes = {"g1": {**r.nodes["g1"], "reserve_usd": 2.0, "spend": 2.0}}
        r.committed_usd = 2.0
        await s.commit()
    await tick(app, run_id)
    pause = (await run_state(app, run_id)).pause
    assert pause["reason"] == "job_approval" and pause["needed_total_usd"] == 1.025
    ok = await http.post(f"/v1/spaces/{space_id}/runs/{run_id}/approve", json={"max_total_usd": 1.025})
    assert ok.status_code == 200 and ok.json()["committed_usd"] == 1.025
    async with app.state.sessions() as s:
        job = await s.get(Job, job_id)
        assert job.max_usd == 1.025 and job.max_reserve_usd is None  # el permiso baja a lo contabilizado


async def test_a_rejected_fallback_approval_publishes_the_fresh_total(env):  # noqa: F811
    """Revisión 56 (H2): si el precio cambió, la pausa muestra el total nuevo para otro clic."""
    app, http, _ = env
    space_id, run_id, job_id = await _fallback_pause(app, http)
    async with app.state.sessions() as s:
        await s.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="awaiting_approval", plan_index=1, version=Job.version + 1)
        )
        await s.commit()
    await tick(app, run_id)
    async with app.state.sessions() as s:  # la barra mostraba un total viejo
        r = await s.get(SpaceRun, run_id)
        r.pause = {**r.pause, "needed_total_usd": 0.9}
        await s.commit()
    res = await http.post(f"/v1/spaces/{space_id}/runs/{run_id}/approve", json={"max_total_usd": 0.9})
    assert res.status_code == 422 and res.json()["error"]["details"]["needed_total_usd"] == 1.025
    state = await run_state(app, run_id)
    assert state.status == "awaiting_approval" and state.pause["needed_total_usd"] == 1.025
    async with app.state.sessions() as s:
        assert (await s.get(Job, job_id)).status == "awaiting_approval"
    ok = await http.post(f"/v1/spaces/{space_id}/runs/{run_id}/approve", json={"max_total_usd": 1.025})
    assert ok.status_code == 200


async def test_the_same_idempotency_key_returns_the_same_run(env):  # noqa: F811
    """Revisión 64: repetir el arranque (respuesta perdida, misma cotización) no crea otra corrida."""
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    body = {"mode": "workflow", "version": version, "max_total_usd": 1}
    headers = {"Idempotency-Key": "quote-q_1"}
    first = await http.post(f"/v1/spaces/{space_id}/runs", json=body, headers=headers)
    assert first.status_code == 201
    await http.post(f"/v1/spaces/{space_id}/runs/{first.json()['id']}/cancel")  # ya terminó
    again = await http.post(f"/v1/spaces/{space_id}/runs", json=body, headers=headers)
    assert (
        again.status_code == 200 and again.json()["id"] == first.json()["id"] and again.json()["deduplicated"]
    )
    other = await http.post(f"/v1/spaces/{space_id}/runs", json={**body, "max_total_usd": 2}, headers=headers)
    assert other.status_code == 409 and other.json()["error"]["code"] == "idempotency_conflict"
    async with app.state.sessions() as s:
        assert len((await s.scalars(select(SpaceRun))).all()) == 1


async def test_run_identity_survives_approval_and_checks_the_version(env):  # noqa: F811
    """Revisión 65: la identidad es la petición original (con su versión y su tope), no el tope aprobado después."""
    app, http, _ = env
    space_id, version = await make_space(
        http, [gen("g1", prompt="a kite", **SETTINGS), gen("g2", prompt="a boat", **SETTINGS)]
    )
    body = {"mode": "workflow", "version": version, "max_total_usd": 0.71}
    headers = {"Idempotency-Key": "quote-q_2"}
    run = (await http.post(f"/v1/spaces/{space_id}/runs", json=body, headers=headers)).json()
    await tick(app, run["id"])  # g2 no cabe: pausa
    await http.post(f"/v1/spaces/{space_id}/runs/{run['id']}/approve", json={"max_total_usd": 1.42})
    again = await http.post(f"/v1/spaces/{space_id}/runs", json=body, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == run["id"]
    other = await http.post(
        f"/v1/spaces/{space_id}/runs", json={**body, "version": version + 1}, headers=headers
    )
    assert other.status_code == 409 and other.json()["error"]["code"] == "idempotency_conflict"


async def test_two_simultaneous_starts_with_one_key_make_one_run(env):  # noqa: F811
    app, http, _ = env
    space_id, version = await make_space(http, [gen("g1", prompt="a kite", **SETTINGS)])
    body = {"mode": "workflow", "version": version, "max_total_usd": 1}
    headers = {"Idempotency-Key": "quote-q_3"}
    a, b = await asyncio.gather(
        *[http.post(f"/v1/spaces/{space_id}/runs", json=body, headers=headers) for _ in range(2)]
    )
    assert sorted([a.status_code, b.status_code]) == [200, 201] and a.json()["id"] == b.json()["id"]
    async with app.state.sessions() as s:
        assert len((await s.scalars(select(SpaceRun))).all()) == 1


async def test_an_existing_database_gets_the_new_run_columns(tmp_path):
    """Revisión 66: una base previa (sin las columnas de idempotencia) se actualiza al arrancar; `jobs` no cambia."""
    from sqlalchemy import inspect, text

    from hf_studio.db import init_db, make_engine

    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
    await init_db(engine)
    async with engine.begin() as conn:  # así era la tabla antes de la fase 3a
        await conn.execute(text("DROP INDEX ix_space_runs_key"))
        await conn.execute(text("ALTER TABLE space_runs DROP COLUMN request_hash"))
        await conn.execute(text("ALTER TABLE space_runs DROP COLUMN idempotency_key"))
    await init_db(engine)
    async with engine.connect() as conn:
        runs = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("space_runs")})
        jobs = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("jobs")})
    await engine.dispose()
    assert {"idempotency_key", "request_hash"} <= runs and "request_hash" not in jobs
