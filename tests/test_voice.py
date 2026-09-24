from __future__ import annotations

import asyncio
import shutil
import subprocess
from itertools import pairwise

import httpx
import pytest

from hf_studio.api import create_app
from hf_studio.config import Settings
from hf_studio.db import ApiClient, Job, hash_token
from hf_studio.voice import VOICE_MODEL, effect_graph

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="requiere ffmpeg")


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def streams(path) -> list[str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return sorted(out.split())


class FakeElevenLabs:
    def __init__(self, voice_wav: bytes):
        self.voice_wav = voice_wav
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["xi-api-key"] == "el-key"
        path = request.url.path
        if path == "/v2/voices":
            search = request.url.params.get("search")
            voices = [
                {"voice_id": "v_demon", "name": "Demon", "preview_url": "https://x/p.mp3", "labels": {}}
            ]
            return httpx.Response(
                200, json={"voices": [] if search and search.startswith("hfs-") else voices}
            )
        if path == "/v1/shared-voices":
            return httpx.Response(200, json={"voices": [
                {"voice_id": "lib1", "name": "Ghoul", "public_owner_id": "owner1", "gender": "male"}
            ], "has_more": False})  # fmt: skip
        if path == "/v1/voices/add/owner1/lib1":
            return httpx.Response(200, json={"voice_id": "added1"})
        if path == "/v1/user/subscription":
            return httpx.Response(
                200, json={"tier": "starter", "character_count": 1000, "character_limit": 30000}
            )
        if path.startswith("/v1/speech-to-speech/"):
            return httpx.Response(200, content=self.voice_wav, headers={"content-type": "audio/wav"})
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
async def voice_env(tmp_path):
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=3", str(tmp_path / "voice.wav"))
    fake = FakeElevenLabs((tmp_path / "voice.wav").read_bytes())
    settings = Settings(
        hf_api_key="kid:ksecret",
        elevenlabs_api_key="el-key",
        elevenlabs_base_url="https://api.elevenlabs.test",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db",
        storage_dir=tmp_path / "files",
        worker_enabled=False,
    )
    app = create_app(settings, transport=httpx.MockTransport(fake))
    async with app.router.lifespan_context(app):
        async with app.state.sessions() as s:
            owner = ApiClient(name="ui", key_hash=hash_token("hfs_a"), key_prefix="hfs_a")
            s.add(owner)
            await s.flush()
            source = Job(owner_id=owner.id, model="kling-video/v3.0/std/text-to-video", input={}, input_hash="x",
                         status="completed", outputs=[{"kind": "video", "url": "https://cdn.test/v.mp4"}],
                         files=[{"name": "0-video.mp4", "kind": "video", "index": 0}])  # fmt: skip
            s.add(source)
            await s.commit()
            src_dir = tmp_path / "files" / "outputs" / source.id
            src_dir.mkdir(parents=True)
            ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=24:duration=6",
                   "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                   str(src_dir / "0-video.mp4"))  # fmt: skip
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t",
                                     headers={"Authorization": "Bearer hfs_a"}) as http:  # fmt: skip
            yield app, http, fake, source.id


async def test_estimate_uses_segment_length(voice_env):
    _, http, _, src = voice_env
    body = {"source_generation_id": src, "start": 1, "end": 4, "voice_id": "v_demon"}
    est = (await http.post("/v1/voice/estimate", json=body)).json()
    assert est["seconds"] == 3 and est["usd"] == round(3 / 60 * 0.12, 4)
    # El fin se recorta a la duración real del video.
    long = (await http.post("/v1/voice/estimate", json={**body, "end": 60})).json()
    assert long["end"] == pytest.approx(6, abs=0.1)


async def test_voice_change_end_to_end_with_library_voice(voice_env):
    app, http, fake, src = voice_env
    body = {"source_generation_id": src, "start": 1, "end": 3.5, "voice_id": "lib1",
            "public_owner_id": "owner1", "effect": "monster", "expected_seconds": 2.5}  # fmt: skip
    job = await http.post("/v1/voice/changes", json=body, headers={"Idempotency-Key": "k1"})
    assert job.status_code == 202 and job.json()["model"] == VOICE_MODEL
    await asyncio.gather(*app.state.tasks)
    done = (await http.get(f"/v1/generations/{job.json()['id']}")).json()
    assert done["status"] == "completed", done["error"]
    # La voz de la biblioteca se añadió a la cuenta y se convirtió con el id nuevo.
    paths = [c.url.path for c in fake.calls]
    assert "/v1/voices/add/owner1/lib1" in paths and "/v1/speech-to-speech/added1" in paths
    video = await http.get(done["outputs"][0]["file_url"])
    assert video.status_code == 200
    out = app.state.settings.storage_dir / "outputs" / done["id"] / "0-video.mp4"
    assert streams(out) == ["audio", "video"]
    # Repetir con la misma clave no lanza otro cambio.
    again = await http.post("/v1/voice/changes", json=body, headers={"Idempotency-Key": "k1"})
    assert again.status_code == 200 and again.json()["id"] == done["id"]


