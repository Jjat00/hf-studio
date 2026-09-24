import asyncio
import hmac
import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import Catalog, get_catalog
from .config import Settings, get_settings
from .db import TERMINAL, ApiClient, Job, Upload, hash_token, init_db, make_engine, make_sessionmaker, utcnow
from .higgsfield import UPLOAD_CONTENT_TYPES, HiggsfieldClient, HiggsfieldError
from .service import ServiceError, check_input, create_generation, get_owned_job
from .worker import Worker

log = logging.getLogger("hf_studio.api")

STAGES = {
    "pending": "Waiting for a free concurrency slot",
    "submitting": "Submitting to Higgsfield",
    "queued": "Queued at Higgsfield",
    "in_progress": "Generating",
    "completed": "Ready",
    "failed": "Failed",
    "nsfw": "Blocked by moderation (not charged)",
    "canceled": "Canceled",
    "timed_out": "Timed out",
}
HF_ERROR_STATUS = {
    "auth": 502, "credits": 402, "not_found": 404, "validation": 422, "bad_request": 400,
    "concurrency": 429, "unavailable": 503, "server": 502, "network": 502, "too_late": 409,
}  # fmt: skip


class GenerationIn(BaseModel):
    model: str = Field(description="ID del endpoint, p. ej. bytedance/seedance-2.0/text-to-video")
    input: dict[str, Any] = Field(description="Argumentos según el input_schema del modelo")
    allow_duplicate: bool = Field(False, description="Permite repetir una petición idéntica aún activa")


