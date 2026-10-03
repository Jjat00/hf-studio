"""Puesta en marcha: `.env`, clave de la UI y comandos para conectar agentes."""

import json
import os
import shlex
import stat

import pytest
from sqlalchemy import select

from hf_studio import setup
from hf_studio.db import ApiClient, hash_token, init_db, make_engine, make_sessionmaker


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / ".env.example").write_text("# Required\nHF_API_KEY=\nELEVENLABS_API_KEY=\n")
    (tmp_path / "web" / ".env.example").write_text("HF_STUDIO_URL=http://127.0.0.1:8787\nHF_STUDIO_TOKEN=\n")
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    monkeypatch.setattr(setup, "ENV_EXAMPLE", tmp_path / ".env.example")
    monkeypatch.setattr(setup, "WEB_ENV", tmp_path / "web" / ".env.local")
    monkeypatch.setattr(setup, "WEB_ENV_EXAMPLE", tmp_path / "web" / ".env.example")
    for var in (
        "HF_API_KEY",
        "HF_API_KEY_ID",
        "HF_API_KEY_SECRET",
        "ELEVENLABS_API_KEY",
        "APIMART_API_KEY",
        "KIE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
async def session(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    await init_db(engine)
    async with make_sessionmaker(engine)() as s:
        yield s
    await engine.dispose()


def test_set_env_replaces_active_or_commented_lines_and_appends_new_ones(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nHF_API_KEY=\n# HF_API_KEY_ID=\n")
    setup.set_env(env, "HF_API_KEY", "id:secret")
    setup.set_env(env, "HF_API_KEY_ID", "abc")
    setup.set_env(env, "NEW", "1")
    assert setup.read_env(env) == {"HF_API_KEY": "id:secret", "HF_API_KEY_ID": "abc", "NEW": "1"}
    assert env.read_text().startswith("# comment\n")


def test_first_run_copies_the_example_and_asks_for_the_keys(repo, monkeypatch):
    answers = iter(["id:secret", "", "am-key", ""])  # Higgsfield sí, ElevenLabs no, APIMart sí, KIE no
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: next(answers))
    assert setup.ensure_env(interactive=True)
    values = setup.read_env(repo / ".env")
    assert values["HF_API_KEY"] == "id:secret" and values["ELEVENLABS_API_KEY"] == ""
    assert values["APIMART_API_KEY"] == "am-key" and "KIE_API_KEY" not in values


def test_without_a_terminal_it_never_prompts(repo, monkeypatch):
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: pytest.fail("prompted"))
    assert not setup.ensure_env(interactive=False)
    (repo / ".env").write_text("HF_API_KEY=id:secret\n")
    assert setup.ensure_env(interactive=False)


async def test_ui_key_is_created_once_and_sees_everything(repo, session):
    assert await setup.ensure_ui_key(session)
    token = setup.read_env(repo / "web" / ".env.local")["HF_STUDIO_TOKEN"]
    client = await session.scalar(select(ApiClient).where(ApiClient.key_hash == hash_token(token)))
    assert client.name == "web-ui" and client.sees_all
    assert not await setup.ensure_ui_key(session)  # la clave sigue siendo válida: no se toca


async def test_rotating_a_key_keeps_the_client_and_its_generations(session):
    first = await setup.rotate_key(session, "codex")
    old = await session.scalar(select(ApiClient).where(ApiClient.name == "codex"))
    old.revoked_at = old.created_at
    await session.commit()
    second = await setup.rotate_key(session, "codex")
    clients = list(await session.scalars(select(ApiClient).where(ApiClient.name == "codex")))
    assert len(clients) == 1 and clients[0].id == old.id and clients[0].revoked_at is None
    assert clients[0].key_hash == hash_token(second) != hash_token(first)


def test_connect_prints_the_command_when_the_cli_is_missing(monkeypatch, capsys):
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    setup.connect("codex", "hfs_x-e1", install=True)
    out = capsys.readouterr().out
    assert (
        f"codex mcp add hf-studio --env HF_STUDIO_URL={setup.API_URL} --env HF_STUDIO_TOKEN=hfs_x-e1" in out
    )
    assert out.rstrip().endswith("hf-studio mcp")


@pytest.mark.skipif(os.name == "nt", reason="comillas POSIX")
def test_printed_commands_are_safe_to_paste_in_a_shell(monkeypatch, capsys, tmp_path):
    weird = tmp_path / "a space" / "$HOME" / "it's"
    monkeypatch.setattr(setup, "ROOT", weird)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    setup.connect("claude-code", "hfs_x", install=True)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert shlex.split(line)[-5:] == ["run", "--directory", str(weird), "hf-studio", "mcp"]
    assert "'" in line and '"$HOME"' not in line  # comillas simples: la shell no expande $HOME


def test_windows_commands_are_literal_in_powershell(monkeypatch):
    monkeypatch.setattr(setup.os, "name", "nt")
    line = setup.shell_join(
        ["uv", "--directory", r"C:\Users\Jaime Jjat\hf-studio", "HF_STUDIO_TOKEN=hfs_x-1"]
    )
    assert line == r"uv --directory 'C:\Users\Jaime Jjat\hf-studio' HF_STUDIO_TOKEN=hfs_x-1"
    for risky in (r"C:\Work&Stuff\a^b", r"C:\%USERNAME%\x", r"C:\$env\x", r"C:\it's"):
        quoted = setup.shell_join([risky])
        assert quoted.startswith("'") and quoted.endswith("'")
        assert quoted[1:-1].replace("''", "'") == risky


def test_a_failed_registration_is_reported(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(setup.subprocess, "run", lambda cmd, check: type("R", (), {"returncode": 1}))
    assert setup.connect("codex", "hfs_x", install=True) == 1


def test_connect_runs_the_agent_cli_when_available(monkeypatch):
    ran = []
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        setup.subprocess, "run", lambda cmd, check: ran.append(cmd) or type("R", (), {"returncode": 0})
    )
    setup.connect("claude-code", "hfs_x", install=True)
    assert ran[0][:6] == ["claude", "mcp", "add", "hf-studio", "--scope", "user"]
    assert "HF_STUDIO_TOKEN=hfs_x" in ran[0]


def test_claude_desktop_on_windows_enters_wsl(monkeypatch, capsys):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/home/u/.local/bin/uv")
    setup.connect("claude-desktop", "hfs_x", install=True)
    out = capsys.readouterr().out
    server = json.loads(out[out.index("{") :])["mcpServers"]["hf-studio"]
    assert server["command"].endswith("wsl.exe")
    assert server["args"][:5] == ["-d", "Ubuntu-24.04", "--", "env", f"HF_STUDIO_URL={setup.API_URL}"]
    assert server["args"][5:7] == ["HF_STUDIO_TOKEN=hfs_x", "/home/u/.local/bin/uv"]
    assert server["args"][-2:] == ["hf-studio", "mcp"]


def test_connect_json_prints_a_stdio_config(monkeypatch, capsys):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    setup.connect("claude-desktop", "hfs_x", install=True)
    out = capsys.readouterr().out
    assert '"hf-studio"' in out and '"HF_STUDIO_TOKEN": "hfs_x"' in out and '"mcp"' in out


@pytest.mark.parametrize(
    ("code", "output", "registered"),
    [
        (0, "hf-studio:\n  command: uv", True),
        (1, 'No MCP server named "hf-studio". Configured servers: …', False),
        (1, "Error: No MCP server named 'hf-studio' found.", False),
        (1, "Error: could not read config.toml", True),  # sin confirmar que no existe: no tocar nada
    ],
)
def test_registration_check_only_trusts_an_explicit_not_found(monkeypatch, code, output, registered):
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    result = type("R", (), {"returncode": code, "stdout": "", "stderr": output})
    monkeypatch.setattr(setup.subprocess, "run", lambda cmd, capture_output, text, check: result)
    assert setup.already_registered("codex") is registered
    assert not setup.already_registered("claude-desktop")


async def test_connecting_never_rotates_an_existing_key(session):
    first_name, first = await setup.new_client_key(session, "codex")
    second_name, second = await setup.new_client_key(session, "codex")
    assert (first_name, second_name) == ("codex", "codex-2") and first != second
    names = {c.name: c.key_hash for c in await session.scalars(select(ApiClient))}
    assert names == {"codex": hash_token(first), "codex-2": hash_token(second)}


posix_only = pytest.mark.skipif(os.name == "nt", reason="Windows no usa permisos POSIX")


@posix_only
def test_secret_files_are_created_private(repo, monkeypatch):
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: "")
    setup.ensure_env(interactive=False)
    assert stat.S_IMODE(os.stat(repo / ".env").st_mode) == 0o600


