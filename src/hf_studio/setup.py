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


HF_KEY_HELP = "https://console.higgsfield.ai -> API keys. Paste it whole (format KEY_ID:KEY_SECRET)."


def masked_input(prompt: str) -> str:
    """Como `getpass`, pero cada carácter se ve como `*`: al pegar se nota que entró algo."""
    if not sys.stdin.isatty():
        return getpass.getpass(prompt)
    chars: list[str] = []
    escape = ""  # secuencia de escape a medias: "", "\x1b" o "\x1b[" + parámetros

    def show_prompt() -> None:
        sys.stdout.write(prompt)
        sys.stdout.flush()

    def feed(text: str) -> bool:
        """Procesa lo leído, sea un carácter (Windows) o un bloque (POSIX); True al llegar Enter.

        Las secuencias de escape (flechas, marcadores de pegado 200~/201~) se descartan aunque lleguen
        partidas entre lecturas: por eso el estado vive fuera de esta función."""
        nonlocal escape
        for ch in text:
            if escape:
                if escape == "\x1b" and ch in "[O":
                    escape += ch  # CSI (ESC [ …) o SS3 (ESC O x, flechas en algunas terminales)
                elif escape == "\x1b" or escape == "\x1bO":
                    escape = ""  # ESC + una tecla, o la tecla final de SS3: se descarta
                elif "@" <= ch <= "~":
                    escape = ""  # fin de la secuencia CSI
                else:
                    escape += ch
                continue
            if ch == "\x1b":
                escape = ch
            elif ch in "\r\n":
                sys.stdout.flush()
                return True
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch in "\x08\x7f":
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif ch >= " ":
                chars.append(ch)
                sys.stdout.write("*")
        sys.stdout.flush()
        return False

    if os.name == "nt":
        import msvcrt

        show_prompt()  # getwch lee sin eco desde el primer momento
        while True:
            ch = msvcrt.getwch()
            if ch in "\x00\xe0":  # tecla especial: su segundo código no es texto
                msvcrt.getwch()
            elif feed(ch):
                break
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            # Sin eco y carácter a carácter ANTES del prompt, y sin descartar lo ya tecleado (TCSANOW):
            # si no, lo pegado en ese instante se perdería o se vería en claro. Ctrl+C sigue funcionando.
            tty.setcbreak(fd, termios.TCSANOW)
            show_prompt()
            while not feed(os.read(fd, 4096).decode(errors="ignore")):
                pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return "".join(chars)


def clean_key(raw: str) -> str:
    """Quita lo que se suele pegar de más: espacios, comillas o la línea entera `HF_API_KEY=…`."""
    key = raw.strip().strip("\"'").strip()
    key = re.sub(r"^[A-Z_]+=", "", key).strip().strip("\"'")
    return key


def preview(key: str) -> str:
    """Vista parcial para confirmar lo pegado sin mostrar la clave."""
    shown = f"{key[:4]}…{key[-4:]}" if len(key) > 12 else "*" * len(key)
    return f"{shown} ({len(key)} characters)"


def ask_hf_key(validate, attempts: int = 3) -> str:
    """Pide la clave de Higgsfield hasta que Higgsfield la acepte. `validate(key)` devuelve 0 si es válida,
    1 si la rechaza u otro valor si no se pudo comprobar (se acepta con aviso). Devuelve "" si se rinde."""
    for attempt in range(attempts):
        key = clean_key(masked_input("HF_API_KEY: "))
        if not key:
            return ""
        print(f"  Got {preview(key)}. Checking it with Higgsfield (no credits spent)...")
        result = validate(key)
        if result == 0:
            print("  Valid key.")
            return key
        if result != 1:
            print("  Could not reach Higgsfield to check it; saving it anyway.")
            return key
        left = attempts - attempt - 1
        print(
            "  Higgsfield rejected this key (401). Copy it again from "
            + HF_KEY_HELP
            + (f" Try again ({left} left, Enter to cancel):" if left else "")
        )
    return ""


def ensure_env_file() -> bool:
    """Crea `.env` desde el ejemplo si no existe. True si lo creó."""
    if ENV.is_file():
        return False
    copy_private(ENV_EXAMPLE, ENV)
    print("Created .env from .env.example")
    return True


