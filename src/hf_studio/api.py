import asyncio
import hmac
import logging
import mimetypes
import re
import shutil
import time
import uuid
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
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .audio import studio_notes
from .catalog import Catalog, get_catalog
from .config import Settings, get_settings
from .db import (
    ACTIVE,
    TERMINAL,
    ApiClient,
    Job,
    Preset,
    Sound,
    Upload,
    hash_token,
    init_db,
    make_engine,
    make_sessionmaker,
    utcnow,
)
from .elevenlabs_audio import (
    AUDIO_MODELS,
    MAX_ISOLATE_SECONDS,
    IsolateIn,
)
from .elevenlabs_audio import SERVICES as AUDIO_SERVICES
from .elevenlabs_audio import estimate as audio_estimate
from .elevenlabs_audio import run as run_audio_service
from .free_voices import FreeVoiceError, free_sample, free_voices
from .higgsfield import UPLOAD_CONTENT_TYPES
from .presets import BUILTIN, render, resolve_values, variables_in
from .pricing import fill_placeholders, total
from .providers import ProviderError
from .providers import registry as provider_registry
from .providers.prices import PriceBook
from .recommend import recommend
from .routing import Plan, Router, video_urls
from .service import ServiceError, check_input, create_generation, get_owned_job, input_hash, trusted_media
from .sounds import LABELS as SOUND_LABELS
from .sounds import as_dict as sound_dict
from .sounds import backfill as backfill_sounds
from .sounds import classify as classify_sound
from .sounds import clean_tags as clean_sound_tags
from .sounds import history_kind as sound_history_kind
from .sounds import register_job as register_sound
from .sounds import title_from as sound_title
from .voice import (
    VOICE_MODEL,
    VOICE_QUOTE_TTL,
    ElevenLabsClient,
    VoiceChangeIn,
    VoiceError,
    change_voice,
    probe_duration,
    segment_bounds,
    voice_digest,
)
from .voice import (
    estimate as voice_estimate,
)
from .worker import Worker

log = logging.getLogger("hf_studio.api")

STAGES = {
    "pending": "Waiting for a free concurrency slot",
    "submitting": "Submitting to the provider",
    "queued": "Queued at the provider",
    "awaiting_approval": "The cheaper provider failed; approve the next one or cancel",
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
    "unsupported": 400, "moderation": 422, "ambiguous": 502,
}  # fmt: skip


# Datos de cotización (p. ej. input_video_seconds): positivos y finitos, o el precio saldría falso.
Hint = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class GenerationIn(BaseModel):
    model: str = Field(description="ID del endpoint, p. ej. bytedance/seedance-2.0/text-to-video")
    input: dict[str, Any] = Field(description="Argumentos según el input_schema del modelo")
    max_usd: float | None = Field(
        None,
        ge=0,
        description="Precio aprobado (el de /v1/estimate). Si la opción más barata cuesta más, responde 409; "
        "un proveedor de respaldo que cueste más pedirá aprobación",
    )
    provider: str | None = Field(
        None, description="Fuerza un proveedor (sin respaldo). Por defecto, el más barato"
    )
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos de cotización, p. ej. input_video_seconds"
    )
    allow_duplicate: bool = Field(False, description="Permite repetir una petición idéntica aún activa")
    keep_source_audio: bool = Field(
        False,
        description="Opción de HF Studio: al terminar, pone al resultado el audio del video de origen (video_url)",
    )


class BatchItem(BaseModel):
    model: str
    input: dict[str, Any]
    count: int = Field(1, ge=1, le=8, description="Copias de esta entrada (variantes)")
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos de cotización propios de este ítem"
    )


class BatchIn(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=20)
    dry_run: bool = Field(False, description="Solo cotiza: devuelve costo por ítem y total, sin generar")
    hints: dict[str, Hint] = Field(default_factory=dict)


class PresetIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    category: str = "Mine"
    model: str
    template: dict[str, Any]
    variables: list[dict[str, Any]] = Field(default_factory=list)
    cover: str | None = None


