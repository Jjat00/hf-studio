"""Content Factory: guion con Claude simulado, composición y tiempos, cotización, trabajo completo con la voz y el
render simulados, y una prueba de humo del render real que se salta si falta Node.js o Chromium."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from pathlib import Path

import httpx
import httpx2
import pytest

from hf_studio import factory as fac
from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, hash_token
from hf_studio.factory_compose import (
    SceneTime,
    Word,
    build_composition,
    caption_groups,
    fit_size,
    fmt_number,
    wrap_lines,
)
from hf_studio.factory_script import OUTPUT_FORMAT, ScriptError, parse_episodes
from hf_studio.factory_styles import STYLES, public_styles

from .test_routing import Fakes, tick

MODEL = "hf-studio/content-factory"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def episode(n_scenes: int = 3) -> dict:
    layouts = [
        "title",
        "counter",
        "map",
        "chart",
        "comparison",
        "list",
        "quote",
        "scale",
        "timeline",
        "timer",
    ]
    scenes = []
    for i in range(n_scenes):
        layout = "closing" if i == n_scenes - 1 and n_scenes > 1 else layouts[i % len(layouts)]
        visual = {"layout": layout, "headline": f"Titular {i}", "value": 1234.5, "unit": "km",
                  "items": [{"label": "Bogotá", "value": 10, "lat": 4.7, "lon": -74.1},
                            {"label": "Madrid", "value": 1000, "lat": 40.4, "lon": -3.7}]}  # fmt: skip
        scenes.append({"narration": f"Esta es la escena número {i}, dicha en voz alta.", "visual": visual})
    return {"title": "¿Qué pasaría si la Luna desapareciera?", "scenes": scenes}


# --- Composición y tiempos ---------------------------------------------------------------------------------------


def test_numbers_follow_the_language():
    assert fmt_number(1234567.5, "es", 1) == "1.234.567,5"
    assert fmt_number(1234567.5, "en", 1) == "1,234,567.5"
    assert fmt_number(-3, "es") == "−3"


def test_headlines_shrink_instead_of_breaking_words():
    text = "¿Y si la Luna desapareciera?"
    size = fit_size(text, "Anton", 168, 44, 4, upper=True)
    assert wrap_lines(text, size, 920, 0.5) <= 4
    assert wrap_lines("DESAPARECIERA", 200, 920, 0.5) == 999  # una palabra que no cabe nunca se parte


def test_captions_break_on_punctuation_pauses_and_length():
    words = [Word("Imagina", 0, 0.3), Word("que", 0.3, 0.4), Word("esta", 0.4, 0.6), Word("noche,", 0.6, 0.9),
             Word("la", 1.5, 1.6), Word("Luna", 1.6, 1.9)]  # fmt: skip
    groups = [[w.text for w in g] for g in caption_groups(words)]
    assert groups == [["Imagina", "que", "esta"], ["noche,"], ["la", "Luna"]]


def test_timeline_adds_lead_in_tail_and_end_hold():
    times, voice_at, total = fac.plan_timeline([2.0, 3.0])
    assert times[0].start == 0 and times[0].duration == pytest.approx(fac.LEAD_IN + 2.0 + fac.TAIL)
    assert times[1].start == pytest.approx(times[0].duration)
    assert voice_at == [fac.LEAD_IN, pytest.approx(times[1].start + fac.LEAD_IN)]
    assert total == pytest.approx(times[1].start + fac.LEAD_IN + 3.0 + fac.TAIL + fac.END_HOLD)


def test_edge_words_get_their_punctuation_back_and_elevenlabs_chars_become_words():
    words = fac.attach_punctuation([Word("Hola", 0, 0.2), Word("mundo", 0.2, 0.5)], "¡Hola, mundo!")
    assert [w.text for w in words] == ["¡Hola,", "mundo!"]
    align = {"characters": list("Hola mundo"), "character_start_times_seconds": [i * 0.1 for i in range(10)],
             "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(10)]}  # fmt: skip
    words = fac.words_from_alignment(align)
    assert [(w.text, round(w.start, 2), round(w.end, 2)) for w in words] == [
        ("Hola", 0, 0.4),
        ("mundo", 0.5, 1.0),
    ]


@pytest.mark.parametrize("style_id", list(STYLES))
def test_every_style_builds_a_deterministic_composition(style_id):
    script = {**episode(11), "episode": 1, "episodes": 2, "series_title": "Serie"}
    times = [SceneTime(i * 3.0, 3.0) for i in range(11)]
    words = [Word("hola,", 0.3, 0.6), Word("mundo", 0.7, 1.0)]
    html = build_composition(script, STYLES[style_id], times, words, "es", 33.0)
    assert 'data-composition-id="factory"' in html and 'data-duration="33.000"' in html
    assert 'data-width="1080" data-height="1920"' in html
    assert len(re.findall(r'class="scene clip" data-start=', html)) == 11
    assert "Math.random" not in html and "Date.now" not in html and "http" not in html.split("<body>")[1]
    anims = json.loads(re.search(r"var A = (\[.*?\]);\n", html).group(1))
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert anims and all(a[0] in ids for a in anims)  # cada animación apunta a un elemento que existe
    assert "Continuará" in html and "Episodio 1/2" in html
    assert html == build_composition(script, STYLES[style_id], times, words, "es", 33.0)  # determinista


def test_the_hud_counter_switches_exactly_at_each_scene():
    times = [SceneTime(0, 4.0), SceneTime(4.0, 6.0)]
    html = build_composition(episode(2), STYLES["swiss"], times, [], "es", 10.0)
    anims = json.loads(re.search(r"var A = (\[.*?\]);\n", html).group(1))
    hud = next(a for a in anims if a[0].startswith("hudn"))
    frames = [(f["offset"], f["content"]) for f in hud[1]]
    assert (
        frames[0] == (0, '"01 / 02"')
        and frames[1][1] == '"01 / 02"'
        and frames[1][0] == pytest.approx(0.3995)
    )
    assert frames[2] == (0.4, '"02 / 02"') and frames[-1][0] == 1


def test_public_styles_have_previews_and_colors():
    styles = public_styles("es")
    assert len(styles) >= 8 and all(
        s["preview"].startswith("/factory/") and len(s["colors"]) == 4 for s in styles
    )
    web = Path(__file__).parents[1] / "web" / "public"
    assert all((web / s["preview"].lstrip("/")).is_file() for s in styles)


# --- Guion ---------------------------------------------------------------------------------------------------------


def test_claude_output_is_cleaned_and_validated():
    raw = {"series_title": "Serie", "episodes": [
        {"title": "Uno", "hook": "", "cliffhanger": None, "scenes": [
            {"narration": "  Hola   mundo ", "visual": {"layout": "chart", "headline": "H", "kicker": None,
             "value": None, "from_value": None, "unit": None, "prefix": None,
             "items": [{"label": "A", "value": 1, "note": None, "lat": None, "lon": None}, {"label": " "}]}}]}]}  # fmt: skip
    series, eps = parse_episodes(raw, 1)
    assert series == "Serie" and eps[0]["scenes"][0]["narration"] == "Hola mundo"
    assert eps[0]["scenes"][0]["visual"]["items"] == [{"label": "A", "value": 1}]
    with pytest.raises(ScriptError):
        parse_episodes(raw, 2)  # faltan episodios
    bad = json.loads(json.dumps(raw))
    bad["episodes"][0]["scenes"][0]["visual"]["layout"] = "nope"
    with pytest.raises(ScriptError):
        parse_episodes(bad, 1)


def test_structured_output_schema_has_no_unsupported_constraints():
    text = json.dumps(OUTPUT_FORMAT)
    for word in ("minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"):
        assert word not in text


class FakeClaude:
    def __init__(self):
        self.requests: list = []
        self.stop = "end_turn"  # "max_tokens": la respuesta se corta (gasta tokens y falla)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        eps = [{**episode(4), "hook": "Gancho", "cliffhanger": "¿Y después?"} for _ in range(2)]
        for ep in eps:
            for sc in ep["scenes"]:
                sc["visual"] = {"kicker": None, "from_value": None, "prefix": None, **sc["visual"]}
        text = json.dumps({"series_title": "La Luna", "episodes": eps})
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": text}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": self.stop, "stop_sequence": None},
                               "usage": {"output_tokens": 2000}}),
            ("message_stop", {"type": "message_stop"}),
        ]  # fmt: skip
        sse = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())


async def _app(tmp_path, anthropic_key: str = "sk-test", eleven: str = ""):
    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        elevenlabs_api_key=eleven,
        provider_keys={"ANTHROPIC_API_KEY": anthropic_key, "ANTHROPIC_BASE_URL": "https://api.anthropic.test"},
        database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    return create_app(settings, transport=httpx.MockTransport(Fakes()))


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr("hf_studio.routing.renderer_problem", lambda: None)
    app = await _app(tmp_path)
    claude = FakeClaude()
    async with app.router.lifespan_context(app):
        app.state.assistant_jobs.http_client_factory = lambda: httpx2.AsyncClient(
            transport=httpx2.MockTransport(claude)
        )
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, claude


async def test_claude_writes_a_series_and_reports_its_cost(env):
    _, http, claude = env
    info = (await http.get("/v1/factory")).json()
    assert info["model"] == MODEL and info["scripts"]["available"] and len(info["styles"]) >= 8
    ask = {
        "topic": "¿Qué pasaría si la Luna desapareciera?",
        "style": "orbital",
        "episodes": 2,
        "duration_seconds": 45,
    }
    calls = len(claude.requests)
    unapproved = await http.post("/v1/factory/scripts", json=ask)  # sin tope aprobado no se llama a Claude
    assert unapproved.status_code == 409 and unapproved.json()["error"]["code"] == "quote_required"
    quote = (await http.post("/v1/factory/scripts/estimate", json=ask)).json()
    assert quote["max_usd"] > 0 and len(claude.requests) == calls
    low = await http.post("/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"] / 2})
    assert low.status_code == 409 and len(claude.requests) == calls
    r = await http.post(
        "/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"]}, headers={"Idempotency-Key": "g1"}
    )
    assert r.status_code == 200, r.text
    again = await http.post(
        "/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"]}, headers={"Idempotency-Key": "g1"}
    )
    assert again.json()["deduplicated"] is True and len(claude.requests) == calls + 1  # el reintento no cobra
    body = r.json()
    assert (
        len(body["episodes"]) == 2
        and body["episodes"][1]["episode"] == 2
        and body["episodes"][0]["episodes"] == 2
    )
    assert body["cost_usd"] == pytest.approx((1000 * 4 + 2000 * 20) / 1_000_000)
    sent = claude.requests[-1]
    assert sent["output_config"]["format"]["type"] == "json_schema" and sent["model"] == "claude-opus-5-5"
    assert sent["stream"] is True
    assert "2 episodes" in sent["messages"][0]["content"] and "Spanish" in sent["messages"][0]["content"]
    bad = await http.post("/v1/factory/scripts", json={"topic": "algo", "style": "nope", "max_usd": 5})
    assert bad.status_code == 422


async def test_scripts_need_the_anthropic_key(tmp_path):
    app = await _app(tmp_path, anthropic_key="")
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            r = await http.post("/v1/factory/scripts", json={"topic": "La Luna", "max_usd": 5})
    assert r.status_code == 503 and r.json()["error"]["code"] == "anthropic_not_configured"


# --- Cotización y trabajo ------------------------------------------------------------------------------------------


async def test_edge_voice_is_free_and_elevenlabs_costs_its_characters(env):
    _, http, _ = env
    body = {
        "model": MODEL,
        "input": {"script": episode(2), "voice": {"engine": "edge", "voice_id": "es-CO-GonzaloNeural"}},
    }
    est = (await http.post("/v1/estimate", json=body)).json()
    assert est["provider"] == "factory" and est["kind"] == "exact" and est["usd"] == 0
    chars = sum(len(s["narration"]) for s in episode(2)["scenes"])
    assert fac.quote({"script": episode(2), "voice": {"engine": "elevenlabs", "voice_id": "v", "model_id": "eleven_flash_v2_5"}}) == {
        "usd": pytest.approx(chars / 1000 * 0.05), "kind": "approx", "basis": pytest.approx(
            f"{chars} chars × $0.05/1K · ElevenLabs eleven_flash_v2_5 · local render")}  # fmt: skip
    # Sin clave de ElevenLabs, narrar con ella no se puede cotizar.
    body["input"]["voice"] = {"engine": "elevenlabs", "voice_id": "v"}
    r = await http.post("/v1/estimate", json=body)
    assert r.status_code == 503 and r.json()["error"]["code"] == "elevenlabs_not_configured"


async def test_without_node_the_estimate_says_why(env, monkeypatch):
    _, http, _ = env
    monkeypatch.setattr("hf_studio.routing.renderer_problem", lambda: "Install Node.js 22+ (with npx)")
    body = {"model": MODEL, "input": {"script": episode(2), "voice": {"engine": "edge", "voice_id": "x"}}}
    est = (await http.post("/v1/estimate", json=body)).json()
    assert est["kind"] == "unavailable" and "Node.js" in est["basis"]
    r = await http.post("/v1/generations", json=body)
    assert r.status_code == 422


async def _finish(app, job_id):
    for _ in range(200):
        await tick(app)
        await asyncio.sleep(0.05)
        async with app.state.sessions() as s:
            job = await s.get(Job, job_id)
            if job.status in ("completed", "failed"):
                return job
    raise AssertionError("did not finish")


async def _silent_mp3(path: Path, seconds: float) -> None:
    code, msg = await fac.run_proc("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                                   "-t", f"{seconds}", "-c:a", "libmp3lame", str(path), timeout=60)  # fmt: skip
    assert code == 0, msg


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
async def test_a_job_narrates_renders_mixes_and_cleans_up(env, monkeypatch):
    app, http, _ = env
    rendered: dict = {}

    async def fake_edge(text, voice, rate, out):
        await _silent_mp3(out, 1.0)
        return [Word(w, 0.1 * i, 0.1 * i + 0.1) for i, w in enumerate(text.split())]

    async def fake_render(self, project, out, total):
        # El render corre con otro cwd: proyecto y salida llegan como rutas absolutas.
        assert project.is_absolute() and out.is_absolute()
        rendered["html"] = (project / "index.html").read_text()
        rendered["fonts"] = sorted(p.name for p in (project / "fonts").iterdir())
        code, msg = await fac.run_proc("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                                       f"color=c=black:s=108x192:d={total}:r=30", str(out), timeout=60)  # fmt: skip
        assert code == 0, msg

    monkeypatch.setattr(fac, "edge_scene", fake_edge)
    monkeypatch.setattr(fac.ContentFactoryJobs, "_render", fake_render)
    body = {"model": MODEL, "input": {"script": episode(3), "style": "riso",
                                      "voice": {"engine": "edge", "voice_id": "es-CO-GonzaloNeural"}}}  # fmt: skip
    est = (await http.post("/v1/estimate", json=body)).json()
    job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
    done = await _finish(app, job["id"])
    assert done.status == "completed", done.error
    assert done.files[0]["kind"] == "video"
    out = app.state.settings.storage_dir / "outputs" / done.id / done.files[0]["name"]
    from hf_studio.audio import duration, has_audio

    assert await has_audio(str(out))
    assert await duration(str(out)) == pytest.approx(
        3 * (fac.LEAD_IN + 1.0 + fac.TAIL) + fac.END_HOLD, abs=0.4
    )  # el MP3 añade relleno
    assert "Anton-Regular.woff2" in rendered["fonts"] and "data-duration" in rendered["html"]
    work = app.state.settings.storage_dir / "factory-work"
    assert not work.exists() or not any(work.iterdir())  # sin carpetas temporales


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
async def test_a_failed_render_fails_the_job_and_leaves_nothing(env, monkeypatch):
    app, http, _ = env

    async def fake_edge(text, voice, rate, out):
        await _silent_mp3(out, 0.5)
        return []

    async def broken_render(self, project, out, total):
        raise fac.FactoryError("HyperFrames could not render the short: boom")

    monkeypatch.setattr(fac, "edge_scene", fake_edge)
    monkeypatch.setattr(fac.ContentFactoryJobs, "_render", broken_render)
    body = {"model": MODEL, "input": {"script": episode(2), "voice": {"engine": "edge", "voice_id": "x"}}}
    job = (await http.post("/v1/generations", json={**body, "max_usd": 0})).json()
    done = await _finish(app, job["id"])
    assert done.status == "failed" and "boom" in done.error
    work = app.state.settings.storage_dir / "factory-work"
    assert not work.exists() or not any(work.iterdir())


async def test_elevenlabs_narration_uses_the_timestamps_endpoint(tmp_path):
    import base64

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"audio_base64": base64.b64encode(b"ID3fake").decode(), "alignment": {
            "characters": list("Hola"), "character_start_times_seconds": [0, 0.1, 0.2, 0.3],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4]}})  # fmt: skip

    from hf_studio.voice import ElevenLabsClient

    settings = Settings(_env_file=None, hf_api_key="k:s", elevenlabs_api_key="el", storage_dir=tmp_path)
    eleven = ElevenLabsClient(settings, httpx.MockTransport(handler))

    async def same(voice_id, owner):
        return voice_id

    eleven.ensure_voice = same
    words = await fac.eleven_scene(
        eleven, "Hola", {"voice_id": "v1", "model_id": "eleven_v4"}, "es", tmp_path / "a.mp3"
    )
    await eleven.aclose()
    assert calls[0].url.path == "/v1/text-to-speech/v1/with-timestamps"
    assert json.loads(calls[0].content) == {"text": "Hola", "model_id": "eleven_v4", "language_code": "es"}
    assert [w.text for w in words] == ["Hola"] and (tmp_path / "a.mp3").read_bytes() == b"ID3fake"


# --- Humo: render real --------------------------------------------------------------------------------------------


@pytest.mark.skipif(
    fac.renderer_problem() is not None or os.environ.get("HF_STUDIO_SKIP_RENDER_SMOKE") == "1",
    reason="needs Node.js 22+, npx and ffmpeg (HyperFrames downloads its Chromium on first use)",
)
async def test_render_smoke(tmp_path):
    """Un corto de 2 s de verdad con HyperFrames (sin voz de red). Se salta si falta Node.js; si falta Chromium y no
    se puede descargar, también."""
    settings = Settings(_env_file=None, hf_api_key="k:s", storage_dir=tmp_path)
    jobs = fac.ContentFactoryJobs(settings)
    project = tmp_path / "project"
    (project / "fonts").mkdir(parents=True)
    for font in (fac.ASSETS / "fonts").glob("*.woff2"):
        shutil.copyfile(font, project / "fonts" / font.name)
    script = episode(2)
    times = [SceneTime(0, 1.0), SceneTime(1.0, 1.0)]
    (project / "index.html").write_text(build_composition(script, STYLES["swiss"], times, [], "es", 2.0))
    out = tmp_path / "out.mp4"
    try:
        await jobs._render(project, out, 2.0)
    except fac.FactoryError as exc:
        if "chrom" in str(exc).lower() or "browser" in str(exc).lower():
            pytest.skip(f"No Chromium for HyperFrames: {exc}")
        raise
    from hf_studio.audio import duration

    assert out.stat().st_size > 0 and await duration(str(out)) == pytest.approx(2.0, abs=0.1)


async def test_a_timeout_kills_the_whole_process_tree(tmp_path):
    """El plazo mata al hijo y a su nieto (npx lanza Chrome), y siempre lo recoge."""
    import asyncio
    import os
    import sys

    from hf_studio.factory import run_proc

    pidfile = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time; "
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"open({str(pidfile)!r}, 'w').write(str(p.pid)); time.sleep(60)"
    )
    rc, msg = await run_proc(sys.executable, "-c", code, timeout=1.5)
    assert (rc, msg) == (124, "timeout")
    await asyncio.sleep(0.3)
    grandchild = int(pidfile.read_text())
    try:
        os.kill(grandchild, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    assert not alive


async def test_a_failed_paid_script_is_not_charged_again_with_the_same_key(env):
    _, http, claude = env
    ask = {"topic": "La Luna", "episodes": 1}
    quote = (await http.post("/v1/factory/scripts/estimate", json=ask)).json()
    claude.stop = "max_tokens"  # Claude gasta tokens y la salida se corta
    calls = len(claude.requests)
    first = await http.post("/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"]},
                            headers={"Idempotency-Key": "k1"})  # fmt: skip
    again = await http.post("/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"]},
                            headers={"Idempotency-Key": "k1"})  # fmt: skip
    assert first.status_code == again.status_code and first.status_code >= 400
    assert "already attempted" in again.json()["error"]["message"]
    assert len(claude.requests) == calls + 1  # el reintento con la misma clave no vuelve a llamar a Claude
    claude.stop = "end_turn"
    fresh = await http.post("/v1/factory/scripts", json={**ask, "max_usd": quote["max_usd"]},
                            headers={"Idempotency-Key": "k2"})  # fmt: skip
    assert fresh.status_code == 200 and len(claude.requests) == calls + 2


async def test_a_cancelled_script_request_is_not_run_again_with_the_same_key(env, monkeypatch):
    import hf_studio.api as api_module

    _, http, _ = env
    ask = {"topic": "La Luna", "episodes": 1}
    quote = (await http.post("/v1/factory/scripts/estimate", json=ask)).json()
    started, calls = asyncio.Event(), []

    async def slow(*args, **kwargs):
        calls.append(1)
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(api_module, "write_scripts", slow)
    body, headers = {**ask, "max_usd": quote["max_usd"]}, {"Idempotency-Key": "c1"}
    task = asyncio.create_task(http.post("/v1/factory/scripts", json=body, headers=headers))
    await started.wait()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    again = await http.post("/v1/factory/scripts", json=body, headers=headers)
    assert again.status_code == 502 and again.json()["error"]["code"] == "script_uncertain"
    assert len(calls) == 1  # la misma clave no vuelve a llamar a Claude tras una cancelación


async def test_a_cut_edge_voice_is_requested_again(tmp_path, monkeypatch):
    calls = []

    async def once(text, voice, rate, out):
        calls.append(1)
        n = 2 if len(calls) == 1 else len(text.split())  # la primera respuesta llega cortada
        return [Word(w, i * 0.2, i * 0.2 + 0.2) for i, w in enumerate(text.split()[:n])]

    monkeypatch.setattr(fac, "_edge_once", once)
    words = await fac.edge_scene(
        "La transformada suma todas las muestras por una onda.", "v", "+0%", tmp_path / "a"
    )
    assert len(calls) == 2 and len(words) == 9
    assert fac.spoken_ratio(words[:2], "uno dos tres cuatro") == 0.5
