from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .audio import supports_source_audio
from .catalog import Catalog
from .config import Settings
from .db import ACTIVE, ApiClient, Job, Upload, utcnow
from .elements import check_available

# «No se indicó» frente a None explícito («sin tope», revisión 32).
UNSET: object = object()


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


async def trusted_media(session: AsyncSession, owner: ApiClient, url: str) -> bool:
    """URL que HF Studio puede abrir con ffmpeg sin riesgo de SSRF: una subida propia o una salida de
    una generación propia (con sees_all, de cualquier cliente). Nunca una URL arbitraria."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    uploads = select(Upload.id).where(Upload.url == url)
    if not owner.sees_all:
        uploads = uploads.where(Upload.owner_id == owner.id)
    if await session.scalar(uploads.limit(1)):
        return True
    jobs = select(Job.outputs).where(Job.status == "completed")
    if not owner.sees_all:
        jobs = jobs.where(Job.owner_id == owner.id)
    return any(o.get("url") == url for outputs in await session.scalars(jobs) for o in outputs or [])


def request_digest(
    model_id: str, arguments: dict, keep_source_audio: bool = False, provider: str | None = None
) -> str:
    """Huella de una petición de generación (deduplicado e idempotencia)."""
    # La opción cambia el resultado, así que forma parte de la huella.
    marked = {**arguments, "__keep_source_audio": True} if keep_source_audio else dict(arguments)
    if provider:
        # Forzar un proveedor es otra petición: no se deduplica con la misma entrada en otro proveedor.
        marked["__provider"] = provider
    return input_hash(model_id, marked)


async def job_for_key(
    session: AsyncSession, owner: ApiClient, idempotency_key: str | None, digest: str
) -> Job | None:
    """El trabajo ya creado con esta Idempotency-Key (o None). La misma clave con otra petición es 409."""
    if not idempotency_key:
        return None
    existing = await session.scalar(
        select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == idempotency_key)
    )
    if existing and existing.input_hash != digest:
        raise ServiceError(
            409, "idempotency_conflict", "This Idempotency-Key was already used for a different request"
        )
    return existing


async def create_generation(
    session: AsyncSession,
    settings: Settings,
    catalog: Catalog,
    owner: ApiClient,
    model_id: str,
    arguments: dict,
    idempotency_key: str | None = None,
    allow_duplicate: bool = False,
    keep_source_audio: bool = False,
    plan: list[dict] | None = None,
    max_usd: float | None | object = UNSET,
    max_reserve_usd: float | None | object = UNSET,
    provider: str | None = None,
    commit: bool = True,
) -> tuple[Job, bool]:
    """Crea un trabajo en cola local. Devuelve (trabajo, creado); creado=False si se reutilizó uno existente.

    `commit=False` solo lo añade a la sesión (flush): quien llama lo confirma junto con otros cambios, o lo
    descarta con un rollback (las corridas de Spaces lo guardan en la misma transacción que su estado).

    `plan` (routing.Plan.stored) dice por qué proveedores probar y en qué orden; sin él va a Higgsfield.
    `max_usd` es lo aprobado: un respaldo que cueste más pedirá una nueva aprobación."""
    model = check_input(catalog, model_id, arguments)
    if keep_source_audio and not supports_source_audio(model):
        raise ServiceError(
            422, "source_audio_unsupported", "keep_source_audio needs a video model with a video_url input"
        )
    if keep_source_audio and not await trusted_media(session, owner, arguments.get("video_url")):
        raise ServiceError(
            422,
            "untrusted_source",
            "keep_source_audio needs a video_url from /v1/uploads (upload_media) or from one of your generations",
        )
    digest = request_digest(model["id"], arguments, keep_source_audio, provider)
    existing = await job_for_key(session, owner, idempotency_key, digest)
    if existing:
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

    # Los elementos se vuelven a comprobar justo antes de insertar (sin red entre medias): un borrado durante
    # la cotización da 404 en vez de un trabajo huérfano (revisión 44).
    await check_available(session, arguments.get("elements"))
    job = Job(
        owner_id=owner.id,
        model=model["id"],
        input=arguments,
        input_hash=digest,
        idempotency_key=idempotency_key,
        keep_source_audio=keep_source_audio,
        plan=plan or [],
        provider=plan[0]["provider"] if plan else "higgsfield",
        # Sin indicar, se aprueba lo que cuesta ahora; None explícito es «sin tope» (precio desconocido
        # aceptado). Las retenciones se tratan igual.
        max_usd=(plan[0].get("usd") if plan else None) if max_usd is UNSET else max_usd,
        max_reserve_usd=(plan[0].get("reserve_usd") if plan else None)
        if max_reserve_usd is UNSET
        else max_reserve_usd,
        attempts_log=[],
    )
    session.add(job)
    if not commit:
        await session.flush()
        return job, True
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
