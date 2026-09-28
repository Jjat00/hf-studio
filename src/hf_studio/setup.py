"""Puesta en marcha sin pasos a mano: `.env`, clave de la UI y conexión de agentes MCP.

Todo trabaja sobre la raíz del repo (`ROOT`): la CLI cambia a ese directorio antes de `setup` y `connect`,
así que `.env`, la base SQLite y el MCP registrado (`uv run --directory ROOT`) son siempre los mismos."""

from __future__ import annotations

import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from .db import ApiClient, hash_token, utcnow

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
WEB_ENV = ROOT / "web" / ".env.local"
WEB_ENV_EXAMPLE = ROOT / "web" / ".env.example"
UI_CLIENT = "web-ui"
API_URL = "http://127.0.0.1:8787"  # la URL en la que `hf-studio start` arranca la API
AGENT_CLI = {"claude-code": "claude", "codex": "codex"}


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs if not k.lstrip().startswith("#")}


def set_env(path: Path, key: str, value: str) -> None:
    """Pone `KEY=value` en el archivo: sustituye la línea (activa o comentada) o la añade al final."""
    text = path.read_text() if path.is_file() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^#?\s*{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _: line, text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text.lstrip("\n"))


def copy_private(source: Path, target: Path) -> None:
    """Copia la plantilla en un archivo nuevo que solo puede leer su dueño (guarda secretos)."""
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(source.read_text())


def ensure_env(interactive: bool) -> bool:
    """Crea `.env` desde el ejemplo y, en una terminal, pide las claves la primera vez.

    Devuelve True si hay clave de Higgsfield en `.env` o en el entorno. ElevenLabs (opcional) solo se pide al
    crear `.env` o cuando falta Higgsfield, para no preguntar en cada arranque a quien no la quiere."""
    created = not ENV.is_file()
    if created:
        copy_private(ENV_EXAMPLE, ENV)
        print("Created .env from .env.example")
    from_env = {
        k: v for k, v in os.environ.items() if k.startswith(("HF_API_KEY", "ELEVENLABS_API_KEY")) and v
    }
    values = {**read_env(ENV), **from_env}
    has_hf = bool(
        values.get("HF_API_KEY") or (values.get("HF_API_KEY_ID") and values.get("HF_API_KEY_SECRET"))
    )
    if not interactive or (has_hf and not created):
        return has_hf
    if not has_hf:
        print(
            "\nHiggsfield API key (required): https://console.higgsfield.ai -> API keys, format KEY_ID:KEY_SECRET"
        )
        key = getpass.getpass("HF_API_KEY: ").strip()
        if key:
            set_env(ENV, "HF_API_KEY", key)
            has_hf = True
    if has_hf and not values.get("ELEVENLABS_API_KEY"):
        print(
            "\nElevenLabs API key (optional, only for voice, sound effects and music):"
            " https://elevenlabs.io/app/settings/api-keys. Press Enter to skip;"
            " you can add ELEVENLABS_API_KEY to .env later."
        )
        eleven = getpass.getpass("ELEVENLABS_API_KEY: ").strip()
        if eleven:
            set_env(ENV, "ELEVENLABS_API_KEY", eleven)
    return has_hf


async def rotate_key(session, name: str, sees_all: bool | None = None) -> str:
    """Clave nueva para `name`. Si el cliente ya existe, rota su clave y conserva sus generaciones."""
    token = ApiClient.new_key()
    client = await session.scalar(select(ApiClient).where(ApiClient.name == name))
    if client is None:
        client = ApiClient(name=name)
        session.add(client)
    client.key_hash, client.key_prefix, client.revoked_at = hash_token(token), token[:12], None
    if sees_all is not None:
        client.sees_all = sees_all
    await session.commit()
    return token


async def new_client_key(session, base: str) -> tuple[str, str]:
    """Crea un cliente nuevo (`base`, `base-2`…) sin tocar las claves que ya existan. Devuelve (nombre, clave)."""
    taken = set(await session.scalars(select(ApiClient.name).where(ApiClient.name.startswith(base))))
    name = next(n for n in (base, *(f"{base}-{i}" for i in range(2, 1000))) if n not in taken)
    token = ApiClient.new_key()
    session.add(ApiClient(name=name, key_hash=hash_token(token), key_prefix=token[:12]))
    await session.commit()
    return name, token


async def revoke(session, name: str) -> None:
    client = await session.scalar(select(ApiClient).where(ApiClient.name == name))
    if client:
        client.revoked_at = utcnow()
        await session.commit()


