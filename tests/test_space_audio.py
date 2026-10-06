"""Nodos de audio de Spaces (voz, efecto, música): modelos del catálogo que corre ElevenLabs desde el worker."""

from __future__ import annotations

import asyncio
import json
import shutil

import httpx
import pytest
from sqlalchemy import select

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, Sound, hash_token

from .test_routing import FIXTURES, Fakes, tick
from .test_voice import FakeElevenLabs, ffmpeg

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


@pytest.fixture
async def audio_env(tmp_path):
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(tmp_path / "voice.wav"))
    eleven = FakeElevenLabs((tmp_path / "voice.wav").read_bytes())
    fakes = Fakes()

    def route(request: httpx.Request) -> httpx.Response:
        return eleven(request) if request.url.host == "api.elevenlabs.test" else fakes(request)

    settings = Settings(
        _env_file=None, hf_api_key="kid:ksecret", hf_base_url="https://api.higgsfield.test",
        elevenlabs_api_key="el-key", elevenlabs_base_url="https://api.elevenlabs.test",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/a.db", storage_dir=tmp_path / "files", worker_enabled=False,
    )  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(route))
    async with app.router.lifespan_context(app):
        for name in ("apimart", "kie"):
            app.state.prices.store(name, json.loads((FIXTURES / f"prices_{name}.json").read_text()))
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, eleven, fakes


async def finish(app, job_id):
    await tick(app)
    for _ in range(100):
        await asyncio.sleep(0.05)
        await tick(app)
        async with app.state.sessions() as s:
            job = await s.get(Job, job_id)
            if job.status in ("completed", "failed"):
                return job
    raise AssertionError("did not finish")


async def test_a_voiceover_node_is_quoted_runs_and_lands_in_the_library(audio_env):
    app, http, eleven, _ = audio_env
    body = {"model": "elevenlabs/tts", "input": {"prompt": "Hola desde Spaces", "voice_id": "v_demon"}}
    est = (await http.post("/v1/estimate", json=body)).json()
    assert (
        est["provider"] == "elevenlabs"
        and est["kind"] == "approx"
        and est["usd"] == round(17 / 1000 * 0.10, 6)
    )
    job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
    assert job["provider"] == "elevenlabs"
    done = await finish(app, job["id"])
    assert done.status == "completed", done.error
    assert done.files[0]["kind"] == "audio" and done.files[0]["name"].endswith(".mp3")
    assert any(c.url.path == "/v1/text-to-speech/v_demon" for c in eleven.calls)
    async with app.state.sessions() as s:
        sound = await s.scalar(select(Sound).where(Sound.job_id == done.id))
    assert sound is not None and sound.kind == "speech" and sound.text == "Hola desde Spaces"


async def test_music_and_effects_use_their_prompt(audio_env):
    app, http, eleven, _ = audio_env
    for model, extra, path in (
        ("elevenlabs/sfx", {"duration_seconds": 3}, "/v1/sound-generation"),
        ("elevenlabs/music-gen", {"seconds": 10, "force_instrumental": True}, "/v1/music"),
    ):
        body = {"model": model, "input": {"prompt": "dark drones", **extra}}
        est = (await http.post("/v1/estimate", json=body)).json()
        job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
        assert (await finish(app, job["id"])).status == "completed"
        sent = json.loads(next(c for c in reversed(eleven.calls) if c.url.path == path).content)
        assert sent.get("text", sent.get("prompt")) == "dark drones"


async def test_a_generated_audio_can_be_chained_as_wav(audio_env):
    """El MP3 de ElevenLabs se sube como WAV: Higgsfield no acepta MP3."""
    app, http, _, fakes = audio_env
    body = {"model": "elevenlabs/sfx", "input": {"prompt": "door creak", "duration_seconds": 2}}
    est = (await http.post("/v1/estimate", json=body)).json()
    job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
    await finish(app, job["id"])
    used = await http.post(f"/v1/generations/{job['id']}/outputs/0/use")
    assert used.status_code == 200 and used.json()["content_type"] == "audio/wav"
    assert fakes.uploads[-1][:4] == b"RIFF"


async def test_audio_nodes_need_elevenlabs(tmp_path):
    settings = Settings(_env_file=None, hf_api_key="kid:ksecret", elevenlabs_api_key="",
                        database_url=f"sqlite+aiosqlite:///{tmp_path}/n.db", storage_dir=tmp_path / "f",
                        worker_enabled=False)  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(Fakes()))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            res = await http.post(
                "/v1/estimate", json={"model": "elevenlabs/music-gen", "input": {"prompt": "x"}}
            )
    assert res.status_code == 503


async def test_two_simultaneous_reuses_of_the_same_mp3_both_succeed(audio_env):
    """Revisión 62 (H1)."""
    app, http, _, _ = audio_env
    body = {"model": "elevenlabs/sfx", "input": {"prompt": "rain", "duration_seconds": 2}}
    est = (await http.post("/v1/estimate", json=body)).json()
    job = (await http.post("/v1/generations", json={**body, "max_usd": est["usd"]})).json()
    await finish(app, job["id"])
    a, b = await asyncio.gather(*[http.post(f"/v1/generations/{job['id']}/outputs/0/use") for _ in range(2)])
    assert a.status_code == b.status_code == 200
    folder = app.state.settings.storage_dir / "outputs" / job["id"]
    assert not [p for p in folder.iterdir() if ".tmp" in p.name]


async def test_an_extra_text_field_is_ignored_not_a_crash(audio_env):
    """Revisión 62 (H3)."""
    _, http, _, _ = audio_env
    res = await http.post(
        "/v1/estimate", json={"model": "elevenlabs/sfx", "input": {"prompt": "rain", "text": "x"}}
    )
    assert res.status_code == 200 and res.json()["provider"] == "elevenlabs"


async def test_a_run_without_elevenlabs_fails_the_step(tmp_path):
    """Revisión 62 (H2): sin la clave, el paso de audio falla visible y la corrida termina."""
    from hf_studio.db import SpaceRun

    settings = Settings(_env_file=None, hf_api_key="kid:ksecret", elevenlabs_api_key="",
                        database_url=f"sqlite+aiosqlite:///{tmp_path}/r.db", storage_dir=tmp_path / "f",
                        worker_enabled=False)  # fmt: skip
    app = create_app(settings, transport=httpx.MockTransport(Fakes()))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            s.add(ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a"))
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            node = {"id": "m", "type": "generator", "position": {"x": 0, "y": 0},
                    "data": {"model": "elevenlabs/music-gen", "values": {"prompt": "drones"}, "runs": []}}  # fmt: skip
            space = (await http.post("/v1/spaces", json={"graph": {"nodes": [node]}})).json()
            run = (
                await http.post(
                    f"/v1/spaces/{space['id']}/runs",
                    json={"mode": "workflow", "version": space["version"], "max_total_usd": 1},
                )
            ).json()
            await app.state.space_runner.tick(run["id"])  # el paso falla
            assert not await app.state.space_runner.tick(run["id"])  # y la corrida termina
            async with app.state.sessions() as s:
                state = await s.get(SpaceRun, run["id"])
            assert state.status == "failed" and "ELEVENLABS_API_KEY" in state.nodes["m"]["error"]
