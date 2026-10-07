"""Contrato del MCP: cada herramienta declara sus pistas y llama a la ruta correcta de la API."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hf_studio import mcp_server

# nombre: (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
READ, READ_EXT = (True, False, True, False), (True, False, True, True)
SPEND = (False, False, False, True)
TOOLS = {
    "find_models": READ,
    "get_model": READ,
    "recommend_models": READ_EXT,  # cotiza con Higgsfield
    "upload_media": (False, False, False, True),
    "estimate_cost": (True, False, False, True),  # cotiza con Higgsfield; cada llamada da otro quote_id
    "generate": SPEND,
    "generate_batch": SPEND,
    "get_generation": READ,
    "wait_generations": READ,
    "list_generations": READ,
    "cancel_generation": (False, True, True, True),
    "download_outputs": (False, True, True, True),
    "list_presets": READ,
    "run_preset": SPEND,
    "save_preset": (False, False, False, False),
    "list_voices": READ_EXT,
    "change_voice": SPEND,
    "text_to_speech": SPEND,
    "sound_effect": SPEND,
    "compose_music": SPEND,
    "isolate_voice": SPEND,
    "elevenlabs_account": READ_EXT,
    "list_sounds": (False, False, True, False),  # registra en la sonoteca los audios que falten
    "label_sound": (False, True, True, False),
    "import_elevenlabs_history": (False, False, True, True),
    "approve_fallback": SPEND,
    "providers_status": READ_EXT,
    "list_elements": READ,
    "use_output": (False, False, True, True),  # sube la copia local a Higgsfield; misma URL 5 días
    "create_element": (False, False, False, True),  # sube las imágenes a Higgsfield
    "delete_element": (False, True, True, False),
    "list_spaces": READ,
    "get_space": READ,
    "create_space": (False, False, False, False),
    "update_space": (False, True, False, False),
    "estimate_space_run": (False, False, False, True),  # cotiza y puede subir salidas previas a Higgsfield
    "run_space": SPEND,
    "get_space_run": READ,
    "approve_space_run": SPEND,
    "cancel_space_run": (False, True, True, False),
}


def _listed():
    return {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_every_tool_is_covered_here():
    assert set(_listed()) == set(TOOLS)


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_every_tool_declares_all_four_hints(name):
    tool = _listed()[name]
    wire = tool.model_dump(by_alias=True, exclude_none=True)["annotations"]
    assert {k: type(v) for k, v in wire.items()} == {
        "readOnlyHint": bool,
        "destructiveHint": bool,
        "idempotentHint": bool,
        "openWorldHint": bool,
    }
    hints = (wire["readOnlyHint"], wire["destructiveHint"], wire["idempotentHint"], wire["openWorldHint"])
    assert hints == TOOLS[name]
    assert tool.title


def test_tools_that_spend_credits_say_so_in_the_title():
    for name in ("generate", "generate_batch", "run_preset", "change_voice", "text_to_speech",
                 "sound_effect", "compose_music", "isolate_voice", "run_space", "approve_space_run"):  # fmt: skip
        assert "spends credits" in _listed()[name].title


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def call(method, path, **kw):
        seen.append((method, path, kw))
        if path == "/v1/presets":
            keys = ("slug", "title", "description", "category", "output", "model", "variables", "builtin")
            return {"presets": [{**{k: k for k in keys}, "template": {"secret": 1}}]}
        if path.endswith("/estimate"):
            # Las rutas de ElevenLabs devuelven su propia cotización, que debe viajar al lanzar.
            return {"usd": 0.1, "complete": True, "missing": [], "voice_quote": "vq_1", "audio_quote": "aq_1"}
        if kw.get("json", {}).get("dry_run") is True:
            price = {"usd": 0.5, "complete": True, "missing": []}
            return {"total": price, "estimate": price}
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_call", call)
    return seen


READS = [
    (lambda: mcp_server.find_models("text-to-video", "video", "seedance"), "GET", "/v1/models",
     {"capability": "text-to-video", "output": "video", "q": "seedance"}),
    (lambda: mcp_server.get_model("a/b"), "GET", "/v1/models/a/b", None),
    (lambda: mcp_server.recommend_models("video barato", "video", 3), "GET", "/v1/recommend",
     {"task": "video barato", "limit": 3, "output": "video"}),
    (lambda: mcp_server.get_generation("g1", 999), "GET", "/v1/generations/g1", {"wait": 120}),
    (lambda: mcp_server.wait_generations(["a", "b"], -5), "GET", "/v1/generations",
     {"ids": "a,b", "wait": 0, "limit": 100}),
    (lambda: mcp_server.list_generations("failed", 5), "GET", "/v1/generations", {"limit": 5, "status": "failed"}),
    (lambda: mcp_server.cancel_generation("g1"), "POST", "/v1/generations/g1/cancel", None),
    (lambda: mcp_server.save_preset("g1", "mi-receta", "Mi receta"), "POST", "/v1/presets/from-generation/g1",
     None),
    (lambda: mcp_server.list_voices("demon", True, 5), "GET", "/v1/voice/voices",
     {"library": True, "limit": 5, "search": "demon"}),
    (lambda: mcp_server.elevenlabs_account(), "GET", "/v1/voice/status", None),
    (lambda: mcp_server.list_sounds("scream", "grito", 10), "GET", "/v1/sounds",
     {"limit": 10, "category": "scream", "q": "grito"}),
    (lambda: mcp_server.label_sound("s1", title="Grito", tags=["terror"]), "PATCH", "/v1/sounds/s1", None),
    (lambda: mcp_server.import_elevenlabs_history(), "POST", "/v1/sounds/import-elevenlabs", None),
    (lambda: mcp_server.list_elements(), "GET", "/v1/elements", None),
    (lambda: mcp_server.use_output("g1", 1), "POST", "/v1/generations/g1/outputs/1/use", None),
    (lambda: mcp_server.delete_element("el_1"), "DELETE", "/v1/elements/el_1", None),
]  # fmt: skip


@pytest.mark.parametrize(("run", "method", "path", "params"), READS)
def test_simple_tools_hit_their_route(calls, run, method, path, params):
    run()
    assert calls[-1][:2] == (method, path)
    if params is not None:
        assert calls[-1][2]["params"] == params


def test_label_sound_only_sends_what_changes(calls):
    mcp_server.label_sound("s1", category="laugh")
    assert calls[-1][2]["json"] == {"category": "laugh"}


def test_list_presets_hides_the_template(calls):
    preset = mcp_server.list_presets()["presets"][0]
    assert "template" not in preset and preset["slug"] == "slug"


def test_upload_media_sends_the_file(calls, tmp_path):
    image = tmp_path / "foto.png"
    image.write_bytes(b"\x89PNG")
    mcp_server.upload_media(str(image))
    method, path, kw = calls[-1]
    assert (method, path) == ("POST", "/v1/uploads")
    assert kw["files"]["file"][0] == "foto.png" and kw["files"]["file"][2] == "image/png"
    with pytest.raises(ToolError, match="No existe"):
        mcp_server.upload_media(str(tmp_path / "no-esta.png"))


def test_windows_paths_are_translated_under_wsl(monkeypatch):
    monkeypatch.setattr(mcp_server.os, "name", "posix")
    monkeypatch.setattr(mcp_server.Path, "is_dir", lambda self: str(self) == "/mnt" or False)
    assert str(mcp_server._local_path(r"C:\Users\Yo\clip.mp4")) == "/mnt/c/Users/Yo/clip.mp4"


@pytest.mark.parametrize(
    ("tool", "service", "args"),
    [
        (mcp_server.text_to_speech, "text-to-speech", {"text": "hola", "voice_id": "v1"}),
        (mcp_server.sound_effect, "sound-effects", {"text": "door creaking"}),
        (mcp_server.compose_music, "music", {"prompt": "dark synth", "seconds": 10}),
    ],
)
def test_audio_tools_quote_first_and_spend_only_with_the_quote(calls, tool, service, args):
    quote = tool(**args)
    assert calls[-1][:2] == ("POST", f"/v1/audio/{service}/estimate") and quote["quote_id"]
    with pytest.raises(ToolError, match="quote_id"):
        tool(**args, quote_id="q_inventado")
    tool(**args, quote_id=quote["quote_id"])
    assert calls[-1][:2] == ("POST", f"/v1/audio/{service}")
    assert calls[-1][2]["headers"]["Idempotency-Key"]
    assert calls[-1][2]["json"]["audio_quote"] == "aq_1"


def test_isolate_voice_and_change_voice_quote_then_run(calls):
    quote = mcp_server.isolate_voice(source_generation_id="g1")
    assert calls[-1][:2] == ("POST", "/v1/audio/voice-isolator/estimate")
    mcp_server.isolate_voice(source_generation_id="g1", quote_id=quote["quote_id"])
    assert calls[-1][:2] == ("POST", "/v1/audio/voice-isolator")
    assert calls[-1][2]["json"]["audio_quote"] == "aq_1"

    quote = mcp_server.change_voice("v1", source_generation_id="g1", start=1, end=2)
    assert calls[-1][:2] == ("POST", "/v1/voice/estimate")
    mcp_server.change_voice("v1", source_generation_id="g1", start=1, end=2, quote_id=quote["quote_id"])
    assert calls[-1][:2] == ("POST", "/v1/voice/changes")
    assert calls[-1][2]["json"]["voice_quote"] == "vq_1"
    # Otro tramo con la misma cotización: rechazado sin gastar.
    before = len(calls)
    with pytest.raises(ToolError, match="quote_id"):
        mcp_server.change_voice("v1", source_generation_id="g1", start=1, end=9, quote_id=quote["quote_id"])
    assert len(calls) == before


def test_download_outputs_refuses_unfinished_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_call", lambda *a, **k: {"status": "in_progress", "outputs": []})
    with pytest.raises(ToolError, match="in_progress"):
        mcp_server.download_outputs("g1", str(tmp_path))


@pytest.mark.parametrize(
    ("quote", "run", "path"),
    [
        (
            lambda: mcp_server.estimate_cost("m", {"prompt": "x"}),
            lambda q: mcp_server.generate("m", {"prompt": "x"}, quote_id=q),
            "/v1/generations",
        ),
        (
            lambda: mcp_server.generate_batch([{"model": "m", "input": {}}]),
            lambda q: mcp_server.generate_batch([{"model": "m", "input": {}}], dry_run=False, quote_id=q),
            "/v1/generations/batch",
        ),
        (
            lambda: mcp_server.run_preset("p", {"prompt": "x"}),
            lambda q: mcp_server.run_preset("p", {"prompt": "x"}, dry_run=False, quote_id=q),
            "/v1/presets/p/run",
        ),
    ],
)
def test_paid_higgsfield_tools_need_their_own_quote(calls, quote, run, path):
    with pytest.raises(ToolError, match="quote_id"):
        run("q_inventado")
    assert not any(c[2].get("json", {}).get("dry_run") is False or c[1] == "/v1/generations" for c in calls)
    quote_id = quote()["quote_id"]
    run(quote_id)
    method, sent_path, kw = calls[-1]
    assert (method, sent_path) == ("POST", path)
    assert kw["headers"]["Idempotency-Key"] == f"quote-{quote_id}"


def test_create_element_sends_files_and_urls(calls, tmp_path):
    front, side = tmp_path / "frente.png", tmp_path / "perfil.jpg"
    front.write_bytes(b"\x89PNG")
    side.write_bytes(b"\xff\xd8\xff")
    mcp_server.create_element("zorro", "zorro rojo", [str(front), str(side)], ["https://cdn.test/a.png"])
    method, path, kw = calls[-1]
    assert (method, path) == ("POST", "/v1/elements")
    assert [f[1][0] for f in kw["files"]] == ["frente.png", "perfil.jpg"]
    assert kw["data"] == {
        "name": "zorro",
        "description": "zorro rojo",
        "image_urls": ["https://cdn.test/a.png"],
    }
    with pytest.raises(ToolError, match="No existe"):
        mcp_server.create_element("x", "y", [str(tmp_path / "no.png")])


@pytest.fixture
def space_calls(monkeypatch):
    seen = []

    def call(method, path, **kw):
        seen.append((method, path, kw))
        if method == "GET" and path == "/v1/spaces/s1":
            return {
                "id": "s1",
                "version": 7,
                "graph": {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
            }
        if kw.get("json", {}).get("dry_run") is True:
            return {"steps": [{"node_id": "g1", "status": "ok", "usd": 0.4}], "total_usd": 0.4, "pending": 0}
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_call", call)
    return seen


def test_a_space_run_needs_its_quote_and_uses_the_quoted_total(space_calls):
    quote = mcp_server.estimate_space_run("s1", "downstream", "g1")
    assert (
        space_calls[-1][:2] == ("POST", "/v1/spaces/s1/runs")
        and space_calls[-1][2]["json"]["dry_run"] is True
    )
    assert quote["version"] == 7 and quote["quote_id"]
    with pytest.raises(ToolError, match="quote_id"):
        mcp_server.run_space("s1", "q_inventado", "downstream", "g1", version=7)
    with pytest.raises(ToolError, match="quote_id"):  # otro modo u otra versión: otra petición
        mcp_server.run_space("s1", quote["quote_id"], "workflow", None, version=7)
    with pytest.raises(ToolError, match="lower"):
        mcp_server.run_space("s1", quote["quote_id"], "downstream", "g1", version=7, max_total_usd=0.1)
    mcp_server.run_space("s1", quote["quote_id"], "downstream", "g1", version=7)
    key = space_calls[-1][2]["headers"]["Idempotency-Key"]
    mcp_server.run_space("s1", quote["quote_id"], "downstream", "g1", version=7)  # reintento: misma clave
    assert space_calls[-1][2]["headers"]["Idempotency-Key"] == key
    assert space_calls[-1][:2] == ("POST", "/v1/spaces/s1/runs")
    assert space_calls[-1][2]["json"] == {
        "mode": "downstream",
        "version": 7,
        "max_total_usd": 0.4,
        "node_id": "g1",
    }


def test_update_space_keeps_what_it_does_not_replace(space_calls):
    node = {"id": "t", "type": "text", "position": {"x": 0, "y": 0}, "data": {"text": "hola"}}
    mcp_server.update_space("s1", 7, nodes=[node])
    method, path, kw = space_calls[-1]
    assert (method, path) == ("PUT", "/v1/spaces/s1")
    assert (
        kw["json"]["version"] == 7
        and kw["json"]["graph"]["edges"] == []
        and kw["json"]["graph"]["nodes"] == [node]
    )


SPACE_ROUTES = [
    (lambda: mcp_server.list_spaces(), "GET", "/v1/spaces"),
    (lambda: mcp_server.get_space("s1"), "GET", "/v1/spaces/s1"),
    (lambda: mcp_server.create_space("Spot"), "POST", "/v1/spaces"),
    (lambda: mcp_server.get_space_run("s1", "r1"), "GET", "/v1/spaces/s1/runs/r1"),
    (lambda: mcp_server.approve_space_run("s1", "r1", 1.5), "POST", "/v1/spaces/s1/runs/r1/approve"),
    (lambda: mcp_server.cancel_space_run("s1", "r1"), "POST", "/v1/spaces/s1/runs/r1/cancel"),
]


@pytest.mark.parametrize(("run", "method", "path"), SPACE_ROUTES)
def test_space_tools_hit_their_route(space_calls, run, method, path):
    run()
    assert space_calls[-1][:2] == (method, path)


def test_a_flow_run_ties_its_inputs_to_the_quote(space_calls):
    quote = mcp_server.estimate_space_run("s1", inputs={"t": "un zorro"})
    assert space_calls[-1][2]["json"]["inputs"] == {"t": "un zorro"}
    with pytest.raises(ToolError, match="quote_id"):  # otras entradas: otra petición
        mcp_server.run_space("s1", quote["quote_id"], version=7, inputs={"t": "un lobo"})
    mcp_server.run_space("s1", quote["quote_id"], version=7, inputs={"t": "un zorro"})
    assert space_calls[-1][2]["json"]["inputs"] == {"t": "un zorro"}