async def ensure_ui_key(session) -> bool:
    """Deja `web/.env.local` apuntando a la API local con una clave activa de `web-ui` que ve todo.

    True si tuvo que crear o rotar la clave."""
    if not WEB_ENV.is_file():
        copy_private(WEB_ENV_EXAMPLE, WEB_ENV)
    if read_env(WEB_ENV).get("HF_STUDIO_URL") != API_URL:
        set_env(WEB_ENV, "HF_STUDIO_URL", API_URL)
    token = read_env(WEB_ENV).get("HF_STUDIO_TOKEN", "")
    client = None
    if token:
        client = await session.scalar(select(ApiClient).where(ApiClient.key_hash == hash_token(token)))
    if client and client.name == UI_CLIENT and client.revoked_at is None:
        if not client.sees_all:
            client.sees_all = True
            await session.commit()
        return False
    set_env(WEB_ENV, "HF_STUDIO_TOKEN", await rotate_key(session, UI_CLIENT, sees_all=True))
    print(f"Created the UI key in {WEB_ENV.relative_to(ROOT)}")
    return True


def already_registered(client: str) -> bool:
    """True si el agente ya tiene un servidor `hf-studio` (o no se pudo comprobar: mejor no tocar nada)."""
    cli = AGENT_CLI.get(client)
    if not cli or not shutil.which(cli):
        return False
    result = subprocess.run([cli, "mcp", "get", "hf-studio"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return True
    # «No MCP server named …» (claude y codex) es la única respuesta que confirma que no existe.
    return "no mcp server named" not in (result.stdout + result.stderr).lower()


def shell_join(cmd: list[str]) -> str:
    """Comando listo para pegar: POSIX (sh, zsh) o, en Windows, PowerShell, su terminal por defecto.

    En PowerShell las comillas simples son literales: no expanden `$`, `%` ni interpretan `&` o `^`."""
    if os.name != "nt":
        return shlex.join(cmd)
    return " ".join(
        a if re.fullmatch(r"[\w@+=:,./\\-]+", a) else "'" + a.replace("'", "''") + "'" for a in cmd
    )


def mcp_command() -> list[str]:
    return ["uv", "run", "--directory", str(ROOT), "hf-studio", "mcp"]


def register_command(client: str, token: str) -> list[str]:
    pairs = [f"HF_STUDIO_URL={API_URL}", f"HF_STUDIO_TOKEN={token}"]
    if client == "claude-code":
        flags = [part for pair in pairs for part in ("-e", pair)]
        return ["claude", "mcp", "add", "hf-studio", "--scope", "user", *flags, "--", *mcp_command()]
    flags = [part for pair in pairs for part in ("--env", pair)]
    return ["codex", "mcp", "add", "hf-studio", *flags, "--", *mcp_command()]


def connect(client: str, token: str, install: bool) -> int:
    """Registra el MCP en el agente (si su CLI está instalada) o imprime cómo hacerlo.

    Devuelve 0 si quedó registrado o impreso (el comando o la configuración llevan una clave nueva y válida);
    1 si el registro pedido falló."""
    if client not in AGENT_CLI:
        env = {"HF_STUDIO_URL": API_URL, "HF_STUDIO_TOKEN": token}
        server = {"command": "uv", "args": mcp_command()[1:], "env": env}
        distro = os.environ.get("WSL_DISTRO_NAME")
        if client == "claude-desktop" and distro:
            # Claude Desktop corre en Windows: entra a WSL. Sus variables no cruzan (van con `env`) y
            # `wsl.exe --` no carga el PATH del perfil (uv va con ruta absoluta).
            uv = shutil.which("uv") or "uv"
            pairs = [f"{k}={v}" for k, v in env.items()]
            args = ["-d", distro, "--", "env", *pairs, uv, *mcp_command()[1:]]
            server = {"command": "C:\\Windows\\System32\\wsl.exe", "args": args}
        config = {"mcpServers": {"hf-studio": server}}
        where = (
            "Claude Desktop: Settings -> Developer -> Edit Config (claude_desktop_config.json)"
            if client == "claude-desktop"
            else "Any stdio MCP client"
        )
        print(f"{where}. Merge this into its configuration:\n")
        print(json.dumps(config, indent=2))
        return 0
    cmd = register_command(client, token)
    if install and shutil.which(cmd[0]):
        try:
            code = subprocess.run(cmd, check=False).returncode
        except OSError as exc:
            print(f"\nCould not run {cmd[0]}: {exc}", file=sys.stderr)
            return 1
        if code == 0:
            print(f"\nhf-studio is registered in {client}. Restart it so it loads the tools.")
            print("The API must be running: uv run hf-studio start (or --api-only, without the UI).")
            return 0
        print(f"\n{cmd[0]} could not register hf-studio.", file=sys.stderr)
        return 1
    if install:
        # Sin la CLI no hay registro: se entrega el comando listo, con su clave, para ejecutarlo donde esté.
        print(f"`{cmd[0]}` is not installed or not on PATH, so nothing was registered.", file=sys.stderr)
    shell = "PowerShell" if os.name == "nt" else "a terminal"
    print(f"Run this in {shell} where it is installed to register the MCP server (it carries a new key):\n")
    print(shell_join(cmd))
    return 0
