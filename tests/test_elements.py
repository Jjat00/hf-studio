"""Elementos de HF Studio: creación con 2 a 4 imágenes, validación, renovación de URLs y borrado."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select, update

from hf_studio.db import ApiClient, Element, Job, utcnow

from .test_routing import Fakes, env, tick  # noqa: F401  (fixture compartida)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def purge_after_grace(app) -> None:
    """Simula que pasó el margen de purga y corre el mantenimiento del worker."""
    async with app.state.sessions() as s:
        await s.execute(update(Element).where(Element.deleted_at.is_not(None))
                        .values(deleted_at=utcnow() - timedelta(minutes=11)))  # fmt: skip
        await s.commit()
    await app.state.worker.purge_elements()


def files(*blobs: bytes) -> list:
    return [("files", (f"{i}.png", blob, "image/png")) for i, blob in enumerate(blobs)]


async def create(http, name="hero_fox", n=2, **extra):
    data = {"name": name, "description": "a red fox with a blue scarf", **extra}
    return await http.post("/v1/elements", data=data, files=files(*[PNG, JPG, PNG, JPG][:n]))


async def test_create_list_get_and_delete_an_element(env):  # noqa: F811
    app, http, fakes = env
    r = await create(http)
    assert r.status_code == 201, r.text
    el = r.json()
    assert el["id"].startswith("el_") and el["mention"] == "@hero_fox" and len(el["images"]) == 2
    assert len(fakes.uploads) == 2  # cada imagen se sube a Higgsfield para tener URL pública
    image = await http.get(el["images"][1])
    assert image.status_code == 200 and image.content == JPG  # se detecta JPG por su firma
    assert [e["id"] for e in (await http.get("/v1/elements")).json()["elements"]] == [el["id"]]
    assert (await http.delete(f"/v1/elements/{el['id']}")).status_code == 204
    assert (await http.get(f"/v1/elements/{el['id']}")).status_code == 404
    folder = app.state.settings.storage_dir / "elements" / el["id"]
    assert folder.exists()  # la purga física espera su margen
    await purge_after_grace(app)
    assert not folder.exists()


async def test_element_rules(env):  # noqa: F811
    _, http, _ = env
    assert (await create(http, n=1)).json()["error"]["code"] == "image_count"
    r = await http.post("/v1/elements", data={"name": "x5", "description": "d"}, files=files(*[PNG] * 5))
    assert r.json()["error"]["code"] == "image_count"
    assert (await create(http, name="Bad Name")).json()["error"]["code"] == "invalid_name"
    gif = [("files", ("a.gif", b"GIF89a" + b"\x00" * 20, "image/gif"))] * 2
    r = await http.post("/v1/elements", data={"name": "anim", "description": "d"}, files=gif)
    assert r.status_code == 415  # KIE solo acepta JPG y PNG
    assert (await create(http)).status_code == 201
    assert (await create(http)).json()["error"]["code"] == "name_taken"


async def test_images_from_your_own_uploads_and_never_arbitrary_urls(env):  # noqa: F811
    _, http, _ = env
    up = (await http.post("/v1/uploads", files={"file": ("a.png", PNG, "image/png")})).json()
    data = {"name": "from_urls", "description": "d", "image_urls": [up["url"], up["url"]]}
    assert (await http.post("/v1/elements", data=data)).status_code == 201
    bad = {"name": "evil", "description": "d", "image_urls": ["https://169.254.169.254/x.png"] * 2}
    assert (await http.post("/v1/elements", data=bad)).json()["error"]["code"] == "untrusted_source"


async def test_old_urls_are_uploaded_again_before_use(env):  # noqa: F811
    app, http, fakes = env
    from hf_studio.elements import resolve

    el = (await create(http)).json()
    async with app.state.sessions() as s:
        first = await resolve(s, [el["id"], "123456"], app.state.settings.storage_dir, app.state.hf.upload)
        assert list(first) == [el["id"]] and len(fakes.uploads) == 2  # recientes: no se vuelven a subir
        await s.execute(update(Element).values(uploaded_at=utcnow() - timedelta(days=6)))
        await s.commit()
        again = await resolve(s, [el["id"]], app.state.settings.storage_dir, app.state.hf.upload)
    assert len(fakes.uploads) == 4 and again[el["id"]]["image_urls"] != first[el["id"]]["image_urls"]
    assert fakes.uploads[2] == PNG  # desde la copia local


I2V = "kling-video/v3.0/std/image-to-video"
T2V = "kling-video/v3.0/std/text-to-video"


def kling(el_id: str, image: bool = True) -> dict:
    data = {"prompt": "@hero_fox runs through the snow", "duration": 5, "elements": [el_id]}
    return {**data, "image_url": "https://cdn.test/first.png"} if image else data


async def test_an_element_goes_inline_to_apimart_and_kie_never_to_higgsfield(env):  # noqa: F811
    app, http, fakes = env
    el = (await create(http)).json()
    body = (await http.post("/v1/estimate", json={"model": I2V, "input": kling(el["id"])})).json()
    assert {o["provider"] for o in body["options"]} == {"apimart", "kie"}
    assert any(
        e["provider"] == "higgsfield" and "HF Studio elements" in e["reason"] for e in body["excluded"]
    )
    job = (
        await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "max_usd": 5})
    ).json()
    await tick(app)
    provider = job["provider"]
    sent = fakes.sent[provider][0]
    payload = sent if provider == "apimart" else sent["input"]
    key = "element_list" if provider == "apimart" else "kling_elements"
    urls = ["https://cdn.test/up-0.png", "https://cdn.test/up-1.png"]
    assert payload[key] == [{"name": "hero_fox", "description": "a red fox with a blue scarf",
                             "element_input_urls": urls}]  # fmt: skip
    assert "elements" not in payload


async def test_kie_takes_elements_only_with_a_first_frame(env):  # noqa: F811
    _, http, _ = env
    el = (await create(http)).json()
    body = (
        await http.post("/v1/estimate", json={"model": T2V, "input": kling(el["id"], image=False)})
    ).json()
    assert [o["provider"] for o in body["options"]] == ["apimart"]
    assert any(e["provider"] == "kie" and "first frame" in e["reason"] for e in body["excluded"])


async def test_elements_are_resolved_by_the_server_only(env):  # noqa: F811
    _, http, _ = env
    r = await http.post("/v1/estimate", json={"model": I2V, "input": kling("el_000000000000")})
    assert r.status_code == 404 and r.json()["error"]["code"] == "element_not_found"
    forged = {
        "el_000000000000": {"name": "x", "description": "x", "image_urls": ["https://evil.test/a.png"] * 2}
    }
    r = await http.post("/v1/estimate", json={"model": I2V, "input": kling("el_000000000000"),
                                              "hints": {"elements": forged}})  # fmt: skip
    assert r.status_code in (404, 422)  # unas pistas del cliente no crean elementos


async def test_higgsfield_element_ids_stay_on_higgsfield(env):  # noqa: F811
    _, http, _ = env
    body = (await http.post("/v1/estimate", json={"model": I2V, "input": kling("123456")})).json()
    assert [o["provider"] for o in body["options"]] == ["higgsfield"]


# --- Revisión 43 ------------------------------------------------------------------------------------


async def test_a_queued_job_sends_the_renewed_urls(env):  # noqa: F811
    """Las URLs se resuelven desde la base al enviar, no desde un snapshot del plan."""
    app, http, fakes = env
    el = (await create(http)).json()
    job = (await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "provider": "apimart",
                                                    "max_usd": 5})).json()  # fmt: skip
    async with app.state.sessions() as s:
        await s.execute(update(Element).values(uploaded_at=utcnow() - timedelta(days=6)))
        await s.commit()
    await tick(app)
    assert fakes.sent["apimart"][0]["element_list"][0]["element_input_urls"] == [
        "https://cdn.test/up-2.png",
        "https://cdn.test/up-3.png",
    ]
    assert job["provider"] == "apimart"


async def test_deleting_an_element_keeps_running_jobs_and_idempotent_retries(env):  # noqa: F811
    app, http, fakes = env
    el = (await create(http)).json()
    body = {"model": I2V, "input": kling(el["id"]), "provider": "apimart", "max_usd": 5}
    headers = {"Idempotency-Key": "element-43"}
    first = await http.post("/v1/generations", json=body, headers=headers)
    assert first.status_code == 202
    assert (await http.delete(f"/v1/elements/{el['id']}")).status_code == 204
    assert (await http.get("/v1/elements")).json()["elements"] == []  # ya no se ofrece
    again = await http.post("/v1/generations", json=body, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    fresh = await http.post("/v1/generations", json=body)
    assert fresh.json()["error"]["code"] == "element_not_found"  # una petición nueva no puede usarlo
    taken = await create(http)
    assert taken.status_code == 409 and "still uses it" in taken.json()["error"]["message"]
    await purge_after_grace(app)  # pasado el margen sigue: el trabajo está activo
    folder = app.state.settings.storage_dir / "elements" / el["id"]
    assert folder.exists()  # el trabajo activo aún necesita sus imágenes
    await tick(app)
    assert fakes.sent["apimart"][0]["element_list"][0]["name"] == "hero_fox"
    fakes.apimart_task = "completed"
    await tick(app)
    await purge_after_grace(app)
    assert not folder.exists()  # terminado el trabajo, se borra del todo
    assert (await create(http)).status_code == 201  # y el nombre vuelve a estar libre


async def test_kie_counts_each_mention_as_37_characters(env):  # noqa: F811
    _, http, _ = env
    el = (
        await http.post("/v1/elements", data={"name": "aa", "description": "d"}, files=files(PNG, JPG))
    ).json()

    def shots(prompt: str) -> dict:
        return {
            **kling(el["id"]),
            "prompt": "",
            "multi_shots": True,
            "multi_prompt": [{"prompt": prompt, "duration": 5}],
        }

    ok = (await http.post("/v1/estimate", json={"model": I2V, "input": shots("x" * 459 + " @aa")})).json()
    assert "kie" in [o["provider"] for o in ok["options"]]  # 460 + 37 = 497
    long = (await http.post("/v1/estimate", json={"model": I2V, "input": shots("x" * 490 + " @aa")})).json()
    assert "kie" not in [o["provider"] for o in long["options"]]  # 491 + 37 = 528
    assert any(e["provider"] == "kie" and "37" in e["reason"] for e in long["excluded"])
    prefix = (
        await http.post("/v1/estimate", json={"model": I2V, "input": shots("x" * 480 + " @aab")})
    ).json()
    assert "kie" in [o["provider"] for o in prefix["options"]]  # @aab no es una mención de @aa


async def test_simultaneous_names_get_a_409_and_blank_descriptions_a_422(env):  # noqa: F811
    app, http, _ = env
    original = app.state.hf.upload

    async def racing_upload(data, content_type):
        # Mientras se sube, otra petición crea el mismo nombre (ya pasó la comprobación previa).
        async with app.state.sessions() as s:
            if not await s.get(Element, "el_rival000000"):
                s.add(Element(id="el_rival000000", name="hero_fox", description="d", images=[],
                              created_by=(await s.scalar(select(ApiClient.id)))))  # fmt: skip
                await s.commit()
        return await original(data, content_type)

    app.state.hf.upload = racing_upload
    r = await create(http)
    app.state.hf.upload = original
    assert r.status_code == 409 and r.json()["error"]["code"] == "name_taken"
    blank = await http.post(
        "/v1/elements", data={"name": "blank", "description": "   "}, files=files(PNG, JPG)
    )
    assert blank.status_code == 422


# --- Revisión 44 ------------------------------------------------------------------------------------


async def test_a_deletion_during_the_quote_never_leaves_an_orphan_job(env):  # noqa: F811
    """Borrar el elemento mientras se cotiza (aquí, durante la renovación de sus imágenes) da 404, no un
    trabajo que apunte a un elemento que se purgará."""
    app, http, _ = env
    el = (await create(http)).json()
    async with app.state.sessions() as s:
        await s.execute(update(Element).values(uploaded_at=utcnow() - timedelta(days=6)))
        await s.commit()
    original = app.state.hf.upload

    async def deleting_upload(data, content_type):
        async with app.state.sessions() as s:
            await s.execute(update(Element).values(deleted_at=utcnow()))
            await s.commit()
        return await original(data, content_type)

    app.state.hf.upload = deleting_upload
    r = await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "max_usd": 5})
    app.state.hf.upload = original
    assert r.status_code == 404 and r.json()["error"]["code"] == "element_not_found"
    async with app.state.sessions() as s:
        assert (await s.scalar(select(func.count()).select_from(Job))) == 0


async def test_a_failed_image_refresh_retries_instead_of_getting_stuck(env):  # noqa: F811
    app, http, fakes = env
    el = (await create(http)).json()
    job = (await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "provider": "apimart",
                                                    "max_usd": 5})).json()  # fmt: skip
    async with app.state.sessions() as s:
        await s.execute(update(Element).values(uploaded_at=utcnow() - timedelta(days=6)))
        await s.commit()
    fakes.upload_down = True
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "pending" and state["error_kind"] == "preparing"
    assert fakes.sent["apimart"] == []  # no hubo POST de generación: nada ambiguo
    fakes.upload_down = False
    await tick(app)
    assert len(fakes.sent["apimart"]) == 1
    sent = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert sent["status"] != "pending" and sent["error"] is None


async def test_a_job_whose_element_vanished_fails_cleanly(env):  # noqa: F811
    app, http, fakes = env
    el = (await create(http)).json()
    job = (await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "provider": "apimart",
                                                    "max_usd": 5})).json()  # fmt: skip
    async with app.state.sessions() as s:  # caso que la purga ya no permite: la fila desapareció
        await s.execute(delete(Element))
        await s.commit()
    await tick(app)
    state = (await http.get(f"/v1/generations/{job['id']}")).json()
    assert state["status"] == "failed" and state["error_kind"] == "element_missing"
    assert fakes.sent["apimart"] == []


async def test_canceling_while_preparing_drops_the_retry_notice(env):  # noqa: F811
    """Revisión 45: un trabajo cancelado no anuncia reintentos."""
    app, http, fakes = env
    el = (await create(http)).json()
    job = (await http.post("/v1/generations", json={"model": I2V, "input": kling(el["id"]), "provider": "apimart",
                                                    "max_usd": 5})).json()  # fmt: skip
    async with app.state.sessions() as s:
        await s.execute(update(Element).values(uploaded_at=utcnow() - timedelta(days=6)))
        await s.commit()
    fakes.upload_down = True
    await tick(app)
    canceled = (await http.post(f"/v1/generations/{job['id']}/cancel")).json()
    assert canceled["status"] == "canceled" and canceled["terminal"]
    assert canceled["error"] is None and canceled["error_kind"] is None
