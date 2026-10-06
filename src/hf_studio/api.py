import asyncio
import hmac
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import time
import uuid
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from .audio import _run as run_ffmpeg
from .audio import guarded, studio_notes
from .catalog import Catalog, get_catalog
from .config import Settings, get_settings
from .db import (
    ACTIVE,
    TERMINAL,
    ApiClient,
    Element,
    Job,
    Preset,
    Sound,
    Space,
    SpaceRun,
    Upload,
    hash_token,
    init_db,
    make_engine,
    make_sessionmaker,
    utcnow,
)
from .elements import (
    MAX_IMAGES,
    MIN_IMAGES,
    ElementError,
    check_image,
    check_name,
    element_out,
    new_element_id,
)
from .elements import check_available as check_element_ids
from .elements import folder as element_folder
from .elements import purge_deleted as purge_deleted_elements
from .elements import resolve as resolve_elements
from .elevenlabs_audio import (
    AUDIO_MODELS,
    MAX_ISOLATE_SECONDS,
    IsolateIn,
)
from .elevenlabs_audio import SERVICES as AUDIO_SERVICES
from .elevenlabs_audio import estimate as audio_estimate
from .elevenlabs_audio import remote_model as audio_remote_model
from .elevenlabs_audio import run as run_audio_service
from .free_voices import FreeVoiceError, free_sample, free_voices
from .higgsfield import UPLOAD_CONTENT_TYPES
from .media import cached_source, local_duration, matches_type
from .media import download as download_media
from .presets import BUILTIN, render, resolve_values, variables_in
from .pricing import fill_placeholders, total
from .providers import ProviderError
from .providers import registry as provider_registry
from .providers.prices import PriceBook
from .recommend import recommend
from .routing import Plan, Router, requote, video_urls
from .service import (
    UNSET,
    ServiceError,
    check_input,
    create_generation,
    get_owned_job,
    input_hash,
    job_for_key,
    request_digest,
    trusted_media,
)
from .sounds import LABELS as SOUND_LABELS
from .sounds import as_dict as sound_dict
from .sounds import backfill as backfill_sounds
from .sounds import classify as classify_sound
from .sounds import clean_tags as clean_sound_tags
from .sounds import history_kind as sound_history_kind
from .sounds import register_job as register_sound
from .sounds import title_from as sound_title
from .space_audio import ElevenLabsJobs, is_audio_node
from .space_runs import (
    Hooks,
    NodeInputError,
    SpaceRunner,
    is_run_key,
    resolve_input,
    run_scope,
    selected_run,
    spend_of,
)
from .space_tools import AUDIO_PROVIDER, BACKGROUND_PROVIDERS, TOOL_PROVIDER, LocalTools, is_tool, tool_media
from .spaces import GraphError, check_graph, check_values, empty_graph, input_kinds
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
from .worker import LOCAL_MODELS, Worker

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


RESERVE_FIELD = (
    "Retención inicial aprobada (reserve_usd de /v1/estimate) si el proveedor retiene más de lo que cobra"
)


class GenerationIn(BaseModel):
    model: str = Field(description="ID del endpoint, p. ej. bytedance/seedance-2.0/text-to-video")
    accept_unknown_cost: bool = Field(
        False, description="El usuario aceptó explícitamente un precio desconocido (solo para esta opción)"
    )
    max_reserve_usd: float | None = Field(None, ge=0, description=RESERVE_FIELD)
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
    max_total_usd: float | None = Field(
        None, ge=0, description="Total aprobado (el del dry_run); si el lote cuesta más o sin precio, 409"
    )
    max_total_reserve_usd: float | None = Field(
        None, ge=0, description="Suma de retenciones iniciales aprobada"
    )
    accept_unknown_cost: bool = Field(
        False, description="Se aceptó explícitamente un total con precios desconocidos"
    )


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
    max_usd: float | None = Field(None, ge=0, description="Precio aprobado (el del dry_run); si subió, 409")
    accept_unknown_cost: bool = Field(
        False, description="El usuario aceptó explícitamente un precio desconocido (solo para esta opción)"
    )
    max_reserve_usd: float | None = Field(None, ge=0, description=RESERVE_FIELD)


SPACE_COVER = r"^/v1/generations/[A-Za-z0-9-]{1,64}/files/[A-Za-z0-9._-]{1,200}$"


class SpaceIn(BaseModel):
    title: str = Field("Untitled space", min_length=1, max_length=120)
    graph: dict[str, Any] | None = None


class SpaceUpdate(BaseModel):
    version: int = Field(ge=1, description="Versión leída; si otro guardado la cambió, 409 version_conflict")
    title: str | None = Field(None, min_length=1, max_length=120)
    graph: dict[str, Any] | None = None
    cover: str | None = Field(None, pattern=SPACE_COVER, description="Archivo local de una salida propia")


class RunIn(BaseModel):
    mode: str = Field(pattern="^(downstream|workflow)$")
    node_id: str | None = Field(None, max_length=64, description="Nodo inicial (modo downstream)")
    version: int = Field(ge=1, description="Versión guardada del Space; la corrida usa exactamente ese grafo")
    dry_run: bool = Field(False, description="Solo cotiza cada paso y el total, sin gastar")
    max_total_usd: float | None = Field(None, ge=0, description="Tope aprobado para toda la corrida")


class RunApprove(BaseModel):
    max_total_usd: float | None = Field(None, ge=0, description="Nuevo tope (debe cubrir el paso en pausa)")
    accept_unknown: bool = Field(False, description="Acepta que el paso en pausa no tiene precio conocido")


class EstimateIn(BaseModel):
    model: str
    input: dict[str, Any]
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos que la API no puede medir, p. ej. input_video_seconds"
    )
    provider: str | None = Field(None, description="Cotiza solo este proveedor")


class ApproveIn(BaseModel):
    accept_unknown_cost: bool = Field(
        False, description="Aprueba aunque el precio sea desconocido; con max_usd, ese tope sigue mandando"
    )
    max_usd: float | None = Field(
        None, ge=0, description="Precio que se aprueba; se recotiza y si cuesta más responde 409"
    )
    max_reserve_usd: float | None = Field(None, ge=0, description=RESERVE_FIELD)