def env_values() -> dict[str, str]:
    """`.env` más las variables del proceso, que tienen prioridad (como en config.Settings)."""
    from_env = {
        k: v
        for k, v in os.environ.items()
        if (k.startswith(("HF_API_KEY", "ELEVENLABS_API_KEY")) or k in _provider_vars()) and v
    }
    return {**read_env(ENV), **from_env}


def _provider_vars() -> set[str]:
    from .providers.registry import PROVIDERS

    return {cls.env_var for cls in PROVIDERS.values()}


def has_hf_key() -> bool:
    values = env_values()
    return bool(values.get("HF_API_KEY") or (values.get("HF_API_KEY_ID") and values.get("HF_API_KEY_SECRET")))


def ensure_env(interactive: bool, validate=lambda key: 0) -> bool:
    """Crea `.env` desde el ejemplo y, en una terminal, pide las claves la primera vez.

    Devuelve True si hay clave de Higgsfield en `.env` o en el entorno. ElevenLabs (opcional) solo se pide al
    crear `.env` o cuando falta Higgsfield, para no preguntar en cada arranque a quien no la quiere."""
    created = ensure_env_file()
    has_hf = has_hf_key()
    if not interactive or (has_hf and not created):
        return has_hf
    if not has_hf:
        print(f"\nHiggsfield API key (required): {HF_KEY_HELP}")
        print("Characters show as * while you paste or type; press Enter when done.")
        key = ask_hf_key(validate)
        if key:
            set_env(ENV, "HF_API_KEY", key)
            has_hf = True
    if has_hf and not env_values().get("ELEVENLABS_API_KEY"):
        print(
            "\nElevenLabs API key (optional, only for voice, sound effects and music):"
            " https://elevenlabs.io/app/settings/api-keys. Press Enter to skip;"
            " you can add ELEVENLABS_API_KEY to .env later."
        )
        eleven = clean_key(masked_input("ELEVENLABS_API_KEY: "))
        if eleven:
            print(f"  Got {preview(eleven)}.")
            set_env(ENV, "ELEVENLABS_API_KEY", eleven)
    if has_hf:
        ask_optional_providers()
    return has_hf


def ask_optional_providers(validate=None) -> None:
    """Ofrece los proveedores opcionales sin clave (APIMart, KIE…), con el enlace de registro y el de la
    clave. Con más proveedores, cada video sale por el más barato y hay respaldo si uno falla."""
    from .providers.registry import PROVIDERS

    missing = [cls for cls in PROVIDERS.values() if not cls.required and not env_values().get(cls.env_var)]
    if not missing:
        return
    print(
        "\nOptional providers: each one you add can make videos cheaper (HF Studio sends every video to the"
        " cheapest provider with a key) and backs up the others. Press Enter to skip any of them;"
        " later: `hf-studio providers --add NAME`."
    )
    for cls in missing:
        ask_provider_key(cls, validate)


def ask_provider_key(cls, validate=None) -> bool:
    """Pide y guarda la clave de un proveedor. `validate(cls, key)` devuelve True, False o None (no se pudo
    comprobar, se guarda igual)."""
    print(f"\n{cls.title}: {cls.blurb}\n  Sign up: {cls.signup_url}\n  Create the key: {cls.key_url}")
    key = clean_key(masked_input(f"{cls.env_var}: "))
    if not key:
        return False
    print(f"  Got {preview(key)}.")
    if validate is not None:
        valid = validate(cls, key)
        if valid is False:
            print(f"  {cls.title} rejected this key; not saved.")
            return False
        if valid is None:
            print(f"  Could not check it with {cls.title}; saving it anyway.")
    set_env(ENV, cls.env_var, key)
    return True


def replace_hf_key(validate) -> bool:
    """La clave guardada fue rechazada: pide otra y la guarda si Higgsfield la acepta."""
    if os.environ.get("HF_API_KEY"):
        print("HF_API_KEY is set in your environment and overrides .env; fix it there.", file=sys.stderr)
        return False
    print(f"\nThe Higgsfield key in .env was rejected (401). Paste the right one: {HF_KEY_HELP}")
    print("Characters show as * while you paste or type; press Enter when done (Enter alone cancels).")
    key = ask_hf_key(validate)
    if key:
        set_env(ENV, "HF_API_KEY", key)
    return bool(key)


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
