"""Herramientas locales (fotograma, combinar, mezclar): modelos gratis que el worker corre con ffmpeg."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest

from hf_studio.audio import duration, has_audio
from hf_studio.db import Job

from .test_routing import Fakes, env, tick  # noqa: F401  (fixture compartida)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def make_video(path, seconds=1, audio=True, size="160x120"):
    args = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate=10:duration={seconds}",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        *(["-c:a", "aac"] if audio else []),
        "-shortest",
        str(path),
    ]
    subprocess.run(args, check=True)
    return path.read_bytes()


def make_audio(path, seconds=1):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
                    str(path)], check=True)  # fmt: skip
    return path.read_bytes()


async def upload(http, data, name, content_type):
    res = await http.post("/v1/uploads", files={"file": (name, data, content_type)})
    assert res.status_code == 201, res.text
    return res.json()["url"]


async def run_tool(app, http, model, input_):
    job = (await http.post("/v1/generations", json={"model": model, "input": input_, "max_usd": 0})).json()
    assert job["provider"] == "hf-studio" and job["cost_usd"] == 0, job
    await tick(app)  # envío: arranca ffmpeg en segundo plano
    for _ in range(100):
        await asyncio.sleep(0.1)
        await tick(app)
        async with app.state.sessions() as s:
            state = await s.get(Job, job["id"])
            if state.status in ("completed", "failed"):
                return state
    raise AssertionError("the tool did not finish")


async def test_tools_are_free_catalog_models(env, tmp_path):  # noqa: F811
    _, http, _ = env
    a = await upload(http, make_video(tmp_path / "a.mp4"), "a.mp4", "video/mp4")
    b = await upload(http, make_video(tmp_path / "b.mp4"), "b.mp4", "video/mp4")
    est = (
        await http.post("/v1/estimate", json={"model": "hf-studio/combine", "input": {"video_urls": [a, b]}})
    ).json()
    assert est["provider"] == "hf-studio" and est["usd"] == 0 and est["kind"] == "exact"
    models = {m["id"]: m for m in (await http.get("/v1/models")).json()["models"]}
    assert models["hf-studio/frame"]["inputs"] == ["video"] and models["hf-studio/frame"]["output"] == "image"
    names = [p["name"] for p in (await http.get("/v1/providers?check=false")).json()["providers"]]
    assert "hf-studio" not in names  # no es un proveedor que se configure


async def test_tools_only_open_your_own_files(env):  # noqa: F811
    _, http, _ = env
    res = await http.post(
        "/v1/generations",
        json={"model": "hf-studio/frame", "input": {"video_url": "https://evil.test/x.mp4"}, "max_usd": 0},
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "untrusted_source"


async def test_frame_combine_and_mix(env, tmp_path):  # noqa: F811
    app, http, _ = env
    with_audio = await upload(http, make_video(tmp_path / "a.mp4", 1, True), "a.mp4", "video/mp4")
    silent = await upload(http, make_video(tmp_path / "b.mp4", 2, False, "320x240"), "b.mp4", "video/mp4")
    music = await upload(http, make_audio(tmp_path / "m.wav", 3), "m.wav", "audio/wav")

    frame = await run_tool(app, http, "hf-studio/frame", {"video_url": with_audio, "which": "last"})
    assert frame.status == "completed", frame.error
    png = app.state.settings.storage_dir / "outputs" / frame.id / frame.files[0]["name"]
    assert frame.files[0]["kind"] == "image" and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    combined = await run_tool(app, http, "hf-studio/combine", {"video_urls": [with_audio, silent]})
    assert combined.status == "completed", combined.error
    out = str(app.state.settings.storage_dir / "outputs" / combined.id / combined.files[0]["name"])
    assert 2.7 < (await duration(out)) < 3.4 and await has_audio(out)  # 1 s + 2 s, con el silencio añadido

    mixed = await run_tool(app, http, "hf-studio/mix", {"video_url": silent, "audio_urls": [music]})
    assert mixed.status == "completed", mixed.error
    out = str(app.state.settings.storage_dir / "outputs" / mixed.id / mixed.files[0]["name"])
    assert await has_audio(out) and 1.8 < (await duration(out)) < 2.3  # dura lo que el video


async def _start_frame(app, http, tmp_path, gate):
    """Un fotograma cuyo ffmpeg queda «en curso» hasta abrir `gate` (tarea controlada)."""
    video = await upload(http, make_video(tmp_path / "a.mp4"), "a.mp4", "video/mp4")
    tools = app.state.local_tools

    async def slow_frame(folder, a):
        (folder / "partial.png").write_bytes(b"x")
        await gate.wait()
        raise AssertionError("should have been canceled")

    tools._frame = slow_frame
    job = (
        await http.post(
            "/v1/generations", json={"model": "hf-studio/frame", "input": {"video_url": video}, "max_usd": 0}
        )
    ).json()
    await tick(app)
    async with app.state.sessions() as s:
        state = await s.get(Job, job["id"])
    assert state.status == "in_progress"
    return state


async def test_a_running_tool_can_be_canceled(env, tmp_path):  # noqa: F811
    """Revisión 58 (H1/H2): la tarea local se detiene y no deja archivos de trabajo."""
    app, http, _ = env
    state = await _start_frame(app, http, tmp_path, asyncio.Event())
    res = await http.post(f"/v1/generations/{state.id}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "canceled"
    tools = app.state.local_tools
    assert state.hf_request_id not in tools.tasks and not (tools.work / state.hf_request_id).exists()


async def test_an_expired_tool_stops_working(env, tmp_path):  # noqa: F811
    from datetime import timedelta

    from sqlalchemy import update

    from hf_studio.db import utcnow

    app, http, _ = env
    state = await _start_frame(app, http, tmp_path, asyncio.Event())
    async with app.state.sessions() as s:
        await s.execute(
            update(Job)
            .where(Job.id == state.id)
            .values(created_at=utcnow() - timedelta(hours=2), version=Job.version + 1)
        )
        await s.commit()
    await app.state.worker.expire()
    async with app.state.sessions() as s:
        assert (await s.get(Job, state.id)).status == "timed_out"
    assert state.hf_request_id not in app.state.local_tools.tasks


async def test_leftovers_of_a_previous_process_are_swept(env):  # noqa: F811
    app, _, _ = env
    tools = app.state.local_tools
    (tools.work / "tool-old").mkdir(parents=True)
    (tools.work / "tool-old" / "0-video.mp4").write_bytes(b"x")
    tools.sweep()
    assert not tools.work.exists()


async def test_a_tool_is_never_completed_without_its_saved_output(env, tmp_path):  # noqa: F811
    """Revisión 58 (H3): sin copia guardada falla; y se guarda aunque download_outputs esté apagado."""
    app, http, _ = env
    video = await upload(http, make_video(tmp_path / "a.mp4"), "a.mp4", "video/mp4")
    app.state.settings.download_outputs = False
    done = await run_tool(app, http, "hf-studio/frame", {"video_url": video, "which": "first"})
    assert done.status == "completed" and done.files and done.files[0]["kind"] == "image"

    tools = app.state.local_tools

    async def broken(url, dest):
        raise OSError("simulated disk error")

    tools.download = broken
    failed = await run_tool(app, http, "hf-studio/frame", {"video_url": video, "which": "last"})
    assert failed.status == "failed" and "save" in failed.error and failed.files == []


async def test_canceling_while_the_worker_polls_ends_canceled(env, tmp_path):  # noqa: F811
    """Revisión 59: un sondeo a la vez que la cancelación no la convierte en un fallo por reinicio."""
    app, http, _ = env
    state = await _start_frame(app, http, tmp_path, asyncio.Event())
    tools = app.state.local_tools
    original = tools.cancel_job

    async def cancel_and_poll(request_id, cancel_url=None):
        await original(request_id, cancel_url)
        await tick(app)  # el worker sondea justo ahora y guarda primero

    tools.cancel_job = cancel_and_poll
    res = await http.post(f"/v1/generations/{state.id}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "canceled"
    async with app.state.sessions() as s:
        assert (await s.get(Job, state.id)).status == "canceled"


async def test_a_poll_that_saves_in_progress_meanwhile_does_not_block_canceling(env, tmp_path):  # noqa: F811
    """Revisión 60: un sondeo que empezó antes y guarda `in_progress` durante la cancelación."""
    from sqlalchemy import update

    app, http, _ = env
    state = await _start_frame(app, http, tmp_path, asyncio.Event())
    tools = app.state.local_tools
    original = tools.cancel_job

    async def cancel_while_poll_saves(request_id, cancel_url=None):
        await original(request_id, cancel_url)
        async with app.state.sessions() as s:  # lo que escribe un sondeo anterior: sigue en curso
            await s.execute(
                update(Job).where(Job.id == state.id).values(status="in_progress", version=Job.version + 1)
            )
            await s.commit()

    tools.cancel_job = cancel_while_poll_saves
    res = await http.post(f"/v1/generations/{state.id}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "canceled"
    async with app.state.sessions() as s:
        assert (await s.get(Job, state.id)).status == "canceled"


async def test_a_tool_that_finished_meanwhile_is_not_reported_as_canceled(env, tmp_path):  # noqa: F811
    from sqlalchemy import update

    app, http, _ = env
    state = await _start_frame(app, http, tmp_path, asyncio.Event())
    tools = app.state.local_tools
    original = tools.cancel_job

    async def cancel_while_it_completes(request_id, cancel_url=None):
        await original(request_id, cancel_url)
        async with app.state.sessions() as s:
            await s.execute(
                update(Job).where(Job.id == state.id).values(status="completed", version=Job.version + 1)
            )
            await s.commit()

    tools.cancel_job = cancel_while_it_completes
    res = await http.post(f"/v1/generations/{state.id}/cancel")
    assert res.status_code == 409


async def test_a_video_output_gives_its_last_frame_and_audio(env, tmp_path):  # noqa: F811
    """Fase 4a: `use_output?as=last_frame|audio` sube el último fotograma o el audio de un video propio."""
    app, http, _ = env
    a = await upload(http, make_video(tmp_path / "a.mp4", 1, True), "a.mp4", "video/mp4")
    silent = await upload(http, make_video(tmp_path / "b.mp4", 1, False), "b.mp4", "video/mp4")
    with_audio = await run_tool(app, http, "hf-studio/combine", {"video_urls": [a, a]})
    frame = await http.post(f"/v1/generations/{with_audio.id}/outputs/0/use?as=last_frame")
    assert frame.status_code == 200 and frame.json()["content_type"] == "image/png", frame.text
    audio = await http.post(f"/v1/generations/{with_audio.id}/outputs/0/use?as=audio")
    assert audio.status_code == 200 and audio.json()["kind"] == "audio"
    again = await http.post(f"/v1/generations/{with_audio.id}/outputs/0/use?as=last_frame")
    assert again.json()["url"] == frame.json()["url"]  # una copia por salida derivada
    still = await run_tool(app, http, "hf-studio/frame", {"video_url": silent})
    res = await http.post(f"/v1/generations/{still.id}/outputs/0/use?as=audio")
    assert res.status_code == 422 and res.json()["error"]["code"] == "not_a_video"
