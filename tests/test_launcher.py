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
def test_stop_cleans_the_group_even_if_the_parent_already_exited():
    ui = _ui(
        "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])"
    )
    ui.proc.wait()
    ui.stop()  # el hijo vivía en el grupo: killpg lo cierra
    for _ in range(50):
        try:
            os.killpg(ui.proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("the UI group is still alive")


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


async def test_setup_starts_anyway_when_higgsfield_is_unreachable(monkeypatch, tmp_path):
    from hf_studio import setup

    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "ensure_env", lambda interactive: True)

    async def unreachable():
        return cli.UNREACHABLE

    monkeypatch.setattr(cli, "_check_credentials", unreachable)
    done = []

    async def fake_session(fn):
        done.append(fn)

    monkeypatch.setattr(cli, "_with_session", fake_session)
    monkeypatch.chdir(tmp_path)
    assert await cli._setup(interactive=False) == 0 and done == [setup.ensure_ui_key]

    async def invalid():
        return 1

    monkeypatch.setattr(cli, "_check_credentials", invalid)
    assert await cli._setup(interactive=False) == 1
