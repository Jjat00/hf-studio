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
                 "sound_effect", "compose_music", "isolate_voice"):  # fmt: skip
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