async def test_voice_lists_and_status(voice_env):
    _, http, _, _ = voice_env
    assert (await http.get("/v1/voice/status")).json()["credits_left"] == 29000
    mine = (await http.get("/v1/voice/voices")).json()["voices"]
    lib = (await http.get("/v1/voice/voices", params={"library": True, "search": "ghoul"})).json()["voices"]
    assert mine[0]["voice_id"] == "v_demon" and lib[0]["public_owner_id"] == "owner1"


async def test_rejects_bad_segments(voice_env):
    _, http, _, src = voice_env
    body = {"source_generation_id": src, "start": 5.9, "end": 6.0, "voice_id": "v_demon"}
    assert (await http.post("/v1/voice/estimate", json=body)).json()["error"]["code"] == "segment_too_short"
    both = {**body, "source_url": "https://cdn.test/v.mp4"}
    assert (await http.post("/v1/voice/estimate", json=both)).status_code == 422


@pytest.mark.parametrize("effect", ["none", "deep", "monster", "ghost"])
def test_effects_are_valid_ffmpeg_graphs(tmp_path, effect):
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=1", str(tmp_path / "in.wav"))
    graph = effect_graph(effect, "0:a", "fx")
    ffmpeg(
        "-i", str(tmp_path / "in.wav"), "-filter_complex", graph, "-map", "[fx]", str(tmp_path / "out.wav")
    )
    assert (tmp_path / "out.wav").stat().st_size > 0


async def test_run_requires_the_quoted_segment(voice_env):
    _, http, fake, src = voice_env
    body = {"source_generation_id": src, "start": 1, "end": 60, "voice_id": "v_demon"}
    unquoted = await http.post("/v1/voice/changes", json=body)
    assert unquoted.json()["error"]["code"] == "quote_required"
    # Se cotizó un tramo de 59 s, pero el video solo da 5 s: no se cobra y hay que volver a cotizar.
    changed = await http.post("/v1/voice/changes", json={**body, "expected_seconds": 59})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "cost_changed"
    assert not [c for c in fake.calls if "speech-to-speech" in c.url.path]


async def test_same_key_for_another_request_is_a_conflict(voice_env):
    app, http, _, src = voice_env
    body = {"source_generation_id": src, "start": 1, "end": 2, "voice_id": "v_demon", "expected_seconds": 1}
    assert (
        await http.post("/v1/voice/changes", json=body, headers={"Idempotency-Key": "k"})
    ).status_code == 202
    other = await http.post(
        "/v1/voice/changes", json={**body, "effect": "ghost"}, headers={"Idempotency-Key": "k"}
    )
    assert other.status_code == 409 and other.json()["error"]["code"] == "idempotency_conflict"
    await asyncio.gather(*app.state.tasks)


async def test_arbitrary_urls_are_not_opened(voice_env):
    _, http, _, _ = voice_env
    body = {"source_url": "https://169.254.169.254/latest/meta-data", "voice_id": "v_demon"}
    r = await http.post("/v1/voice/estimate", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "untrusted_source"


def test_shorter_converted_voice_only_ducks_while_it_sounds(tmp_path):
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=24:duration=6", "-f", "lavfi",
           "-i", "sine=frequency=880:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-shortest", str(tmp_path / "src.mp4"))  # fmt: skip
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(tmp_path / "voice.wav"))
    from hf_studio.voice import VoiceChangeIn, mix_command

    body = VoiceChangeIn(source_url="https://x/v.mp4", voice_id="v", start=2, end=5)
    subprocess.run(mix_command(str(tmp_path / "src.mp4"), tmp_path / "voice.wav", tmp_path / "out.mp4",
                               2, 5, body, voiced=1.0), check=True)  # fmt: skip

    def hz(start: float) -> float:
        """Frecuencia dominante por cruces por cero: 220 Hz es la voz nueva, 880 Hz el original."""
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(tmp_path / "out.mp4"), "-ss", str(start), "-t", "0.5",
                              "-f", "s16le", "-ac", "1", "-ar", "8000", "-"], capture_output=True, check=True).stdout  # fmt: skip
        x = memoryview(pcm).cast("h")
        return sum((a < 0) != (b < 0) for a, b in pairwise(x)) / 2 / 0.5

    # Voz nueva de 1 s (2 → 3 s) con el original apagado; después vuelve el original, no un hueco mudo.
    assert abs(hz(2.3) - 220) < 30
    assert abs(hz(3.5) - 880) < 60