class PresetFromGeneration(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = ""


class PresetRun(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    hints: dict[str, Hint] = Field(default_factory=dict)


class EstimateIn(BaseModel):
    model: str
    input: dict[str, Any]
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos que la API no puede medir, p. ej. input_video_seconds"
    )
    provider: str | None = Field(None, description="Cotiza solo este proveedor")


class ApproveIn(BaseModel):
    max_usd: float | None = Field(
        None, ge=0, description="Precio que se aprueba; si el respaldo cuesta más, 409"
    )


PRICE_REFRESH_SECONDS = 3600
COST_TOLERANCE_USD = 0.005


async def refresh_prices(app: FastAPI) -> None:
    """Mantiene al día las tablas públicas de precios (una descarga al día por proveedor)."""
    while True:
        results = await app.state.prices.refresh(app.state.providers)
        if results:
            log.info("Tablas de precios: %s", results)
        await asyncio.sleep(PRICE_REFRESH_SECONDS)


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        await init_db(engine)
        app.state.sessions = make_sessionmaker(engine)
        app.state.providers = provider_registry.build(settings, transport)
        # Higgsfield también guarda los medios de entrada y cotiza su catálogo.
        app.state.hf = app.state.providers[provider_registry.DEFAULT_PROVIDER]
        app.state.worker = Worker(app.state.sessions, app.state.providers, settings)
        app.state.prices = PriceBook(Path(settings.storage_dir) / "prices")
        app.state.router = Router(app.state.providers, app.state.prices, get_catalog)
        app.state.tasks = set()
        app.state.eleven = ElevenLabsClient(settings, transport)
        app.state.voice_slots = asyncio.Semaphore(2)
        app.state.voice_quotes = {}
        # Un cambio de voz corre dentro de este proceso: si se reinició a medias, no va a terminar.
        async with app.state.sessions() as s:
            await s.execute(
                update(Job)
                .where(Job.model.in_((VOICE_MODEL, *AUDIO_MODELS)), Job.status.in_(ACTIVE))
                .values(status="failed", error_kind="interrupted", error="Interrupted by a server restart",
                        finished_at=utcnow())
            )  # fmt: skip
            await s.commit()
        if not settings.hf_configured:
            log.warning("Falta HF_API_KEY (o HF_API_KEY_ID + HF_API_KEY_SECRET): los envíos fallarán")
        if settings.worker_enabled:
            app.state.worker.start()
            refresher = asyncio.create_task(refresh_prices(app), name="hf-studio-prices")
            app.state.tasks.add(refresher)
            refresher.add_done_callback(app.state.tasks.discard)
        yield
        await app.state.worker.stop()
        for provider in app.state.providers.values():
            await provider.aclose()
        await app.state.eleven.aclose()
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

    @app.exception_handler(VoiceError)
    async def _voice_error(_: Request, exc: VoiceError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(ProviderError)
    async def _provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        provider = exc.provider or provider_registry.DEFAULT_PROVIDER
        title = getattr(provider_registry.PROVIDERS.get(provider), "title", provider)
        message = f"The server's {title} credentials are invalid" if exc.kind == "auth" else exc.message
        body = {"code": f"{provider}_{exc.kind}", "message": message, "correlation_id": exc.correlation_id}
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

    async def client_names(session: AsyncSession) -> dict[str, str]:
        return dict((await session.execute(select(ApiClient.id, ApiClient.name))).tuples().all())

    def job_out(job: Job, deduplicated: bool | None = None, source: str | None = None) -> dict:
        files = {f["index"]: f for f in job.files or []}
        outputs = []
        for i, out in enumerate(job.outputs or []):
            item = dict(out)
            if i in files:
                item["file_url"] = f"/v1/generations/{job.id}/files/{files[i]['name']}"
                if "audio" in files[i]:
                    item["audio"] = files[i]["audio"]
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
            "keep_source_audio": job.keep_source_audio,
            "outputs": outputs,
            "error": job.error,
            "error_kind": job.error_kind,
            "request_id": job.hf_request_id,
            "correlation_id": job.correlation_id,
            "provider": job.provider,
            "cost_usd": (job.plan[job.plan_index].get("usd") if job.plan else None),
            "max_usd": job.max_usd,
            "plan": [{"provider": o["provider"], "usd": o.get("usd")} for o in job.plan or []],
            "attempts": job.attempts_log or [],
            "created_at": iso(job.created_at),
            "submitted_at": iso(job.submitted_at),
            "finished_at": iso(job.finished_at),
            "elapsed_seconds": round((end - job.created_at).total_seconds(), 1),
        }
        if source is not None:
            body["source"] = source
        if deduplicated is not None:
            body["deduplicated"] = deduplicated
        return body

    def model_out(m: dict, full: bool = False) -> dict:
        keys = ("id", "title", "output", "workflow", "family", "capabilities", "docs_url")
        base = {k: m[k] for k in keys}
        return (
            {
                **base,
                "summary": m["summary"],
                "notes": m["notes"],
                "studio_notes": studio_notes(m),
                "input_schema": m["input_schema"],
            }
            if full
            else base
        )

    # --- Rutas ---------------------------------------------------------------------------------

    @app.get("/health", tags=["sistema"])
    async def health() -> dict:
        return {
            "ok": True,
            "higgsfield_configured": settings.hf_configured,
            "providers_configured": provider_registry.configured(settings),
            "catalog_synced_at": get_catalog().synced_at,
        }

    @app.get("/v1/providers", tags=["sistema"])
    async def providers(request: Request, _: Owner, check: bool = True) -> dict:
        """Proveedores registrados con sus enlaces; con `check`, valida cada clave y lee el saldo (gratis)."""
        items = []
        for provider in request.app.state.providers.values():
            item = provider.info()
            if check and provider.configured:
                result = await provider.check_key()
                item.update(
                    valid=result.valid, balance_usd=result.balance_usd, message=result.message or None
                )
            items.append(item)
        return {"providers": items}

    @app.get("/v1/me", tags=["sistema"])
    async def me(owner: Owner) -> dict:
        return {"id": owner.id, "name": owner.name, "sees_all": owner.sees_all}

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

    async def complete_hints(session: AsyncSession, owner: ApiClient, arguments: dict, hints: dict) -> dict:
        """Mide la duración de los videos de entrada (si no viene en `hints`): varios proveedores cobran
        por ella. Solo medios propios: ffprobe nunca abre URLs arbitrarias (SSRF)."""
        hints = dict(hints or {})
        urls = video_urls(arguments)
        if "input_video_seconds" in hints or not urls:
            return hints
        seconds = 0.0
        for url in urls:
            if not await trusted_media(session, owner, url):
                return hints
            measured = await probe_duration(url)
            if not measured:
                return hints
            seconds += measured
        hints["input_video_seconds"] = round(seconds, 2)
        return hints

    async def make_plan(
        request: Request, session: AsyncSession, owner: ApiClient, model: dict, arguments: dict, hints: dict,
        provider: str | None = None,
    ) -> Plan:  # fmt: skip
        hints = await complete_hints(session, owner, arguments, hints)
        if provider and provider not in provider_registry.PROVIDERS:
            raise ServiceError(422, "unknown_provider", f"Unknown provider {provider!r}")
        return await request.app.state.router.plan(model, arguments, hints, only=provider)

    def estimate_body(plan: Plan) -> dict:
        """Costo de la opción elegida con los campos de siempre, más todas las opciones y el ahorro."""
        best = plan.best
        if best is None:
            reasons = "; ".join(f"{e['title']}: {e['reason']}" for e in plan.excluded) or "no provider"
            base = {"kind": "unavailable", "credits": None, "usd": None, "discount_pct": None,
                    "basis": f"No provider can run this request ({reasons})", "missing": [], "description": None}  # fmt: skip
        else:
            keys = ("kind", "credits", "usd", "discount_pct", "basis", "missing", "description")
            base = {k: getattr(best, k) for k in keys}
            if best.provider != provider_registry.DEFAULT_PROVIDER:
                base["basis"] = f"{best.title}: {best.basis}"
        return {**base, **plan.public()}

    @app.post("/v1/estimate", tags=["generaciones"])
    async def estimate(
        body: EstimateIn, request: Request, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Costo antes de generar en cada proveedor, con el más barato primero (y el motivo de los excluidos)."""
        model = catalog.get(body.model)
        if not model:
            raise ServiceError(404, "unknown_model", f"Unknown model: {body.model}")
        filled, _ = fill_placeholders(model["input_schema"], body.input)
        check_input(catalog, model["id"], filled)
        plan = await make_plan(request, session, owner, model, body.input, body.hints, body.provider)
        return estimate_body(plan)

    @app.get("/v1/recommend", tags=["modelos"])
    async def recommend_models(
        request: Request,
        _: Owner,
        catalog: CatalogDep,
        task: str = Query(min_length=3, max_length=500, description="Qué quieres crear, en lenguaje natural"),
        limit: int = Query(5, ge=1, le=10),
        output: str | None = Query(None, pattern="^(video|image)$"),
    ) -> dict:
        """Sugiere modelos para una tarea, con el costo de una configuración estándar."""
        return await recommend(request.app.state.hf, catalog, task, limit, output)

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
        model = check_input(catalog, body.model, body.input)
        plan = await make_plan(request, session, owner, model, body.input, body.hints, body.provider)
        best = plan.best
        if best is None:
            raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
        if body.max_usd is not None and best.usd is not None and best.usd > body.max_usd + COST_TOLERANCE_USD:
            raise ServiceError(
                409, "cost_changed",
                f"The cheapest option now costs {best.usd:.2f} USD (approved {body.max_usd:.2f}); quote again",
                plan.public(),
            )  # fmt: skip
        job, created = await create_generation(
            session,
            settings,
            catalog,
            owner,
            body.model,
            body.input,
            idempotency_key,
            body.allow_duplicate,
            keep_source_audio=body.keep_source_audio,
            plan=plan.stored(),
            max_usd=body.max_usd if body.max_usd is not None else best.usd,
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
        ids: str | None = Query(None, description="IDs separados por coma (espera múltiple con wait)"),
        wait: int = Query(0, ge=0, le=120, description="Con ids: espera hasta N s a que todas terminen"),
    ) -> dict:
        query = select(Job) if owner.sees_all else select(Job).where(Job.owner_id == owner.id)
        if ids:
            wanted = [i for i in ids.split(",") if i][:50]
            query = query.where(Job.id.in_(wanted))
        if status:
            query = query.where(Job.status == status)
        query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)
        jobs = list(await session.scalars(query))
        deadline = asyncio.get_running_loop().time() + (wait if ids else 0)
        while any(j.status not in TERMINAL for j in jobs) and asyncio.get_running_loop().time() < deadline:
            await session.commit()
            await asyncio.sleep(1)
            for j in jobs:
                await session.refresh(j)
        names = await client_names(session) if owner.sees_all else {}
        return {
            "generations": [job_out(j, source=names.get(j.owner_id)) for j in jobs],
            "all_terminal": all(j.status in TERMINAL for j in jobs),
        }

    @app.post("/v1/generations/batch", tags=["generaciones"])
    async def create_batch(
        body: BatchIn,
        request: Request,
        session: Session,
        owner: Owner,
        catalog: CatalogDep,
        idempotency_key: Annotated[str | None, Header(max_length=180)] = None,
    ) -> JSONResponse:
        """Varias generaciones de una vez. Con dry_run solo cotiza (costo por ítem y total)."""
        for item in body.items:
            if not catalog.get(item.model):
                raise ServiceError(404, "unknown_model", f"Unknown model: {item.model}")
        if body.dry_run:
            plans = [
                await make_plan(
                    request, session, owner, catalog.get(i.model), i.input, {**body.hints, **i.hints}
                )
                for i in body.items
            ]
            quotes = [estimate_body(p) for p in plans]
            counts = [i.count for i in body.items]
            items = [
                {"model": i.model, "count": i.count, "estimate": q}
                for i, q in zip(body.items, quotes, strict=True)
            ]
            return JSONResponse({"items": items, "total": total(quotes, counts)})
        for item in body.items:
            check_input(catalog, item.model, item.input)
        wanted = sum(i.count for i in body.items)
        if idempotency_key:
            # Reintento del mismo lote: devolver lo ya creado antes de mirar cupos.
            keys = [f"{idempotency_key}:{n}" for n in range(wanted)]
            found = {
                j.idempotency_key: j
                for j in await session.scalars(
                    select(Job).where(Job.owner_id == owner.id, Job.idempotency_key.in_(keys))
                )
            }
            if len(found) == wanted:
                return JSONResponse({"generations": [job_out(found[k]) for k in keys]}, status_code=200)
        active = await session.scalar(
            select(func.count()).select_from(Job).where(Job.owner_id == owner.id, Job.status.in_(ACTIVE))
        )
        if active + wanted > settings.max_active_jobs_per_client:
            raise ServiceError(
                429,
                "too_many_active",
                f"This batch needs {wanted} slots; you have {active} active of {settings.max_active_jobs_per_client}",
            )
        jobs, created_any = [], False
        n = 0
        for item in body.items:
            plan = await make_plan(
                request, session, owner, catalog.get(item.model), item.input, {**body.hints, **item.hints}
            )
            if plan.best is None:
                raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
            for _ in range(item.count):
                key = f"{idempotency_key}:{n}" if idempotency_key else None
                job, created = await create_generation(
                    session, settings, catalog, owner, item.model, item.input, key, allow_duplicate=True,
                    plan=plan.stored(),
                )  # fmt: skip
                jobs.append(job)
                created_any |= created
                n += 1
        if created_any:
            request.app.state.worker.wake()
        return JSONResponse(
            {"generations": [job_out(j) for j in jobs]}, status_code=202 if created_any else 200
        )

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
        source = (await client_names(session)).get(job.owner_id) if owner.sees_all else None
        return job_out(job, source=source)

    @app.delete("/v1/generations/{job_id}", tags=["generaciones"], status_code=204)
    async def delete_generation(job_id: str, session: Session, owner: Owner) -> None:
        """Quita una generación terminada del historial y borra su copia local."""
        job = await get_owned_job(session, owner, job_id)
        if job.status not in TERMINAL:
            raise ServiceError(409, "still_active", "Cancel the generation before deleting it")
        await session.execute(delete(Sound).where(Sound.job_id == job.id))  # su sonido en la sonoteca
        await session.delete(job)
        await session.commit()
        shutil.rmtree(Path(settings.storage_dir) / "outputs" / job_id, ignore_errors=True)

    @app.post("/v1/generations/{job_id}/approve", tags=["generaciones"])
    async def approve(job_id: str, body: ApproveIn, request: Request, session: Session, owner: Owner) -> dict:
        """Aprueba el proveedor de respaldo más caro que espera un trabajo (`awaiting_approval`)."""
        job = await get_owned_job(session, owner, job_id)
        if job.status != "awaiting_approval" or job.plan_index + 1 >= len(job.plan or []):
            raise ServiceError(
                409, "not_awaiting_approval", f"Generation is {job.status}; nothing to approve"
            )
        option = job.plan[job.plan_index + 1]
        usd = option.get("usd")
        if body.max_usd is not None and (usd is None or usd > body.max_usd + COST_TOLERANCE_USD):
            price = f"{usd:.2f} USD" if usd is not None else "an unknown price"
            raise ServiceError(
                409, "cost_changed", f"The fallback costs {price}, more than {body.max_usd:.2f}"
            )
        done = await session.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "awaiting_approval")
            .values(status="pending", plan_index=job.plan_index + 1, provider=option["provider"],
                    max_usd=max(job.max_usd or 0, usd) if usd is not None else job.max_usd,
                    error=None, error_kind=None, next_check_at=None)
        )  # fmt: skip
        await session.commit()
        if done.rowcount != 1:
            raise ServiceError(409, "not_awaiting_approval", "Generation changed; nothing to approve")
        await session.refresh(job)
        request.app.state.worker.wake()
        return job_out(job)

    @app.post("/v1/generations/{job_id}/cancel", tags=["generaciones"])
    async def cancel(job_id: str, request: Request, session: Session, owner: Owner) -> dict:
        job = await get_owned_job(session, owner, job_id)
        if job.status in ("pending", "awaiting_approval"):
            # Atómico frente al worker, que reclama los pendientes con la misma condición.
            done = await session.execute(
                update(Job)
                .where(Job.id == job.id, Job.status.in_(("pending", "awaiting_approval")))
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
            await request.app.state.worker.provider(job).cancel_job(job.hf_request_id, job.cancel_url)
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

    async def find_preset(session: AsyncSession, owner: ApiClient, slug: str) -> dict:
        for p in BUILTIN:
            if p["slug"] == slug:
                return {**p, "builtin": True}
        own = await session.scalar(select(Preset).where(Preset.owner_id == owner.id, Preset.slug == slug))
        if not own:
            raise ServiceError(404, "not_found", f"Unknown preset: {slug}")
        return own.as_dict()

    def check_preset(catalog: Catalog, body: PresetIn) -> dict:
        model = catalog.get(body.model)
        if not model:
            raise ServiceError(404, "unknown_model", f"Unknown model: {body.model}")
        declared = {v.get("key") for v in body.variables}
        undeclared = variables_in(body.template) - declared
        if undeclared:
            raise ServiceError(
                422, "invalid_preset", f"Undeclared variables in template: {sorted(undeclared)}"
            )
        return model

    @app.get("/v1/presets", tags=["presets"])
    async def list_presets(session: Session, owner: Owner) -> dict:
        own = await session.scalars(
            select(Preset).where(Preset.owner_id == owner.id).order_by(Preset.created_at.desc())
        )
        return {"presets": [p.as_dict() for p in own] + [{**p, "builtin": True} for p in BUILTIN]}

    @app.get("/v1/presets/{slug}", tags=["presets"])
    async def get_preset(slug: str, session: Session, owner: Owner) -> dict:
        return await find_preset(session, owner, slug)

    @app.post("/v1/presets", tags=["presets"], status_code=201)
    async def create_preset(body: PresetIn, session: Session, owner: Owner, catalog: CatalogDep) -> dict:
        model = check_preset(catalog, body)
        if any(p["slug"] == body.slug for p in BUILTIN):
            raise ServiceError(409, "slug_taken", "A built-in preset already uses this slug")
        if await session.scalar(select(Preset).where(Preset.owner_id == owner.id, Preset.slug == body.slug)):
            raise ServiceError(409, "slug_taken", "You already have a preset with this slug")
        preset = Preset(owner_id=owner.id, output=model["output"], **body.model_dump())
        session.add(preset)
        await session.commit()
        return preset.as_dict()

    @app.post("/v1/presets/from-generation/{job_id}", tags=["presets"], status_code=201)
    async def preset_from_generation(
        job_id: str, body: PresetFromGeneration, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Convierte una generación en preset: mismos ajustes y medios; el prompt queda como variable."""
        job = await get_owned_job(session, owner, job_id)
        template = dict(job.input)
        variables = []
        if isinstance(template.get("prompt"), str):
            variables.append(
                {"key": "prompt", "label": "Prompt", "type": "textarea", "default": template["prompt"]}
            )
            template["prompt"] = "{{prompt}}"
        return await create_preset(
            PresetIn(
                slug=body.slug,
                title=body.title,
                description=body.description,
                model=job.model,
                template=template,
                variables=variables,
            ),
            session,
            owner,
            catalog,
        )

    @app.delete("/v1/presets/{slug}", tags=["presets"], status_code=204)
    async def delete_preset(slug: str, session: Session, owner: Owner) -> None:
        own = await session.scalar(select(Preset).where(Preset.owner_id == owner.id, Preset.slug == slug))
        if not own:
            raise ServiceError(404, "not_found", "Only your own presets can be deleted")
        await session.delete(own)
        await session.commit()

    @app.post("/v1/presets/{slug}/run", tags=["presets"])
    async def run_preset(
        slug: str,
        body: PresetRun,
        request: Request,
        session: Session,
        owner: Owner,
        catalog: CatalogDep,
        idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
    ) -> JSONResponse:
        """Rellena la plantilla del preset. Con dry_run devuelve la entrada resultante y su costo."""
        preset = await find_preset(session, owner, slug)
        values, missing = resolve_values(preset, body.variables)
        model_input = render(preset["template"], values)
        if body.dry_run:
            q = estimate_body(
                await make_plan(
                    request, session, owner, catalog.get(preset["model"]), model_input, body.hints
                )
            )
            return JSONResponse(
                {"model": preset["model"], "input": model_input, "missing_variables": missing, "estimate": q}
            )
        if missing:
            raise ServiceError(
                422,
                "missing_variables",
                "Fill the required fields",
                [{"path": k, "message": "required"} for k in missing],
            )
        model = check_input(catalog, preset["model"], model_input)
        plan = await make_plan(request, session, owner, model, model_input, body.hints)
        if plan.best is None:
            raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
        job, created = await create_generation(
            session,
            settings,
            catalog,
            owner,
            preset["model"],
            model_input,
            idempotency_key,
            plan=plan.stored(),
        )
        if created:
            request.app.state.worker.wake()
        return JSONResponse(job_out(job, deduplicated=not created), status_code=202 if created else 200)

    # --- Cambio de voz (ElevenLabs) --------------------------------------------------------------

    async def voice_source(session: AsyncSession, owner: ApiClient, body: VoiceChangeIn) -> str:
        """Ruta local o URL del video de origen."""
        if body.source_url:
            # Solo medios propios: ffmpeg no debe abrir URLs arbitrarias (SSRF).
            if not await trusted_media(session, owner, body.source_url):
                raise ServiceError(
                    422,
                    "untrusted_source",
                    "source_url must come from /v1/uploads (upload_media) or be one of your generations",
                )
            return body.source_url
        job = await get_owned_job(session, owner, body.source_generation_id or "")
        videos = [o for o in job.outputs or [] if o.get("kind") == "video"]
        if job.status != "completed" or not videos:
            raise ServiceError(422, "invalid_source", "The source generation is not a completed video")
        for f in job.files or []:
            path = Path(settings.storage_dir) / "outputs" / job.id / f["name"]
            if f.get("kind") == "video" and path.exists():
                return str(path.resolve())
        return videos[0]["url"]

    async def voice_plan(
        session: AsyncSession, owner: ApiClient, body: VoiceChangeIn
    ) -> tuple[str, float, float]:
        source = await voice_source(session, owner, body)
        duration = await probe_duration(source)
        if duration is None:
            raise ServiceError(422, "invalid_source", "Could not read the source video")
        start, end = segment_bounds(body, duration)
        return source, start, end

    @app.get("/v1/voice/status", tags=["voz"])
    async def voice_status(request: Request, _: Owner) -> dict:
        """Si ElevenLabs está configurado y, si lo está, el plan y los créditos que quedan."""
        eleven = request.app.state.eleven
        if not eleven.configured:
            return {"configured": False}
        return {"configured": True, **(await eleven.subscription())}

    @app.get("/v1/voice/voices", tags=["voz"])
    async def voice_list(
        request: Request,
        _: Owner,
        search: str | None = Query(None, max_length=100),
        library: bool = Query(False, description="Buscar en la biblioteca pública de ElevenLabs"),
        limit: int = Query(30, ge=1, le=100),
        language: str | None = Query(
            None, max_length=10, description="Solo biblioteca: código ISO, p. ej. es"
        ),
        accent: str | None = Query(None, max_length=40, description="Solo biblioteca: p. ej. colombian"),
        gender: str | None = Query(None, max_length=20, description="Solo biblioteca: male o female"),
    ) -> dict:
        filters = {k: v for k, v in {"language": language, "accent": accent, "gender": gender}.items() if v}
        return {"voices": await request.app.state.eleven.voices(search, library, limit, filters)}

    @app.get("/v1/voice/free-voices", tags=["voz"])
    async def free_voice_list(_: Owner, lang: str = Query("es", pattern=r"^[a-z]{2}$")) -> dict:
        """Voces gratis de edge-tts (Microsoft Edge) de un idioma. No gasta créditos ni necesita clave."""
        try:
            return {"voices": await free_voices(lang)}
        except Exception as exc:
            raise ServiceError(
                502, "free_voices_unavailable", f"Could not list the free voices: {exc}"
            ) from exc

    @app.get("/v1/voice/free-sample", tags=["voz"])
    async def free_voice_sample(
        _: Owner,
        voice: str = Query(..., max_length=80),
        text: str = Query(..., max_length=600),
        rate: str = Query("+0%", max_length=5),
    ) -> FileResponse:
        """MP3 de una voz gratis diciendo el texto (hasta 300 caracteres). Gratis; se guarda en caché."""
        try:
            path = await free_sample(voice, text, rate, settings.storage_dir)
        except FreeVoiceError as exc:
            raise ServiceError(exc.status, exc.code, exc.message) from exc
        return FileResponse(
            path, media_type="audio/mpeg", filename=path.name, content_disposition_type="inline"
        )

    @app.post("/v1/voice/estimate", tags=["voz"])
    async def voice_estimate_route(
        body: VoiceChangeIn, request: Request, session: Session, owner: Owner
    ) -> dict:
        """Costo de un cambio de voz antes de lanzarlo, con un voice_quote de un solo uso para lanzarlo."""
        _, start, end = await voice_plan(session, owner, body)
        quotes: dict = request.app.state.voice_quotes
        now = time.monotonic()
        for qid in [q for q, v in quotes.items() if v["expires"] < now]:
            del quotes[qid]
        qid = "vq_" + uuid.uuid4().hex
        quotes[qid] = {"owner": owner.id, "digest": voice_digest(body), "seconds": end - start,
                       "expires": now + VOICE_QUOTE_TTL, "used": False}  # fmt: skip
        return {**voice_estimate(end - start, settings), "start": start, "end": end, "voice_quote": qid}

    @app.post("/v1/voice/changes", tags=["voz"], status_code=202)
    async def voice_change(
        body: VoiceChangeIn,
        request: Request,
        session: Session,
        owner: Owner,
        idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
    ) -> JSONResponse:
        """Lanza un cambio de voz. Es asíncrono: sigue el trabajo con GET /v1/generations/{id}."""
        if not request.app.state.eleven.configured:
            raise VoiceError(
                503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env to change voices"
            )
        if not body.voice_quote:
            raise ServiceError(
                422, "quote_required", "Quote first (POST /v1/voice/estimate) and send its voice_quote"
            )
        request_args = body.model_dump(exclude_none=True, exclude={"voice_quote"})
        digest = voice_digest(body)
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
                return JSONResponse(job_out(existing, deduplicated=True), status_code=200)
        # Regla del dueño: solo se gasta con una cotización de esta API, de este cliente, de esta misma
        # petición, vigente y sin usar; y si el tramo real cambió desde entonces, no se cobra.
        quote = request.app.state.voice_quotes.get(body.voice_quote)
        if (
            not quote
            or quote["owner"] != owner.id
            or quote["digest"] != digest
            or quote["used"]
            or quote["expires"] < time.monotonic()
        ):
            raise ServiceError(
                409,
                "quote_invalid",
                "Missing, expired, used or mismatched voice_quote. Quote this exact request again",
            )
        # Reserva atómica: entre la comprobación y esta línea no hay ningún await, así que dos envíos
        # simultáneos no pueden canjear la misma cotización. Si algo falla antes de crear el trabajo, se libera.
        quote["used"] = True
        try:
            source, start, end = await voice_plan(session, owner, body)
            if abs((end - start) - quote["seconds"]) > 0.05:
                raise ServiceError(
                    409,
                    "cost_changed",
                    f"The segment now lasts {end - start:.2f}s, not the quoted {quote['seconds']:.2f}s. "
                    "Quote again and show the new cost",
                )
            active = await session.scalar(
                select(func.count()).select_from(Job).where(Job.owner_id == owner.id, Job.status.in_(ACTIVE))
            )
            if active >= settings.max_active_jobs_per_client:
                raise ServiceError(
                    429,
                    "too_many_active",
                    f"You have {active} active jobs (maximum {settings.max_active_jobs_per_client})",
                )
            args = {**request_args, "start": start, "end": end}
            job = Job(
                owner_id=owner.id,
                model=VOICE_MODEL,
                input=args,
                input_hash=digest,
                idempotency_key=idempotency_key,
                status="in_progress",
                submitted_at=utcnow(),
            )
            session.add(job)
            try:
                await session.commit()
            except IntegrityError:
                # Dos envíos simultáneos con la misma Idempotency-Key: gana el primero.
                await session.rollback()
                existing = await session.scalar(
                    select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == idempotency_key)
                )
                if existing and existing.input_hash == digest:
                    quote["used"] = False  # ese trabajo ya existía: esta petición no gasta
                    return JSONResponse(job_out(existing, deduplicated=True), status_code=200)
                raise ServiceError(
                    409,
                    "idempotency_conflict",
                    "This Idempotency-Key was already used for a different request",
                ) from None
        except BaseException:
            quote["used"] = False
            raise
        task = asyncio.create_task(run_voice_change(request.app, job.id, body, source, start, end))
        request.app.state.tasks.add(task)
        task.add_done_callback(request.app.state.tasks.discard)
        return JSONResponse(job_out(job, deduplicated=False), status_code=202)

    async def run_voice_change(
        app: FastAPI, job_id: str, body: VoiceChangeIn, source: str, start: float, end: float
    ) -> None:
        name = "0-video.mp4"
        out = Path(settings.storage_dir) / "outputs" / job_id / name
        error: tuple[str, str] | None = None

        async def convert() -> None:
            async with app.state.voice_slots:
                await change_voice(app.state.eleven, body, source, start, end, out)

        # El plazo cuenta desde la creación, también mientras espera un hueco (el semáforo).
        try:
            await asyncio.wait_for(convert(), settings.job_timeout_seconds)
        except TimeoutError:
            error = ("timed_out", f"Exceeded {settings.job_timeout_seconds}s")
        except VoiceError as exc:
            error = (exc.code, exc.message)
        except Exception as exc:  # no dejar el trabajo colgado en in_progress
            log.exception("Cambio de voz %s falló", job_id)
            error = ("internal", str(exc))
        async with app.state.sessions() as s:
            job = await s.get(Job, job_id)
            if not job:
                return
            job.finished_at = utcnow()
            if error:
                job.status = "timed_out" if error[0] == "timed_out" else "failed"
                job.error_kind, job.error = error[0], error[1]
            else:
                job.status = "completed"
                job.outputs = [{"kind": "video", "url": f"/v1/generations/{job_id}/files/{name}"}]
                job.files = [{"name": name, "kind": "video", "size": out.stat().st_size,
                              "content_type": "video/mp4", "index": 0}]  # fmt: skip
            await s.commit()

    # --- Audio de ElevenLabs: texto a voz, efectos, música y aislamiento ------------------------

    async def audio_source(session: AsyncSession, owner: ApiClient, body: IsolateIn) -> str:
        """Ruta local o URL de un video o audio propio (nunca una URL arbitraria)."""
        if body.source_url:
            if not await trusted_media(session, owner, body.source_url):
                raise ServiceError(
                    422,
                    "untrusted_source",
                    "source_url must come from /v1/uploads (upload_media) or your generations",
                )
            return body.source_url
        job = await get_owned_job(session, owner, body.source_generation_id or "")
        media = [o for o in job.outputs or [] if o.get("kind") in ("video", "audio")]
        if job.status != "completed" or not media:
            raise ServiceError(
                422, "invalid_source", "The source generation is not a completed video or audio"
            )
        for f in job.files or []:
            path = Path(settings.storage_dir) / "outputs" / job.id / f["name"]
            if f.get("kind") in ("video", "audio") and path.exists():
                return str(path.resolve())
        return media[0]["url"]

    async def audio_plan(session: AsyncSession, owner: ApiClient, body: BaseModel) -> tuple[str | None, dict]:
        """(fuente, cotización) de un servicio de audio; el aislamiento mide la duración de la fuente."""
        if not isinstance(body, IsolateIn):
            return None, audio_estimate(body)
        source = await audio_source(session, owner, body)
        seconds = await probe_duration(source)
        if seconds is None:
            raise ServiceError(422, "invalid_source", "Could not read the source media")
        if seconds > MAX_ISOLATE_SECONDS:
            raise ServiceError(
                422, "source_too_long", f"The source must last at most {MAX_ISOLATE_SECONDS:.0f}s"
            )
        return source, audio_estimate(body, seconds)

    def add_audio_routes(service: str, model_id: str, schema: type[BaseModel]) -> None:
        def digest_of(body: BaseModel) -> str:
            return input_hash(model_id, body.model_dump(exclude_none=True, exclude={"audio_quote"}))

        async def estimate_route(body: schema, request: Request, session: Session, owner: Owner) -> dict:  # type: ignore[valid-type]
            _, est = await audio_plan(session, owner, body)
            quotes: dict = request.app.state.voice_quotes
            now = time.monotonic()
            for qid in [q for q, v in quotes.items() if v["expires"] < now]:
                del quotes[qid]
            qid = "aq_" + uuid.uuid4().hex
            quotes[qid] = {"owner": owner.id, "digest": digest_of(body), "seconds": est["units"],
                           "expires": now + VOICE_QUOTE_TTL, "used": False}  # fmt: skip
            return {**est, "audio_quote": qid}

        async def create_route(
            body: schema,  # type: ignore[valid-type]
            request: Request,
            session: Session,
            owner: Owner,
            idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
        ) -> JSONResponse:
            if not request.app.state.eleven.configured:
                raise VoiceError(503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env")
            if not body.audio_quote:
                raise ServiceError(
                    422,
                    "quote_required",
                    f"Quote first (POST /v1/audio/{service}/estimate) and send its audio_quote",
                )
            digest = digest_of(body)
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
                    return JSONResponse(job_out(existing, deduplicated=True), status_code=200)
            quote = request.app.state.voice_quotes.get(body.audio_quote)
            if (
                not quote
                or quote["owner"] != owner.id
                or quote["digest"] != digest
                or quote["used"]
                or quote["expires"] < time.monotonic()
            ):
                raise ServiceError(
                    409,
                    "quote_invalid",
                    "Missing, expired, used or mismatched audio_quote. Quote this exact request again",
                )
            # Reserva atómica (sin await desde la comprobación); se libera si falla antes de crear el trabajo.
            quote["used"] = True
            try:
                source, est = await audio_plan(session, owner, body)
                if abs(est["units"] - quote["seconds"]) > 0.05:
                    raise ServiceError(
                        409, "cost_changed", "The input changed since it was quoted. Quote again"
                    )
                active = await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.owner_id == owner.id, Job.status.in_(ACTIVE))
                )
                if active >= settings.max_active_jobs_per_client:
                    raise ServiceError(
                        429, "too_many_active",
                        f"You have {active} active jobs (maximum {settings.max_active_jobs_per_client})",
                    )  # fmt: skip
                job = Job(
                    owner_id=owner.id,
                    model=model_id,
                    input=body.model_dump(exclude_none=True, exclude={"audio_quote"}),
                    input_hash=digest,
                    idempotency_key=idempotency_key,
                    status="in_progress",
                    submitted_at=utcnow(),
                )
                session.add(job)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    existing = await session.scalar(
                        select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == idempotency_key)
                    )
                    if existing and existing.input_hash == digest:
                        quote["used"] = False
                        return JSONResponse(job_out(existing, deduplicated=True), status_code=200)
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "This Idempotency-Key was already used for a different request",
                    ) from None
            except BaseException:
                quote["used"] = False
                raise
            task = asyncio.create_task(run_audio_job(request.app, job.id, body, source))
            request.app.state.tasks.add(task)
            task.add_done_callback(request.app.state.tasks.discard)
            return JSONResponse(job_out(job, deduplicated=False), status_code=202)

        estimate_route.__doc__ = f"Costo de {service} en ElevenLabs, con un audio_quote de un solo uso."
        create_route.__doc__ = (
            f"Lanza {service} en ElevenLabs (asíncrono: sigue el trabajo en /v1/generations)."
        )
        app.post(f"/v1/audio/{service}/estimate", tags=["audio"], operation_id=f"estimate_{service}")(
            estimate_route
        )
        app.post(f"/v1/audio/{service}", tags=["audio"], status_code=202, operation_id=f"create_{service}")(
            create_route
        )

    for _service, (_model, _schema) in AUDIO_SERVICES.items():
        add_audio_routes(_service, _model, _schema)

    async def run_audio_job(app: FastAPI, job_id: str, body: BaseModel, source: str | None) -> None:
        name = "0-audio.mp3"
        out = Path(settings.storage_dir) / "outputs" / job_id / name
        error: tuple[str, str] | None = None

        async def produce() -> None:
            async with app.state.voice_slots:
                await run_audio_service(app.state.eleven, body, out, source)

        try:
            await asyncio.wait_for(produce(), settings.job_timeout_seconds)
        except TimeoutError:
            error = ("timed_out", f"Exceeded {settings.job_timeout_seconds}s")
        except VoiceError as exc:
            error = (exc.code, exc.message)
        except Exception as exc:
            log.exception("Trabajo de audio %s falló", job_id)
            error = ("internal", str(exc))
        async with app.state.sessions() as s:
            job = await s.get(Job, job_id)
            if not job:
                return
            job.finished_at = utcnow()
            if error:
                job.status = "timed_out" if error[0] == "timed_out" else "failed"
                job.error_kind, job.error = error[0], error[1]
            else:
                job.status = "completed"
                job.outputs = [{"kind": "audio", "url": f"/v1/generations/{job_id}/files/{name}"}]
                job.files = [{"name": name, "kind": "audio", "size": out.stat().st_size,
                              "content_type": "audio/mpeg", "index": 0}]  # fmt: skip
                await register_sound(s, job, Path(settings.storage_dir))
            await s.commit()

    # --- Sonoteca ------------------------------------------------------------------------------

    def sounds_query(owner: ApiClient):
        query = select(Sound)
        return query if owner.sees_all else query.where(Sound.owner_id == owner.id)

    async def owned_sound(session: AsyncSession, owner: ApiClient, sound_id: str) -> Sound:
        sound = await session.get(Sound, sound_id)
        if not sound or (sound.owner_id != owner.id and not owner.sees_all):
            raise ServiceError(404, "not_found", "Sound not found")
        return sound

    @app.get("/v1/sounds", tags=["sonoteca"])
    async def list_sounds(
        session: Session,
        owner: Owner,
        category: str | None = Query(None, description="voice, scream, laugh, creature, ambience, impact…"),
        q: str | None = Query(None, max_length=100, description="Busca en título, texto y etiquetas"),
        limit: int = Query(200, ge=1, le=500),
    ) -> dict:
        """Sonidos de ElevenLabs (de HF Studio e importados), del más nuevo al más viejo, con el recuento por categoría."""
        await backfill_sounds(session, Path(settings.storage_dir), owner)
        rows = list(await session.scalars(sounds_query(owner).order_by(Sound.created_at.desc())))
        counts = {c: 0 for c in SOUND_LABELS}
        for r in rows:
            counts[r.category] = counts.get(r.category, 0) + 1
        if category:
            rows = [r for r in rows if r.category == category]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in f"{r.title} {r.text} {' '.join(r.tags or [])}".lower()]
        names = await client_names(session) if owner.sees_all else {}
        return {
            "sounds": [sound_dict(r, names.get(r.owner_id)) for r in rows[:limit]],
            "counts": counts,
            "categories": list(SOUND_LABELS),
        }

    class SoundPatch(BaseModel):
        title: str | None = Field(None, min_length=1, max_length=200)
        category: str | None = None
        tags: list[str] | None = Field(None, max_length=12)

    @app.patch("/v1/sounds/{sound_id}", tags=["sonoteca"])
    async def update_sound(sound_id: str, body: SoundPatch, session: Session, owner: Owner) -> dict:
        """Corrige el título, la categoría o las etiquetas de un sonido."""
        sound = await owned_sound(session, owner, sound_id)
        if body.category is not None:
            if body.category not in SOUND_LABELS:
                raise ServiceError(
                    422, "invalid_category", f"category must be one of {', '.join(SOUND_LABELS)}"
                )
            sound.category = body.category
        if body.title is not None:
            sound.title = body.title.strip()
        if body.tags is not None:
            sound.tags = clean_sound_tags(body.tags)
        await session.commit()
        return sound_dict(sound)

    @app.get("/v1/sounds/{sound_id}/file", tags=["sonoteca"])
    async def sound_file(sound_id: str, session: Session, owner: Owner) -> FileResponse:
        sound = await owned_sound(session, owner, sound_id)
        root = Path(settings.storage_dir).resolve()
        path = (root / sound.file_name).resolve()
        if not path.is_relative_to(root) or not path.exists():
            raise ServiceError(404, "not_found", "The sound file is missing")
        slug = re.sub(r"[^a-z0-9]+", "-", sound.title.lower()).strip("-")[:60] or "sound"
        return FileResponse(path, media_type="audio/mpeg", filename=f"{slug}{path.suffix}",
                            content_disposition_type="inline")  # fmt: skip

    @app.post("/v1/sounds/import-elevenlabs", tags=["sonoteca"])
    async def import_elevenlabs(request: Request, session: Session, owner: Owner) -> dict:
        """Trae a la sonoteca el historial de voz de ElevenLabs (lo generado en su web u otras apps). Gratis:
        solo lee. La API de ElevenLabs no expone los efectos ni la música de su historial."""
        eleven = request.app.state.eleven
        known = set(await session.scalars(select(Sound.external_id).where(Sound.owner_id == owner.id,
                                                                           Sound.external_id.is_not(None))))  # fmt: skip
        folder = Path(settings.storage_dir) / "sounds"
        folder.mkdir(parents=True, exist_ok=True)
        imported, skipped, after = 0, 0, None
        for _ in range(10):  # hasta 1.000 elementos
            page = await eleven.history(100, after)
            for item in page.get("history", []):
                hid = item.get("history_item_id")
                if not hid or hid in known:
                    skipped += 1
                    continue
                data = await eleven.history_audio(hid)
                name = f"sounds/{re.sub(r'[^A-Za-z0-9_-]', '', hid)}.mp3"
                (Path(settings.storage_dir) / name).write_bytes(data)
                kind = sound_history_kind(item.get("source"))
                text = item.get("text") or " ".join(d.get("text", "") for d in item.get("dialogue") or [])
                category, tags = classify_sound(text, kind)
                session.add(Sound(
                    owner_id=owner.id, external_id=hid, origin="elevenlabs", kind=kind,
                    title=sound_title(text) if text else "ElevenLabs", category=category,
                    tags=clean_sound_tags([*tags, str(item.get("source") or "").lower()]), text=text,
                    file_name=name, duration=await probe_duration(str(Path(settings.storage_dir) / name)),
                    created_at=datetime.fromtimestamp(item.get("date_unix") or 0, UTC).replace(tzinfo=None),
                ))  # fmt: skip
                known.add(hid)
                imported += 1
            await session.commit()
            after = page.get("last_history_item_id")
            if not page.get("has_more") or not after:
                break
        return {"imported": imported, "skipped": skipped}

    @app.post("/v1/webhooks/{provider}/{job_id}", tags=["sistema"], include_in_schema=False)
    @app.post("/v1/webhooks/{provider}/{job_id}/callback", tags=["sistema"], include_in_schema=False)
    async def webhook(
        provider: str, job_id: str, request: Request, session: Session, token: str = ""
    ) -> dict:
        """Aviso de un proveedor (APIMart añade `/callback` a la URL). El cuerpo no se usa como verdad:
        solo dispara una consulta autoritativa al endpoint de estado del proveedor."""
        try:
            payload = await request.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ServiceError(400, "bad_envelope", "Unrecognized webhook body")
        if provider == "higgsfield" and not (
            isinstance(payload.get("request_id"), str)
            and payload.get("status") in ("completed", "failed", "nsfw", "canceled")
        ):
            raise ServiceError(400, "bad_envelope", "Unrecognized webhook body")
        job = await session.get(Job, job_id)
        if (
            not job
            or job.provider != provider
            or not hmac.compare_digest(job.webhook_token, token)
            or (provider == "higgsfield" and job.hf_request_id != payload["request_id"])
        ):
            raise ServiceError(404, "not_found", "Unknown webhook")
        if job.status not in TERMINAL or job.status == "timed_out":
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
