"""Usar una creación propia como entrada de otra: URL vigente desde la copia local."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select, update

from hf_studio.db import ApiClient, Job, Upload, utcnow

from .test_routing import Fakes, env  # noqa: F401  (fixture compartida)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def finished_image(
    app, owner_name: str = "agente", content: bytes = PNG, content_type="image/png"
) -> str:
    async with app.state.sessions() as s:
        owner = await s.scalar(select(ApiClient).where(ApiClient.name == owner_name))
        job = Job(owner_id=owner.id, model="higgsfield-ai/soul/v2/standard", input={"prompt": "fox"},
                  input_hash="h", status="completed", webhook_token="t", outputs=[{"kind": "image",
                  "url": "https://cdn.test/old.png"}], files=[{"name": "0-image.png", "kind": "image",
                  "size": len(content), "content_type": content_type, "index": 0}], poll_delay=2.0, attempts=1)  # fmt: skip
        s.add(job)
        await s.commit()
        folder = app.state.settings.storage_dir / "outputs" / job.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "0-image.png").write_bytes(content)
        return job.id


async def test_an_output_becomes_a_fresh_trusted_input(env):  # noqa: F811
    app, http, fakes = env
    job_id = await finished_image(app)
    first = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()
    assert first["url"] == "https://cdn.test/up-0.png" and first["kind"] == "image"
    assert fakes.uploads == [PNG]  # la copia local, subida a Higgsfield
    again = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()
    assert again["url"] == first["url"] and len(fakes.uploads) == 1  # reciente: misma URL, sin resubir
    async with app.state.sessions() as s:
        await s.execute(update(Upload).values(created_at=utcnow() - timedelta(days=6)))
        await s.commit()
    renewed = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()
    assert renewed["url"] == "https://cdn.test/up-1.png"
    # La URL vale como medio propio: sirve, por ejemplo, para crear un elemento.
    data = {"name": "zorro", "description": "d", "image_urls": [renewed["url"], renewed["url"]]}
    assert (await http.post("/v1/elements", data=data)).status_code == 201


async def test_only_finished_own_outputs(env):  # noqa: F811
    app, http, _ = env
    job_id = await finished_image(app)
    assert (await http.post(f"/v1/generations/{job_id}/outputs/3/use")).status_code == 404
    async with app.state.sessions() as s:
        s.add(ApiClient(name="otro", key_hash="x" * 64, key_prefix="hfs_o"))
        await s.commit()
    other = await finished_image(app, "otro")
    assert (await http.post(f"/v1/generations/{other}/outputs/0/use")).status_code == 404  # ajeno
    fake = await finished_image(app, content=b"<?xml dash manifest", content_type="video/mp4")
    assert (await http.post(f"/v1/generations/{fake}/outputs/0/use")).status_code == 415


async def test_an_upload_named_like_the_output_cannot_replace_it(env):  # noqa: F811
    """Revisión 47: la asociación vive en `source`, no en el nombre de archivo que elige el cliente."""
    app, http, fakes = env
    job_id = await finished_image(app)
    other = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
    await http.post("/v1/uploads", files={"file": (f"generation:{job_id}:0", other, "image/png")})
    used = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()
    assert fakes.uploads[-1] == PNG and used["url"] == f"https://cdn.test/up-{len(fakes.uploads) - 1}.png"


async def test_simultaneous_requests_upload_once(env):  # noqa: F811
    app, http, fakes = env
    job_id = await finished_image(app)
    results = await asyncio.gather(*[http.post(f"/v1/generations/{job_id}/outputs/0/use") for _ in range(3)])
    assert [r.status_code for r in results] == [200, 200, 200]
    assert len({r.json()["url"] for r in results}) == 1 and fakes.uploads == [PNG]
    async with app.state.sessions() as s:
        rows = (await s.scalars(select(Upload).where(Upload.source == f"generation:{job_id}:0"))).all()
    assert len(rows) == 1


async def test_renewing_keeps_the_previous_url_trusted(env):  # noqa: F811
    """Revisión 48: la copia anterior queda como historial y su URL sigue valiendo como medio propio."""
    app, http, _ = env
    job_id = await finished_image(app)
    old = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()["url"]
    async with app.state.sessions() as s:
        await s.execute(update(Upload).values(created_at=utcnow() - timedelta(days=6)))
        await s.commit()
    new = (await http.post(f"/v1/generations/{job_id}/outputs/0/use")).json()["url"]
    assert new != old
    data = {"name": "vieja", "description": "d", "image_urls": [old, old]}
    assert (await http.post("/v1/elements", data=data)).status_code == 201
    async with app.state.sessions() as s:
        current = (await s.scalars(select(Upload).where(Upload.source == f"generation:{job_id}:0"))).all()
    assert [u.url for u in current] == [new]


async def test_losing_a_race_with_another_instance_returns_the_winner(env):  # noqa: F811
    """Otro proceso (sin candado común) registra la misma salida mientras esta sube: 200 con su URL."""
    app, http, _ = env
    job_id = await finished_image(app)
    original = app.state.hf.upload

    async def racing_upload(data, content_type):
        async with app.state.sessions() as s:
            owner = await s.scalar(select(ApiClient).where(ApiClient.name == "agente"))
            s.add(Upload(owner_id=owner.id, filename="x", content_type="image/png", size=1,
                         url="https://cdn.test/winner.png", source=f"generation:{job_id}:0"))  # fmt: skip
            await s.commit()
        return await original(data, content_type)

    app.state.hf.upload = racing_upload
    r = await http.post(f"/v1/generations/{job_id}/outputs/0/use")
    app.state.hf.upload = original
    assert r.status_code == 200 and r.json()["url"] == "https://cdn.test/winner.png"
    assert r.json()["generation_id"] == job_id
