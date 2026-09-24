from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import Catalog
from .config import Settings
from .db import ACTIVE, ApiClient, Job, utcnow


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: object = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def input_hash(model: str, arguments: dict) -> str:
    canonical = json.dumps({"model": model, "input": arguments}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def check_input(catalog: Catalog, model_id: str, arguments: dict) -> dict:
    model = catalog.get(model_id)
    if not model:
        raise ServiceError(404, "unknown_model", f"Unknown model: {model_id}. See GET /v1/models")
    if errors := catalog.validate(model["id"], arguments):
        raise ServiceError(422, "invalid_input", "The input does not match the model schema", errors)
    return model


async def get_owned_job(session: AsyncSession, owner: ApiClient, job_id: str) -> Job:
    job = await session.get(Job, job_id)
    if not job or (job.owner_id != owner.id and not owner.sees_all):
        # 404 también para trabajos ajenos: no se revela su existencia.
        raise ServiceError(404, "not_found", "Generation not found")
    return job


async def create_generation(
    session: AsyncSession,
    settings: Settings,
    catalog: Catalog,
    owner: ApiClient,
    model_id: str,
    arguments: dict,
    idempotency_key: str | None = None,
    allow_duplicate: bool = False,
) -> tuple[Job, bool]:
    """Crea un trabajo en cola local. Devuelve (trabajo, creado); creado=False si se reutilizó uno existente."""
    model = check_input(catalog, model_id, arguments)
    digest = input_hash(model["id"], arguments)

    if idempotency_key:
        existing = await session.scalar(
            select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.input_hash != digest:
                raise ServiceError(
                    409,
                    "idempotency_conflict",
                    "This Idempotency-Key was already used for a different request",
                )
            return existing, False
    if not allow_duplicate:
        since = utcnow() - timedelta(seconds=settings.dedupe_window_seconds)
        existing = await session.scalar(
            select(Job)
            .where(
                Job.owner_id == owner.id,
                Job.input_hash == digest,
                Job.status.in_(ACTIVE),
                Job.created_at >= since,
            )
            .order_by(Job.created_at.desc())
        )
        if existing:
            return existing, False

    active = await session.scalar(
        select(func.count()).select_from(Job).where(Job.owner_id == owner.id, Job.status.in_(ACTIVE))
    )
    if active >= settings.max_active_jobs_per_client:
        raise ServiceError(
            429,
            "too_many_active",
            f"You have {active} active generations (maximum {settings.max_active_jobs_per_client})",
        )

    job = Job(
        owner_id=owner.id,
        model=model["id"],
        input=arguments,
        input_hash=digest,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        # Dos peticiones simultáneas con la misma Idempotency-Key: gana la primera.
        await session.rollback()
        existing = await session.scalar(
            select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == idempotency_key)
        )
        if existing and existing.input_hash == digest:
            return existing, False
        raise ServiceError(
            409, "idempotency_conflict", "This Idempotency-Key was already used for a different request"
        ) from None
    return job, True
