"""hf-studio start [--api-only] | setup | connect CLIENT | serve | create-key NAME | list-keys | revoke-key NAME | check-credentials | sync-catalog | mcp"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import select

from .config import get_settings
from .db import ApiClient, hash_token, init_db, make_engine, make_sessionmaker, utcnow


async def _with_session(fn):
    engine = make_engine(get_settings().database_url)
    await init_db(engine)
    try:
        async with make_sessionmaker(engine)() as session:
            return await fn(session)
    finally:
        await engine.dispose()


async def _create_key(session, name: str) -> int:
    if await session.scalar(select(ApiClient).where(ApiClient.name == name)):
        print(f"Ya existe un cliente llamado {name!r}", file=sys.stderr)
        return 1
    token = ApiClient.new_key()
    session.add(ApiClient(name=name, key_hash=hash_token(token), key_prefix=token[:12]))
    await session.commit()
    print(f"Clave para {name!r} (se muestra una sola vez):\n{token}")
    return 0


async def _list_keys(session) -> int:
    for c in await session.scalars(select(ApiClient).order_by(ApiClient.created_at)):
        state = f"revocada {c.revoked_at:%Y-%m-%d}" if c.revoked_at else "activa"
        scope = "  ve todo" if c.sees_all else ""
        print(f"{c.name:30} {c.key_prefix}…  {state}{scope}")
    return 0


async def _revoke_key(session, name: str) -> int:
    client = await session.scalar(select(ApiClient).where(ApiClient.name == name))
    if not client:
        print(f"No existe {name!r}", file=sys.stderr)
        return 1
    client.revoked_at = utcnow()
    await session.commit()
    print(f"Revocada la clave de {name!r}")
    return 0


async def _set_sees_all(session, name: str, value: bool) -> int:
    client = await session.scalar(select(ApiClient).where(ApiClient.name == name))
    if not client:
        print(f"No existe {name!r}", file=sys.stderr)
        return 1
    client.sees_all = value
    await session.commit()
    what = "ve las generaciones de todos los clientes" if value else "solo ve sus propias generaciones"
    print(f"{name!r} ahora {what}")
    return 0


async def _keep_source_audio(session, job_id: str) -> int:
    """Pone a posteriori el audio del video de origen a una generación ya descargada."""
    from pathlib import Path

    from .audio import MUXED, SOURCE_KEY, apply_to_files
    from .db import Job

    job = await session.get(Job, job_id)
    source = job.input.get(SOURCE_KEY) if job else None
    if not job or job.status != "completed" or not job.files or not isinstance(source, str):
        print(
            "La generación no existe, no está completada, no tiene copia local o no tiene video_url",
            file=sys.stderr,
        )
        return 1
    storage = Path(get_settings().storage_dir) / "outputs" / job.id
    job.files = await apply_to_files(job.files, storage, source)
    job.keep_source_audio = True
    await session.commit()
    states = [f.get("audio") for f in job.files if f.get("kind") == "video"]
    print(f"{job_id}: {', '.join(str(s) for s in states)}")
    return 0 if all(s == MUXED for s in states) else 1


UNREACHABLE = 2  # Higgsfield no respondió (red o 5xx): no dice nada de la clave


async def _check_credentials() -> int:
    """0 si la clave es válida, 1 si falta o es inválida, UNREACHABLE si no se pudo comprobar."""
    import httpx

    from .higgsfield import HiggsfieldClient, HiggsfieldError

    settings = get_settings()
    if not settings.hf_configured:
        print("Falta HF_API_KEY en .env", file=sys.stderr)
        return 1
    client = HiggsfieldClient(settings)
    try:
        ok = await client.check_credentials()
    except httpx.TransportError as exc:
        print(f"No se pudo contactar a Higgsfield ({exc!r}); la clave no se comprobó.", file=sys.stderr)
        return UNREACHABLE
    except HiggsfieldError as exc:
        print(f"Respuesta inesperada de Higgsfield ({exc.status}): {exc.message}", file=sys.stderr)
        return UNREACHABLE if exc.status >= 500 else 1
    finally:
        await client.aclose()
    if ok:
        print("Credenciales válidas: Higgsfield aceptó la clave (sin gastar créditos).")
        return 0
    print("Credenciales inválidas (401). Revisa HF_API_KEY: debe ser `KEY_ID:KEY_SECRET`.", file=sys.stderr)
    return 1


async def _setup(interactive: bool) -> int:
    from . import setup

    os.chdir(setup.ROOT)  # .env y la base SQLite son relativos a la raíz del repo
    if not setup.ensure_env(interactive):
        print(
            "Missing HF_API_KEY in .env. Get one at https://console.higgsfield.ai (API keys) and paste it there.",
            file=sys.stderr,
        )
        return 1
    get_settings.cache_clear()
    checked = await _check_credentials()
    if checked == 1:
        return 1
    if checked == UNREACHABLE:  # sin red o Higgsfield caído: la biblioteca local sigue sirviendo
        print("Starting anyway; generating will fail until Higgsfield is reachable.", file=sys.stderr)
    await _with_session(setup.ensure_ui_key)
    return 0


async def _connect(client: str, name: str | None, install: bool) -> int:
    """Crea una clave nueva para el agente (nunca rota una en uso) y lo registra o imprime cómo hacerlo."""
    from . import setup

    os.chdir(setup.ROOT)  # la misma base que usará el MCP registrado con `uv run --directory ROOT`
    get_settings.cache_clear()
    if install and setup.already_registered(client):
        cli = setup.AGENT_CLI[client]
        print(
            f"hf-studio is already registered in {client} (or it could not be checked). To replace it:"
            f" {cli} mcp remove hf-studio, then run this again.",
            file=sys.stderr,
        )
        return 1
    key_name, token = await _with_session(lambda s: setup.new_client_key(s, name or client))
    code = setup.connect(client, token, install)
    if code != 0:
        await _with_session(lambda s: setup.revoke(s, key_name))
        print(f"Revoked the unused key {key_name!r}.", file=sys.stderr)
    else:
        print(f"Key name: {key_name} (hf-studio list-keys / revoke-key {key_name})")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(prog="hf-studio")
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start", help="Set up on the first run and start the API and the web UI")
    start.add_argument(
        "--api-only", action="store_true", help="Only the API (enough for MCP agents, no Node.js)"
    )
    setup_cmd = sub.add_parser("setup", help="First run: creates .env (asks for missing keys) and the UI key")
    setup_cmd.add_argument(
        "--no-input", action="store_true", help="Never prompt; fail if HF_API_KEY is missing"
    )
    connect = sub.add_parser("connect", help="Register the MCP server in an agent with its own key")
    connect.add_argument("client", choices=["claude-code", "codex", "claude-desktop", "json"])
    connect.add_argument("--name", help="Key name (defaults to the client; -2, -3… if taken)")
    connect.add_argument(
        "--print",
        action="store_true",
        help="Print the command or config (with a new key) instead of registering it",
    )
    serve = sub.add_parser("serve", help="Arranca la API y el worker")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--reload", action="store_true")
    sub.add_parser("create-key", help="Crea un cliente (agente, UI…) y muestra su clave").add_argument("name")
    sub.add_parser("list-keys", help="Lista los clientes")
    sub.add_parser("revoke-key", help="Revoca la clave de un cliente").add_argument("name")
    see_all = sub.add_parser(
        "see-all", help="Deja que un cliente (p. ej. web-ui) vea las generaciones de todos"
    )
    see_all.add_argument("name")
    see_all.add_argument("--off", action="store_true", help="Vuelve a limitarlo a sus propias generaciones")
    sub.add_parser(
        "keep-source-audio", help="Pone a una generación ya hecha el audio de su video de origen (ffmpeg)"
    ).add_argument("job_id")
    sub.add_parser("check-credentials", help="Verifica la clave de Higgsfield sin gastar créditos")
    sub.add_parser("sync-catalog", help="Regenera catalog.json desde docs.higgsfield.ai")
    sub.add_parser("mcp", help="Servidor MCP por stdio para Claude Code / Codex")
    args = parser.parse_args()

    if args.cmd == "start":
        from .launcher import start as launch

        interactive = sys.stdin.isatty()
        return launch(args.api_only, lambda: asyncio.run(_setup(interactive)))
    if args.cmd == "setup":
        return asyncio.run(_setup(interactive=not args.no_input and sys.stdin.isatty()))
    if args.cmd == "connect":
        return asyncio.run(_connect(args.client, args.name, install=not args.print))
    if args.cmd == "serve":
        import uvicorn

        # Un solo proceso: el worker vive dentro de la API (el reclamo atómico evita dobles envíos igualmente).
        uvicorn.run("hf_studio.main:app", host=args.host, port=args.port, reload=args.reload)
        return 0
    if args.cmd == "create-key":
        return asyncio.run(_with_session(lambda s: _create_key(s, args.name)))
    if args.cmd == "list-keys":
        return asyncio.run(_with_session(_list_keys))
    if args.cmd == "revoke-key":
        return asyncio.run(_with_session(lambda s: _revoke_key(s, args.name)))
    if args.cmd == "see-all":
        return asyncio.run(_with_session(lambda s: _set_sees_all(s, args.name, not args.off)))
    if args.cmd == "keep-source-audio":
        return asyncio.run(_with_session(lambda s: _keep_source_audio(s, args.job_id)))
    if args.cmd == "check-credentials":
        return 0 if asyncio.run(_check_credentials()) == 0 else 1
    if args.cmd == "sync-catalog":
        from .catalog_sync import main as sync

        return sync()
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