@posix_only
async def test_ui_env_file_is_private_and_points_to_the_local_api(repo, session):
    (repo / "web" / ".env.local").write_text("HF_STUDIO_URL=http://old-host:9999\nHF_STUDIO_TOKEN=\n")
    await setup.ensure_ui_key(session)
    assert setup.read_env(repo / "web" / ".env.local")["HF_STUDIO_URL"] == setup.API_URL
    (repo / "web" / ".env.local").unlink()
    await setup.ensure_ui_key(session)
    assert stat.S_IMODE(os.stat(repo / "web" / ".env.local").st_mode) == 0o600


async def test_a_stale_ui_key_is_replaced(repo, session):
    _, agent_token = await setup.new_client_key(session, "codex")
    (repo / "web" / ".env.local").write_text(
        f"HF_STUDIO_URL={setup.API_URL}\nHF_STUDIO_TOKEN={agent_token}\n"
    )
    assert await setup.ensure_ui_key(session)  # la clave de otro cliente no vale para la UI
    token = setup.read_env(repo / "web" / ".env.local")["HF_STUDIO_TOKEN"]
    ui = await session.scalar(select(ApiClient).where(ApiClient.name == "web-ui"))
    assert ui.key_hash == hash_token(token)
    ui.sees_all = False
    await session.commit()
    assert not await setup.ensure_ui_key(session) and ui.sees_all  # recupera el see-all sin rotar


