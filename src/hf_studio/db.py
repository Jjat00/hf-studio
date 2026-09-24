from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Estados propios: `pending` (cola local) y `submitting` (envío en curso) preceden a los de Higgsfield;
# `timed_out` es el límite de la aplicación, no un estado remoto.
ACTIVE = ("pending", "submitting", "queued", "in_progress")
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
    status: Mapped[str] = mapped_column(String(20), index=True, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    error_kind: Mapped[str | None] = mapped_column(String(40))

    hf_request_id: Mapped[str | None] = mapped_column(String(64), unique=True)
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


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        from pathlib import Path

        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(url)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
