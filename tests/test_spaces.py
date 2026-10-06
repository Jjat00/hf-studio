"""Spaces: lienzos de nodos guardados por cliente, con grafo validado y guardado con versión."""

from __future__ import annotations

import pytest

from hf_studio.db import ApiClient, Job, Space
from hf_studio.spaces import GraphError, check_graph

from .test_reuse import finished_image
from .test_routing import Fakes, env  # noqa: F401  (fixture compartida)


def node(id_, type_="text", **data):
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "data": data}


def edge(id_, source, target, handle="prompt"):
    return {"id": id_, "source": source, "target": target, "sourceHandle": "out", "targetHandle": handle}


GEN = {"model": "higgsfield-ai/soul/v2/standard", "values": {}, "runs": []}


def test_graph_is_normalized_and_view_state_dropped():
    raw = {
        "nodes": [{**node("t1", text="un zorro"), "selected": True, "measured": {"width": 1}}],
        "edges": [],
        "viewport": {"x": 10, "y": 5, "zoom": 0.6},
    }
    clean = check_graph(raw)
    assert clean["nodes"] == [
        {"id": "t1", "type": "text", "position": {"x": 0, "y": 0}, "data": {"text": "un zorro"}}
    ]
    assert clean["viewport"] == {"x": 10, "y": 5, "zoom": 0.6}


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        ({"nodes": [node("a"), node("a")]}, "unique"),
        ({"nodes": [node("a")], "edges": [edge("e", "a", "missing")]}, "does not exist"),
        ({"nodes": [node("a")], "edges": [edge("e", "a", "a")]}, "itself"),
        (
            {
                "nodes": [node("a", "generator", **GEN), node("b", "generator", **GEN)],
                "edges": [edge("e1", "a", "b", "image_url"), edge("e2", "b", "a", "image_url")],
            },
            "loop",
        ),
        ({"nodes": [node("a", "generator", values={})]}, "needs a model"),
        ({"nodes": [node("a", "media", kind="pdf")]}, "kind"),
        ({"nodes": [node("a", "shader")]}, "Invalid graph"),
        ({"nodes": [node("a")], "edges": [edge("e", "a", "a", "Bad Handle")]}, "Invalid graph"),
    ],
)
def test_invalid_graphs_are_rejected(graph, message):
    with pytest.raises(GraphError, match=message):
        check_graph(graph)


def test_graph_size_is_capped():
    huge = {"nodes": [node(f"n{i}", text="x" * 4000) for i in range(200)]}
    with pytest.raises(GraphError, match="too large"):
        check_graph(huge)