def test_the_key_can_come_from_the_environment(repo, monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "id:secret")
    assert setup.ensure_env(interactive=False)


def test_elevenlabs_is_offered_on_the_first_run_only(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: asked.append(prompt) or "")
    (repo / ".env").write_text("HF_API_KEY=id:secret\nELEVENLABS_API_KEY=\n")
    assert (
        setup.ensure_env(interactive=True) and asked == []
    )  # .env ya existía: no se pregunta en cada arranque
    (repo / ".env").unlink()
    monkeypatch.setenv("HF_API_KEY", "id:secret")
    assert setup.ensure_env(interactive=True)
    assert asked == ["ELEVENLABS_API_KEY: ", "APIMART_API_KEY: ", "KIE_API_KEY: "]


def test_launching_the_agent_cli_can_fail_without_a_traceback(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)

    def boom(cmd, check):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(setup.subprocess, "run", boom)
    assert setup.connect("claude-code", "hfs_x", install=True) == 1


async def test_a_failed_connect_revokes_its_new_key(repo, monkeypatch, tmp_path):
    from hf_studio import cli

    db = tmp_path / "cli.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.chdir(tmp_path)  # _connect cambia de directorio; monkeypatch lo restaura al terminar
    monkeypatch.setattr(setup, "already_registered", lambda client: False)
    monkeypatch.setattr(setup, "connect", lambda client, token, install: 1)
    cli.get_settings.cache_clear()
    try:
        assert await cli._connect("codex", None, install=True) == 1
        engine = make_engine(f"sqlite+aiosqlite:///{db}")
        async with make_sessionmaker(engine)() as s:
            client = await s.scalar(select(ApiClient).where(ApiClient.name == "codex"))
        await engine.dispose()
        assert client.revoked_at is not None
    finally:
        cli.get_settings.cache_clear()


def test_pasted_keys_are_cleaned():
    assert setup.clean_key('  "id:secret"\n') == "id:secret"
    assert setup.clean_key("HF_API_KEY=id:secret") == "id:secret"
    assert setup.clean_key("HF_API_KEY='id:secret' ") == "id:secret"


def test_preview_never_shows_the_whole_key():
    key = "abcd1234:efgh5678ijkl9012"
    shown = setup.preview(key)
    assert shown.startswith("abcd…9012") and f"({len(key)} characters)" in shown and "efgh" not in shown
    assert setup.preview("short") == "***** (5 characters)"