class EstimateIn(BaseModel):
    model: str
    input: dict[str, Any]


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        await init_db(engine)
        app.state.sessions = make_sessionmaker(engine)
        app.state.hf = HiggsfieldClient(settings, transport)
        app.state.worker = Worker(app.state.sessions, app.state.hf, settings)
        app.state.tasks = set()
        if not settings.hf_configured:
            log.warning("Falta HF_API_KEY (o HF_API_KEY_ID + HF_API_KEY_SECRET): los envíos fallarán")
        if settings.worker_enabled:
            app.state.worker.start()
        yield
        await app.state.worker.stop()
        await app.state.hf.aclose()
        await engine.dispose()

    app = FastAPI(
        title="HF Studio",
        version="0.1.0",
        description="API propia sobre Higgsfield para agentes y UI. Autenticación: `Authorization: Bearer hfs_…`.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"]
        )

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        body = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse({"error": body}, status_code=exc.status)

    @app.exception_handler(HiggsfieldError)
    async def _hf_error(_: Request, exc: HiggsfieldError) -> JSONResponse:
        message = "The server's Higgsfield credentials are invalid" if exc.kind == "auth" else exc.message
        body = {"code": f"higgsfield_{exc.kind}", "message": message, "correlation_id": exc.correlation_id}
        return JSONResponse({"error": body}, status_code=HF_ERROR_STATUS.get(exc.kind, 502))

    # --- Dependencias --------------------------------------------------------------------------

    async def session_dep(request: Request) -> AsyncIterator[AsyncSession]:
        async with request.app.state.sessions() as session:
            yield session

    Session = Annotated[AsyncSession, Depends(session_dep)]

    async def client_dep(
        session: Session, authorization: Annotated[str | None, Header()] = None
    ) -> ApiClient:
        token = (authorization or "").removeprefix("Bearer ").strip()
        client = (
            await session.scalar(select(ApiClient).where(ApiClient.key_hash == hash_token(token)))
            if token
            else None
        )
        if not client or client.revoked_at:
            raise ServiceError(401, "unauthorized", "Missing or invalid key (Authorization: Bearer hfs_…)")
        return client

    Owner = Annotated[ApiClient, Depends(client_dep)]
    CatalogDep = Annotated[Catalog, Depends(get_catalog)]

    def job_out(job: Job, deduplicated: bool | None = None) -> dict:
        files = {f["index"]: f for f in job.files or []}
        outputs = []
        for i, out in enumerate(job.outputs or []):
            item = dict(out)
            if i in files:
                item["file_url"] = f"/v1/generations/{job.id}/files/{files[i]['name']}"
            outputs.append(item)
        end = job.finished_at or utcnow()

        def iso(dt: datetime | None) -> str | None:
            return dt.replace(tzinfo=UTC).isoformat() if dt else None

        body = {
            "id": job.id,
            "model": job.model,
            "status": job.status,
            "stage": STAGES.get(job.status, job.status),
            "terminal": job.status in TERMINAL,
            "input": job.input,
            "outputs": outputs,
            "error": job.error,
            "error_kind": job.error_kind,
            "request_id": job.hf_request_id,
            "correlation_id": job.correlation_id,
            "created_at": iso(job.created_at),
            "submitted_at": iso(job.submitted_at),
            "finished_at": iso(job.finished_at),
            "elapsed_seconds": round((end - job.created_at).total_seconds(), 1),
        }
        if deduplicated is not None:
            body["deduplicated"] = deduplicated
        return body

    def model_out(m: dict, full: bool = False) -> dict:
        keys = ("id", "title", "output", "workflow", "family", "capabilities", "docs_url")
        base = {k: m[k] for k in keys}
        return (
            {**base, "summary": m["summary"], "notes": m["notes"], "input_schema": m["input_schema"]}
            if full
            else base
        )

    # --- Rutas ---------------------------------------------------------------------------------

    @app.get("/health", tags=["sistema"])
    async def health() -> dict:
        return {
            "ok": True,
            "higgsfield_configured": settings.hf_configured,
            "catalog_synced_at": get_catalog().synced_at,
        }

    @app.get("/v1/me", tags=["sistema"])
    async def me(owner: Owner) -> dict:
        return {"id": owner.id, "name": owner.name}

    @app.get("/v1/models", tags=["modelos"])
    async def list_models(
        _: Owner,
        catalog: CatalogDep,
        capability: str | None = Query(
            None,
            description="text-to-video, image-to-video, first-last-frame, "
            "video-input, reference-to-video, image-references, video-edit, …",
        ),
        output: str | None = Query(None, pattern="^(video|image|audio)$"),
        q: str | None = Query(None, description="Texto en el id o título"),
    ) -> dict:
        models = catalog.search(capability, output, q)
        caps = sorted({c for m in catalog.models.values() for c in m["capabilities"]})
        return {
            "synced_at": catalog.synced_at,
            "capabilities": caps,
            "models": [model_out(m) for m in models],
        }

    @app.get("/v1/models/{model_id:path}", tags=["modelos"])
    async def get_model(model_id: str, _: Owner, catalog: CatalogDep) -> dict:
        model = catalog.get(model_id)
        if not model:
            raise ServiceError(404, "unknown_model", f"Unknown model: {model_id}")
        return model_out(model, full=True)

    @app.post("/v1/estimate", tags=["generaciones"])
    async def estimate(body: EstimateIn, request: Request, _: Owner, catalog: CatalogDep) -> dict:
        model = check_input(catalog, body.model, body.input)
        return await request.app.state.hf.estimate(model["id"], body.input)

    @app.post("/v1/uploads", status_code=201, tags=["archivos"])
    async def upload(
        request: Request, session: Session, owner: Owner, file: Annotated[UploadFile, File()]
    ) -> dict:
        content_type = (file.content_type or "").lower()
        if content_type not in UPLOAD_CONTENT_TYPES:
            content_type = (mimetypes.guess_type(file.filename or "")[0] or "").lower()
        if content_type not in UPLOAD_CONTENT_TYPES:
            raise ServiceError(
                415, "unsupported_media", f"Supported types: {', '.join(sorted(UPLOAD_CONTENT_TYPES))}"
            )
        data = bytearray()
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > settings.max_upload_bytes:
                raise ServiceError(
                    413, "too_large", f"Maximum {settings.max_upload_bytes // (1024 * 1024)} MB"
                )
        if not data:
            raise ServiceError(422, "empty_file", "The file is empty")
        url = await request.app.state.hf.upload(bytes(data), content_type)
        record = Upload(
            owner_id=owner.id,
            filename=file.filename or "archivo",
            content_type=content_type,
            size=len(data),
            url=url,
        )
        session.add(record)
        await session.commit()
        return {
            "id": record.id,
            "url": url,
            "content_type": content_type,
            "size": len(data),
            "filename": record.filename,
        }

    @app.get("/v1/uploads", tags=["archivos"])
    async def list_uploads(session: Session, owner: Owner, limit: int = Query(50, ge=1, le=200)) -> dict:
        rows = await session.scalars(
            select(Upload).where(Upload.owner_id == owner.id).order_by(Upload.created_at.desc()).limit(limit)
        )
        return {"uploads": [
            {"id": u.id, "url": u.url, "content_type": u.content_type, "size": u.size, "filename": u.filename,
             "created_at": u.created_at.replace(tzinfo=UTC).isoformat()}
            for u in rows
        ]}  # fmt: skip

    @app.post("/v1/generations", tags=["generaciones"], status_code=202)
    async def create(
        body: GenerationIn,
        request: Request,
        session: Session,
        owner: Owner,
        catalog: CatalogDep,
        idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
    ) -> JSONResponse:
        job, created = await create_generation(
            session, settings, catalog, owner, body.model, body.input, idempotency_key, body.allow_duplicate
        )
        if created:
            request.app.state.worker.wake()
        return JSONResponse(job_out(job, deduplicated=not created), status_code=202 if created else 200)

    @app.get("/v1/generations", tags=["generaciones"])
    async def list_generations(
        session: Session,
        owner: Owner,
        status: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict:
        query = select(Job).where(Job.owner_id == owner.id)
        if status:
            query = query.where(Job.status == status)
        jobs = await session.scalars(query.order_by(Job.created_at.desc()).offset(offset).limit(limit))
        return {"generations": [job_out(j) for j in jobs]}

    @app.get("/v1/generations/{job_id}", tags=["generaciones"])
    async def get_generation(
        job_id: str,
        session: Session,
        owner: Owner,
        wait: int = Query(0, ge=0, le=120, description="Espera hasta N s a que termine (long-poll)"),
    ) -> dict:
        job = await get_owned_job(session, owner, job_id)
        deadline = asyncio.get_running_loop().time() + wait
        while job.status not in TERMINAL and asyncio.get_running_loop().time() < deadline:
            await session.commit()  # cierra la transacción para ver lo que escriba el worker
            await asyncio.sleep(1)
            await session.refresh(job)
        return job_out(job)

    @app.post("/v1/generations/{job_id}/cancel", tags=["generaciones"])
    async def cancel(job_id: str, request: Request, session: Session, owner: Owner) -> dict:
        job = await get_owned_job(session, owner, job_id)
        if job.status == "pending":
            # Atómico frente al worker, que reclama los pendientes con la misma condición.
            done = await session.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "pending")
                .values(status="canceled", finished_at=utcnow(), next_check_at=None)
            )
            await session.commit()
            await session.refresh(job)
            if done.rowcount != 1:
                raise ServiceError(
                    409, "not_cancelable", f"Cannot cancel a generation in status {job.status}"
                )
            return job_out(job)
        if job.status == "queued" and job.hf_request_id:
            await request.app.state.hf.cancel(job.hf_request_id, job.cancel_url)
            job.status, job.finished_at, job.next_check_at = "canceled", utcnow(), None
        else:
            raise ServiceError(409, "not_cancelable", f"Cannot cancel a generation in status {job.status}")
        await session.commit()
        return job_out(job)

    @app.get("/v1/generations/{job_id}/files/{name}", tags=["generaciones"])
    async def get_file(job_id: str, name: str, session: Session, owner: Owner) -> FileResponse:
        job = await get_owned_job(session, owner, job_id)
        entry = next((f for f in job.files or [] if f["name"] == name), None)
        path = Path(settings.storage_dir) / "outputs" / job.id / name
        if not entry or not path.is_file():
            raise ServiceError(404, "not_found", "Archivo no encontrado")
        return FileResponse(path, media_type=entry.get("content_type"), filename=name)

    @app.post("/v1/webhooks/higgsfield/{job_id}", tags=["sistema"], include_in_schema=False)
    async def webhook(job_id: str, request: Request, session: Session, token: str = "") -> dict:
        try:
            payload = await request.json()
        except ValueError:
            payload = None
        if not (isinstance(payload, dict) and isinstance(payload.get("request_id"), str)
                and payload.get("status") in ("completed", "failed", "nsfw", "canceled")):  # fmt: skip
            raise ServiceError(400, "bad_envelope", "Unrecognized webhook body")
        job = await session.get(Job, job_id)
        if (
            not job
            or not hmac.compare_digest(job.webhook_token, token)
            or job.hf_request_id != payload["request_id"]
        ):
            raise ServiceError(404, "not_found", "Unknown webhook")
        if job.status not in TERMINAL or job.status == "timed_out":
            # El webhook no va firmado: solo dispara una consulta autoritativa al endpoint de estado.
            task = asyncio.create_task(refresh_job(request.app, job.id))
            request.app.state.tasks.add(task)
            task.add_done_callback(request.app.state.tasks.discard)
        return {"ok": True}

    async def refresh_job(app: FastAPI, job_id: str) -> None:
        async with app.state.sessions() as session:
            job = await session.get(Job, job_id)
            if job:
                await app.state.worker.refresh(session, job)
                await session.commit()

    return app
