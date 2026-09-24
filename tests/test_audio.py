from __future__ import annotations

import shutil
import subprocess

import pytest

from hf_studio.audio import MUXED, NO_SOURCE_AUDIO, apply_to_files, duration

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="requiere ffmpeg")


def make(path, seconds, audio):
    args = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=160x120:rate=24:duration={seconds}",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
    subprocess.run([*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def streams(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return sorted(out.split())


async def test_muxes_source_audio_and_keeps_generated_copy(tmp_path):
    make(tmp_path / "0-video.mp4", 2, audio=False)
    make(tmp_path / "src.mp4", 3, audio=True)
    files = [{"name": "0-video.mp4", "kind": "video", "size": 1, "index": 0}]
    [f] = await apply_to_files(files, tmp_path, str(tmp_path / "src.mp4"))
    assert f["audio"] == MUXED and f["size"] == (tmp_path / "0-video.mp4").stat().st_size
    assert streams(tmp_path / "0-video.mp4") == ["audio", "video"]
    assert streams(tmp_path / "0-video.generated.mp4") == ["video"]
    # Repetirlo no vuelve a mezclar ni pisa la copia generada.
    assert (await apply_to_files([f], tmp_path, str(tmp_path / "src.mp4")))[0]["audio"] == MUXED


async def test_source_without_audio_leaves_result_untouched(tmp_path):
    make(tmp_path / "0-video.mp4", 2, audio=True)
    make(tmp_path / "src.mp4", 2, audio=False)
    [f] = await apply_to_files(
        [{"name": "0-video.mp4", "kind": "video"}], tmp_path, str(tmp_path / "src.mp4")
    )
    assert f["audio"] == NO_SOURCE_AUDIO
    assert streams(tmp_path / "0-video.mp4") == ["audio", "video"]


async def test_shorter_source_audio_never_cuts_the_video(tmp_path):
    make(tmp_path / "0-video.mp4", 4, audio=False)
    make(tmp_path / "src.mp4", 2, audio=True)
    [f] = await apply_to_files(
        [{"name": "0-video.mp4", "kind": "video"}], tmp_path, str(tmp_path / "src.mp4")
    )
    assert f["audio"] == MUXED
    assert abs(await duration(str(tmp_path / "0-video.mp4")) - 4) < 0.1
