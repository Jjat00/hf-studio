from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Estados propios: `pending` (cola local) y `submitting` (envío en curso) preceden a los del proveedor;
# `awaiting_approval` espera que se apruebe un proveedor de respaldo más caro; `timed_out` es el límite de
# la aplicación, no un estado remoto.
ACTIVE = ("pending", "submitting", "queued", "in_progress", "awaiting_approval")
TERMINAL = ("completed", "failed", "nsfw", "canceled", "timed_out")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Base(DeclarativeBase):
    pass


class ApiClient(Base):
    """Identidad dueña de los trabajos: un agente, una persona o la UI. Se autentica con Bearer."""

    __tablename__ = "api_clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Ve y gestiona las generaciones de todos los clientes (pensado para la UI, no para agentes).
    sees_all: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))

    @staticmethod
    def new_key() -> str:
        return "hfs_" + secrets.token_urlsafe(32)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    model: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    # Opción de HF Studio: al terminar, poner al resultado el audio del video de origen (audio.py).
    keep_source_audio: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), index=True, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    error_kind: Mapped[str | None] = mapped_column(String(40))

    # Proveedor que ejecuta (o ejecutó) el trabajo; `hf_request_id` es el id de la tarea en ese proveedor.
    provider: Mapped[str] = mapped_column(
        String(30), default="higgsfield", server_default=text("'higgsfield'")
    )
    hf_request_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Plan de proveedores (routing.Plan.stored): opciones de la más barata a la más cara, cada una con su
    # modelo y entrada ya traducidos. Vacío en trabajos anteriores: van a Higgsfield con `model` e `input`.
    plan: Mapped[list] = mapped_column(JSON, default=list)
    plan_index: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # Lo máximo aprobado en USD: el respaldo que cueste lo mismo o menos corre sin preguntar.
    max_usd: Mapped[float | None] = mapped_column(Float)
    # Intentos fallidos en otros proveedores: [{provider, request_id, error_kind, error, at}].
    attempts_log: Mapped[list] = mapped_column(JSON, default=list)
    status_url: Mapped[str | None] = mapped_column(Text)
    cancel_url: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    webhook_token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(24))

    outputs: Mapped[list] = mapped_column(JSON, default=list)
    files: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Próxima acción del worker: reintento de envío (pending) o sondeo (queued/in_progress).
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    poll_delay: Mapped[float] = mapped_column(Float, default=2.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Bloqueo optimista: cada escritura exige la versión leída. Así un sondeo o webhook tardío no pisa un
    # trabajo que otro proceso ya movió (p. ej. al proveedor de respaldo) y no se envía dos veces.
    # Las actualizaciones directas (`update(Job)`) deben subirla a mano: `version=Job.version + 1`.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        from pathlib import Path

        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(url)


# Columnas añadidas después de crear la tabla: create_all no altera tablas existentes.
ADDED_COLUMNS = {
    "api_clients": {"sees_all": "BOOLEAN NOT NULL DEFAULT 0"},
    "jobs": {
        "keep_source_audio": "BOOLEAN NOT NULL DEFAULT 0",
        "provider": "VARCHAR(30) NOT NULL DEFAULT 'higgsfield'",
        "plan": "JSON",
        "plan_index": "INTEGER NOT NULL DEFAULT 0",
        "max_usd": "FLOAT",
        "attempts_log": "JSON",
        "version": "INTEGER NOT NULL DEFAULT 1",
    },
}


def _add_missing_columns(conn) -> None:
    from sqlalchemy import inspect

    insp = inspect(conn)
    for table, columns in ADDED_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in columns.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


class Preset(Base):
    """Preset propio de un cliente (los de serie viven en presets.BUILTIN)."""

    __tablename__ = "presets"
    __table_args__ = (UniqueConstraint("owner_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="Mine")
    output: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(200))
    template: Mapped[dict] = mapped_column(JSON)
    variables: Mapped[list] = mapped_column(JSON, default=list)
    cover: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def as_dict(self) -> dict:
        return {
            "slug": self.slug, "title": self.title, "description": self.description, "category": self.category,
            "output": self.output, "model": self.model, "template": self.template, "variables": self.variables,
            "cover": self.cover, "builtin": False,
        }  # fmt: skip


class Sound(Base):
    """Un sonido de la sonoteca: salida de un trabajo de audio de HF Studio o un audio importado del
    historial de ElevenLabs. Guarda cómo se identifica (título, categoría, etiquetas) para reutilizarlo."""

    __tablename__ = "sounds"
    __table_args__ = (UniqueConstraint("owner_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    external_id: Mapped[str | None] = mapped_column(String(64))  # history_item_id de ElevenLabs
    origin: Mapped[str] = mapped_column(String(20))  # studio | elevenlabs
    kind: Mapped[str] = mapped_column(String(20))  # speech | voice_change | sound_effect | music | isolated
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(Text, default="")  # texto o descripción que lo generó
    file_name: Mapped[str] = mapped_column(String(200))  # relativo a storage_dir
    duration: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