async def test_space_lifecycle(env):  # noqa: F811
    _, http, _ = env
    created = await http.post("/v1/spaces", json={"title": "Spot"})
    assert created.status_code == 201
    space = created.json()
    assert space["title"] == "Spot" and space["version"] == 1 and space["graph"]["nodes"] == []

    graph = {
        "nodes": [node("t1", text="un zorro"), node("g1", "generator", **GEN)],
        "edges": [edge("e1", "t1", "g1")],
    }
    saved = await http.put(
        f"/v1/spaces/{space['id']}", json={"version": 1, "graph": graph, "title": "Spot 2"}
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["version"] == 2 and body["title"] == "Spot 2" and len(body["graph"]["edges"]) == 1

    listed = (await http.get("/v1/spaces")).json()["spaces"]
    assert [(s["id"], s["nodes"]) for s in listed] == [(space["id"], 2)]
    assert "graph" not in listed[0]  # la lista es liviana

    assert (await http.delete(f"/v1/spaces/{space['id']}")).status_code == 204
    assert (await http.get(f"/v1/spaces/{space['id']}")).status_code == 404


async def test_a_stale_version_does_not_overwrite(env):  # noqa: F811
    _, http, _ = env
    space = (await http.post("/v1/spaces", json={})).json()
    first = await http.put(f"/v1/spaces/{space['id']}", json={"version": 1, "title": "A"})
    assert first.status_code == 200
    stale = await http.put(f"/v1/spaces/{space['id']}", json={"version": 1, "title": "B"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert (await http.get(f"/v1/spaces/{space['id']}")).json()["title"] == "A"


async def test_invalid_graph_and_cover_are_422(env):  # noqa: F811
    app, http, _ = env
    space = (await http.post("/v1/spaces", json={})).json()
    bad = await http.put(
        f"/v1/spaces/{space['id']}", json={"version": 1, "graph": {"nodes": [node("a"), node("a")]}}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_graph"
    for cover in ("https://evil.test/x.png", "/v1/generations/nonexistent/files/ghost.png"):
        res = await http.put(f"/v1/spaces/{space['id']}", json={"version": 1, "cover": cover})
        assert res.status_code == 422, cover
    image = await finished_image(app)
    video = await finished_image(app, content=b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")
    async with app.state.sessions() as s:
        job = await s.get(Job, video)
        job.files = [{**job.files[0], "kind": "video"}]
        await s.commit()
    as_video = await http.put(
        f"/v1/spaces/{space['id']}",
        json={"version": 1, "cover": f"/v1/generations/{video}/files/0-image.png"},
    )
    assert as_video.status_code == 422
    path = f"/v1/generations/{image}/files/0-image.png"
    ok = await http.put(f"/v1/spaces/{space['id']}", json={"version": 1, "cover": path})
    assert ok.status_code == 200 and ok.json()["cover"] == path
    cleared = await http.put(f"/v1/spaces/{space['id']}", json={"version": 2, "cover": None})
    assert cleared.status_code == 200 and cleared.json()["cover"] is None


def test_generator_data_is_normalized_for_the_ui():
    clean = check_graph({"nodes": [node("g", "generator", model="higgsfield-ai/soul/v2/standard", extra=1)]})
    assert clean["nodes"][0]["data"] == {"model": "higgsfield-ai/soul/v2/standard", "values": {}, "runs": []}
    media = check_graph({"nodes": [node("m", "media", url="https://x.test/a.png", kind="image", junk=True)]})
    assert media["nodes"][0]["data"] == {"url": "https://x.test/a.png", "kind": "image"}
    assert check_graph({"nodes": [node("t", "text")]})["nodes"][0]["data"] == {"text": ""}
    for selected in (3, -1, True, "0"):
        with pytest.raises(GraphError, match="selected"):
            check_graph({"nodes": [node("g", "generator", model="m", runs=["a", "b"], selected=selected)]})


async def test_save_returns_its_own_write(env):  # noqa: F811
    """Revisión 51: la respuesta es lo que dejó esta escritura, no lo que otro guardó después."""
    _, http, _ = env
    space = (await http.post("/v1/spaces", json={})).json()
    first = (await http.put(f"/v1/spaces/{space['id']}", json={"version": 1, "title": "A"})).json()
    assert (first["title"], first["version"]) == ("A", 2)
    second = (await http.put(f"/v1/spaces/{space['id']}", json={"version": 2, "title": "B"})).json()
    assert (second["title"], second["version"]) == ("B", 3)


async def test_spaces_are_private_to_their_client(env):  # noqa: F811
    app, http, _ = env
    await http.post("/v1/spaces", json={"title": "Mío"})
    async with app.state.sessions() as s:
        other = ApiClient(name="otro", key_hash="y" * 64, key_prefix="hfs_y")
        s.add(other)
        await s.flush()
        foreign = Space(owner_id=other.id, title="Ajeno", graph={"nodes": [], "edges": []})
        s.add(foreign)
        await s.commit()
        foreign_id = foreign.id
    assert [x["title"] for x in (await http.get("/v1/spaces")).json()["spaces"]] == ["Mío"]
    assert (await http.get(f"/v1/spaces/{foreign_id}")).status_code == 404
    assert (await http.put(f"/v1/spaces/{foreign_id}", json={"version": 1, "title": "x"})).status_code == 404
    assert (await http.delete(f"/v1/spaces/{foreign_id}")).status_code == 404


async def test_models_list_the_kinds_their_ports_accept(env):  # noqa: F811
    _, http, _ = env
    models = {m["id"]: m for m in (await http.get("/v1/models")).json()["models"]}
    assert all(set(m["inputs"]) <= {"text", "image", "video", "audio"} for m in models.values())
    assert "text" in models["higgsfield-ai/soul/v2/standard"]["inputs"]
    assert any("video" in m["inputs"] for m in models.values())


async def test_generator_values_must_fit_the_model_schema(env):  # noqa: F811
    """Revisión 52: un valor con otro tipo rompería el control del inspector; se rechaza al guardar."""
    _, http, _ = env
    kling = "kling-video/v3.0/std/text-to-video"
    bad = {"nodes": [node("g", "generator", model=kling, values={"elements": {}})]}
    res = await http.post("/v1/spaces", json={"graph": bad})
    assert res.status_code == 422 and "elements" in res.json()["error"]["message"]
    ok = {
        "nodes": [node("g", "generator", model=kling, values={"elements": [], "unknown": 1, "prompt": "x"})]
    }
    saved = (await http.post("/v1/spaces", json={"graph": ok})).json()
    assert saved["graph"]["nodes"][0]["data"]["values"] == {"elements": [], "prompt": "x"}


async def test_a_cover_without_its_local_copy_is_rejected(env):  # noqa: F811
    app, http, _ = env
    space = (await http.post("/v1/spaces", json={})).json()
    image = await finished_image(app)
    (app.state.settings.storage_dir / "outputs" / image / "0-image.png").unlink()
    res = await http.put(
        f"/v1/spaces/{space['id']}",
        json={"version": 1, "cover": f"/v1/generations/{image}/files/0-image.png"},
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "invalid_cover"


async def test_values_with_shared_definitions_are_validated_against_the_root(env):  # noqa: F811
    """Revisión 53: los `$ref` a `#/$defs/…` del catálogo se resuelven con las definiciones de la raíz."""
    _, http, _ = env
    model = "v1/custom-references"
    image = {"type": "image_url", "image_url": "https://cdn.test/a.png"}
    for values in ({"model_version": "v1"}, {"input_images": [image]}):
        res = await http.post(
            "/v1/spaces", json={"graph": {"nodes": [node("g", "generator", model=model, values=values)]}}
        )
        assert res.status_code == 201, (values, res.text)
        assert res.json()["graph"]["nodes"][0]["data"]["values"] == values
    space = (
        await http.post("/v1/spaces", json={"graph": {"nodes": [node("g", "generator", model=model)]}})
    ).json()
    for version, values, status in (
        (1, {"model_version": "v1"}, 200),
        (2, {"input_images": [image]}, 200),
        (3, {"model_version": "nope"}, 422),
        (3, {"input_images": [{"type": "image_url"}]}, 422),
    ):
        graph = {"nodes": [node("g", "generator", model=model, values=values)]}
        res = await http.put(f"/v1/spaces/{space['id']}", json={"version": version, "graph": graph})
        assert res.status_code == status, (values, res.text)