PRICE_REFRESH_SECONDS = 3600
# Solo error de redondeo de coma flotante: nunca amplía lo que el usuario aprobó (revisión 28).
COST_TOLERANCE_USD = 1e-9


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
        # El worker conoce además el proveedor interno de las herramientas locales (no se lista como proveedor).
        app.state.local_tools = LocalTools(settings, transport, plain=app.state.hf.plain)
        app.state.local_tools.sweep()
        app.state.eleven = ElevenLabsClient(settings, transport)
        app.state.voice_slots = asyncio.Semaphore(2)
        app.state.audio_jobs = ElevenLabsJobs(
            settings, app.state.eleven, transport, slots=app.state.voice_slots
        )
        app.state.audio_jobs.sweep()
        app.state.worker = Worker(
            app.state.sessions,
            {
                **app.state.providers,
                TOOL_PROVIDER: app.state.local_tools,
                AUDIO_PROVIDER: app.state.audio_jobs,
            },
            settings,
        )
        app.state.prices = PriceBook(Path(settings.storage_dir) / "prices")

        async def element_resolver(ids: list[str]) -> dict[str, dict]:
            # Desde la base en cada plan, recotización o aprobación: URLs vigentes, nunca un snapshot viejo.
            async with app.state.sessions() as s:
                return await resolve_elements(s, ids, settings.storage_dir, app.state.hf.upload)

        app.state.router = Router(app.state.providers, app.state.prices, get_catalog, element_resolver)
        app.state.worker.router = app.state.router
        app.state.tasks = set()
        app.state.voice_quotes = {}
        # Un cambio de voz corre dentro de este proceso: si se reinició a medias, no va a terminar.
        async with app.state.sessions() as s:
            await s.execute(
                update(Job)
                .where(Job.model.in_((VOICE_MODEL, *AUDIO_MODELS)), Job.status.in_(ACTIVE))
                .values(status="failed", error_kind="interrupted", error="Interrupted by a server restart",
                        finished_at=utcnow(), version=Job.version + 1)
            )  # fmt: skip
            await s.commit()
        if not settings.hf_configured:
            log.warning("Falta HF_API_KEY (o HF_API_KEY_ID + HF_API_KEY_SECRET): los envíos fallarán")
        app.state.space_runner = SpaceRunner(app.state.sessions, space_hooks())
        if settings.worker_enabled:
            app.state.worker.start()
            await app.state.space_runner.resume_all()
            refresher = asyncio.create_task(refresh_prices(app), name="hf-studio-prices")
            app.state.tasks.add(refresher)
            refresher.add_done_callback(app.state.tasks.discard)
        yield
        await app.state.space_runner.stop()
        await app.state.worker.stop()
        for provider in app.state.providers.values():
            await provider.aclose()
        await app.state.local_tools.aclose()
        await app.state.audio_jobs.aclose()
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

    @app.exception_handler(ElementError)
    async def _element_error(_: Request, exc: ElementError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

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
        current = job.plan[job.plan_index] if job.plan and job.plan_index < len(job.plan) else {}
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
            # Los trabajos de audio corren en ElevenLabs aunque la columna conserve su valor por defecto.
            "provider": "elevenlabs" if job.model in LOCAL_MODELS else job.provider,
            # Canal exacto en el proveedor (id de su modelo) y precio cotizado de la opción en curso: tras
            # completarse, lo que costó la generación (aproximado si `cost_kind` es approx).
            "provider_model": current.get("model"),
            "official": current.get("official", True),
            "cost_usd": current.get("usd"),
            "cost_kind": current.get("kind"),
            "max_usd": job.max_usd,
            "max_reserve_usd": job.max_reserve_usd,
            "reserve_usd": current.get("reserve_usd"),
            "plan": [
                {
                    "provider": o["provider"],
                    "model": o.get("model"),
                    "official": o.get("official", True),
                    "usd": o.get("usd"),
                    "kind": o.get("kind"),
                    "reserve_usd": o.get("reserve_usd"),
                }
                for o in job.plan or []
            ],
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

    def local_option(model: str | None, estimate: dict) -> dict:
        """Opción única de un trabajo de ElevenLabs: guarda el modelo y lo que se cotizó para el historial."""
        return {"provider": "elevenlabs", "model": model, "official": True, "usd": estimate.get("usd"),
                "kind": estimate.get("kind")}  # fmt: skip

    def model_out(m: dict, full: bool = False) -> dict:
        keys = ("id", "title", "output", "workflow", "family", "capabilities", "docs_url")
        base = {**{k: m[k] for k in keys}, "inputs": input_kinds(m["input_schema"])}
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

    async def complete_hints(
        request: Request, session: AsyncSession, owner: ApiClient, arguments: dict, hints: dict
    ) -> dict:
        """Mide la duración de los videos de entrada (si no viene en `hints`): varios proveedores cobran
        por ella. Solo medios propios, descargados y medidos en local sin red (SSRF, revisión 28)."""
        hints = dict(hints or {})
        urls = video_urls(arguments)
        if "input_video_seconds" in hints or not urls:
            return hints
        seconds = 0.0
        for url in urls:
            if not await trusted_media(session, owner, url):
                return hints
            measured = await local_duration(url, request.app.state.hf.plain, settings.max_upload_bytes)
            if not measured:
                return hints
            seconds += measured
        hints["input_video_seconds"] = round(seconds, 2)
        return hints

    async def make_plan(
        request: Request, session: AsyncSession, owner: ApiClient, model: dict, arguments: dict, hints: dict,
        provider: str | None = None,
    ) -> Plan:  # fmt: skip
        hints = await complete_hints(request, session, owner, arguments, hints)
        # Una petición nueva solo cita elementos vivos; sus imágenes las pone el router desde la base, nunca
        # el cliente (las pistas no llevan elementos).
        hints.pop("elements", None)
        await check_element_ids(session, arguments.get("elements"))
        if is_audio_node(model["id"]) and not app.state.eleven.configured:
            # ServiceError (no VoiceError): también la entiende el motor de corridas, que marca el paso fallido.
            raise ServiceError(503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env")
        if is_tool(model["id"]):
            # ffmpeg abre estos archivos en local: solo subidas o salidas propias (como keep_source_audio).
            for url in tool_media(arguments):
                if not await trusted_media(session, owner, url):
                    raise ServiceError(
                        422, "untrusted_source", "Tools only take files from /v1/uploads or your generations"
                    )
        if provider and provider not in provider_registry.PROVIDERS:
            raise ServiceError(422, "unknown_provider", f"Unknown provider {provider!r}")
        return await request.app.state.router.plan(model, arguments, hints, only=provider)

    def check_reserve(
        reserve: float | None, approved: float | None, details=None, what: str = "This provider"
    ) -> None:
        if reserve and (approved is None or reserve > approved + COST_TOLERANCE_USD):
            raise ServiceError(409, "reserve_not_approved",
                               f"{what} first holds {reserve:.4f} USD (refunded after); approve that hold",
                               details)  # fmt: skip

    def authorize(
        plan: Plan, max_usd: float | None, max_reserve_usd: float | None, accept_unknown: bool
    ) -> tuple[list[dict], float | None, float | None]:
        """Comprueba lo aprobado contra la opción más barata de ahora y devuelve (plan para guardar, precio
        aprobado, retención aprobada). La retención se aprueba aparte del precio: también con un precio
        desconocido aceptado (revisión 30). Una petición sin ningún dato de aprobación (API directa, sin
        cotización previa) aprueba lo que cueste ahora."""
        best, details = plan.best, plan.public()
        unknown = best.usd is None or bool(best.missing)
        if max_usd is not None:
            if unknown and not accept_unknown:
                raise ServiceError(409, "cost_unknown",
                                   "The price is no longer known; quote again before generating", details)  # fmt: skip
            if not unknown and best.usd > max_usd + COST_TOLERANCE_USD:
                raise ServiceError(
                    409, "cost_changed",
                    f"The cheapest option now costs {best.usd:.4f} USD (approved {max_usd:.4f}); quote again", details,
                )  # fmt: skip
        quoted = max_usd is not None or max_reserve_usd is not None or accept_unknown
        if quoted:
            check_reserve(best.reserve_usd, max_reserve_usd, details)
        stored = plan.stored()
        if accept_unknown:
            # Solo esta opción, aunque su precio ya se conozca de nuevo; un respaldo pedirá aprobación.
            stored[0]["unknown_accepted"] = True
        # Desconocido aceptado sin tope: queda sin tope (no se fija el precio de ahora como techo).
        approved_usd = max_usd if max_usd is not None else (None if accept_unknown else best.usd)
        return stored, approved_usd, (max_reserve_usd if quoted else best.reserve_usd)

    def estimate_body(plan: Plan) -> dict:
        """Costo de la opción elegida con los campos de siempre, más todas las opciones y el ahorro."""
        best = plan.best
        if best is None:
            reasons = "; ".join(f"{e['title']}: {e['reason']}" for e in plan.excluded) or "no provider"
            base = {"kind": "unavailable", "credits": None, "usd": None, "discount_pct": None,
                    "basis": f"No provider can run this request ({reasons})", "missing": [], "description": None}  # fmt: skip
        else:
            keys = (
                "kind",
                "credits",
                "usd",
                "discount_pct",
                "basis",
                "missing",
                "description",
                "reserve_usd",
            )
            base = {k: getattr(best, k) for k in keys}
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

        async def price(model: dict, arguments: dict) -> dict:
            return estimate_body(await request.app.state.router.plan(model, arguments, {}))

        return await recommend(price, catalog, task, limit, output)

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
        if not matches_type(bytes(data[:16]), content_type):
            # Solo el contenido que dice ser: un manifiesto DASH/HLS como «video/mp4» haría que ffmpeg
            # abriera las URLs de dentro (SSRF, revisión 28).
            raise ServiceError(415, "content_mismatch", f"The file content is not a valid {content_type}")
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
        # Un reintento con la misma Idempotency-Key devuelve el trabajo ya creado antes de volver a cotizar o
        # resolver medios: un elemento borrado o un precio nuevo no lo convierten en otra petición (revisión 43).
        digest = request_digest(model["id"], body.input, body.keep_source_audio, body.provider)
        if existing := await job_for_key(session, owner, idempotency_key, digest):
            return JSONResponse(job_out(existing, deduplicated=True), status_code=200)
        plan = await make_plan(request, session, owner, model, body.input, body.hints, body.provider)
        best = plan.best
        if best is None:
            raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
        stored, approved_usd, approved_reserve = authorize(
            plan, body.max_usd, body.max_reserve_usd, body.accept_unknown_cost
        )
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
            plan=stored,
            max_usd=approved_usd,
            max_reserve_usd=approved_reserve,
            provider=body.provider,
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
        plans = []
        for item in body.items:
            plan = await make_plan(
                request, session, owner, catalog.get(item.model), item.input, {**body.hints, **item.hints}
            )
            if plan.best is None:
                raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
            plans.append(plan)
        # Antes de crear el primer trabajo: el lote entero dentro de lo aprobado (revisiones 28 a 33).
        if body.accept_unknown_cost and body.max_total_usd is not None:
            # Un tope total no se puede hacer cumplir por trabajo si algún precio es desconocido: o hay tope o se
            # acepta el total desconocido sin tope, nunca las dos cosas.
            raise ServiceError(422, "conflicting_approval",
                               "Pass either max_total_usd or accept_unknown_cost=true (no cap), not both")  # fmt: skip
        unknown = [p.best.usd is None or bool(p.best.missing) for p in plans]
        if body.max_total_usd is not None:
            if any(unknown) and not body.accept_unknown_cost:
                raise ServiceError(
                    409, "cost_unknown", "Some item no longer has a price; quote the batch again"
                )
            cost = sum(
                p.best.usd * i.count for p, i, u in zip(plans, body.items, unknown, strict=True) if not u
            )
            if cost > body.max_total_usd + COST_TOLERANCE_USD:
                raise ServiceError(409, "cost_changed",
                                   f"The batch now costs {cost:.4f} USD (approved {body.max_total_usd:.4f})", cost)  # fmt: skip
        quoted = (
            body.max_total_usd is not None
            or body.max_total_reserve_usd is not None
            or body.accept_unknown_cost
        )
        held = sum((p.best.reserve_usd or 0) * i.count for p, i in zip(plans, body.items, strict=True))
        if quoted:
            check_reserve(held, body.max_total_reserve_usd, held, "The batch")
        jobs, created_any = [], False
        n = 0
        for item, plan in zip(body.items, plans, strict=True):
            for _ in range(item.count):
                key = f"{idempotency_key}:{n}" if idempotency_key else None
                stored = plan.stored()
                if body.accept_unknown_cost:
                    stored[0]["unknown_accepted"] = True  # el total se aceptó sin tope
                job, created = await create_generation(
                    session, settings, catalog, owner, item.model, item.input, key, allow_duplicate=True,
                    plan=stored, max_reserve_usd=plan.best.reserve_usd if quoted else UNSET,
                    max_usd=None if body.accept_unknown_cost else UNSET,
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
    async def approve(
        job_id: str, body: ApproveIn, request: Request, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Aprueba el precio del proveedor que espera un trabajo (`awaiting_approval`). Se vuelve a cotizar
        en el momento: si ahora cuesta más que `max_usd` o no tiene precio, responde 409 con el actual."""
        job = await get_owned_job(session, owner, job_id)
        if job.status != "awaiting_approval" or not job.plan:
            raise ServiceError(
                409, "not_awaiting_approval", f"Generation is {job.status}; nothing to approve"
            )
        if is_run_key(job.idempotency_key):
            # Un paso de una corrida de Spaces se aprueba desde la corrida: ahí se aplica su tope total.
            raise ServiceError(
                409, "approve_in_run", "This step belongs to a space run; approve it from the run"
            )
        index, version = job.plan_index, job.version
        fresh = await requote(request.app.state.router, catalog.get(job.model), job.input, job.plan[index])
        if fresh is None:
            raise ServiceError(
                409, "provider_unavailable", "That provider can no longer run this request; cancel it"
            )
        problem = None
        if body.max_usd is None and not body.accept_unknown_cost:
            raise ServiceError(
                422, "missing_max_usd", "Pass max_usd (or accept_unknown_cost=true to approve without a cap)"
            )
        # El permiso de esta aprobación (también False) solo se guarda si la aprobación sale bien: un 409 no
        # añade ni hereda autorizaciones (revisión 32).
        fresh.pop("unknown_accepted", None)
        if fresh["usd"] is None and not body.accept_unknown_cost:
            problem = (
                "cost_unknown",
                "The price is unknown now; cancel it, try later or accept an unknown cost",
            )
        elif (
            fresh["usd"] is not None
            and body.max_usd is not None
            and fresh["usd"] > body.max_usd + COST_TOLERANCE_USD
        ):
            problem = ("cost_changed", f"It now costs {fresh['usd']:.4f} USD, more than {body.max_usd:.4f}")
        elif fresh.get("reserve_usd") is not None and (
            body.max_reserve_usd is None or fresh["reserve_usd"] > body.max_reserve_usd + COST_TOLERANCE_USD
        ):
            problem = ("reserve_not_approved",
                       f"It first holds {fresh['reserve_usd']:.4f} USD (refunded after); approve max_reserve_usd")  # fmt: skip
        if problem:
            # Se guarda la cotización nueva (sigue esperando aprobación): la UI y el agente ven el precio actual
            # y pueden aprobarlo con una acción explícita, sin repetir el importe viejo (revisión 29).
            plan = list(job.plan)
            # Importes nuevos, pero el permiso que ya tenía la opción (no el de esta petición rechazada).
            plan[index] = {**fresh, "unknown_accepted": bool(job.plan[index].get("unknown_accepted"))}
            await session.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "awaiting_approval", Job.version == version,
                       Job.plan_index == index)
                .values(plan=plan, error=problem[1], version=Job.version + 1)
            )  # fmt: skip
            await session.commit()
            raise ServiceError(
                409, problem[0], problem[1], {"usd": fresh["usd"], "reserve_usd": fresh.get("reserve_usd")}
            )
        plan = list(job.plan)
        # `approved`: esta opción (proveedor y canal) la eligió el usuario; el primer envío ya no replanifica
        # hacia otra más barata, solo la recotiza (revisión 41).
        plan[index] = {**fresh, "unknown_accepted": body.accept_unknown_cost, "approved": True}
        # CAS sobre la versión leída: dos aprobaciones, o aprobar y cancelar a la vez, no pueden ganar ambas.
        done = await session.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "awaiting_approval", Job.version == version,
                   Job.plan_index == index)
            .values(status="pending", plan=plan, max_usd=body.max_usd, error=None,
                    max_reserve_usd=max(job.max_reserve_usd or 0, fresh.get("reserve_usd") or 0) or job.max_reserve_usd,
                    error_kind=None, next_check_at=None, version=Job.version + 1)
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
                .values(
                    status="canceled",
                    finished_at=utcnow(),
                    next_check_at=None,
                    version=Job.version + 1,
                    # El aviso «retrying» de una preparación fallida no vale para un trabajo cancelado.
                    error=case((Job.error_kind == "preparing", None), else_=Job.error),
                    error_kind=case((Job.error_kind == "preparing", None), else_=Job.error_kind),
                )
            )
            await session.commit()
            await session.refresh(job)
            if done.rowcount != 1:
                raise ServiceError(
                    409, "not_cancelable", f"Cannot cancel a generation in status {job.status}"
                )
            return job_out(job)
        if job.hf_request_id and (
            job.status == "queued" or (job.status == "in_progress" and job.provider in BACKGROUND_PROVIDERS)
        ):
            # Una herramienta local sí se puede detener en curso: la tarea es nuestra (revisión 58).
            await request.app.state.worker.provider(job).cancel_job(job.hf_request_id, job.cancel_url)
            job.status, job.finished_at, job.next_check_at = "canceled", utcnow(), None
        else:
            raise ServiceError(409, "not_cancelable", f"Cannot cancel a generation in status {job.status}")
        local = job.provider in BACKGROUND_PROVIDERS
        for _ in range(3):
            if await request.app.state.worker.commit(session, job.id):
                return job_out(job)
            # Con una herramienta local la tarea ya se detuvo: un sondeo que se cruzó (guardó `in_progress`
            # o ya `canceled`) no invalida la cancelación. Otro estado final sí gana (revisiones 59 y 60).
            fresh = await session.get(Job, job_id, populate_existing=True)
            if not local or fresh is None:
                break
            if fresh.status == "canceled":
                return job_out(fresh)
            if fresh.status != "in_progress":
                break
            fresh.status, fresh.finished_at, fresh.next_check_at = "canceled", utcnow(), None
            job = fresh
        raise ServiceError(409, "not_cancelable", "The generation changed while canceling; check it again")

    @app.get("/v1/generations/{job_id}/files/{name}", tags=["generaciones"])
    async def get_file(job_id: str, name: str, session: Session, owner: Owner) -> FileResponse:
        job = await get_owned_job(session, owner, job_id)
        entry = next((f for f in job.files or [] if f["name"] == name), None)
        path = Path(settings.storage_dir) / "outputs" / job.id / name
        if not entry or not path.is_file():
            raise ServiceError(404, "not_found", "Archivo no encontrado")
        return FileResponse(path, media_type=entry.get("content_type"), filename=name)

    REUSE_FRESH = timedelta(days=5)  # las URLs de Higgsfield duran ~7 días; se vuelve a subir pasados 5
    # Candados por (dueño, salida); se sueltan solos cuando ninguna petición los usa (revisión 48).
    reuse_locks: weakref.WeakValueDictionary[tuple[str, str], asyncio.Lock] = weakref.WeakValueDictionary()

    @app.post("/v1/generations/{job_id}/outputs/{index}/use", tags=["generaciones"])
    async def use_output(job_id: str, index: int, session: Session, owner: Owner) -> dict:
        """URL pública y vigente de una salida propia, para usarla como entrada de otra generación (fotograma
        inicial, referencia, video a editar…). Sube la copia local a Higgsfield (gratis) y la registra como
        subida propia; si ya se subió hace menos de 5 días, devuelve esa misma URL."""
        return await fresh_output(session, owner, job_id, index)

    wav_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = weakref.WeakValueDictionary()

    async def mp3_as_wav(path: Path) -> Path:
        """Copia WAV (junto al MP3, una vez) de una salida de audio propia. Un candado por archivo y un temporal
        único: dos usos a la vez no se pisan, y un fallo no deja medio archivo (revisión 62)."""
        wav = path.with_suffix(".wav")
        lock = wav_locks.get(wav)
        if lock is None:
            lock = wav_locks[wav] = asyncio.Lock()
        async with lock:
            if wav.is_file():
                return wav
            fd, name = tempfile.mkstemp(prefix=f"{wav.stem}.", suffix=".tmp.wav", dir=wav.parent)
            os.close(fd)
            tmp = Path(name)
            try:
                code, err = await run_ffmpeg(
                    "ffmpeg", "-y", "-v", "error", *guarded(str(path)), "-c:a", "pcm_s16le", str(tmp)
                )
                if code != 0 or not tmp.stat().st_size:
                    raise ServiceError(
                        422, "audio_convert_failed", f"Could not prepare that audio as an input: {err[:200]}"
                    )
                tmp.replace(wav)
            finally:
                tmp.unlink(missing_ok=True)
        return wav

    async def fresh_output(session: AsyncSession, owner: ApiClient, job_id: str, index: int) -> dict:
        """Núcleo de `use_output`; también lo usan las corridas de Spaces para encadenar pasos."""
        job = await get_owned_job(session, owner, job_id)
        entry = next((f for f in job.files or [] if f["index"] == index), None)
        if job.status != "completed" or entry is None:
            raise ServiceError(404, "not_found", "That output is not available (finished generations only)")
        path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"]
        if not path.is_file():
            raise ServiceError(404, "not_found", "The local copy of that output is missing")
        content_type = (entry.get("content_type") or "").split(";")[0].strip().lower()
        if content_type == "audio/mpeg":
            # Higgsfield no acepta MP3 (el audio de ElevenLabs): se sube una copia WAV hecha con ffmpeg, así
            # la voz o la música generadas se pueden encadenar como entrada (Spaces, fase 2c).
            path = await mp3_as_wav(path)
            content_type = "audio/wav"
        if content_type not in UPLOAD_CONTENT_TYPES:
            raise ServiceError(
                415, "unsupported_media", f"{content_type or 'This output'} cannot be used as an input"
            )
        # La asociación salida → subida vive en `Upload.source`, que solo escribe el servidor (revisión 47). Una
        # fila por dueño y salida (índice único); el candado evita dos subidas simultáneas en este proceso.
        source = f"generation:{job.id}:{index}"
        # Valores propios, no del ORM: un rollback por conflicto expira los objetos cargados (revisión 48).
        owner_id, generation_id, kind = owner.id, job.id, entry["kind"]
        lock = reuse_locks.get((owner_id, source))
        if lock is None:
            lock = reuse_locks[(owner_id, source)] = asyncio.Lock()
        async with lock:
            row = await session.scalar(  # lectura fresca dentro del candado
                select(Upload)
                .where(Upload.owner_id == owner_id, Upload.source == source)
                .execution_options(populate_existing=True)
            )
            if row is None or row.created_at < utcnow() - REUSE_FRESH:
                data = path.read_bytes()
                if len(data) > settings.max_upload_bytes:
                    raise ServiceError(
                        413, "too_large", f"Maximum {settings.max_upload_bytes // (1024 * 1024)} MB"
                    )
                if not matches_type(data[:16], content_type):
                    raise ServiceError(415, "content_mismatch", f"The output is not a valid {content_type}")
                url = await app.state.hf.upload(data, content_type)
                if row is not None:
                    # La copia anterior pasa a historial (sin `source`): su URL sigue siendo un medio propio
                    # mientras funcione (revisión 48). La vigente es una fila nueva.
                    row.source = None
                    await session.flush()
                row = Upload(owner_id=owner_id, filename=entry["name"], content_type=content_type,
                             size=len(data), url=url, source=source)  # fmt: skip
                session.add(row)
                try:
                    await session.commit()
                except IntegrityError:
                    # Otro proceso registró la misma salida a la vez: vale la suya (la subida extra no cobra).
                    await session.rollback()
                    row = await session.scalar(
                        select(Upload).where(Upload.owner_id == owner_id, Upload.source == source)
                    )
            url = row.url
        return {"url": url, "kind": kind, "content_type": content_type,
                "generation_id": generation_id, "index": index}  # fmt: skip

    # --- Elementos (Kling 3.0 en APIMart y KIE) ------------------------------------------------

    async def element_image(
        session: AsyncSession, owner: ApiClient, source: UploadFile | str
    ) -> tuple[bytes, str]:
        """Bytes y tipo real de una imagen de elemento: un archivo subido o una URL propia (subida o salida de
        una generación; nunca una URL arbitraria, SSRF)."""
        if isinstance(source, str):
            if not await trusted_media(session, owner, source):
                raise ServiceError(
                    422, "untrusted_source", "Element images must come from /v1/uploads or your generations"
                )
            with tempfile.TemporaryDirectory(prefix="hfs-element-") as tmp:
                path = Path(tmp) / "image"
                if not await download_media(source, app.state.hf.plain, settings.max_upload_bytes, path):
                    raise ServiceError(422, "invalid_source", f"Could not download {source}")
                data = path.read_bytes()
        else:
            data = await source.read()
        if not data:
            raise ServiceError(422, "empty_file", "An element image is empty")
        return data, check_image(data, "")

    @app.post("/v1/elements", status_code=201, tags=["elementos"])
    async def create_element(
        request: Request,
        session: Session,
        owner: Owner,
        name: Annotated[str, Form()],
        description: Annotated[str, Form(min_length=1, max_length=500)],
        files: Annotated[list[UploadFile], File()] = [],  # noqa: B006
        image_urls: Annotated[list[str], Form()] = [],  # noqa: B006
    ) -> dict:
        """Crea un elemento con 2 a 4 imágenes JPG o PNG (archivos o URLs propias). Se cita con @nombre."""
        name = check_name(name)
        description = description.strip()
        if not description:
            raise ServiceError(422, "invalid_description", "The description cannot be empty")
        await purge_deleted_elements(session, settings.storage_dir)
        sources: list = [*files, *image_urls]
        if not MIN_IMAGES <= len(sources) <= MAX_IMAGES:
            raise ServiceError(422, "image_count", f"An element needs {MIN_IMAGES} to {MAX_IMAGES} images")
        taken = await session.scalar(select(Element).where(Element.name == name))
        if taken:
            message = f"There is already an element called @{name}"
            if taken.deleted_at:
                message = f"@{name} was deleted recently or a running generation still uses it; try again in a few minutes"
            raise ServiceError(409, "name_taken", message)
        images = [await element_image(session, owner, src) for src in sources]
        element_id = new_element_id()
        target = element_folder(settings.storage_dir, element_id)
        target.mkdir(parents=True, exist_ok=True)
        stored = []
        try:
            for i, (data, kind) in enumerate(images):
                file = f"{i}{'.png' if kind == 'image/png' else '.jpg'}"
                (target / file).write_bytes(data)
                stored.append(
                    {"file": file, "content_type": kind, "url": await request.app.state.hf.upload(data, kind)}
                )
            element = Element(id=element_id, name=name, description=description, images=stored,
                              created_by=owner.id)  # fmt: skip
            session.add(element)
            await session.commit()
        except IntegrityError:
            # Otra creación simultánea ganó el mismo nombre (revisión 43): 409, no 500.
            await session.rollback()
            shutil.rmtree(target, ignore_errors=True)
            if await session.scalar(select(Element.id).where(Element.name == name)):
                raise ServiceError(409, "name_taken", f"There is already an element called @{name}") from None
            raise
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return element_out(element)

    @app.get("/v1/elements", tags=["elementos"])
    async def list_elements(session: Session, owner: Owner) -> dict:
        rows = await session.scalars(
            select(Element).where(Element.deleted_at.is_(None)).order_by(Element.created_at.desc())
        )
        return {"elements": [element_out(e) for e in rows]}

    async def get_element_or_404(session: AsyncSession, element_id: str) -> Element:
        element = await session.get(Element, element_id)
        if element is None or element.deleted_at is not None:
            raise ServiceError(404, "element_not_found", f"Unknown element: {element_id}")
        return element

    @app.get("/v1/elements/{element_id}", tags=["elementos"])
    async def get_element(element_id: str, session: Session, owner: Owner) -> dict:
        return element_out(await get_element_or_404(session, element_id))

    @app.get("/v1/elements/{element_id}/images/{index}", tags=["elementos"])
    async def element_image_file(element_id: str, index: int, session: Session, owner: Owner) -> FileResponse:
        element = await get_element_or_404(session, element_id)
        if not 0 <= index < len(element.images):
            raise ServiceError(404, "not_found", "Image not found")
        image = element.images[index]
        return FileResponse(element_folder(settings.storage_dir, element.id) / image["file"],
                            media_type=image["content_type"])  # fmt: skip

    @app.delete("/v1/elements/{element_id}", status_code=204, tags=["elementos"])
    async def delete_element(element_id: str, session: Session, owner: Owner) -> None:
        """Deja de ofrecerlo al momento; sus imágenes se borran cuando ya no lo use ningún trabajo activo."""
        element = await get_element_or_404(session, element_id)
        element.deleted_at = utcnow()
        await session.commit()
        await purge_deleted_elements(session, settings.storage_dir)

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

    # --- Spaces (lienzo de nodos) -----------------------------------------------------------------

    def valid_graph(raw: Any, catalog: Catalog) -> dict:
        try:
            graph = check_graph(raw)
            models = {n["data"]["model"] for n in graph["nodes"] if n["type"] == "generator"}
            schemas = {m: catalog.get(m)["input_schema"] for m in models if catalog.get(m)}
            return check_values(graph, schemas)
        except GraphError as exc:
            raise ServiceError(422, "invalid_graph", str(exc)) from None

    async def valid_cover(session: AsyncSession, owner: ApiClient, cover: str | None) -> str | None:
        """La portada es una imagen terminada de una generación visible para el cliente (o null para quitarla)."""
        if cover is None:
            return None
        _, _, _, job_id, _, name = cover.split("/", 5)
        job = await session.get(Job, job_id)
        entry = next((f for f in (job.files or []) if f.get("name") == name), None) if job else None
        if (
            job is None
            or (job.owner_id != owner.id and not owner.sees_all)  # misma regla que leer sus archivos
            or job.status != "completed"
            or entry is None
            or entry.get("kind") != "image"
            # La misma copia local que sirve GET /files: sin ella la portada saldría rota (revisión 52).
            or not (Path(settings.storage_dir) / "outputs" / job.id / name).is_file()
        ):
            raise ServiceError(
                422, "invalid_cover", "The cover must be an image from one of your finished generations"
            )
        return cover

    async def get_owned_space(session: AsyncSession, owner: ApiClient, space_id: str) -> Space:
        space = await session.get(Space, space_id)
        if space is None or space.owner_id != owner.id:
            raise ServiceError(404, "not_found", "Space not found")
        return space

    @app.get("/v1/spaces", tags=["spaces"])
    async def list_spaces(session: Session, owner: Owner) -> dict:
        rows = await session.scalars(
            select(Space).where(Space.owner_id == owner.id).order_by(Space.updated_at.desc())
        )
        return {"spaces": [s.summary() for s in rows]}

    @app.post("/v1/spaces", tags=["spaces"], status_code=201)
    async def create_space(body: SpaceIn, session: Session, owner: Owner, catalog: CatalogDep) -> dict:
        graph = valid_graph(body.graph, catalog) if body.graph is not None else empty_graph()
        space = Space(owner_id=owner.id, title=body.title, graph=graph)
        session.add(space)
        await session.commit()
        return space.as_dict()

    @app.get("/v1/spaces/{space_id}", tags=["spaces"])
    async def get_space(space_id: str, session: Session, owner: Owner) -> dict:
        return (await get_owned_space(session, owner, space_id)).as_dict()

    @app.put("/v1/spaces/{space_id}", tags=["spaces"])
    async def update_space(
        space_id: str, body: SpaceUpdate, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Guarda título, grafo o portada. Exige la versión leída: si otra pestaña guardó antes, 409 con la
        versión vigente, para que el cliente recargue en vez de pisar cambios."""
        await get_owned_space(session, owner, space_id)
        values: dict[str, Any] = {"version": Space.version + 1, "updated_at": utcnow()}
        if body.title is not None:
            values["title"] = body.title
        if body.graph is not None:
            values["graph"] = valid_graph(body.graph, catalog)
        if "cover" in body.model_fields_set:
            values["cover"] = await valid_cover(session, owner, body.cover)
        result = await session.execute(
            update(Space)
            .where(Space.id == space_id, Space.owner_id == owner.id, Space.version == body.version)
            .values(**values)
        )
        if result.rowcount == 0:
            await session.rollback()
            current = await session.scalar(select(Space.version).where(Space.id == space_id))
            raise ServiceError(
                409, "version_conflict", "This space changed in another tab; reload it", {"version": current}
            )
        # Lo que esta escritura dejó, leído dentro de su transacción: otro guardado posterior no se cuela en
        # la respuesta (el cliente adoptaría una versión con cambios que no vio, revisión 51).
        mine = await session.scalar(
            select(Space).where(Space.id == space_id).execution_options(populate_existing=True)
        )
        out = mine.as_dict()
        await session.commit()
        return out

    @app.delete("/v1/spaces/{space_id}", tags=["spaces"], status_code=204)
    async def delete_space(space_id: str, session: Session, owner: Owner) -> None:
        """Borra el lienzo; sus generaciones siguen en el historial."""
        space = await get_owned_space(session, owner, space_id)
        await session.execute(delete(SpaceRun).where(SpaceRun.space_id == space.id))
        await session.delete(space)
        await session.commit()

    # --- Corridas de Spaces (fase 2) -------------------------------------------------------------

    def space_hooks() -> Hooks:
        """El motor de corridas usa las mismas piezas que generar a mano: cotizar con el router, aprobar con
        `authorize` y crear con `create_generation` (idempotente por corrida y nodo)."""
        fake_request = SimpleNamespace(app=app)  # make_plan/complete_hints solo leen app.state

        async def plan(session: AsyncSession, owner: ApiClient, model_id: str, arguments: dict) -> Plan:
            model = check_input(get_catalog(), model_id, arguments)
            return await make_plan(fake_request, session, owner, model, arguments, {})

        async def create(session, owner, model_id, arguments, key, plan, usd, reserve, accept_unknown) -> Job:
            stored, approved_usd, approved_reserve = authorize(plan, usd, reserve, accept_unknown)
            job, _ = await create_generation(
                session, settings, get_catalog(), owner, model_id, arguments, key, allow_duplicate=True,
                plan=stored, max_usd=approved_usd, max_reserve_usd=approved_reserve, commit=False,
            )  # fmt: skip
            return job

        async def trusted(session: AsyncSession, owner: ApiClient, url: str) -> bool:
            return await trusted_media(session, owner, url)

        async def output_url(session: AsyncSession, owner: ApiClient, job_id: str) -> str:
            try:
                return (await fresh_output(session, owner, job_id, 0))["url"]
            except ServiceError as exc:
                raise NodeInputError(f"A connected step has no usable output ({exc.message})") from None

        def schema(model_id: str) -> dict | None:
            model = get_catalog().get(model_id)
            return model["input_schema"] if model else None

        def output_of(model_id: str) -> str | None:
            model = get_catalog().get(model_id)
            return model["output"] if model else None

        return Hooks(plan, create, output_url, trusted, schema, output_of, app.state.worker.wake)

    async def estimate_run(session: AsyncSession, owner: ApiClient, graph: dict, order: list[str]) -> dict:
        """Cotiza cada paso con lo que hay hoy en el lienzo. Un paso que depende de otro de la corrida sin salida
        todavía se cotiza al llegar (`later`); si entonces no cabe en el tope, la corrida se pausa."""
        hooks = app.state.space_runner.hooks
        nodes = {n["id"]: n for n in graph["nodes"]}
        items, total, reserve_total = [], 0.0, 0.0
        for node_id in order:
            model_id = nodes[node_id]["data"]["model"]
            item: dict[str, Any] = {"node_id": node_id, "model": model_id}
            in_run = [e["source"] for e in graph["edges"] if e["target"] == node_id and e["source"] in order]
            try:
                arguments = await resolve_input(
                    graph, node_id, hooks.schema(model_id) or {}, hooks.output_of,
                    lambda src: selected_run(nodes[src]["data"]),
                    lambda job_id: hooks.output_url(session, owner, job_id),
                )  # fmt: skip
                plan = await hooks.plan(session, owner, model_id, arguments)
            except (NodeInputError, ServiceError, ProviderError) as exc:
                message = str(getattr(exc, "message", None) or exc)
                items.append({**item, "status": "later" if in_run else "error", "error": message})
                continue
            best = plan.best
            if best is None:
                items.append({**item, "status": "error", "error": estimate_body(plan)["basis"]})
                continue
            unknown = best.usd is None or bool(best.missing)
            item.update(status="unknown" if unknown else "ok", usd=best.usd, reserve_usd=best.reserve_usd,
                        provider=best.provider, kind=best.kind)  # fmt: skip
            if not unknown:
                total += spend_of(best.usd, best.reserve_usd)
            reserve_total += best.reserve_usd or 0.0
            items.append(item)
        return {"steps": items, "total_usd": round(total, 6), "reserve_usd": round(reserve_total, 6),
                "pending": sum(1 for i in items if i["status"] != "ok")}  # fmt: skip

    async def get_owned_run(session: AsyncSession, owner: ApiClient, space_id: str, run_id: str) -> SpaceRun:
        run = await session.get(SpaceRun, run_id)
        if run is None or run.owner_id != owner.id or run.space_id != space_id:
            raise ServiceError(404, "not_found", "Run not found")
        return run

    @app.post("/v1/spaces/{space_id}/runs", tags=["spaces"])
    async def create_run(space_id: str, body: RunIn, session: Session, owner: Owner) -> JSONResponse:
        """Corre un nodo y lo que depende de él, o todo el lienzo, en el servidor. Primero `dry_run` (precio de
        cada paso y total); luego la misma petición con `max_total_usd`, el tope que aprobó el usuario."""
        space = await get_owned_space(session, owner, space_id)
        if body.version != space.version:
            raise ServiceError(
                409, "space_changed", "Save the space before running it", {"version": space.version}
            )
        try:
            order = run_scope(space.graph, body.mode, body.node_id)
        except NodeInputError as exc:
            raise ServiceError(422, "invalid_run", str(exc)) from None
        if not order:
            raise ServiceError(422, "nothing_to_run", "There are no generation nodes to run")
        if body.dry_run:
            return JSONResponse(await estimate_run(session, owner, space.graph, order))
        if body.max_total_usd is None:
            raise ServiceError(
                422, "budget_required", "Approve a total budget (max_total_usd) to start the run"
            )
        active = await session.scalar(
            select(SpaceRun.id).where(
                SpaceRun.space_id == space.id, SpaceRun.status.in_(("running", "awaiting_approval"))
            )
        )
        if active:
            raise ServiceError(
                409, "run_active", "This space already has a run in progress", {"run_id": active}
            )
        run = SpaceRun(
            space_id=space.id, owner_id=owner.id, mode=body.mode, start_node=body.node_id, graph=space.graph,
            order=order, nodes={i: {"status": "pending"} for i in order}, max_total_usd=body.max_total_usd,
        )  # fmt: skip
        session.add(run)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise ServiceError(409, "run_active", "This space already has a run in progress") from None
        if settings.worker_enabled:
            app.state.space_runner.start(run.id)
        return JSONResponse(run.as_dict(), status_code=201)

    @app.get("/v1/spaces/{space_id}/runs", tags=["spaces"])
    async def list_runs(
        space_id: str, session: Session, owner: Owner, limit: int = Query(10, ge=1, le=50)
    ) -> dict:
        await get_owned_space(session, owner, space_id)
        rows = await session.scalars(
            select(SpaceRun)
            .where(SpaceRun.space_id == space_id)
            .order_by(SpaceRun.created_at.desc())
            .limit(limit)
        )
        return {"runs": [r.as_dict() for r in rows]}

    @app.get("/v1/spaces/{space_id}/runs/{run_id}", tags=["spaces"])
    async def get_run(space_id: str, run_id: str, session: Session, owner: Owner) -> dict:
        return (await get_owned_run(session, owner, space_id, run_id)).as_dict()

    async def approve_run_job(session: AsyncSession, run: SpaceRun, pause: dict, body: RunApprove) -> None:
        """Aprueba el proveedor de respaldo de un paso dentro de su corrida: se recotiza ahora y el nuevo total
        (lo comprometido sin el paso más su precio nuevo) debe caber en el tope que se aprueba. El trabajo y la
        corrida se guardan en el mismo commit que hace quien llama (revisión 55).

        Los permisos del trabajo quedan iguales a lo que cuenta la corrida (precio y retención de esta
        cotización): una retención vieja no puede volver a usarse sin pasar por el tope (revisión 56). Si la
        cotización nueva no cabe, se publica en la pausa y se rechaza, para que la barra ofrezca el total real."""
        job = await session.get(Job, pause["job_id"])
        if job is None or job.status != "awaiting_approval" or not job.plan:
            raise ServiceError(409, "run_changed", "That step is no longer waiting for approval")
        index, version = job.plan_index, job.version
        fresh = await requote(app.state.router, get_catalog().get(job.model), job.input, job.plan[index])
        if fresh is None:
            raise ServiceError(
                409, "provider_unavailable", "That provider can no longer run this step; stop the run"
            )
        fresh.pop("unknown_accepted", None)
        unknown = fresh["usd"] is None
        nodes = {k: dict(v) for k, v in run.nodes.items()}
        state = nodes[pause["node"]]
        new_spend = spend_of(fresh["usd"], fresh.get("reserve_usd"))
        needed = round(run.committed_usd - state.get("spend", 0.0) + new_spend, 6)
        problem = None
        if unknown and not body.accept_unknown:
            problem = ("unknown_not_accepted", "This step has no known price now; accept it explicitly")
        elif body.max_total_usd is None or body.max_total_usd + COST_TOLERANCE_USD < needed:
            problem = ("budget_too_low", f"It now needs {needed:.4f} USD in total; approve that amount")
        plan = list(job.plan)
        if problem:
            # La cotización nueva queda en el trabajo (sigue esperando) y en la pausa de la corrida.
            plan[index] = {**fresh, "unknown_accepted": bool(job.plan[index].get("unknown_accepted"))}
            await session.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "awaiting_approval", Job.version == version)
                .values(plan=plan, version=Job.version + 1)
            )
            run.pause = {**pause, "usd": fresh["usd"], "reserve_usd": fresh.get("reserve_usd"),
                         "needed_total_usd": needed, "unknown": unknown}  # fmt: skip
            try:
                await session.commit()
            except StaleDataError:
                await session.rollback()
                raise ServiceError(409, "run_changed", "The run changed meanwhile; check it again") from None
            raise ServiceError(422, problem[0], problem[1], {"needed_total_usd": needed, "unknown": unknown})
        plan[index] = {**fresh, "unknown_accepted": unknown, "approved": True}
        done = await session.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "awaiting_approval", Job.version == version, Job.plan_index == index)
            .values(status="pending", plan=plan, max_usd=fresh["usd"], max_reserve_usd=fresh.get("reserve_usd"),
                    error=None, error_kind=None, next_check_at=None, version=Job.version + 1)
        )  # fmt: skip
        if done.rowcount != 1:
            await session.rollback()
            raise ServiceError(409, "run_changed", "That step changed meanwhile; check it again")
        state.update(usd=fresh["usd"], reserve_usd=fresh.get("reserve_usd"), spend=new_spend, waiting=False)
        run.nodes = nodes
        run.committed_usd = needed

    @app.post("/v1/spaces/{space_id}/runs/{run_id}/approve", tags=["spaces"])
    async def approve_run(
        space_id: str, run_id: str, body: RunApprove, session: Session, owner: Owner
    ) -> dict:
        """Reanuda una corrida en pausa: un tope mayor que cubra el paso, o aceptar su precio desconocido."""
        run = await get_owned_run(session, owner, space_id, run_id)
        pause = run.pause or {}
        if run.status != "awaiting_approval" or not pause:
            raise ServiceError(409, "not_paused", "This run is not waiting for approval")
        # En una pausa de respaldo el total nuevo puede bajar (una retención que desaparece): lo valida
        # approve_run_job contra lo que de verdad queda comprometido.
        if (
            pause.get("reason") != "job_approval"
            and body.max_total_usd is not None
            and body.max_total_usd + COST_TOLERANCE_USD < run.committed_usd
        ):
            raise ServiceError(
                422, "budget_too_low", "The budget cannot be lower than what is already committed"
            )
        if pause.get("reason") == "over_budget":
            needed = pause.get("needed_total_usd") or 0.0
            if body.max_total_usd is None or body.max_total_usd + COST_TOLERANCE_USD < needed:
                raise ServiceError(
                    422,
                    "budget_too_low",
                    f"Approve at least {needed:.4f} USD in total",
                    {"needed_total_usd": needed},
                )
        if pause.get("reason") == "unknown_cost":
            if not body.accept_unknown:
                raise ServiceError(
                    422, "unknown_not_accepted", "This step has no known price; accept it explicitly"
                )
            nodes = {k: dict(v) for k, v in run.nodes.items()}
            nodes[pause["node"]]["accept_unknown"] = True
            run.nodes = nodes
        if pause.get("reason") == "job_approval":
            await approve_run_job(session, run, pause, body)
        if body.max_total_usd is not None:
            run.max_total_usd = body.max_total_usd
        run.status, run.pause = "running", None
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            raise ServiceError(409, "run_changed", "The run changed meanwhile; check it again") from None
        app.state.worker.wake()
        if settings.worker_enabled:
            app.state.space_runner.start(run.id)
        return run.as_dict()

    @app.post("/v1/spaces/{space_id}/runs/{run_id}/cancel", tags=["spaces"])
    async def cancel_run(space_id: str, run_id: str, session: Session, owner: Owner) -> dict:
        """Detiene la corrida: no se envían más pasos y se cancelan los que siguen en la cola local o esperan
        aprobación (gratis).
        Lo ya terminado se conserva; un paso que el proveedor ya está generando termina por su cuenta."""
        run = await get_owned_run(session, owner, space_id, run_id)
        if run.status not in ("running", "awaiting_approval"):
            raise ServiceError(409, "not_active", "This run already finished")
        nodes = {k: dict(v) for k, v in run.nodes.items()}
        for state in nodes.values():
            if state["status"] == "pending":
                state["status"] = "canceled"
            elif state["status"] == "running":
                # En la cola local o esperando aprobación todavía no cuesta nada: se cancela (revisión 55).
                await session.execute(
                    update(Job)
                    .where(Job.id == state["job_id"], Job.status.in_(("pending", "awaiting_approval")))
                    .values(
                        status="canceled", finished_at=utcnow(), next_check_at=None, version=Job.version + 1
                    )
                )
        run.nodes = nodes
        run.status, run.pause, run.finished_at = "canceled", None, utcnow()
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            raise ServiceError(409, "run_changed", "The run changed meanwhile; try again") from None
        return run.as_dict()

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
        stored, approved_usd, approved_reserve = authorize(
            plan, body.max_usd, body.max_reserve_usd, body.accept_unknown_cost
        )
        job, created = await create_generation(
            session, settings, catalog, owner, preset["model"], model_input, idempotency_key, plan=stored,
            max_usd=approved_usd, max_reserve_usd=approved_reserve,
        )  # fmt: skip
        if created:
            request.app.state.worker.wake()
        return JSONResponse(job_out(job, deduplicated=not created), status_code=202 if created else 200)

    # --- Cambio de voz (ElevenLabs) --------------------------------------------------------------

    async def local_source(request: Request, url: str) -> str:
        """Copia local controlada de un medio propio: ffmpeg nunca abre URLs (SSRF, revisión 29)."""
        path = await cached_source(
            url, Path(settings.storage_dir), request.app.state.hf.plain, settings.max_upload_bytes
        )
        if path is None:
            raise ServiceError(
                422, "invalid_source", "Could not download the source as an audio or video file"
            )
        return path

    async def voice_source(
        request: Request, session: AsyncSession, owner: ApiClient, body: VoiceChangeIn
    ) -> str:
        """Ruta local del video de origen (los remotos se descargan antes)."""
        if body.source_url:
            # Solo medios propios: ffmpeg no debe abrir URLs arbitrarias (SSRF).
            if not await trusted_media(session, owner, body.source_url):
                raise ServiceError(
                    422,
                    "untrusted_source",
                    "source_url must come from /v1/uploads (upload_media) or be one of your generations",
                )
            return await local_source(request, body.source_url)
        job = await get_owned_job(session, owner, body.source_generation_id or "")
        videos = [o for o in job.outputs or [] if o.get("kind") == "video"]
        if job.status != "completed" or not videos:
            raise ServiceError(422, "invalid_source", "The source generation is not a completed video")
        for f in job.files or []:
            path = Path(settings.storage_dir) / "outputs" / job.id / f["name"]
            if f.get("kind") == "video" and path.exists():
                return str(path.resolve())
        return await local_source(request, videos[0]["url"])

    async def voice_plan(
        request: Request, session: AsyncSession, owner: ApiClient, body: VoiceChangeIn
    ) -> tuple[str, float, float]:
        source = await voice_source(request, session, owner, body)
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
        _, start, end = await voice_plan(request, session, owner, body)
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
            source, start, end = await voice_plan(request, session, owner, body)
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
            cost = voice_estimate(end - start, settings)
            job = Job(
                owner_id=owner.id,
                model=VOICE_MODEL,
                input=args,
                input_hash=digest,
                idempotency_key=idempotency_key,
                status="in_progress",
                submitted_at=utcnow(),
                plan=[local_option(settings.elevenlabs_sts_model, cost)],
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

    async def audio_source(request: Request, session: AsyncSession, owner: ApiClient, body: IsolateIn) -> str:
        """Ruta local de un video o audio propio (los remotos se descargan antes; nunca una URL arbitraria)."""
        if body.source_url:
            if not await trusted_media(session, owner, body.source_url):
                raise ServiceError(
                    422,
                    "untrusted_source",
                    "source_url must come from /v1/uploads (upload_media) or your generations",
                )
            return await local_source(request, body.source_url)
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
        return await local_source(request, media[0]["url"])

    async def audio_plan(
        request: Request, session: AsyncSession, owner: ApiClient, body: BaseModel
    ) -> tuple[str | None, dict]:
        """(fuente, cotización) de un servicio de audio; el aislamiento mide la duración de la fuente."""
        if not isinstance(body, IsolateIn):
            return None, audio_estimate(body)
        source = await audio_source(request, session, owner, body)
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
            _, est = await audio_plan(request, session, owner, body)
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
                source, est = await audio_plan(request, session, owner, body)
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
                    plan=[local_option(audio_remote_model(body), est)],
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
                await app.state.worker.commit(session, job_id)

    return app
