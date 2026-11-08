"""Katana: análisis de la referencia (video sintético), compositor (EDL a HTML), plan a lienzo, rutas con Claude
simulado y el nodo de montaje con el render simulado. Nada llama a Higgsfield, a Claude ni a HyperFrames de verdad."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import httpx2
import pytest

from hf_studio import katana as kmod
from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, hash_token
from hf_studio.katana_analysis import analyze, aspect_of
from hf_studio.katana_compose import Edl, build
from hf_studio.katana_edit import KATANA_EDIT_MODEL, KatanaEditJobs, edl_problem
from hf_studio.katana_plan import OUTPUT_FORMAT, PlanError, parse_plan, ref_shots_needed, to_graph
from hf_studio.spaces import check_graph

from .test_routing import Fakes, tick

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")


def ffmpeg(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def make_reference(path: Path) -> bytes:
    """3 planos de 1 s (rojo, azul con 2 cuadros blancos a mitad, verde) a 30 fps, con clics de audio."""
    graph = (
        "color=c=red:s=160x284:r=30:d=1[a];"
        "color=c=blue:s=160x284:r=30:d=0.5[b1];color=c=white:s=160x284:r=30:d=0.0667[w];"
        "color=c=blue:s=160x284:r=30:d=0.4333[b2];"
        "color=c=green:s=160x284:r=30:d=1[c];"
        "[a][b1][w][b2][c]concat=n=5:v=1:a=0[v]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,0.5),0.01),0.9,0)':d=3:s=22050",
         "-filter_complex", graph, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def raw_plan(look: str = "photoreal") -> dict:
    stills = []
    clip_refs = ["subject:0", "location:L1"]
    loc_shot = None
    if look == "stylised":
        stills = [{"id": "K1", "kind": "hero_keyframe", "prompt": "The first reference owns the art style only.",
                   "refs": ["ref_shot:1", "subject:0"]}]  # fmt: skip
        clip_refs = ["still:K1", "location:L1"]
        loc_shot = 2
    return {
        "title": "Neon run",
        "trick": "The trick of this ref is colour blocks on the beat so that it pulses.",
        "concept": "The subject sprints through a neon city.",
        "look": look,
        "style_shot": 1 if look == "stylised" else None,
        "style_descriptors": None,
        "hero": {"identity": "short dark hair", "garments": "black hoodie"},
        "aspect": "9:16",
        "duration": 3.0,
        "locations": [{"id": "L1", "prompt": "A neon street at night. No people, no text.", "evidence_shot": loc_shot}],
        "stills": stills,
        "clips": [
            {
                "id": "C1",
                "duration": 6,
                "prompt": "@image1 is the hero; @image2 is the location. Shot 1 (0-3 s): runs. Shot 2 (3-6 s): turns.",
                "refs": clip_refs,
                "slots": [{"start": 0, "end": 3, "label": "run"}, {"start": 3, "end": 6, "label": "turn"}],
            }
        ],
        "edl": {
            "background": "#000000",
            "shots": [
                {"kind": "clip", "ref": "C1", "start": 0, "duration": 1.2, "media_start": 0.4, "rate": 1,
                 "camera_move": "push_in", "camera_amount": 0.1, "grade": "teal_orange", "tint": None,
                 "transition_in": "cut", "transition_s": 0.2, "focus_x": 0.5, "focus_y": 0.4},
                {"kind": "subject", "ref": "0", "start": 1.2, "duration": 0.6, "media_start": 0, "rate": 1,
                 "camera_move": "crash_zoom", "camera_amount": 0.1, "grade": "bw", "tint": "#ff00aa",
                 "transition_in": "flash", "transition_s": 0.1, "focus_x": 0.5, "focus_y": 0.5},
                {"kind": "clip", "ref": "C1", "start": 1.8, "duration": 1.2, "media_start": 99, "rate": 1,
                 "camera_move": "warp", "camera_amount": 0.1, "grade": "nope", "tint": None,
                 "transition_in": "whip", "transition_s": 0.2, "focus_x": 0.5, "focus_y": 0.5},
                {"kind": "clip", "ref": "C9", "start": 2.5, "duration": 0.5, "media_start": 0, "rate": 1,
                 "camera_move": "none", "camera_amount": 0, "grade": "none", "tint": None,
                 "transition_in": "cut", "transition_s": 0.2, "focus_x": 0.5, "focus_y": 0.5},
            ],
            "effects": [
                {"type": "shake", "t": 0.5, "duration": 0.3, "intensity": 0.8, "color": None},
                {"type": "explode", "t": 0.7, "duration": 0.3, "intensity": 0.8, "color": None},
                {"type": "flash", "t": 1.8, "duration": 0.1, "intensity": 1, "color": "#ffffff"},
            ],
            "texts": [
                {"text": "run *faster*", "start": 0.2, "duration": 1.0, "font": "display", "size": 0.1,
                 "color": "#ffffff", "accent": "#ff3355", "uppercase": True, "tracking": 0, "x": 0.5, "y": 0.7,
                 "align": "center", "animation": "slam", "exit": "fade", "stroke": None, "background": None,
                 "blend": "normal"},
            ],
            "finish": {"grain": 0.2, "vignette": 0.3, "scanlines": 0, "letterbox": 0, "chroma": 0, "border": None},
            "audio": {"music": "reference", "music_start": 0, "fade_in": 0, "fade_out": 0.5},
        },
        "notes": "Adaptado a una calle de neón.",
    }  # fmt: skip


# --------------------------------------------------------------------------------------------- análisis


@needs_ffmpeg
async def test_analysis_finds_cuts_flash_and_hits(tmp_path):
    ref = tmp_path / "ref.mp4"
    make_reference(ref)
    result = await analyze(str(ref), tmp_path / "out")
    energy = result["energy"]
    cuts = energy["cuts"]
    assert any(abs(c - 1.0) < 0.05 for c in cuts) and any(abs(c - 2.0) < 0.05 for c in cuts), cuts
    assert any(abs(f["t"] - 1.5) < 0.07 for f in energy["flashes"]), energy["flashes"]
    assert not any(abs(c - 1.5) < 0.05 for c in cuts)  # el destello vuelve al mismo plano: no es corte
    assert len(energy["hits"]) >= 4 and energy["rates"]["cuts_per_s"] > 0
    assert result["probe"]["fps"] == "30/1" and result["aspect"] == "9:16"
    assert (tmp_path / "out" / "analysis.json").is_file() and result["sheets"]
    assert all((tmp_path / "out" / "sheets" / s["file"]).is_file() for s in result["sheets"])
    assert len(result["shot_frames"]) == len(energy["shots"]) and result["music"] == "music.wav"


def test_aspect_snaps_to_known_ratios():
    assert aspect_of(1080, 1920) == "9:16" and aspect_of(1152, 720) == "16:9" and aspect_of(600, 450) == "4:3"


# --------------------------------------------------------------------------------------------- compositor


def test_compose_writes_timed_clips_effects_and_escaped_text():
    edl = Edl.model_validate({
        "aspect": "9:16", "duration": 3,
        "shots": [{"kind": "video", "source": 0, "start": 0, "duration": 2, "media_start": 1.5, "rate": 1.5,
                   "camera": {"move": "push_in", "amount": 0.1}},
                  {"kind": "image", "source": 0, "start": 2, "duration": 1, "transition_in": "fade"}],
        "effects": [{"type": "shake", "t": 0.5}, {"type": "rgb_split", "t": 1}, {"type": "flash", "t": 1.9}],
        "texts": [{"text": "<b>hola</b> *mundo*", "start": 0, "duration": 2, "accent": "#ff0000"}],
        "finish": {"grain": 0.3, "chroma": 0.2},
    })  # fmt: skip
    html = build(edl, ["media/v0.mp4"], ["media/i0.jpg"])
    assert 'data-media-start="1.500"' in html and 'data-playback-rate="1.5"' in html
    assert 'src="media/i0.jpg"' in html and "stage-shake" in html and 'filter id="rgb' in html
    assert "&lt;B&gt;HOLA&lt;/B&gt;" in html and "<b>" not in html.split("<body>")[1].split("<script>")[0]
    assert 'class="w acc"' in html and "data-no-timeline" in html
    # la toma anterior a un fundido sigue debajo mientras dura la transición
    assert 'data-duration="2.200"' in html


def test_edl_problem_checks_media_indices():
    edl = {"duration": 2, "shots": [{"kind": "video", "source": 1, "start": 0, "duration": 2}]}
    assert "clip 2" in edl_problem({"edl": edl, "video_urls": ["https://x/a.mp4"]})
    assert edl_problem({"edl": edl, "video_urls": ["https://x/a.mp4", "https://x/b.mp4"]}) is None
    assert "Invalid edl" in edl_problem({"edl": {"duration": 2, "shots": []}})
    sfx = {**edl, "audio": {"sfx": [{"source": 0, "t": 1}]}}
    assert "sound 1" in edl_problem({"edl": sfx, "video_urls": ["a", "b"]})


# --------------------------------------------------------------------------------------------- plan


def test_plan_becomes_a_canvas_that_ends_in_the_edit_node():
    plan = parse_plan(raw_plan(), subjects=1, shots=3)
    graph = to_graph(plan, ["https://cdn.test/up-0.png"], {}, "https://cdn.test/up-1.wav", "720p")
    check_graph(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["loc-L1"]["data"]["model"] == "higgsfield-ai/soul/cinema"
    clip = nodes["clip-C1"]["data"]["values"]
    assert clip["generate_audio"] is False and clip["duration"] == 6 and clip["aspect_ratio"] == "9:16"
    into_clip = [e["source"] for e in graph["edges"] if e["target"] == "clip-C1"]
    assert into_clip == ["subject-0", "loc-L1"]  # el orden de las aristas es el de @image1, @image2
    edl = nodes["edit"]["data"]["values"]["edl"]
    kinds = [(s["kind"], s["source"]) for s in edl["shots"]]
    assert kinds == [("video", 0), ("image", 0), ("video", 0)]  # el clip C9 que no existe se descarta
    assert edl["shots"][2]["media_start"] <= 6 - 1.2  # el punto de entrada cabe en el clip
    assert edl["shots"][2]["camera"]["move"] == "none" and edl["shots"][2]["grade"]["preset"] == "none"
    assert [e["type"] for e in edl["effects"]] == ["shake", "flash"]
    assert edl["shots"][1]["grade"]["tint"] == "#ff00aa"
    into_edit = [(e["source"], e["targetHandle"]) for e in graph["edges"] if e["target"] == "edit"]
    assert into_edit == [("clip-C1", "video_urls"), ("subject-0", "image_urls"), ("music", "music_url")]
    assert edl_problem({"edl": edl, "video_urls": ["a"], "image_urls": ["b"]}) is None


def test_stylised_plan_starts_with_the_keyframe():
    plan = parse_plan(raw_plan("stylised"), subjects=1, shots=3)
    assert ref_shots_needed(plan) == [1, 2]
    graph = to_graph(plan, ["https://cdn.test/up-0.png"], {1: "https://cdn.test/r1.jpg", 2: "https://cdn.test/r2.jpg"},
                     None, "1080p")  # fmt: skip
    check_graph(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["loc-L1"]["data"]["model"] == "openai/gpt-image-2.6/flare/edit"
    into_loc = [e["source"] for e in graph["edges"] if e["target"] == "loc-L1"]
    assert into_loc == ["still-K1", "ref-2"]
    into_k1 = [e["source"] for e in graph["edges"] if e["target"] == "still-K1"]
    assert into_k1 == ["ref-1", "subject-0"]
    assert "music" not in nodes and nodes["edit"]["data"]["values"]["edl"]["audio"]["fade_out"] == 0


def test_plan_rejects_unknown_references():
    bad = raw_plan()
    bad["clips"][0]["refs"] = ["subject:3"]
    with pytest.raises(PlanError):
        parse_plan(bad, subjects=1, shots=3)
    bad = raw_plan()
    bad["clips"][0]["refs"] = ["ref_shot:9"]
    with pytest.raises(PlanError):
        parse_plan(bad, subjects=1, shots=3)


def test_output_schema_is_strict():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        elif node.get("type") == "array":
            walk(node["items"])

    walk(OUTPUT_FORMAT["schema"])


def test_presets_only_accept_the_gallery_videos():
    url = kmod.presets()[0]["video_url"]
    assert kmod.is_preset_video(url) and kmod.preset_for(url) == "kinetic-tech-edit"
    assert not kmod.is_preset_video("https://static-public-media.higgsfield.ai/other/x.mp4")
    assert not kmod.is_preset_video(url + "?a=1") and not kmod.is_preset_video(url.replace("https", "http"))


# --------------------------------------------------------------------------------------------- rutas


class PlanClaude:
    def __init__(self, plan: dict):
        self.plan = plan
        self.requests: list = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        text = json.dumps(self.plan)
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 9000, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": text}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": {"output_tokens": 3000}}),
            ("message_stop", {"type": "message_stop"}),
        ]  # fmt: skip
        sse = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())


@pytest.fixture
async def kenv(tmp_path, monkeypatch):
    monkeypatch.setattr("hf_studio.routing.renderer_problem", lambda: None)
    fakes = Fakes()
    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        provider_keys={"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_BASE_URL": "https://api.anthropic.test"},
        database_url=f"sqlite+aiosqlite:///{tmp_path}/k.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(fakes))
    claude = PlanClaude(raw_plan())
    async with app.router.lifespan_context(app):
        app.state.assistant_jobs.http_client_factory = lambda: httpx2.AsyncClient(
            transport=httpx2.MockTransport(claude)
        )
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, claude, fakes


async def upload(http, data: bytes, name: str, content_type: str) -> str:
    res = await http.post("/v1/uploads", files={"file": (name, data, content_type)})
    assert res.status_code == 201, res.text
    return res.json()["url"]


@needs_ffmpeg
async def test_project_analyzes_plans_and_builds_a_space(kenv, tmp_path):
    app, http, claude, _ = kenv
    ref_url = await upload(http, make_reference(tmp_path / "ref.mp4"), "ref.mp4", "video/mp4")
    photo = await upload(http, PNG, "me.png", "image/png")
    bad = await http.post("/v1/katana/projects", json={"reference_url": "https://evil.test/x.mp4"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "untrusted_source"
    r = await http.post("/v1/katana/projects", json={"reference_url": ref_url})
    assert r.status_code == 201, r.text
    project = r.json()
    pid = project["id"]
    assert project["analysis"]["energy"]["cuts"] and project["planned"] is False
    sheet = project["analysis"]["sheets"][0]["file"]
    f = await http.get(f"/v1/katana/projects/{pid}/files/sheets/{sheet}")
    assert f.status_code == 200 and f.headers["content-type"] == "image/jpeg"
    assert (await http.get(f"/v1/katana/projects/{pid}/files/sheets/..%2Fref.mp4")).status_code == 404

    ask = {"subject_urls": [photo], "brief": "hazlo épico"}
    unapproved = await http.post(f"/v1/katana/projects/{pid}/plan", json=ask)
    assert unapproved.status_code == 409 and not claude.requests
    quote = (await http.post(f"/v1/katana/projects/{pid}/plan/estimate", json=ask)).json()
    assert (
        quote["max_usd"] > 0
        and quote["options"]["aspect"] == "9:16"
        and quote["options"]["music"] == "reference"
    )
    stranger = await http.post(f"/v1/katana/projects/{pid}/plan",
                               json={**ask, "subject_urls": ["https://evil.test/a.png"], "max_usd": quote["max_usd"]})  # fmt: skip
    assert stranger.status_code == 422 and not claude.requests
    planned = await http.post(f"/v1/katana/projects/{pid}/plan", json={**ask, "max_usd": quote["max_usd"]},
                              headers={"Idempotency-Key": "p1"})  # fmt: skip
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["space_id"] and body["plan"]["title"] == "Neon run" and body["generated_seconds"] == 6
    assert body["cost_usd"] == pytest.approx((9000 * 4 + 3000 * 20) / 1_000_000)
    again = await http.post(f"/v1/katana/projects/{pid}/plan", json={**ask, "max_usd": quote["max_usd"]},
                            headers={"Idempotency-Key": "p1"})  # fmt: skip
    assert again.json()["deduplicated"] is True and len(claude.requests) == 1
    sent = claude.requests[0]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    images = [b for b in sent["messages"][0]["content"] if b["type"] == "image"]
    assert images[-1]["source"] == {"type": "url", "url": photo} and images[0]["source"]["type"] == "base64"
    space = (await http.get(f"/v1/spaces/{body['space_id']}")).json()
    nodes = {n["id"]: n for n in space["graph"]["nodes"]}
    assert nodes["edit"]["data"]["model"] == KATANA_EDIT_MODEL and nodes["music"]["data"]["kind"] == "audio"
    assert nodes["music"]["data"]["url"].startswith("https://cdn.test/")  # la música de la referencia, subida
    listed = (await http.get("/v1/katana/projects")).json()["projects"]
    assert listed[0]["id"] == pid and listed[0]["planned"] is True
    assert (await http.delete(f"/v1/katana/projects/{pid}")).status_code == 204
    assert not kmod.folder(app.state.katana_jobs.settings.storage_dir, pid).exists()


@needs_ffmpeg
async def test_edit_node_renders_and_mixes_the_music(kenv, tmp_path, monkeypatch):
    app, http, _, _ = kenv
    clip = tmp_path / "clip.mp4"
    ffmpeg("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=24:duration=4",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip))  # fmt: skip
    music = tmp_path / "m.wav"
    ffmpeg("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=5", str(music))
    clip_url = await upload(http, clip.read_bytes(), "clip.mp4", "video/mp4")
    music_url = await upload(http, music.read_bytes(), "m.wav", "audio/wav")
    seen: dict = {}

    async def fake_render(self, project: Path, out: Path, total: float) -> None:
        seen["html"] = (project / "index.html").read_text()
        seen["media"] = sorted(p.name for p in (project / "media").iterdir())
        await asyncio.to_thread(ffmpeg, "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                                f"color=c=black:s=108x192:r=30:d={total}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                str(out))  # fmt: skip

    monkeypatch.setattr(KatanaEditJobs, "_render", fake_render)
    edl = {"duration": 2, "shots": [{"kind": "video", "source": 0, "start": 0, "duration": 2, "media_start": 1}],
           "texts": [{"text": "hola", "start": 0, "duration": 1, "font": "mono"}],
           "audio": {"music_start": 0.5, "fade_out": 0.3}}  # fmt: skip
    stranger = await http.post("/v1/generations", json={"model": KATANA_EDIT_MODEL, "max_usd": 0,
                                "input": {"edl": edl, "video_urls": ["https://evil.test/a.mp4"]}})  # fmt: skip
    assert stranger.status_code == 422
    job = (await http.post("/v1/generations", json={"model": KATANA_EDIT_MODEL, "max_usd": 0,
           "input": {"edl": edl, "video_urls": [clip_url], "music_url": music_url}})).json()  # fmt: skip
    assert job["provider"] == "katana" and job["cost_usd"] == 0, job
    await tick(app)
    for _ in range(150):
        await asyncio.sleep(0.1)
        await tick(app)
        async with app.state.sessions() as s:
            state = await s.get(Job, job["id"])
            if state.status in ("completed", "failed"):
                break
    assert state.status == "completed", state.error
    assert seen["media"] == ["v0.mp4"] and 'data-media-start="1.000"' in seen["html"]
    out = Path(app.state.katana_jobs.settings.storage_dir) / "outputs" / state.id / state.files[0]["name"]
    probe = ffmpeg(
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)
    ).split()
    assert probe.count("audio") == 1 and probe.count("video") == 1


async def test_edit_node_with_bad_indices_is_not_quoted(kenv):
    _, http, _, _ = kenv
    edl = {"duration": 2, "shots": [{"kind": "video", "source": 3, "start": 0, "duration": 2}]}
    r = await http.post("/v1/estimate", json={"model": KATANA_EDIT_MODEL, "input": {"edl": edl}})
    assert r.status_code == 200 and not r.json()["options"] and "clip 4" in r.json()["excluded"][0]["reason"]