def test_a_rejected_key_is_asked_again(monkeypatch, capsys):
    answers = iter(["id:twice-pasted", "id:secret"])
    monkeypatch.setattr(setup, "masked_input", lambda prompt: next(answers))
    key = setup.ask_hf_key(lambda k: 0 if k == "id:secret" else 1)
    out = capsys.readouterr().out
    assert key == "id:secret" and "rejected" in out and "Valid key" in out


def test_giving_up_saves_nothing(repo, monkeypatch):
    answers = iter(["bad:1", ""])
    monkeypatch.setattr(setup, "masked_input", lambda prompt: next(answers))
    assert not setup.ensure_env(interactive=True, validate=lambda k: 1)
    assert setup.read_env(repo / ".env")["HF_API_KEY"] == ""


def _in_terminal(expected: str, chunks: list[bytes]) -> tuple[int, bytes]:
    """Ejecuta masked_input en un proceso nuevo cuya terminal de control es un pty, como en una terminal
    de verdad (pty.fork crea la sesión; exec evita heredar la captura de pytest). Escribe los trozos por
    separado y devuelve (código de salida, todo lo que se vio). Con límites de tiempo: nunca se cuelga."""
    import pty
    import select
    import signal
    import sys
    import time

    code = f"from hf_studio import setup; raise SystemExit(0 if setup.masked_input('KEY: ') == {expected!r} else 3)"
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c", code])

    def read_for(seconds: float) -> bytes:
        got, end = b"", time.time() + seconds
        while time.time() < end and select.select([fd], [], [], 0.1)[0]:
            try:
                chunk = os.read(fd, 1024)
            except OSError:  # el hijo cerró la terminal
                break
            if not chunk:
                break
            got += chunk
        return got

    out, end = b"", time.time() + 20
    while b"KEY: " not in out and time.time() < end:
        out += read_for(0.2)
    for chunk in chunks:
        os.write(fd, chunk)
        time.sleep(0.15)  # lecturas separadas en el hijo
    code_out = None
    for _ in range(100):
        out += read_for(0.1)
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            code_out = os.waitstatus_to_exitcode(status)
            break
    if code_out is None:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        code_out = -1
    out += read_for(0.2)
    os.close(fd)
    return code_out, out


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX")
def test_masked_input_echoes_stars_and_handles_backspace():
    """Se ven `*`, nunca la clave, y el retroceso borra."""
    code, out = _in_terminal("ab:cd", [b"ab:cdX\x7f\r"])  # pega, borra la X y Enter
    assert code == 0, out
    assert b"******" in out and b"ab:cd" not in out


def test_masked_input_on_windows_reads_keys_and_ignores_arrows(monkeypatch, capsys):
    import sys
    import types

    keys = iter(["a", "b", "\xe0", "K", ":", "c", "X", "\x08", "d", "\r"])  # "\xe0K" = flecha izquierda
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getwch=lambda: next(keys)))
    monkeypatch.setattr(setup.os, "name", "nt")
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    assert setup.masked_input("KEY: ") == "ab:cd"
    out = capsys.readouterr().out
    assert out.startswith("KEY: ") and out.count("*") == 6 and "ab" not in out


@pytest.mark.parametrize(
    "chunks",
    [
        ["\x1b[200~id:secret\x1b[201~\r"],  # todo junto
        list("\x1b[200~id:secret\x1b[201~\r"),  # un carácter por lectura (Windows)
        ["\x1b[Did:secret\x1bOA\r"],  # flecha izquierda y una secuencia SS3
    ],
)
def test_paste_markers_and_arrows_never_reach_the_key(monkeypatch, capsys, chunks):
    import sys
    import types

    keys = iter("".join(chunks))
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getwch=lambda: next(keys)))
    monkeypatch.setattr(setup.os, "name", "nt")
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    value = setup.masked_input("KEY: ")
    assert value.endswith("id:secret") and "[" not in value and "~" not in value


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX")
def test_paste_markers_split_across_posix_reads_never_reach_the_key():
    """Los marcadores de pegado llegan partidos en varias lecturas de os.read: el estado debe sobrevivir."""
    code, out = _in_terminal("id:secret", [b"\x1b[20", b"0~id:sec", b"ret\x1b", b"[201~", b"\r"])
    assert code == 0, out
