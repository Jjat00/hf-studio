"""`hf-studio start`: la UI caída detiene todo y el cierre limpia su grupo de procesos."""

import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from hf_studio import cli, launcher


def _ui(code: str) -> launcher.UI:
    """Una UI de mentira: python en vez de pnpm, con el mismo grupo o job que la de verdad."""
    ui = launcher.UI.__new__(launcher.UI)
    ui.stopping, ui.job = threading.Event(), None
    flags = {"start_new_session": True} if os.name != "nt" else {}
    ui.proc = subprocess.Popen([sys.executable, "-c", code], **flags)
    return ui


@pytest.mark.parametrize("exit_code", [0, 3])
def test_a_ui_that_exits_on_its_own_stops_the_api(monkeypatch, exit_code):
    raised = []
    monkeypatch.setattr(launcher.signal, "raise_signal", raised.append)
    crashed = threading.Event()
    _ui(f"raise SystemExit({exit_code})").watch(crashed)
    assert crashed.is_set() and raised == [signal.SIGINT]


def test_a_ui_we_stopped_is_not_a_crash(monkeypatch):
    monkeypatch.setattr(launcher.signal, "raise_signal", lambda s: pytest.fail("stopped the API"))
    ui = _ui("import time; time.sleep(30)")
    crashed = threading.Event()
    watcher = threading.Thread(target=ui.watch, args=(crashed,))
    watcher.start()
    ui.stop()
    watcher.join(10)
    assert not crashed.is_set()


@pytest.mark.skipif(os.name == "nt", reason="grupos de procesos POSIX")
def test_stop_cleans_the_group_even_if_the_parent_already_exited(tmp_path):
    pid_file = tmp_path / "child.pid"
    child = "import time; time.sleep(60)"
    ui = _ui(
        "import subprocess, sys;"
        f"p = subprocess.Popen([sys.executable, '-c', {child!r}]);"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))"
    )
    ui.proc.wait()
    pid = int(pid_file.read_text())
    ui.stop()  # el hijo vivía en el grupo: killpg lo cierra
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("the UI child is still alive")


@pytest.mark.skipif(os.name != "nt", reason="Job Object de Windows")
def test_windows_job_closes_children_even_after_the_parent_exited(tmp_path, monkeypatch):
    """La UI real (creada suspendida y metida al job antes de correr) con python haciendo de pnpm."""
    pid_file = tmp_path / "child.pid"
    child = "import time; time.sleep(60)"
    script = tmp_path / "fake_pnpm.py"
    script.write_text(
        "import subprocess, sys\n"
        f"p = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
    )
    real_popen = subprocess.Popen
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda cmd, **kw: real_popen([sys.executable, str(script)], **kw)
    )
    ui = launcher.UI("pnpm")
    assert ui.job is not None
    ui.proc.wait(20)  # el padre ya salió; el hijo sigue vivo dentro del job
    pid = pid_file.read_text()
    ui.stop()
    time.sleep(1)
    alive = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False)
    assert pid not in alive.stdout


def test_start_fails_cleanly_when_the_ui_cannot_start(monkeypatch, capsys):
    def broken(pnpm):
        raise OSError("could not resume the web UI process 42")

    monkeypatch.setattr(launcher, "UI", broken)
    monkeypatch.setattr(launcher, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0}))
    assert launcher.start(api_only=False, setup_ok=lambda: 0) == 1
    assert "could not resume" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="Job Object de Windows")
def test_a_ui_that_cannot_be_resumed_is_killed(monkeypatch):
    def fail(self, pid):
        raise OSError("could not resume")

    monkeypatch.setattr(launcher._WindowsJob, "resume", fail)
    real_popen = subprocess.Popen
    procs = []
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda cmd, **kw: (
            procs.append(real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kw)) or procs[-1]
        ),
    )
    with pytest.raises(OSError):
        launcher.UI("pnpm")
    assert procs[0].poll() is not None  # no quedó suspendido


def test_setup_starts_anyway_when_higgsfield_is_unreachable(monkeypatch, tmp_path):
    from hf_studio import setup

    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "ensure_env", lambda interactive, validate: True)

    async def unreachable(key=None):
        return cli.UNREACHABLE

    monkeypatch.setattr(cli, "_check_credentials", unreachable)
    done = []

    async def fake_session(fn):
        done.append(fn)

    monkeypatch.setattr(cli, "_with_session", fake_session)
    monkeypatch.chdir(tmp_path)
    assert cli._setup(interactive=False) == 0 and done == [setup.ensure_ui_key]

    async def invalid(key=None):
        return 1

    monkeypatch.setattr(cli, "_check_credentials", invalid)
    assert cli._setup(interactive=False) == 1


def test_a_rejected_saved_key_is_asked_again_in_a_terminal(monkeypatch, tmp_path):
    from hf_studio import setup

    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    (tmp_path / ".env").write_text("HF_API_KEY=wrong:key\n")
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setattr(setup, "ensure_env", lambda interactive, validate: True)

    async def check(key=None):
        current = key or setup.read_env(tmp_path / ".env")["HF_API_KEY"]
        return 0 if current == "good:key" else 1

    monkeypatch.setattr(cli, "_check_credentials", check)
    monkeypatch.setattr(setup, "masked_input", lambda prompt: "good:key")

    async def fake_session(fn):
        return None

    monkeypatch.setattr(cli, "_with_session", fake_session)
    monkeypatch.chdir(tmp_path)
    assert cli._setup(interactive=True) == 0
    assert setup.read_env(tmp_path / ".env")["HF_API_KEY"] == "good:key"


def _fake_ffmpeg(folder, filters: str):
    """ffmpeg y ffprobe de mentira que responden `-filters` con el texto dado."""
    folder.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        exe = folder / name
        exe.write_text(f"#!/bin/sh\necho '{filters}'\n")
        exe.chmod(0o755)
    return folder


@pytest.mark.skipif(os.name == "nt", reason="ejecutables de shell")
def test_macos_puts_homebrew_ffmpeg_full_first_even_if_it_is_already_in_path(monkeypatch, tmp_path, capsys):
    plain = _fake_ffmpeg(tmp_path / "plain", " ..C volume  A->A")
    full = _fake_ffmpeg(tmp_path / "full", " ..C rubberband  A->A")
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "BREW_FFMPEG_FULL", (str(full),))
    monkeypatch.setenv("PATH", os.pathsep.join([str(plain), str(full), "/usr/bin", "/bin"]))
    launcher.check_ffmpeg()
    assert launcher.shutil.which("ffmpeg") == str(full / "ffmpeg")
    assert launcher.shutil.which("ffprobe") == str(full / "ffprobe")
    assert os.environ["PATH"].split(os.pathsep).count(str(full)) == 1
    assert capsys.readouterr().out == ""


def test_warns_when_ffmpeg_has_no_rubberband(monkeypatch, capsys):
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "BREW_FFMPEG_FULL", ())
    monkeypatch.setattr(launcher.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        launcher.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": " ... volume A->A"})
    )
    launcher.check_ffmpeg()
    assert "brew install ffmpeg-full" in capsys.readouterr().out
