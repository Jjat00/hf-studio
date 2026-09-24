"""hf-studio serve | create-key NAME | list-keys | revoke-key NAME | check-credentials | sync-catalog | mcp"""

from __future__ import annotations

import argparse
import asyncio
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


async def _check_credentials() -> int:
    from .higgsfield import HiggsfieldClient, HiggsfieldError

    settings = get_settings()
    if not settings.hf_configured:
        print("Falta HF_API_KEY en .env", file=sys.stderr)
        return 1
    client = HiggsfieldClient(settings)
    try:
        ok = await client.check_credentials()
    except HiggsfieldError as exc:
        print(f"Respuesta inesperada de Higgsfield ({exc.status}): {exc.message}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()
    if ok:
        print("Credenciales válidas: Higgsfield aceptó la clave (sin gastar créditos).")
        return 0
    print("Credenciales inválidas (401). Revisa HF_API_KEY: debe ser `KEY_ID:KEY_SECRET`.", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="hf-studio")
    sub = parser.add_subparsers(dest="cmd", required=True)
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
        return asyncio.run(_check_credentials())
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
