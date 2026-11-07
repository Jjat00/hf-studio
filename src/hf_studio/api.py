import asyncio
import hashlib
import hmac
import json
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
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import anthropic
import httpx
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, delete, func, or_, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from . import director as dr
from . import projects
from . import skills as skill_files
from . import supercomputer as sc
from .audio import _run as run_ffmpeg
from .audio import guarded, has_audio, studio_notes, supports_source_audio
from .catalog import ALIASES as CATALOG_ALIASES
from .catalog import Catalog, get_catalog
from .config import Settings, get_settings
from .db import (
    ACTIVE,
    TERMINAL,
    ApiClient,
    Chat,
    Element,
    Folder,
    Job,
    Preset,
    Project,
    ProjectDocument,
    ProjectDocumentVersion,
    Shot,
    Skill,
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
    CATEGORIES as ELEMENT_CATEGORIES,
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
from .elements import fresh_urls as fresh_element_urls
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
from .factory import ContentFactoryJobs, is_factory, renderer_problem
from .factory_script import MAX_EPISODES, ScriptError, write_scripts
from .factory_script import max_cost_usd as factory_max_cost
from .factory_styles import STYLES as FACTORY_STYLES
from .factory_styles import public_styles as factory_styles
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
from .routing import AUDIO_FIELDS, Plan, Router, requote, video_urls
from .service import (
    UNSET,
    ServiceError,
    check_input,
    create_generation,
    get_owned_job,
    input_hash,
    job_for_key,
    request_digest,
    request_digests,
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
from .space_assistant import CLAUDE_PRICES, DEFAULT_CLAUDE, AnthropicJobs, is_assistant
from .space_audio import ElevenLabsJobs, is_audio_node
from .space_runs import (
    Hooks,
    NodeInputError,
    SpaceRunner,
    is_run_key,
    resolve_input,
    run_steps,
    selected_run,
    spend_of,
    split_step,
    step_deps,
)
from .space_tools import (
    ASSISTANT_PROVIDER,
    AUDIO_PROVIDER,
    BACKGROUND_PROVIDERS,
    FACTORY_PROVIDER,
    TOOL_PROVIDER,
    LocalTools,
    is_tool,
    tool_media,
)
from .spaces import (
    GraphError,
    Share,
    apply_inputs,
    check_flow,
    check_graph,
    check_values,
    empty_graph,
    flow_for_graph,
    graph_refs,
    input_kinds,
)
from .store import seedance_draft
from .styles import StyleCatalog
from .usage import UsageRow, summarize
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
from .voice_creation import DESIGN_MODEL, DesignVoiceIn, SaveVoiceIn, design_estimate, preview_path
from .voice_creation import clone as clone_voice
from .voice_creation import design as design_voice
from .voice_creation import save as save_designed_voice
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

MP3_TYPES = {"audio/mpeg", "audio/mp3"}


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
    project_id: str | None = Field(None, max_length=36, description="Proyecto donde se guarda (opcional)")
    folder_id: str | None = Field(None, max_length=36, description="Carpeta del proyecto (opcional)")


class MoveIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)
    project_id: str | None = Field(None, max_length=36, description="null: fuera de todo proyecto")
    folder_id: str | None = Field(None, max_length=36, description="null: sin carpeta")


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=300)
    brief: str | None = Field(
        None, max_length=50000, description="Markdown; sin él, la plantilla de secciones"
    )


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=300)
    brief: str | None = Field(None, max_length=50000)
    cover: str | None = Field(None, max_length=2000, description="URL propia; cadena vacía la quita")


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BatchItem(BaseModel):
    model: str
    input: dict[str, Any]
    count: int = Field(1, ge=1, le=8, description="Copias de esta entrada (variantes)")
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos de cotización propios de este ítem"
    )


# Tantas como la Biblioteca puede mostrar (su ventana de lectura): «Seleccionar todo» cabe en una sola escritura.
MAX_LIBRARY_IDS = 2000


class HideIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_LIBRARY_IDS)
    hidden: bool = True


class FavoriteIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_LIBRARY_IDS)
    favorite: bool = True


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
    flow: dict[str, Any] | None = Field(
        None,
        description="Publicar como flujo: {title, description, inputs: [{node_id, label}]}; null lo retira",
    )


class RunIn(BaseModel):
    mode: str = Field(pattern="^(downstream|workflow)$")
    node_id: str | None = Field(None, max_length=64, description="Nodo inicial (modo downstream)")
    version: int = Field(ge=1, description="Versión guardada del Space; la corrida usa exactamente ese grafo")
    dry_run: bool = Field(False, description="Solo cotiza cada paso y el total, sin gastar")
    max_total_usd: float | None = Field(None, ge=0, description="Tope aprobado para toda la corrida")
    inputs: dict[str, Any] | None = Field(
        None,
        description="Valores de las entradas de un flujo publicado: {node_id: texto, URL o lista de textos}",
    )


class RunApprove(BaseModel):
    max_total_usd: float | None = Field(None, ge=0, description="Nuevo tope (debe cubrir el paso en pausa)")
    accept_unknown: bool = Field(
        False,
        description="Acepta que el paso en pausa y los que faltan de la corrida no tengan precio conocido",
    )


class SkillIn(BaseModel):
    slug: str | None = Field(None, max_length=64, description="Nombre con el que se llama: /slug")
    description: str | None = Field(None, max_length=skill_files.MAX_DESCRIPTION)
    body: str | None = Field(None, max_length=skill_files.MAX_BODY)
    skill_md: str | None = Field(
        None,
        max_length=skill_files.MAX_BODY + 2000,
        description="Un SKILL.md completo (frontmatter y cuerpo)",
    )
    files: dict[str, str] | None = Field(
        None, description="Archivos de referencia {ruta: texto}; en una edición, si no viene, se conservan"
    )


class ChatIn(BaseModel):
    model: Literal[tuple(CLAUDE_PRICES)] = Field(DEFAULT_CLAUDE, description="Modelo de Claude del chat")  # type: ignore[valid-type]
    project_id: str | None = Field(
        None, max_length=36, description="Proyecto del chat (su brief va de contexto)"
    )


class ChatPatch(BaseModel):
    project_id: str | None = Field(None, max_length=36, description="Cadena vacía: sin proyecto")
    auto_budget_usd: float | None = Field(
        None, ge=0, le=500, description="Tope de la generación automática; 0 la apaga"
    )


class ChatDocument(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Nombre del archivo, p. ej. brief.md")
    content: str = Field(max_length=sc.MAX_DOCUMENT_CHARS, description="Texto del archivo (.md, .txt)")


class ChatAttachment(BaseModel):
    url: str = Field(
        max_length=2000, description="URL de una subida propia (/v1/uploads) o de una salida propia"
    )
    content_type: str | None = Field(None, max_length=100)
    filename: str | None = Field(None, max_length=255)


class ChatRef(BaseModel):
    name: str = Field(
        pattern=sc.REF_NAME, description="Nombre con que el usuario lo cita, sin @: imagen2, video1"
    )
    url: str = Field(max_length=2000, description="Subida propia o salida de una generación propia")
    content_type: str | None = Field(None, max_length=100)


class ChatMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    mode: Literal["ask", "auto"] = Field("ask", description="ask: aclara antes de proponer; auto: propone ya")
    effort: Literal["low", "medium", "high"] = "medium"
    model: Literal[tuple(CLAUDE_PRICES)] | None = None  # type: ignore[valid-type]
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=sc.MAX_ATTACHMENTS)
    documents: list[ChatDocument] = Field(default_factory=list, max_length=sc.MAX_DOCUMENTS)
    refs: list[ChatRef] = Field(
        default_factory=list,
        max_length=sc.MAX_REFS,
        description="Medios del chat citados con @imagenN, @videoN",
    )
    timezone: str | None = Field(
        None,
        max_length=64,
        pattern=r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$",
        description="Zona IANA del navegador",
    )


class ProposalJobIn(BaseModel):
    job_id: str = Field(max_length=36)


class ShotPatch(BaseModel):
    status: (
        Literal["planned", "boarded", "proposed", "generating", "review", "approved", "retake", "cut"] | None
    ) = None
    selected_job_id: str | None = Field(None, max_length=36, description="Toma buena; cadena vacía la quita")
    notes: str | None = Field(None, max_length=4000)
    verdict: str | None = Field(None, max_length=4000)


class DocumentIn(BaseModel):
    kind: Literal[
        "treatment", "breakdown", "bible", "lookbook", "color_script", "blocking", "script", "notes", "other"
    ] = "notes"
    title: str = Field(min_length=1, max_length=120)
    markdown: str = Field("", max_length=dr.MAX_DOCUMENT)


class DocumentPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    kind: (
        Literal[
            "treatment",
            "breakdown",
            "bible",
            "lookbook",
            "color_script",
            "blocking",
            "script",
            "notes",
            "other",
        ]
        | None
    ) = None
    markdown: str | None = Field(None, max_length=dr.MAX_DOCUMENT)
    base_version: int = Field(description="Versión leída: si otro la cambió, 409")


class EstimateIn(BaseModel):
    model: str
    input: dict[str, Any]
    hints: dict[str, Hint] = Field(
        default_factory=dict, description="Datos que la API no puede medir, p. ej. input_video_seconds"
    )
    provider: str | None = Field(None, description="Cotiza solo este proveedor")


class FactoryScriptIn(BaseModel):
    topic: str = Field(
        min_length=3, max_length=500, description="Escenario, p. ej. «¿Qué pasaría si la Luna desapareciera?»"
    )
    style: str = Field("neon-grid", max_length=40, description="Estilo visual (GET /v1/factory)")
    duration_seconds: int = Field(60, ge=30, le=90, description="Duración aproximada de cada episodio")
    episodes: int = Field(1, ge=1, le=MAX_EPISODES, description="Episodios de la serie")
    language: str = Field("es", pattern=r"^[a-z]{2}$", description="Idioma del guion y la voz")
    max_usd: float | None = Field(
        None,
        ge=0,
        description="Tope aprobado (el `max_usd` de /v1/factory/scripts/estimate). Sin él no se escribe",
    )


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
        app.state.styles = StyleCatalog(app.state.hf)
        # El worker conoce además el proveedor interno de las herramientas locales (no se lista como proveedor).
        app.state.local_tools = LocalTools(settings, transport, plain=app.state.hf.plain)
        app.state.local_tools.sweep()
        app.state.eleven = ElevenLabsClient(settings, transport)
        app.state.voice_slots = asyncio.Semaphore(2)
        app.state.audio_jobs = ElevenLabsJobs(
            settings, app.state.eleven, transport, slots=app.state.voice_slots
        )
        app.state.audio_jobs.sweep()
        app.state.assistant_jobs = AnthropicJobs(settings, transport)
        app.state.assistant_jobs.sweep()
        app.state.factory_jobs = ContentFactoryJobs(settings, app.state.eleven, transport)
        app.state.factory_jobs.sweep()
        app.state.worker = Worker(
            app.state.sessions,
            {
                **app.state.providers,
                TOOL_PROVIDER: app.state.local_tools,
                AUDIO_PROVIDER: app.state.audio_jobs,
                ASSISTANT_PROVIDER: app.state.assistant_jobs,
                FACTORY_PROVIDER: app.state.factory_jobs,
            },
            settings,
        )
        app.state.prices = PriceBook(Path(settings.storage_dir) / "prices")

        async def element_resolver(ids: list[str]) -> dict[str, dict]:
            # Desde la base en cada plan, recotización o aprobación: URLs vigentes, nunca un snapshot viejo.
            async with app.state.sessions() as s:
                return await resolve_elements(s, ids, settings.storage_dir, app.state.hf.upload)

        async def draft_resolver(generation_id: object) -> dict | None:
            # El borrador de Seedance 2.5 que pide un final: proveedor, id de tarea y lo que cobra el final.
            if not isinstance(generation_id, str):
                return None
            async with app.state.sessions() as s:
                job = await s.get(Job, generation_id)
            if job is None or job.status != "completed" or not seedance_draft.is_draft(job.model):
                return None
            if not job.hf_request_id or job.provider not in seedance_draft.EXPIRES:
                return None
            hints = (job.plan[job.plan_index] if job.plan and job.plan_index < len(job.plan) else {}).get(
                "hints"
            ) or {}
            return {
                "provider": job.provider, "task_id": job.hf_request_id, "duration": job.input.get("duration") or 5,
                "has_video": bool(job.input.get("video_urls")), "input_video_seconds": hints.get("input_video_seconds"),
            }  # fmt: skip

        app.state.router = Router(
            app.state.providers, app.state.prices, get_catalog, element_resolver, draft_resolver
        )
        app.state.worker.router = app.state.router
        app.state.tasks = set()
        app.state.chats_busy = set()
        # Un candado por chat para escribir sus propuestas (vincular, generar en automático, guardar un turno):
        # ninguna escritura pisa a otra ni el tope automático se reparte dos veces.
        app.state.chat_locks = {}
        app.state.factory_scripts = {}  # guiones por (cliente, Idempotency-Key): un reintento no vuelve a cobrar
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
        await app.state.assistant_jobs.aclose()
        await app.state.factory_jobs.aclose()
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

    @app.exception_handler(skill_files.SkillError)
    async def _skill_error(_: Request, exc: skill_files.SkillError) -> JSONResponse:
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
            "hidden": bool(job.hidden),
            "favorite": bool(job.favorite),
            "project_id": job.project_id,
            "folder_id": job.folder_id,
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
        # `store`: solo lo venden APIMart y KIE (paquete `store/`), no Higgsfield.
        base = {
            **{k: m[k] for k in keys},
            "inputs": input_kinds(m["input_schema"]),
            "store": bool(m.get("store")),
        }
        return (
            {
                **base,
                "summary": m["summary"],
                "notes": m["notes"],
                "studio_notes": studio_notes(m),
                # Si admite keep_source_audio: la UI ofrece «Conservar audio» solo cuando la API lo acepta.
                "keep_source_audio": supports_source_audio(m),
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

    @app.get("/v1/usage", tags=["sistema"])
    async def usage(
        session: Session,
        owner: Owner,
        days: int = Query(30, ge=0, le=3650, description="Últimos N días; 0 = todo el historial"),
        utc_offset: int = Query(
            0, ge=-840, le=840, description="Minutos respecto de UTC para agrupar por día"
        ),
    ) -> dict:
        """Gasto de las generaciones terminadas, por día, proveedor y modelo. Es el precio cotizado de la
        opción que corrió, no el cobro conciliado con el proveedor (sin gastar: solo lee la base)."""
        now = utcnow()
        since = None
        if days:
            # Desde la medianoche local de hace N-1 días: «7 días» incluye hoy completo y seis días enteros.
            local_today = (now + timedelta(minutes=utc_offset)).date()
            start = datetime.combine(local_today - timedelta(days=days - 1), datetime.min.time())
            since = start - timedelta(minutes=utc_offset)
        query = select(Job.model, Job.provider, Job.plan, Job.plan_index, Job.created_at).where(
            Job.status == "completed"
        )
        if not owner.sees_all:
            query = query.where(Job.owner_id == owner.id)
        if since:
            query = query.where(Job.created_at >= since)
        rows = []
        for model, provider, plan, index, created in (await session.execute(query)).tuples():
            option = plan[index] if plan and index < len(plan) else {}
            rows.append(UsageRow(
                model=CATALOG_ALIASES.get(model, model),  # ids renombrados: una sola fila por modelo
                # Como en job_out: los trabajos de audio corren en ElevenLabs aunque la columna diga otra cosa.
                provider="elevenlabs" if model in LOCAL_MODELS else provider,
                usd=option.get("usd"),
                kind=option.get("kind"),
                at=created,
            ))  # fmt: skip
        return summarize(rows, since, now, utc_offset)

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

    @app.get("/v1/model-styles/{model_id:path}", tags=["modelos"])
    async def list_model_styles(model_id: str, request: Request, _: Owner, catalog: CatalogDep) -> dict:
        """Estilos vigentes de un modelo que los elige por `preset_id` (Genjutsu Restyle). Gratis."""
        model = catalog.get(model_id)
        if not model:
            raise ServiceError(404, "unknown_model", f"Unknown model: {model_id}")
        return {"model": model["id"], "styles": await request.app.state.styles.list(model["id"])}

    @app.get("/v1/model-options/{model_id:path}", tags=["modelos"])
    async def list_model_options(model_id: str, request: Request, _: Owner, catalog: CatalogDep) -> dict:
        """Rasgos vigentes de un modelo que los elige por clave (AI Influencer: `selection`). Gratis."""
        model = catalog.get(model_id)
        if not model:
            raise ServiceError(404, "unknown_model", f"Unknown model: {model_id}")
        return {"model": model["id"], **await request.app.state.styles.options(model["id"])}

    async def complete_hints(
        request: Request, session: AsyncSession, owner: ApiClient, arguments: dict, hints: dict
    ) -> dict:
        """Mide la duración de los videos y audios de entrada (si no viene en `hints`): varios proveedores
        cobran por ella. Solo medios propios, descargados y medidos en local sin red (SSRF, revisión 28)."""
        hints = dict(hints or {})
        for key, urls, audio in (
            ("input_video_seconds", video_urls(arguments), False),
            ("input_audio_seconds", video_urls(arguments, AUDIO_FIELDS), True),
        ):
            if key in hints or not urls:
                continue
            seconds = 0.0
            for url in urls:
                if not await trusted_media(session, owner, url):
                    break
                measured = await local_duration(
                    url, request.app.state.hf.plain, settings.max_upload_bytes, audio=audio
                )
                if not measured:
                    break
                seconds += measured
            else:
                hints[key] = round(seconds, 2)
        return hints

    async def make_plan(
        request: Request, session: AsyncSession, owner: ApiClient, model: dict, arguments: dict, hints: dict,
        provider: str | None = None,
    ) -> Plan:  # fmt: skip
        hints = await complete_hints(request, session, owner, arguments, hints)
        await request.app.state.styles.check(model["id"], arguments)
        # Una petición nueva solo cita elementos vivos; sus imágenes las pone el router desde la base, nunca
        # el cliente (las pistas no llevan elementos).
        hints.pop("elements", None)
        await check_element_ids(session, arguments.get("elements"))
        if is_assistant(model["id"]) and not app.state.assistant_jobs.available:
            raise ServiceError(
                503, "anthropic_not_configured", "Set ANTHROPIC_API_KEY in .env to use the Assistant"
            )
        if (
            is_factory(model["id"])
            and (arguments.get("voice") or {}).get("engine") == "elevenlabs"
            and (not app.state.eleven.configured)
        ):
            raise ServiceError(503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env")
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
        if model["id"] == seedance_draft.FINAL_ID:
            await check_draft(session, owner, arguments.get("draft_generation_id"))
        return await request.app.state.router.plan(model, arguments, hints, only=provider)

    async def check_draft(session: AsyncSession, owner: ApiClient, generation_id: object) -> None:
        """El final de un borrador: solo de un borrador propio, terminado y que la tienda aún guarda."""
        job = await session.get(Job, generation_id) if isinstance(generation_id, str) else None
        if job is None or not (owner.sees_all or job.owner_id == owner.id):
            raise ServiceError(404, "draft_not_found", "Unknown draft generation")
        if not seedance_draft.is_draft(job.model):
            raise ServiceError(422, "not_a_draft", "That generation is not a Seedance 2.5 draft")
        if job.status != "completed":
            raise ServiceError(422, "draft_not_ready", "The draft has not finished yet")
        expires = seedance_draft.EXPIRES.get(job.provider)
        if expires is None or utcnow() - (job.finished_at or job.created_at) > expires - timedelta(
            minutes=10
        ):
            raise ServiceError(422, "draft_expired", "The draft expired; make a new one")

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
        if content_type not in UPLOAD_CONTENT_TYPES | MP3_TYPES:
            content_type = (mimetypes.guess_type(file.filename or "")[0] or "").lower()
        if content_type not in UPLOAD_CONTENT_TYPES | MP3_TYPES:
            raise ServiceError(
                415,
                "unsupported_media",
                f"Supported types: {', '.join(sorted(UPLOAD_CONTENT_TYPES | MP3_TYPES))}",
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
        if content_type in MP3_TYPES:
            # Higgsfield no acepta MP3: se sube una copia WAV hecha con ffmpeg (solo el demuxer mp3).
            data, content_type = bytearray(await upload_mp3_as_wav(bytes(data))), "audio/wav"
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

    @app.delete("/v1/uploads/{upload_id}", tags=["archivos"], status_code=204)
    async def delete_upload(upload_id: str, session: Session, owner: Owner) -> None:
        """Quita una subida de la lista del cliente (p. ej. repetidas). Las generaciones que la usaron no cambian."""
        row = await session.get(Upload, upload_id)
        if row is None or row.owner_id != owner.id:
            raise ServiceError(404, "not_found", "Upload not found")
        await session.delete(row)
        await session.commit()

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
        project_id, folder_id = await check_place(session, owner, body.project_id, body.folder_id)
        # Un reintento con la misma Idempotency-Key devuelve el trabajo ya creado antes de volver a cotizar o
        # resolver medios: un elemento borrado o un precio nuevo no lo convierten en otra petición (revisión 43).
        digest = request_digest(model["id"], body.input, body.keep_source_audio, body.provider)
        same = request_digests(model["id"], body.input, body.keep_source_audio, body.provider)
        if existing := await job_for_key(session, owner, idempotency_key, digest, same):
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
        if created and project_id:
            job.project_id, job.folder_id = project_id, folder_id
            await session.commit()
        if created:
            request.app.state.worker.wake()
        return JSONResponse(job_out(job, deduplicated=not created), status_code=202 if created else 200)

    async def check_place(
        session: AsyncSession, owner: ApiClient, project_id: str | None, folder_id: str | None
    ) -> tuple[str | None, str | None]:
        """Proyecto y carpeta propios (una carpeta implica su proyecto); 404 si no existen o son de otro."""
        if folder_id:
            folder = await session.get(Folder, folder_id)
            if folder is None:
                raise ServiceError(404, "folder_not_found", "Folder not found")
            if project_id and project_id != folder.project_id:
                raise ServiceError(422, "folder_mismatch", "The folder belongs to another project")
            project_id = folder.project_id
        if project_id:
            await get_owned_project(session, owner, project_id)
        return project_id, folder_id

    async def get_owned_project(session: AsyncSession, owner: ApiClient, project_id: str) -> Project:
        project = await session.get(Project, project_id)
        if project is None or (project.owner_id != owner.id and not owner.sees_all):
            raise ServiceError(404, "project_not_found", "Project not found")
        return project

    @app.get("/v1/generations", tags=["generaciones"])
    async def list_generations(
        session: Session,
        owner: Owner,
        status: str | None = None,
        # Hasta 2000: la Biblioteca relee de una vez todo lo que ya se cargó con el scroll.
        limit: int = Query(20, ge=1, le=MAX_LIBRARY_IDS),
        offset: int = Query(0, ge=0),
        ids: str | None = Query(None, description="IDs separados por coma (espera múltiple con wait)"),
        wait: int = Query(0, ge=0, le=120, description="Con ids: espera hasta N s a que todas terminen"),
        hidden: bool = Query(False, description="true: solo las ocultas (sin ids, las ocultas no se listan)"),
        favorite: bool = Query(False, description="true: solo las favoritas"),
        project: str | None = Query(None, max_length=36, description="Id de proyecto, o none: sin proyecto"),
        folder: str | None = Query(None, max_length=36, description="Id de carpeta, o none: sin carpeta"),
        model: Annotated[list[str] | None, Query(description="Modelos (repetible); OR con text")] = None,
        text: Annotated[
            list[str] | None, Query(description="Texto que contiene la entrada (repetible, OR)")
        ] = None,
    ) -> dict:
        query = select(Job) if owner.sees_all else select(Job).where(Job.owner_id == owner.id)
        if ids:
            wanted = [i for i in ids.split(",") if i][:50]
            query = query.where(Job.id.in_(wanted))
        else:
            # Pedidas por id (un lienzo, una espera) se devuelven aunque estén ocultas; en un listado, no.
            query = query.where(Job.hidden == hidden)
        if favorite:
            query = query.where(Job.favorite.is_(True))
        if project:
            query = query.where(Job.project_id.is_(None) if project == "none" else Job.project_id == project)
        if folder:
            query = query.where(Job.folder_id.is_(None) if folder == "none" else Job.folder_id == folder)
        if status:
            query = query.where(Job.status == status)
        # Filtro de una página (p. ej. el historial de AI Influencer): cualquiera de los modelos o de los textos.
        matches = [Job.model.in_(model[:20])] if model else []
        matches += [
            cast(Job.input, String).contains(t[:200], autoescape=True) for t in (text or [])[:10] if t
        ]
        if matches:
            query = query.where(or_(*matches))
        query = query.order_by(Job.created_at.desc(), Job.id.desc()).offset(offset).limit(limit)
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

    @app.get("/v1/approvals", tags=["generaciones"])
    async def list_approvals(session: Session, owner: Owner, limit: int = Query(50, ge=1, le=100)) -> dict:
        """Generaciones que esperan aprobación (el precio, la retención o el proveedor cambió fuera de lo
        aprobado), con su total. Las de una corrida de Spaces traen `space_run` (su Space y su corrida): se aprueban
        desde la corrida, contra su tope, no con /approve."""
        query = select(Job).where(Job.status == "awaiting_approval")
        if not owner.sees_all:
            query = query.where(Job.owner_id == owner.id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        jobs = list(await session.scalars(query.order_by(Job.created_at.desc()).limit(limit)))
        run_ids = {j.idempotency_key.split(":")[1] for j in jobs if is_run_key(j.idempotency_key)}
        runs = {}
        if run_ids:
            rows = await session.execute(
                select(SpaceRun.id, SpaceRun.space_id, Space.title)
                .join(Space, Space.id == SpaceRun.space_id)
                .where(SpaceRun.id.in_(run_ids))
            )
            runs = {
                run_id: {"run_id": run_id, "space_id": space_id, "title": title}
                for run_id, space_id, title in rows
            }
        names = await client_names(session) if owner.sees_all else {}
        out = []
        for j in jobs:
            body = job_out(j, source=names.get(j.owner_id))
            run_id = j.idempotency_key.split(":")[1] if is_run_key(j.idempotency_key) else None
            body["space_run"] = runs.get(run_id) if run_id else None
            out.append(body)
        return {"total": total, "generations": out}

    batch_locks: weakref.WeakValueDictionary[tuple[str, str], asyncio.Lock] = weakref.WeakValueDictionary()

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
        # Un lote con clave se recupera y crea bajo un candado por dueño y clave: dos reintentos a la vez no pueden
        # contar cada uno con su propia foto de lo creado y sumar más de lo aprobado (revisión 72).
        async with AsyncExitStack() as guard:
            if idempotency_key and not body.dry_run:
                lock = batch_locks.get((owner.id, idempotency_key))
                if lock is None:
                    lock = batch_locks[(owner.id, idempotency_key)] = asyncio.Lock()
                await guard.enter_async_context(lock)
            # Posiciones del lote (un ítem con count 3 son tres) y lo que un intento anterior con esta misma clave ya
            # creó. Lo ya creado se recupera con su trabajo y su compromiso persistidos (tope y retención de
            # entonces), sin volver a cotizarlo ni exigir su proveedor; solo se cotizan las posiciones nuevas. La
            # cotización en seco con la clave usa las mismas cuentas que la ejecución (revisiones 70 y 71).
            positions: list[tuple[int, str | None]] = []
            for idx, item in enumerate(body.items):
                positions += [(idx, None)] * item.count
            if idempotency_key:
                positions = [(idx, f"{idempotency_key}:{n}") for n, (idx, _) in enumerate(positions)]
                found = {
                    j.idempotency_key: j
                    for j in await session.scalars(
                        select(Job).where(
                            Job.owner_id == owner.id, Job.idempotency_key.in_([k for _, k in positions])
                        )
                    )
                }
            else:
                found = {}
            for idx, key in positions:
                prior = found.get(key)
                item = body.items[idx]
                if prior is not None and prior.input_hash not in request_digests(item.model, item.input):
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "This Idempotency-Key was already used for a different batch",
                    )
            if not body.dry_run:
                for item in body.items:
                    check_input(catalog, item.model, item.input)
                if found and len(found) == len(positions):
                    # Reintento del lote completo: devolver lo ya creado antes de mirar cupos.
                    return JSONResponse(
                        {"generations": [job_out(found[k]) for _, k in positions]}, status_code=200
                    )
                active = await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.owner_id == owner.id, Job.status.in_(ACTIVE))
                )
                # Lo ya creado de un reintento parcial no vuelve a ocupar cupo (revisión 69).
                wanted = len(positions) - len(found)
                if active + wanted > settings.max_active_jobs_per_client:
                    raise ServiceError(
                        429,
                        "too_many_active",
                        f"This batch needs {wanted} slots; you have {active} active of {settings.max_active_jobs_per_client}",
                    )
            plans: dict[int, Any] = {}
            for idx in dict.fromkeys(idx for idx, key in positions if key not in found):
                item = body.items[idx]
                plans[idx] = await make_plan(
                    request, session, owner, catalog.get(item.model), item.input, {**body.hints, **item.hints}
                )
            spends: list[
                tuple[float | None, float]
            ] = []  # por posición: (usd o None si desconocido, retención)
            for idx, key in positions:
                prior = found.get(key)
                if prior is not None:
                    spends.append((prior.max_usd, prior.max_reserve_usd or 0.0))
                else:
                    best = plans[idx].best
                    usd = None if best is None or best.usd is None or best.missing else best.usd
                    spends.append((usd, (best.reserve_usd or 0.0) if best else 0.0))
            if body.dry_run:
                quotes = {idx: estimate_body(plan) for idx, plan in plans.items()}
                items = []
                for idx, item in enumerate(body.items):
                    recovered = sum(1 for i, k in positions if i == idx and k in found)
                    items.append({"model": item.model, "count": item.count, "estimate": quotes.get(idx),
                                  **({"recovered": recovered} if recovered else {})})  # fmt: skip
                if not found:
                    return JSONResponse(
                        {"items": items, "total": total(list(quotes.values()), [i.count for i in body.items])}
                    )
                usd = sum(u for u, _ in spends if u is not None)
                reserve = sum(r for _, r in spends)
                return JSONResponse({"items": items, "total": {
                    "usd": round(usd, 4), "credits": None, "complete": all(u is not None for u, _ in spends),
                    "reserve_usd": round(reserve, 4) or None, "recovered": len(found),
                }})  # fmt: skip
            for idx, plan in plans.items():
                if plan.best is None:
                    raise ServiceError(422, "no_provider", estimate_body(plan)["basis"], plan.public())
            # Antes de crear el primer trabajo: el lote entero dentro de lo aprobado (revisiones 28 a 33).
            if body.accept_unknown_cost and body.max_total_usd is not None:
                # Un tope total no se puede hacer cumplir por trabajo si algún precio es desconocido: o hay tope o se
                # acepta el total desconocido sin tope, nunca las dos cosas.
                raise ServiceError(422, "conflicting_approval",
                                   "Pass either max_total_usd or accept_unknown_cost=true (no cap), not both")  # fmt: skip
            if body.max_total_usd is not None:
                if any(u is None for u, _ in spends) and not body.accept_unknown_cost:
                    raise ServiceError(
                        409, "cost_unknown", "Some item no longer has a price; quote the batch again"
                    )
                cost = sum(u for u, _ in spends if u is not None)
                if cost > body.max_total_usd + COST_TOLERANCE_USD:
                    raise ServiceError(409, "cost_changed",
                                       f"The batch now costs {cost:.4f} USD (approved {body.max_total_usd:.4f})", cost)  # fmt: skip
            quoted = (
                body.max_total_usd is not None
                or body.max_total_reserve_usd is not None
                or body.accept_unknown_cost
            )
            held = sum(r for _, r in spends)
            if quoted:
                check_reserve(held, body.max_total_reserve_usd, held, "The batch")
            jobs, created_any = [], False
            for idx, key in positions:
                if key in found:
                    jobs.append(found[key])
                    continue
                item, plan = body.items[idx], plans[idx]
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

    async def set_library_flag(
        session: AsyncSession, owner: ApiClient, ids: list[str], values: dict, *conditions: Any
    ) -> set[str]:
        """Cambia una marca de biblioteca (oculta, favorita) de varias generaciones del cliente (o de todos con
        sees_all). Es una UPDATE directa que no sube `Job.version`: organizar la biblioteca no debe invalidar la
        escritura de un worker que en ese momento envía o sondea el trabajo (perdería su request_id). El worker,
        por su parte, solo escribe las columnas que cambió, así que tampoco pisa la marca."""
        where = [Job.id.in_(set(ids)), *conditions]
        if not owner.sees_all:
            where.append(Job.owner_id == owner.id)
        changed = set(await session.scalars(select(Job.id).where(*where)))
        if changed:
            await session.execute(
                update(Job)
                .where(Job.id.in_(changed))
                .values(**values)
                .execution_options(synchronize_session=False)
            )
        await session.commit()
        return changed

    @app.post("/v1/generations/hide", tags=["generaciones"])
    async def hide_generations(body: HideIn, session: Session, owner: Owner) -> dict:
        """Oculta (o vuelve a mostrar, con `hidden: false`) varias generaciones terminadas del historial y de los
        listados. Siguen accesibles por su id. Las que siguen en curso o no son del cliente se dejan igual."""
        changed = await set_library_flag(
            session, owner, body.ids, {"hidden": body.hidden}, Job.status.in_(TERMINAL)
        )
        return {"changed": sorted(changed), "skipped": sorted(set(body.ids) - changed)}

    @app.post("/v1/generations/favorite", tags=["generaciones"])
    async def favorite_generations(body: FavoriteIn, session: Session, owner: Owner) -> dict:
        """Marca (o desmarca, con `favorite: false`) varias generaciones como favoritas de la biblioteca."""
        changed = await set_library_flag(session, owner, body.ids, {"favorite": body.favorite})
        return {"changed": sorted(changed), "skipped": sorted(set(body.ids) - changed)}

    @app.post("/v1/generations/move", tags=["generaciones"])
    async def move_generations(body: MoveIn, session: Session, owner: Owner) -> dict:
        """Mueve varias generaciones a un proyecto y carpeta (o fuera, con null)."""
        project_id, folder_id = await check_place(session, owner, body.project_id, body.folder_id)
        changed = await set_library_flag(
            session, owner, body.ids, {"project_id": project_id, "folder_id": folder_id}
        )
        return {"changed": sorted(changed), "skipped": sorted(set(body.ids) - changed)}

    # --- Proyectos y carpetas --------------------------------------------------------------------

    async def project_view(session: AsyncSession, project: Project, full: bool = False) -> dict:
        count = await session.scalar(select(func.count(Job.id)).where(Job.project_id == project.id))
        latest = await session.scalars(
            select(Job.outputs)
            .where(Job.project_id == project.id, Job.status == "completed", Job.hidden.is_(False))
            .order_by(Job.created_at.desc())
            .limit(4)
        )
        thumbs = [o.get("url") for outs in latest for o in (outs or [])[:1] if o.get("url")]
        data = {**project.out(full), "generations": count or 0, "thumbnails": thumbs}
        if full:
            folders = await session.scalars(
                select(Folder).where(Folder.project_id == project.id).order_by(Folder.name)
            )
            data["folders"] = [f.out() for f in folders]
        return data

    @app.get("/v1/projects", tags=["proyectos"])
    async def list_projects(session: Session, owner: Owner) -> dict:
        query = select(Project) if owner.sees_all else select(Project).where(Project.owner_id == owner.id)
        rows = list(await session.scalars(query.order_by(Project.updated_at.desc())))
        return {"projects": [await project_view(session, p) for p in rows]}

    @app.post("/v1/projects", tags=["proyectos"], status_code=201)
    async def create_project(body: ProjectIn, session: Session, owner: Owner) -> dict:
        """Crea un proyecto con un brief (por defecto, la plantilla de secciones)."""
        brief = body.brief if body.brief is not None else projects.brief_template(body.name)
        project = Project(owner_id=owner.id, name=body.name.strip(), description=body.description.strip(),
                          brief=brief)  # fmt: skip
        session.add(project)
        await session.commit()
        return await project_view(session, project, full=True)

    @app.get("/v1/projects/{project_id}", tags=["proyectos"])
    async def get_project(project_id: str, session: Session, owner: Owner) -> dict:
        return await project_view(session, await get_owned_project(session, owner, project_id), full=True)

    @app.patch("/v1/projects/{project_id}", tags=["proyectos"])
    async def update_project(project_id: str, body: ProjectPatch, session: Session, owner: Owner) -> dict:
        project = await get_owned_project(session, owner, project_id)
        if body.name is not None:
            project.name = body.name.strip()
        if body.description is not None:
            project.description = body.description.strip()
        if body.brief is not None:
            project.brief = body.brief
        if body.cover is not None:
            if body.cover and not await trusted_media(session, owner, body.cover):
                raise ServiceError(
                    422, "untrusted_source", "The cover must be one of your uploads or outputs"
                )
            project.cover = body.cover or None
        project.updated_at = utcnow()
        await session.commit()
        return await project_view(session, project, full=True)

    @app.delete("/v1/projects/{project_id}", tags=["proyectos"], status_code=204)
    async def delete_project(project_id: str, session: Session, owner: Owner) -> None:
        """Borra el proyecto y sus carpetas; sus generaciones siguen en el historial, sin proyecto."""
        project = await get_owned_project(session, owner, project_id)
        await session.execute(
            update(Job).where(Job.project_id == project.id).values(project_id=None, folder_id=None)
            .execution_options(synchronize_session=False)
        )  # fmt: skip
        await session.execute(
            update(Chat).where(Chat.project_id == project.id).values(project_id=None)
            .execution_options(synchronize_session=False)
        )  # fmt: skip
        await session.execute(delete(Folder).where(Folder.project_id == project.id))
        await session.execute(delete(Shot).where(Shot.project_id == project.id))
        doc_ids = select(ProjectDocument.id).where(ProjectDocument.project_id == project.id)
        await session.execute(
            delete(ProjectDocumentVersion).where(ProjectDocumentVersion.document_id.in_(doc_ids))
        )
        await session.execute(delete(ProjectDocument).where(ProjectDocument.project_id == project.id))
        await session.delete(project)
        await session.commit()

    @app.post("/v1/projects/{project_id}/folders", tags=["proyectos"], status_code=201)
    async def create_folder(project_id: str, body: FolderIn, session: Session, owner: Owner) -> dict:
        project = await get_owned_project(session, owner, project_id)
        folder = Folder(project_id=project.id, name=body.name.strip())
        session.add(folder)
        await session.commit()
        return folder.out()

    async def get_owned_folder(session: AsyncSession, owner: ApiClient, folder_id: str) -> Folder:
        folder = await session.get(Folder, folder_id)
        if folder is None:
            raise ServiceError(404, "folder_not_found", "Folder not found")
        await get_owned_project(session, owner, folder.project_id)
        return folder

    @app.patch("/v1/folders/{folder_id}", tags=["proyectos"])
    async def rename_folder(folder_id: str, body: FolderIn, session: Session, owner: Owner) -> dict:
        folder = await get_owned_folder(session, owner, folder_id)
        folder.name = body.name.strip()
        await session.commit()
        return folder.out()

    @app.delete("/v1/folders/{folder_id}", tags=["proyectos"], status_code=204)
    async def delete_folder(folder_id: str, session: Session, owner: Owner) -> None:
        """Borra la carpeta; sus generaciones siguen en el proyecto, sin carpeta."""
        folder = await get_owned_folder(session, owner, folder_id)
        await session.execute(
            update(Job).where(Job.folder_id == folder.id).values(folder_id=None)
            .execution_options(synchronize_session=False)
        )  # fmt: skip
        await session.delete(folder)
        await session.commit()

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
    async def use_output(
        job_id: str,
        index: int,
        session: Session,
        owner: Owner,
        as_: Annotated[
            Literal["last_frame", "first_frame", "audio"] | None,
            Query(alias="as", description="De un video: su último o primer fotograma, o su pista de audio"),
        ] = None,
    ) -> dict:
        """URL pública y vigente de una salida propia, para usarla como entrada de otra generación (fotograma
        inicial, referencia, video a editar…). Sube la copia local a Higgsfield (gratis) y la registra como
        subida propia; si ya se subió hace menos de 5 días, devuelve esa misma URL."""
        return await fresh_output(session, owner, job_id, index, as_)

    wav_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = weakref.WeakValueDictionary()

    async def upload_mp3_as_wav(data: bytes) -> bytes:
        """WAV de un MP3 subido. Valida la firma antes de dárselo a ffmpeg, limitado al demuxer mp3."""
        head = data[:16]
        if not (head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)):
            raise ServiceError(415, "content_mismatch", "The file content is not a valid audio/mpeg")
        with tempfile.TemporaryDirectory(prefix="hfs-mp3-") as tmp:
            src, dst = Path(tmp) / "in.mp3", Path(tmp) / "out.wav"
            src.write_bytes(data)
            code, err = await run_ffmpeg(
                "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file", "-format_whitelist", "mp3",
                "-f", "mp3", "-i", str(src), "-vn", "-c:a", "pcm_s16le",
                # ffmpeg deja de escribir al pasar el límite: el WAV expandido nunca crece sin tope (revisión 69).
                "-fs", str(settings.max_upload_bytes + 1), str(dst),
            )  # fmt: skip
            if code != 0 or not dst.is_file() or not dst.stat().st_size:
                raise ServiceError(422, "audio_convert_failed", f"Could not convert that MP3: {err[:200]}")
            too_big = dst.stat().st_size > settings.max_upload_bytes  # antes de cargarlo en memoria
            wav = b"" if too_big else dst.read_bytes()
        if too_big:
            raise ServiceError(
                413, "too_large", f"Maximum {settings.max_upload_bytes // (1024 * 1024)} MB as WAV"
            )
        return wav

    async def derived_file(path: Path, derive: str) -> Path:
        """Último fotograma (PNG) o pista de audio (WAV) de un video propio, hecho una vez junto a él con
        ffmpeg. Mismo candado y temporal único que `mp3_as_wav`."""
        suffix = {"last_frame": "last.png", "first_frame": "first.png"}.get(derive, "audio.wav")
        out = path.with_name(f"{path.stem}.{suffix}")
        lock = wav_locks.get(out)
        if lock is None:
            lock = wav_locks[out] = asyncio.Lock()
        async with lock:
            if out.is_file():
                return out
            if derive == "audio" and not await has_audio(str(path)):
                raise ServiceError(422, "no_audio", "That video has no audio track")
            fd, name = tempfile.mkstemp(prefix=f"{out.stem}.", suffix=f".tmp{out.suffix}", dir=out.parent)
            os.close(fd)
            tmp = Path(name)
            try:
                if derive == "last_frame":
                    # Desde el último segundo, cada fotograma reescribe el archivo: queda el último.
                    args = ["-sseof", "-1", *guarded(str(path)), "-update", "1", str(tmp)]
                elif derive == "first_frame":
                    args = [*guarded(str(path)), "-frames:v", "1", str(tmp)]
                else:
                    args = [*guarded(str(path)), "-vn", "-c:a", "pcm_s16le", str(tmp)]
                code, err = await run_ffmpeg("ffmpeg", "-y", "-v", "error", *args)
                if code != 0 or not tmp.stat().st_size:
                    raise ServiceError(
                        422, "derive_failed", f"Could not extract that from the video: {err[:200]}"
                    )
                tmp.replace(out)
            finally:
                tmp.unlink(missing_ok=True)
        return out

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

    async def fresh_output(
        session: AsyncSession,
        owner: ApiClient,
        job_id: str,
        index: int,
        derive: str | None = None,
        share: Share | None = None,
    ) -> dict:
        """Núcleo de `use_output`; también lo usan las corridas de Spaces para encadenar pasos. `derive`
        ("last_frame" o "audio") da en su lugar el último fotograma o el audio de una salida de video. `share`:
        lo que comparte el lienzo de la corrida (sus generaciones valen aunque las haya hecho otro cliente)."""
        job = await get_owned_job(session, owner, job_id, share)
        entry = next((f for f in job.files or [] if f["index"] == index), None)
        if job.status != "completed" or entry is None:
            raise ServiceError(404, "not_found", "That output is not available (finished generations only)")
        path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"]
        if not path.is_file():
            raise ServiceError(404, "not_found", "The local copy of that output is missing")
        content_type = (entry.get("content_type") or "").split(";")[0].strip().lower()
        kind = entry["kind"]
        if derive is not None:
            if kind != "video":
                raise ServiceError(
                    422, "not_a_video", "Only a video output has a last frame or an audio track"
                )
            path = await derived_file(path, derive)
            frame = derive in ("last_frame", "first_frame")
            content_type, kind = ("image/png", "image") if frame else ("audio/wav", "audio")
        elif content_type == "audio/mpeg":
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
        source = f"generation:{job.id}:{index}" + (f":{derive}" if derive else "")
        # Valores propios, no del ORM: un rollback por conflicto expira los objetos cargados (revisión 48).
        owner_id, generation_id = owner.id, job.id
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
                row = Upload(owner_id=owner_id, filename=path.name, content_type=content_type,
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
        category: Annotated[str, Form()] = "other",
    ) -> dict:
        """Crea un elemento (personaje, lugar o prop) con 1 a 4 imágenes JPG o PNG (archivos o URLs propias). Se
        cita con @nombre; Kling 3.0 necesita 2 o más."""
        sources: list = [*files, *image_urls]
        return await store_element(request, session, owner, name, description, category, sources)

    async def store_element(
        request: Request,
        session: AsyncSession,
        owner: ApiClient,
        name: str,
        description: str,
        category: str,
        sources: list,
    ) -> dict:
        """Valida y guarda un elemento con sus imágenes: archivos, URLs propias o bytes ya leídos `(datos, tipo)`."""
        name = check_name(name)
        if category not in ELEMENT_CATEGORIES:
            raise ServiceError(
                422, "invalid_category", f"category must be one of {', '.join(ELEMENT_CATEGORIES)}"
            )
        description = description.strip()
        if not description:
            raise ServiceError(422, "invalid_description", "The description cannot be empty")
        await purge_deleted_elements(session, settings.storage_dir)
        if not MIN_IMAGES <= len(sources) <= MAX_IMAGES:
            raise ServiceError(422, "image_count", f"An element needs {MIN_IMAGES} to {MAX_IMAGES} images")
        taken = await session.scalar(select(Element).where(Element.name == name))
        if taken:
            message = f"There is already an element called @{name}"
            if taken.deleted_at:
                message = f"@{name} was deleted recently or a running generation still uses it; try again in a few minutes"
            raise ServiceError(409, "name_taken", message)
        images = [
            (src[0], check_image(src[0], ""))
            if isinstance(src, tuple)
            else await element_image(session, owner, src)
            for src in sources
        ]
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
                              category=category, created_by=owner.id)  # fmt: skip
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

    @app.post("/v1/elements/{element_id}/urls", tags=["elementos"])
    async def element_urls(element_id: str, request: Request, session: Session, owner: Owner) -> dict:
        """URLs públicas y vigentes de sus imágenes, para pasarlas como referencias a cualquier modelo (las
        vuelve a subir si caducan pronto; subir no cobra)."""
        element = await get_element_or_404(session, element_id)
        urls = await fresh_element_urls(element, settings.storage_dir, request.app.state.hf.upload)
        await session.commit()
        return {"id": element.id, "mention": f"@{element.name}", "description": element.description,
                "image_urls": urls}  # fmt: skip

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

    async def check_refs(session: AsyncSession, owner: ApiClient, before: dict | None, after: dict) -> None:
        """Lo que un lienzo guarda lo comparte con quien lo abre (`spaces.Share`), así que solo se puede añadir lo
        que quien guarda ya ve: sus generaciones y archivos (con sees_all, los de todos). Lo que ya estaba se
        conserva aunque lo haya puesto otro cliente. Una URL que no es de nadie no se comparte, así que se deja."""
        if owner.sees_all:
            return
        old_jobs, old_urls = graph_refs(before)
        new_jobs, new_urls = graph_refs(after)
        for job_id in sorted(new_jobs - old_jobs):
            try:
                await get_owned_job(session, owner, job_id)
            except ServiceError:
                raise ServiceError(422, "invalid_graph", f"Generation {job_id} is not one of yours") from None
        for url in sorted(new_urls - old_urls):
            if await trusted_media(session, None, url) and not await trusted_media(session, owner, url):
                raise ServiceError(
                    422, "invalid_graph", "A file in the graph is not one of your uploads or generations"
                )

    async def get_owned_space(session: AsyncSession, owner: ApiClient, space_id: str) -> Space:
        space = await session.get(Space, space_id)
        # Como las generaciones: la UI (sees_all) ve también los lienzos que crea un agente por MCP.
        if space is None or (space.owner_id != owner.id and not owner.sees_all):
            raise ServiceError(404, "not_found", "Space not found")
        return space

    @app.get("/v1/spaces", tags=["spaces"])
    async def list_spaces(session: Session, owner: Owner) -> dict:
        query = select(Space) if owner.sees_all else select(Space).where(Space.owner_id == owner.id)
        rows = await session.scalars(query.order_by(Space.updated_at.desc()))
        return {"spaces": [s.summary() for s in rows]}

    @app.post("/v1/spaces", tags=["spaces"], status_code=201)
    async def create_space(body: SpaceIn, session: Session, owner: Owner, catalog: CatalogDep) -> dict:
        graph = valid_graph(body.graph, catalog) if body.graph is not None else empty_graph()
        await check_refs(session, owner, None, graph)
        space = Space(owner_id=owner.id, title=body.title, graph=graph)
        session.add(space)
        await session.commit()
        return space.as_dict()

    @app.get("/v1/flows", tags=["spaces"])
    async def list_flows(session: Session, owner: Owner) -> dict:
        """Spaces publicados como flujo, con sus entradas (tipo y etiqueta) para pedirlas en un formulario."""
        rows = await session.scalars(
            select(Space)
            .where(Space.flow.is_not(None), true() if owner.sees_all else Space.owner_id == owner.id)
            .order_by(Space.updated_at.desc())
        )
        flows = []
        for sp in rows:
            if not sp.flow:
                continue
            nodes = {n["id"]: n for n in sp.graph["nodes"]}
            inputs = [
                {**i, "type": nodes[i["node_id"]]["type"],
                 "kind": "text" if nodes[i["node_id"]]["type"] == "text" else nodes[i["node_id"]]["data"].get("kind")}
                for i in sp.flow["inputs"] if i["node_id"] in nodes
            ]  # fmt: skip
            flows.append(
                {"space_id": sp.id, "version": sp.version, "cover": sp.cover, **sp.flow, "inputs": inputs}
            )
        return {"flows": flows}

    @app.get("/v1/spaces/{space_id}", tags=["spaces"])
    async def get_space(space_id: str, session: Session, owner: Owner) -> dict:
        return (await get_owned_space(session, owner, space_id)).as_dict()

    @app.put("/v1/spaces/{space_id}", tags=["spaces"])
    async def update_space(
        space_id: str, body: SpaceUpdate, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Guarda título, grafo o portada. Exige la versión leída: si otra pestaña guardó antes, 409 con la
        versión vigente, para que el cliente recargue en vez de pisar cambios."""
        current = await get_owned_space(session, owner, space_id)
        values: dict[str, Any] = {"version": Space.version + 1, "updated_at": utcnow()}
        if body.title is not None:
            values["title"] = body.title
        graph = current.graph
        if body.graph is not None:
            values["graph"] = graph = valid_graph(body.graph, catalog)
            await check_refs(session, owner, current.graph, graph)
            # Un flujo publicado sigue al grafo: pierde las entradas cuyos nodos se borraron.
            values["flow"] = flow_for_graph(current.flow, graph)
        if "flow" in body.model_fields_set:
            try:
                values["flow"] = check_flow(body.flow, graph) if body.flow is not None else None
            except GraphError as exc:
                raise ServiceError(422, "invalid_flow", str(exc)) from None
        if "cover" in body.model_fields_set:
            values["cover"] = await valid_cover(session, owner, body.cover)
        result = await session.execute(
            update(Space)
            .where(Space.id == space_id, Space.owner_id == current.owner_id, Space.version == body.version)
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

    # --- Supercomputer: chat con un agente que aclara la idea y propone generaciones ---------------

    def chat_view(chat: Chat) -> dict:
        return {**chat.summary(), "messages": sc.visible_messages(chat.messages, chat.proposals)}

    async def get_owned_chat(session: AsyncSession, owner: ApiClient, chat_id: str) -> Chat:
        chat = await session.get(Chat, chat_id)
        if chat is None or (chat.owner_id != owner.id and not owner.sees_all):
            raise ServiceError(404, "not_found", "Chat not found")
        return chat

    # --- Skills de Supercomputer -------------------------------------------------------------------

    def skill_fields(body: SkillIn) -> tuple[str, str, str]:
        if body.skill_md:
            return skill_files.parse_skill_md(body.skill_md)
        return skill_files.check(body.slug or "", body.description or "", body.body or "")

    async def seed_skills(session: AsyncSession, owner: ApiClient) -> None:
        """Instala una vez las skills que trae HF Studio (las que el usuario ya tenga o haya borrado no se tocan)."""
        pending, marker = skill_files.unseeded(settings.storage_dir)
        if not pending:
            return
        builtin = skill_files.builtin()
        existing = set(await session.scalars(select(Skill.slug).where(Skill.slug.in_(pending))))
        for slug in pending:
            if slug not in existing:
                description, text_, files = builtin[slug]
                session.add(
                    Skill(slug=slug, description=description, body=text_, files=files, created_by=owner.id)
                )
        await session.commit()
        skill_files.mark_seeded(marker, pending)

    async def get_skill_or_404(session: AsyncSession, slug: str) -> Skill:
        skill = await session.scalar(select(Skill).where(Skill.slug == slug))
        if skill is None:
            raise ServiceError(404, "skill_not_found", f"Unknown skill /{slug}")
        return skill

    @app.get("/v1/skills", tags=["supercomputer"])
    async def list_skills(session: Session, owner: Owner, full: bool = False) -> dict:
        """Skills de Supercomputer (se llaman con /slug en el chat). Sin `full`, solo nombre y descripción."""
        await seed_skills(session, owner)
        rows = await session.scalars(select(Skill).order_by(Skill.slug))
        return {"skills": [s.out(full) for s in rows]}

    @app.get("/v1/skills/{slug}", tags=["supercomputer"])
    async def get_skill(slug: str, session: Session, _: Owner) -> dict:
        return (await get_skill_or_404(session, slug)).out()

    @app.post("/v1/skills", status_code=201, tags=["supercomputer"])
    async def create_skill(body: SkillIn, session: Session, owner: Owner) -> dict:
        """Crea una skill con `slug`, `description` y `body`, o importando un SKILL.md entero (`skill_md`)."""
        slug, description, text_ = skill_fields(body)
        if await session.scalar(select(Skill.id).where(Skill.slug == slug)):
            raise ServiceError(409, "skill_exists", f"There is already a skill called /{slug}")
        files = skill_files.check_files(body.files)
        skill = Skill(slug=slug, description=description, body=text_, files=files, created_by=owner.id)
        session.add(skill)
        await session.commit()
        return skill.out()

    @app.put("/v1/skills/{slug}", tags=["supercomputer"])
    async def update_skill(slug: str, body: SkillIn, session: Session, _: Owner) -> dict:
        skill = await get_skill_or_404(session, slug)
        new_slug, description, text_ = skill_fields(body)
        if new_slug != slug and await session.scalar(select(Skill.id).where(Skill.slug == new_slug)):
            raise ServiceError(409, "skill_exists", f"There is already a skill called /{new_slug}")
        skill.slug, skill.description, skill.body, skill.updated_at = new_slug, description, text_, utcnow()
        if body.files is not None:
            skill.files = skill_files.check_files(body.files)
        await session.commit()
        return skill.out()

    @app.get("/v1/skills/{slug}/files/{path:path}", tags=["supercomputer"])
    async def get_skill_file(slug: str, path: str, session: Session, _: Owner) -> dict:
        skill = await get_skill_or_404(session, slug)
        if path not in (skill.files or {}):
            raise ServiceError(404, "skill_file_not_found", f"/{slug} has no file {path}")
        return {"path": path, "content": skill.files[path]}

    @app.delete("/v1/skills/{slug}", status_code=204, tags=["supercomputer"])
    async def delete_skill(slug: str, session: Session, _: Owner) -> None:
        await session.delete(await get_skill_or_404(session, slug))
        await session.commit()

    @app.get("/v1/chats", tags=["supercomputer"])
    async def list_chats(session: Session, owner: Owner) -> dict:
        query = select(Chat) if owner.sees_all else select(Chat).where(Chat.owner_id == owner.id)
        rows = await session.scalars(query.order_by(Chat.updated_at.desc()).limit(200))
        return {"available": app.state.assistant_jobs.available, "models": list(CLAUDE_PRICES),
                "default_model": DEFAULT_CLAUDE, "chats": [c.summary() for c in rows]}  # fmt: skip

    @app.post("/v1/chats", tags=["supercomputer"], status_code=201)
    async def create_chat(body: ChatIn, session: Session, owner: Owner) -> dict:
        if body.project_id:
            await get_owned_project(session, owner, body.project_id)
        chat = Chat(owner_id=owner.id, title="New chat", model=body.model, messages=[], proposals={},
                    project_id=body.project_id)  # fmt: skip
        session.add(chat)
        await session.commit()
        return chat_view(chat)

    @app.get("/v1/chats/{chat_id}", tags=["supercomputer"])
    async def get_chat(chat_id: str, session: Session, owner: Owner) -> dict:
        return chat_view(await get_owned_chat(session, owner, chat_id))

    @app.patch("/v1/chats/{chat_id}", tags=["supercomputer"])
    async def update_chat(chat_id: str, body: ChatPatch, session: Session, owner: Owner) -> dict:
        """Cambia el proyecto del chat o el tope de la generación automática (0 la apaga y reinicia lo gastado)."""
        await get_owned_chat(session, owner, chat_id)
        fields = body.model_fields_set
        if "project_id" in fields and body.project_id:
            await get_owned_project(session, owner, body.project_id)
        # Bajo el candado del chat: un cambio de tope no se cruza con una generación automática en curso.
        async with chat_lock(chat_id):
            chat = await session.get(Chat, chat_id, populate_existing=True)
            if chat is None:
                raise ServiceError(404, "not_found", "Chat not found")
            if "project_id" in fields:
                chat.project_id = body.project_id or None
            if "auto_budget_usd" in fields:
                if not body.auto_budget_usd:
                    chat.auto_budget_usd, chat.auto_spent_usd = None, 0.0
                else:
                    chat.auto_budget_usd = body.auto_budget_usd
            await session.commit()
            return chat.summary()

    @app.delete("/v1/chats/{chat_id}", tags=["supercomputer"], status_code=204)
    async def delete_chat(chat_id: str, session: Session, owner: Owner) -> None:
        """Borra la conversación; las generaciones que salieron de ella siguen en el historial."""
        await session.delete(await get_owned_chat(session, owner, chat_id))
        await session.commit()

    @app.post("/v1/chats/{chat_id}/proposals/{proposal_id}/job", tags=["supercomputer"])
    async def link_proposal_job(
        chat_id: str, proposal_id: str, body: ProposalJobIn, session: Session, owner: Owner
    ) -> dict:
        """Anota la generación que el usuario lanzó desde una propuesta: el agente sabrá cómo terminó."""
        await get_owned_chat(session, owner, chat_id)
        await get_owned_job(session, owner, body.job_id)
        async with chat_lock(chat_id):
            chat = await session.get(Chat, chat_id, populate_existing=True)
            if chat is None or proposal_id not in chat.proposals or chat.proposals[proposal_id].get("kind"):
                raise ServiceError(404, "not_found", "Proposal not found")
            proposals = dict(chat.proposals)
            p = proposals[proposal_id]
            jobs = list(dict.fromkeys([*proposal_jobs(p), body.job_id]))
            if len(jobs) > max(1, int(p.get("variations") or 1)):
                raise ServiceError(
                    409, "proposal_complete", "All the generations of this proposal were already launched"
                )
            proposals[proposal_id] = {**p, "job_id": jobs[0], "job_ids": jobs, "reported": None}
            chat.proposals = proposals
            await link_shot_jobs(session, chat.project_id, p, [(jobs.index(body.job_id), body.job_id)])
            await session.commit()
            return proposals[proposal_id]

    def chat_lock(chat_id: str) -> asyncio.Lock:
        locks: dict[str, asyncio.Lock] = app.state.chat_locks
        return locks.setdefault(chat_id, asyncio.Lock())

    def proposal_jobs(p: dict) -> list[str]:
        return list(p.get("job_ids") or ([p["job_id"]] if p.get("job_id") else []))

    @app.post("/v1/chats/{chat_id}/proposals/{proposal_id}/auto", tags=["supercomputer"])
    async def auto_generate_proposal(
        chat_id: str, proposal_id: str, request: Request, session: Session, owner: Owner, catalog: CatalogDep
    ) -> dict:
        """Generación automática: lanza las generaciones que faltan de una propuesta guardada si su compromiso
        total (precio o retención inicial, lo mayor, cotizado aquí) cabe en lo que queda del tope del chat. Todo o
        nada, bajo el candado del chat; cada posición tiene su clave de idempotencia y solo lo creado cuenta contra
        el tope, así que repetir la petición no lanza ni cobra dos veces."""
        await get_owned_chat(session, owner, chat_id)
        async with chat_lock(chat_id):
            chat = await session.get(Chat, chat_id, populate_existing=True)
            if (
                chat is None
                or proposal_id not in (chat.proposals or {})
                or chat.proposals[proposal_id].get("kind")
            ):
                raise ServiceError(404, "not_found", "Proposal not found")
            if not chat.auto_budget_usd:
                raise ServiceError(409, "auto_off", "Auto-generation is off for this chat")
            p = chat.proposals[proposal_id]
            inputs = p.get("inputs") or [p["input"]]
            done = proposal_jobs(p)
            model = check_input(catalog, p["model"], inputs[0])
            pending = []
            for i in range(len(done), len(inputs)):
                plan = await make_plan(request, session, owner, model, inputs[i], {})
                best = plan.best
                if best is None or best.usd is None:
                    raise ServiceError(
                        409, "auto_unknown_price", "This proposal has no known price; generate it by hand"
                    )
                pending.append((i, plan, best.usd, best.reserve_usd))
            commit_usd = round(sum(max(usd, reserve or 0) for _, _, usd, reserve in pending), 4)
            left = round(chat.auto_budget_usd - (chat.auto_spent_usd or 0), 4)
            if commit_usd > left + 1e-9:
                raise ServiceError(
                    409,
                    "auto_budget_exceeded",
                    f"Needs {commit_usd} USD and the chat has {max(left, 0)} USD left",
                )
            jobs, spent, launched = list(done), 0.0, []
            for i, plan, usd, reserve in pending:
                stored, approved_usd, approved_reserve = authorize(plan, usd, reserve, False)
                job, created = await create_generation(
                    session, settings, catalog, owner, p["model"], inputs[i], f"auto:{chat.id}:{proposal_id}:{i}",
                    allow_duplicate=True, plan=stored, max_usd=approved_usd, max_reserve_usd=approved_reserve,
                    commit=False,
                )  # fmt: skip
                if created:
                    job.project_id = chat.project_id
                    spent += max(usd, reserve or 0)
                if job.id not in jobs:
                    jobs.append(job.id)
                launched.append((i, job.id))
            await link_shot_jobs(session, chat.project_id, p, launched)
            proposals = dict(chat.proposals)
            proposals[proposal_id] = {
                **p,
                "job_id": jobs[0] if jobs else None,
                "job_ids": jobs,
                "reported": None,
            }
            chat.proposals = proposals
            chat.auto_spent_usd = round((chat.auto_spent_usd or 0) + spent, 4)
            await session.commit()
        request.app.state.worker.wake()
        return {"proposal": proposals[proposal_id], "auto_spent_usd": chat.auto_spent_usd}

    async def generation_updates(session: AsyncSession, proposals: dict) -> tuple[list[str], dict]:
        """Novedades de las generaciones lanzadas desde propuestas que el agente aún no conoce."""
        lines, changed = [], dict(proposals)
        for pid, p in proposals.items():
            ids = p.get("job_ids") or ([p["job_id"]] if p.get("job_id") else [])
            reported = dict(p.get("reported_jobs") or {})
            if (
                p.get("reported") and ids and ids[0] not in reported
            ):  # chats guardados antes de las variaciones
                reported[ids[0]] = p["reported"]
            for n, job_id in enumerate(ids, 1):
                job = await session.get(Job, job_id)
                if job is None or job.status == reported.get(job_id):
                    continue
                which = f" variation {n}/{len(ids)}" if len(ids) > 1 else ""
                line = f'Proposal "{p.get("title") or pid}"{which} on {p["model"]} (generation {job.id}): {job.status}'
                if job.status == "completed":
                    urls = [o.get("url") for o in job.outputs or [] if o.get("url")]
                    line += ". Outputs: " + ", ".join(urls)
                elif job.error:
                    line += f" ({job.error[:200]})"
                lines.append(line)
                reported[job_id] = job.status
            if reported != (p.get("reported_jobs") or {}):
                changed[pid] = {
                    **p,
                    "reported_jobs": reported,
                    "reported": reported.get(ids[0]) if ids else None,
                }
        return lines, changed

    # --- AI Director: lista de tomas y documentos del proyecto ----------------------------------------

    def take_brief(job: Job | None) -> dict | None:
        """Una generación de una toma en pocas líneas: estado, primera salida y lo que costó."""
        if job is None:
            return None
        body = job_out(job)
        first = body["outputs"][0] if body["outputs"] else {}
        return {"job_id": job.id, "status": job.status, "kind": first.get("kind"), "url": first.get("url"),
                "file_url": first.get("file_url"), "cost_usd": body["cost_usd"]}  # fmt: skip

    async def sync_shots(session: AsyncSession, shots: list[Shot]) -> None:
        """Una toma en `generating` pasa a `review` cuando todas sus tomas terminaron (a `retake` si ninguna salió)."""
        changed = False
        for shot in shots:
            if shot.status != "generating" or not shot.take_job_ids:
                continue
            statuses = list(await session.scalars(select(Job.status).where(Job.id.in_(shot.take_job_ids))))
            if statuses and all(s in TERMINAL for s in statuses):
                shot.status = "review" if "completed" in statuses else "retake"
                shot.updated_at = utcnow()
                changed = True
        if changed:
            await session.commit()

    async def project_shots(session: AsyncSession, project_id: str) -> list[Shot]:
        rows = list(await session.scalars(select(Shot).where(Shot.project_id == project_id)))
        await sync_shots(session, rows)
        return sorted(rows, key=dr.sort_key)

    async def shot_views(session: AsyncSession, shots: list[Shot]) -> list[dict]:
        ids = {j for s in shots for j in [*(s.take_job_ids or []), s.board_job_id, s.selected_job_id] if j}
        jobs = {j.id: j for j in await session.scalars(select(Job).where(Job.id.in_(ids)))} if ids else {}
        views = []
        for s in shots:
            takes = [b for b in (take_brief(jobs.get(j)) for j in s.take_job_ids or []) if b]
            views.append({**s.out(), "takes": takes, "board": take_brief(jobs.get(s.board_job_id or "")),
                          "selected": take_brief(jobs.get(s.selected_job_id or ""))})  # fmt: skip
        return views

    async def link_shot_jobs(
        session: AsyncSession, project_id: str | None, proposal: dict, pairs: list[tuple[int, str]]
    ) -> None:
        """Anota en la toma de cada posición de la propuesta la generación lanzada (sin hacer commit)."""
        links = proposal.get("shots") or []
        if not project_id or not links:
            return
        for index, job_id in pairs:
            link = links[index] if index < len(links) else None
            shot = await session.get(Shot, link["shot_id"]) if link else None
            if shot is None or shot.project_id != project_id:
                continue
            if link.get("role") == "board":
                shot.board_job_id = job_id
                if shot.status in ("planned", "proposed"):
                    shot.status = "boarded"
            else:
                if job_id not in (shot.take_job_ids or []):
                    shot.take_job_ids = [*(shot.take_job_ids or []), job_id]
                shot.status = "generating"
            shot.updated_at = utcnow()

    async def get_owned_shot(session: AsyncSession, owner: ApiClient, shot_id: str) -> Shot:
        shot = await session.get(Shot, shot_id)
        if shot is None:
            raise ServiceError(404, "shot_not_found", "Shot not found")
        await get_owned_project(session, owner, shot.project_id)
        return shot

    async def get_owned_document(
        session: AsyncSession, owner: ApiClient, document_id: str
    ) -> ProjectDocument:
        doc = await session.get(ProjectDocument, document_id)
        if doc is None:
            raise ServiceError(404, "document_not_found", "Document not found")
        await get_owned_project(session, owner, doc.project_id)
        return doc

    async def save_document_version(
        session: AsyncSession, doc: ProjectDocument, base: int, title: str, markdown: str, kind: str, by: str
    ) -> bool:
        """Escribe la versión `base + 1` solo si el documento sigue en `base` (UPDATE condicional, atómico frente a
        otra pestaña, otro chat o el agente) y archiva la versión `base` en el historial, en la misma transacción.
        False si otro guardado ganó: quien llama responde conflicto."""
        old = (doc.title, doc.markdown, doc.updated_by)
        done = await session.execute(
            update(ProjectDocument)
            .where(ProjectDocument.id == doc.id, ProjectDocument.version == base)
            .values(
                title=title,
                markdown=markdown,
                kind=kind,
                updated_by=by,
                version=base + 1,
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if done.rowcount != 1:
            await session.rollback()
            return False
        session.add(ProjectDocumentVersion(document_id=doc.id, version=base, title=old[0], markdown=old[1],
                                           updated_by=old[2]))  # fmt: skip
        await session.commit()
        await session.refresh(doc)
        return True

    async def director_context(session: AsyncSession, project_id: str) -> list[str]:
        """Índice de documentos y resumen de la lista de tomas para el mensaje del agente."""
        docs = list(
            await session.scalars(
                select(ProjectDocument)
                .where(ProjectDocument.project_id == project_id)
                .order_by(ProjectDocument.updated_at.desc())
            )
        )
        statuses = list(await session.scalars(select(Shot.status).where(Shot.project_id == project_id)))
        counts = {s: statuses.count(s) for s in dr.SHOT_STATUSES if s in statuses}
        blocks = [dr.documents_block([d.summary() for d in docs]), dr.shots_block(counts)]
        return [b for b in blocks if b]

    @app.get("/v1/projects/{project_id}/shots", tags=["proyectos"])
    async def list_shots(project_id: str, session: Session, owner: Owner) -> dict:
        """Lista de tomas del proyecto en orden, con sus generaciones (storyboard, tomas y la elegida)."""
        project = await get_owned_project(session, owner, project_id)
        return {"shots": await shot_views(session, await project_shots(session, project.id))}

    @app.patch("/v1/shots/{shot_id}", tags=["proyectos"])
    async def update_shot_route(shot_id: str, body: ShotPatch, session: Session, owner: Owner) -> dict:
        shot = await get_owned_shot(session, owner, shot_id)
        if body.status is not None:
            shot.status = body.status
        if body.notes is not None:
            shot.notes = body.notes
        if body.verdict is not None:
            shot.verdict = body.verdict
        if body.selected_job_id is not None:
            if body.selected_job_id and body.selected_job_id not in (shot.take_job_ids or []):
                raise ServiceError(
                    422, "not_a_take", "The selected take must be one of the shot's generations"
                )
            shot.selected_job_id = body.selected_job_id or None
        shot.updated_at = utcnow()
        await session.commit()
        return (await shot_views(session, [shot]))[0]

    @app.delete("/v1/shots/{shot_id}", tags=["proyectos"], status_code=204)
    async def delete_shot(shot_id: str, session: Session, owner: Owner) -> None:
        """Borra la toma de la lista; sus generaciones siguen en el proyecto."""
        await session.delete(await get_owned_shot(session, owner, shot_id))
        await session.commit()

    @app.get("/v1/projects/{project_id}/documents", tags=["proyectos"])
    async def list_documents(project_id: str, session: Session, owner: Owner) -> dict:
        project = await get_owned_project(session, owner, project_id)
        rows = await session.scalars(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project.id)
            .order_by(ProjectDocument.updated_at.desc())
        )
        return {"documents": [d.summary() for d in rows]}

    @app.post("/v1/projects/{project_id}/documents", tags=["proyectos"], status_code=201)
    async def create_document(project_id: str, body: DocumentIn, session: Session, owner: Owner) -> dict:
        project = await get_owned_project(session, owner, project_id)
        doc = ProjectDocument(project_id=project.id, kind=body.kind, title=body.title.strip(),
                              markdown=body.markdown, updated_by="user")  # fmt: skip
        session.add(doc)
        await session.commit()
        return doc.out()

    @app.get("/v1/documents/{document_id}", tags=["proyectos"])
    async def get_document(document_id: str, session: Session, owner: Owner) -> dict:
        return (await get_owned_document(session, owner, document_id)).out()

    @app.patch("/v1/documents/{document_id}", tags=["proyectos"])
    async def update_document(document_id: str, body: DocumentPatch, session: Session, owner: Owner) -> dict:
        """Guarda un documento: exige la versión leída (si el agente u otra pestaña lo cambió, 409)."""
        doc = await get_owned_document(session, owner, document_id)
        if body.base_version != doc.version:
            raise ServiceError(
                409, "version_conflict", "The document changed; reload it", {"version": doc.version}
            )
        saved = await save_document_version(session, doc, body.base_version, (body.title or doc.title).strip(),
                                            doc.markdown if body.markdown is None else body.markdown,
                                            body.kind or doc.kind, "user")  # fmt: skip
        if not saved:
            await session.refresh(doc)
            raise ServiceError(
                409, "version_conflict", "The document changed; reload it", {"version": doc.version}
            )
        return doc.out()

    @app.delete("/v1/documents/{document_id}", tags=["proyectos"], status_code=204)
    async def delete_document(document_id: str, session: Session, owner: Owner) -> None:
        doc = await get_owned_document(session, owner, document_id)
        await session.execute(
            delete(ProjectDocumentVersion).where(ProjectDocumentVersion.document_id == doc.id)
        )
        await session.delete(doc)
        await session.commit()

    async def output_bytes(session: AsyncSession, owner: ApiClient, source: dict) -> bytes:
        """Imagen de una salida propia para un elemento: la imagen tal cual o un fotograma de un video."""
        job = await get_owned_job(session, owner, str(source.get("job_id") or ""))
        index = int(source.get("output_index") or 0)
        entry = next((f for f in job.files or [] if f["index"] == index), None)
        if job.status != "completed" or entry is None:
            raise ServiceError(404, "not_found", "That output is not available (finished generations only)")
        path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"]
        if not path.is_file():
            raise ServiceError(404, "not_found", "The local copy of that output is missing")
        if entry["kind"] == "video":
            which = "first_frame" if source.get("frame") == "first" else "last_frame"
            path = await derived_file(path, which)
        elif entry["kind"] != "image":
            raise ServiceError(422, "not_an_image", "Elements take images or video frames")
        return path.read_bytes()

    @app.post("/v1/chats/{chat_id}/proposals/{proposal_id}/element", tags=["supercomputer"], status_code=201)
    async def create_proposed_element(
        chat_id: str, proposal_id: str, request: Request, session: Session, owner: Owner
    ) -> dict:
        """Crea el elemento que propuso el agente (`create_element_from_generation`): solo con el clic del usuario."""
        await get_owned_chat(session, owner, chat_id)
        async with chat_lock(chat_id):
            chat = await session.get(Chat, chat_id, populate_existing=True)
            p = (chat.proposals or {}).get(proposal_id) if chat else None
            if p is None or p.get("kind") != "element":
                raise ServiceError(404, "not_found", "Proposal not found")
            if p.get("element_id"):
                raise ServiceError(409, "element_created", "This element was already created")
            images = [(await output_bytes(session, owner, src), "") for src in p["sources"]]
            element = await store_element(
                request, session, owner, p["name"], p["description"], p["category"], images
            )
            chat = await session.get(Chat, chat_id, populate_existing=True)
            proposals = dict(chat.proposals)
            proposals[proposal_id] = {**p, "element_id": element["id"]}
            chat.proposals = proposals
            await session.commit()
        return element

    def director_tools(request: Request, owner: ApiClient, catalog: Catalog, project_id: str | None) -> dict:
        """Herramientas del director para el agente (todas gratis). Las de proyecto exigen que el chat tenga uno."""

        def need_project() -> str:
            if not project_id:
                raise dr.DirectorError(dr.NO_PROJECT)
            return project_id

        def agent_shot(view: dict) -> dict:
            """Una toma como la lee el agente: el plan, el estado y sus generaciones, sin rutas locales."""
            keep = ("id", "scene", "number", "order", "purpose", "shot_size", "duration_s", "screen_direction",
                    "element_ids", "model_id", "params", "prompt", "notes", "status", "verdict",
                    "selected_job_id", "start_frame_url")  # fmt: skip
            out = {
                ("shot_id" if k == "id" else k): view[k]
                for k in keep
                if view.get(k) not in (None, "", [], {})
            }

            def brief(b: dict) -> dict:
                return {k: b[k] for k in ("job_id", "status", "url") if b.get(k)}

            if view.get("board"):
                out["board"] = brief(view["board"])
            if view.get("takes"):
                out["takes"] = [brief(b) for b in view["takes"]]
            return out

        async def upsert_shots(args: dict) -> tuple[dict, None]:
            pid = need_project()
            raw = args.get("shots")
            if not isinstance(raw, list) or not 1 <= len(raw) <= dr.MAX_SHOTS:
                raise dr.DirectorError(f"`shots` takes 1 to {dr.MAX_SHOTS} shots")
            warnings: list[str] = []
            async with app.state.sessions() as s:
                rows = list(await s.scalars(select(Shot).where(Shot.project_id == pid)))
                by_id = {r.id: r for r in rows}
                by_number = {(r.scene, r.number): r for r in rows if r.number}
                touched: list[Shot] = []
                for item in raw:
                    fields = dr.shot_fields(item, partial=True)
                    shot_id = item.get("shot_id") if isinstance(item, dict) else None
                    if shot_id:
                        shot = by_id.get(shot_id)
                        if shot is None:
                            raise dr.DirectorError(f"Unknown shot {shot_id!r}; call get_shot_list")
                    else:
                        key = (fields.get("scene", "1"), fields.get("number"))
                        shot = by_number.get(key) if key[1] else None
                    if fields.get("model_id") and not catalog.get(fields["model_id"]):
                        warnings.append(f"Unknown model {fields['model_id']!r}; use find_models")
                    if shot is None:
                        if len(rows) >= dr.MAX_SHOTS_PER_PROJECT:
                            raise dr.DirectorError(f"A project holds up to {dr.MAX_SHOTS_PER_PROJECT} shots")
                        full = dr.shot_fields(item)
                        full.setdefault("order", 1 + sum(1 for r in rows if r.scene == full["scene"]))
                        shot = Shot(project_id=pid, **full)
                        s.add(shot)
                        rows.append(shot)
                        if shot.number:
                            by_number[(shot.scene, shot.number)] = shot
                    else:
                        for key, value in fields.items():
                            setattr(shot, key, value)
                        shot.updated_at = utcnow()
                    touched.append(shot)
                await s.commit()
                result = {
                    "ok": True,
                    "shots": [
                        {"shot_id": t.id, "scene": t.scene, "number": t.number, "status": t.status}
                        for t in touched
                    ],
                    "note": "Saved in the project's shot list (the user sees it as a table and a storyboard)",
                }
                if warnings:
                    result["warnings"] = warnings
                return result, None

        async def get_shot_list(args: dict) -> tuple[dict, None]:
            pid = need_project()
            async with app.state.sessions() as s:
                views = await shot_views(s, await project_shots(s, pid))
            if isinstance(args.get("scene"), str):
                views = [v for v in views if v["scene"] == args["scene"]]
            if args.get("status") in dr.SHOT_STATUSES:
                views = [v for v in views if v["status"] == args["status"]]
            return {"shots": [agent_shot(v) for v in views], "count": len(views)}, None

        async def update_shot(args: dict) -> tuple[dict, None]:
            pid = need_project()
            fields = dr.shot_fields(args, partial=True)
            async with app.state.sessions() as s:
                shot = await s.get(Shot, str(args.get("shot_id") or ""))
                if shot is None or shot.project_id != pid:
                    raise dr.DirectorError("Unknown shot; call get_shot_list")
                for key in ("selected_job_id", "board_job_id"):
                    job_id = args.get(key)
                    if isinstance(job_id, str) and job_id:
                        await get_owned_job(s, owner, job_id)
                        setattr(shot, key, job_id)
                        if key == "selected_job_id" and job_id not in (shot.take_job_ids or []):
                            shot.take_job_ids = [*(shot.take_job_ids or []), job_id]
                if isinstance(args.get("verdict"), str):
                    shot.verdict = args["verdict"].strip()[:4000]
                for key, value in fields.items():
                    setattr(shot, key, value)
                shot.updated_at = utcnow()
                await s.commit()
                view = (await shot_views(s, [shot]))[0]
            return {"ok": True, "shot": agent_shot(view)}, None

        async def image_of(s: AsyncSession, ref: str) -> tuple[str, dict] | None:
            """Imagen para comparar: la primera de un elemento o la primera salida (o fotograma) de una generación."""
            if ref.startswith("el_"):
                element = await s.get(Element, ref)
                if element is None or not element.images:
                    return None
                path = element_folder(settings.storage_dir, element.id) / element.images[0]["file"]
                data = await dr.small_image(path) if path.is_file() else None
                block = dr.image_block(data) if data else dr.url_block(element.images[0].get("url") or "")
                return f"Element @{element.name}", block
            job = await get_owned_job(s, owner, ref)
            entry = next((f for f in job.files or [] if f["index"] == 0), None)
            path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"] if entry else None
            if path is None or not path.is_file():
                url = next((o.get("url") for o in job.outputs or [] if o.get("kind") == "image"), None)
                return (f"Generation {job.id}", dr.url_block(url)) if url else None
            if entry["kind"] == "video":
                frames, _ = await dr.video_frames(path, 1)
                return (
                    (f"Generation {job.id} (first frame)", dr.image_block(frames[0][1])) if frames else None
                )
            data = await dr.small_image(path)
            return (f"Generation {job.id}", dr.image_block(data)) if data else None

        async def review_generation(args: dict) -> tuple[dict, None]:
            count = args.get("frames") if isinstance(args.get("frames"), int) else 4
            compare = [c for c in args.get("compare_with") or [] if isinstance(c, str)][:4]
            blocks: list[dict] = []
            async with app.state.sessions() as s:
                job = await get_owned_job(s, owner, str(args.get("job_id") or ""))
                if job.status != "completed":
                    return {
                        "error": f"Generation {job.id} is {job.status}; review it once it is completed"
                    }, None
                info: dict = {"job_id": job.id, "model": job.model, "input": job.input, "outputs": []}
                files = {f["index"]: f for f in job.files or []}
                for i, out in enumerate((job.outputs or [])[:4]):
                    entry = files.get(i)
                    path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"] if entry else None
                    local = path is not None and path.is_file()
                    item: dict = {"index": i, "kind": out.get("kind"), "url": out.get("url")}
                    if out.get("kind") == "video" and local:
                        frames, length = await dr.video_frames(path, count)
                        item["duration_s"] = round(length, 2) if length else None
                        item["has_audio"] = await has_audio(str(path))
                        item["frames_at_s"] = [t for t, _ in frames]
                        for t, data in frames:
                            blocks.append({"type": "text", "text": f"Output {i + 1}, frame at {t:.2f}s:"})
                            blocks.append(dr.image_block(data))
                        info["outputs"].append(item)
                        break  # un video llena el cupo de imágenes
                    if out.get("kind") == "image":
                        data = await dr.small_image(path) if local else None
                        blocks.append({"type": "text", "text": f"Output {i + 1}:"})
                        blocks.append(dr.image_block(data) if data else dr.url_block(out["url"]))
                    elif not local:
                        item["note"] = "No local copy to extract frames from"
                    info["outputs"].append(item)
                for ref in compare:
                    try:
                        found = await image_of(s, ref)
                    except ServiceError:
                        found = None
                    if found:
                        blocks.append({"type": "text", "text": f"For comparison, {found[0]}:"})
                        blocks.append(found[1])
                    else:
                        info.setdefault("not_found", []).append(ref)
            info["images"] = sum(1 for b in blocks if b["type"] == "image")
            return {**info, "_blocks": blocks}, None

        async def save_document(args: dict) -> tuple[dict, None]:
            pid = need_project()
            kind, title, markdown = args.get("kind"), args.get("title"), args.get("markdown")
            if kind not in dr.DOC_KINDS:
                raise dr.DirectorError(f"`kind` must be one of {', '.join(dr.DOC_KINDS)}")
            if not isinstance(title, str) or not title.strip() or not isinstance(markdown, str):
                raise dr.DirectorError("`title` and `markdown` are required")
            if len(markdown) > dr.MAX_DOCUMENT:
                raise dr.DirectorError(f"A document is limited to {dr.MAX_DOCUMENT:,} characters")
            async with app.state.sessions() as s:
                doc_id = args.get("document_id")
                if doc_id:
                    doc = await s.get(ProjectDocument, str(doc_id))
                    if doc is None or doc.project_id != pid:
                        raise dr.DirectorError("Unknown document; call list_documents")
                    if args.get("base_version") != doc.version:
                        return {"error": f"The document is at version {doc.version} (the user may have edited "
                                         "it): read_document again and merge before saving",
                                "version": doc.version}, None  # fmt: skip
                    if not await save_document_version(s, doc, doc.version, title.strip()[:120], markdown, kind,
                                                       "agent"):  # fmt: skip
                        await s.refresh(doc)
                        return {"error": f"The document is at version {doc.version} (it changed meanwhile): "
                                         "read_document again and merge before saving",
                                "version": doc.version}, None  # fmt: skip
                    return {"ok": True, "document_id": doc.id, "version": doc.version,
                            "note": "Saved in the project's Documents"}, None  # fmt: skip
                else:
                    doc = ProjectDocument(project_id=pid, kind=kind, title=title.strip()[:120], markdown=markdown,
                                          updated_by="agent")  # fmt: skip
                    s.add(doc)
                await s.commit()
                return {"ok": True, "document_id": doc.id, "version": doc.version,
                        "note": "Saved in the project's Documents"}, None  # fmt: skip

        async def read_document(args: dict) -> tuple[dict, None]:
            pid = need_project()
            async with app.state.sessions() as s:
                doc = await s.get(ProjectDocument, str(args.get("document_id") or ""))
                if doc is None or doc.project_id != pid:
                    raise dr.DirectorError("Unknown document; call list_documents")
                return doc.out(), None

        async def list_documents_tool(args: dict) -> tuple[dict, None]:
            pid = need_project()
            query = select(ProjectDocument).where(ProjectDocument.project_id == pid)
            if args.get("kind") in dr.DOC_KINDS:
                query = query.where(ProjectDocument.kind == args["kind"])
            async with app.state.sessions() as s:
                rows = await s.scalars(query.order_by(ProjectDocument.updated_at.desc()))
                return {"documents": [d.summary() for d in rows]}, None

        async def update_project_brief(args: dict) -> tuple[dict, None]:
            pid = need_project()
            section, markdown = args.get("section"), args.get("markdown")
            mode = "append" if args.get("mode") == "append" else "replace"
            if section not in dr.BRIEF_SECTIONS or not isinstance(markdown, str) or not markdown.strip():
                raise dr.DirectorError(
                    f"`section` ({', '.join(dr.BRIEF_SECTIONS)}) and `markdown` are required"
                )
            async with app.state.sessions() as s:
                project = await s.get(Project, pid)
                if project is None:
                    raise dr.DirectorError(dr.NO_PROJECT)
                brief = dr.replace_section(project.brief or projects.brief_template(project.name), section,
                                           markdown[:8000], mode)  # fmt: skip
                if len(brief) > 50_000:
                    raise dr.DirectorError("The brief would pass 50,000 characters; keep it short")
                project.brief, project.updated_at = brief, utcnow()
                await s.commit()
            return {"ok": True, "section": section, "mode": mode, "brief_chars": len(brief)}, None

        async def chain_shot(args: dict) -> tuple[dict, None]:
            which = "first_frame" if args.get("which") == "first" else "last_frame"
            async with app.state.sessions() as s:
                job = await get_owned_job(s, owner, str(args.get("from_job_id") or ""))
                video = next((f for f in job.files or [] if f["kind"] == "video"), None)
                if video is None:
                    raise dr.DirectorError("That generation has no finished video output")
                frame = await fresh_output(s, owner, job.id, video["index"], which)
                shot = None
                if args.get("to_shot_id"):
                    pid = need_project()
                    shot = await s.get(Shot, str(args["to_shot_id"]))
                    if shot is None or shot.project_id != pid:
                        raise dr.DirectorError("Unknown shot; call get_shot_list")
                    shot.start_frame_url, shot.updated_at = frame["url"], utcnow()
                    await s.commit()
                path = Path(settings.storage_dir) / "outputs" / job.id / video["name"]
                small = await dr.small_image(await derived_file(path, which))
            result = {"ok": True, "image_url": frame["url"], "which": which.split("_")[0],
                      "note": "Pass image_url as the start frame or first image reference of the next shot"}  # fmt: skip
            if shot is not None:
                result["shot_id"] = shot.id
            if small:
                result["_blocks"] = [dr.image_block(small)]
            return result, None

        async def estimate_shot_list(args: dict) -> tuple[dict, None]:
            pid = need_project()
            takes = args.get("takes_per_shot")
            takes = float(takes) if isinstance(takes, int | float) and 1 <= takes <= 5 else 1.5
            ids = [i for i in args.get("shot_ids") or [] if isinstance(i, str)]
            async with app.state.sessions() as s:
                shots = [x for x in await project_shots(s, pid) if x.status != "cut"]
                if ids:
                    shots = [x for x in shots if x.id in ids]
                if isinstance(args.get("scene"), str):
                    shots = [x for x in shots if x.scene == args["scene"]]
                lines, total, unknown = [], 0.0, 0
                for shot in shots:
                    line: dict = {"shot_id": shot.id, "number": shot.number, "model_id": shot.model_id}
                    model = catalog.get(shot.model_id or "")
                    if not model or not shot.prompt:
                        line["error"] = "Needs model_id and prompt"
                        unknown += 1
                    else:
                        arguments = dr.shot_input(shot.out())
                        try:
                            if found := catalog.validate(
                                model["id"], fill_placeholders(model["input_schema"], arguments)[0]
                            ):
                                raise dr.DirectorError(str(found)[:300])
                            body = estimate_body(await make_plan(request, s, owner, model, arguments, {}))
                            line.update(
                                usd=body.get("usd"), kind=body.get("kind"), provider=body.get("provider")
                            )
                            if body.get("usd") is None:
                                unknown += 1
                            else:
                                total += body["usd"]
                        except (ServiceError, dr.DirectorError) as exc:
                            line["error"] = str(exc)[:300]
                            unknown += 1
                    lines.append(line)
                spent = 0.0
                rows = await s.execute(
                    select(Job.plan, Job.plan_index).where(Job.project_id == pid, Job.status == "completed")
                )
                for plan, index in rows.tuples():
                    option = plan[index] if plan and index < len(plan) else {}
                    spent += option.get("usd") or 0
            return {
                "shots": lines, "total_usd": round(total, 4), "takes_per_shot": takes,
                "total_with_retakes_usd": round(total * takes, 4), "unpriced_shots": unknown,
                "project_spent_usd": round(spent, 4),
                "note": "Storyboard frames are not included; a cheaper alternative is 480p or a Seedance 2.5 Draft",
            }, None  # fmt: skip

        async def create_element_from_generation(args: dict) -> tuple[dict, dict | None]:
            name = check_name(str(args.get("name") or ""))
            category = args.get("category") if args.get("category") in ELEMENT_CATEGORIES else "other"
            description = str(args.get("description") or "").strip()[:500]
            sources = args.get("sources")
            if not description:
                raise dr.DirectorError("`description` is required")
            if not isinstance(sources, list) or not MIN_IMAGES <= len(sources) <= MAX_IMAGES:
                raise dr.DirectorError(f"`sources` takes {MIN_IMAGES} to {MAX_IMAGES} items")
            clean, previews = [], []
            async with app.state.sessions() as s:
                if await s.scalar(select(Element.id).where(Element.name == name)):
                    raise dr.DirectorError(f"There is already an element called @{name}; pick another name")
                for src in sources:
                    if not isinstance(src, dict):
                        raise dr.DirectorError("Each source is an object with job_id")
                    job = await get_owned_job(s, owner, str(src.get("job_id") or ""))
                    index = src.get("output_index") if isinstance(src.get("output_index"), int) else 0
                    out = (job.outputs or [])[index] if index < len(job.outputs or []) else None
                    if job.status != "completed" or out is None:
                        raise dr.DirectorError(f"Generation {job.id} has no finished output {index}")
                    if out.get("kind") not in ("image", "video"):
                        raise dr.DirectorError("Elements take images or video frames")
                    frame = (src.get("frame") if src.get("frame") in ("first", "last") else "last") if out[
                        "kind"] == "video" else None  # fmt: skip
                    clean.append(
                        {"job_id": job.id, "output_index": index, **({"frame": frame} if frame else {})}
                    )
                    previews.append({"url": out.get("url"), "kind": out["kind"], "frame": frame})
            proposal = {"kind": "element", "title": f"@{name}", "name": name, "category": category,
                        "description": description, "sources": clean, "previews": previews, "element_id": None}  # fmt: skip
            note = ("Shown to the user as a card with a Create button; the element exists only after they click it. "
                    "Do not cite it until then.")  # fmt: skip
            return {"ok": True, "note": note}, proposal

        tools = {
            "upsert_shots": upsert_shots, "get_shot_list": get_shot_list, "update_shot": update_shot,
            "review_generation": review_generation, "save_document": save_document, "read_document": read_document,
            "list_documents": list_documents_tool, "update_project_brief": update_project_brief,
            "chain_shot": chain_shot, "estimate_shot_list": estimate_shot_list,
            "create_element_from_generation": create_element_from_generation,
        }  # fmt: skip

        def safe(fn):
            async def run(args: dict) -> tuple[dict, dict | None]:
                try:
                    return await fn(args)
                except (dr.DirectorError, ServiceError, ElementError) as exc:
                    return {"error": str(exc)[:500]}, None

            return run

        return {name: safe(fn) for name, fn in tools.items()}

    def chat_toolbox(
        request: Request, owner: ApiClient, catalog: Catalog, project_id: str | None = None
    ) -> sc.Toolbox:
        async def price(model: dict, arguments: dict) -> dict:
            return estimate_body(await request.app.state.router.plan(model, arguments, {}))

        async def find_models(task: str, output: str | None, limit: int) -> dict:
            found = await recommend(price, catalog, task, limit, output)
            return {"understood": found["understood"], "models": [
                {"id": m["id"], "title": m["title"], "output": m["output"], "capabilities": m["capabilities"],
                 "standard_input": m["standard_input"], "usd": m["estimate"].get("usd"),
                 "price_kind": m["estimate"].get("kind"), "provider": m.get("provider"),
                 "available": m["estimate"].get("usd") is not None or m["estimate"].get("kind") != "unavailable"}
                for m in found["models"]
            ]}  # fmt: skip

        async def get_model_info(model_id: str) -> dict:
            model = catalog.get(model_id)
            if not model or model["output"] not in ("video", "image"):
                return {"error": f"Unknown model {model_id!r}; use find_models"}
            return model_out(model, full=True)

        async def propose(
            model_id: str,
            arguments: dict | None,
            title: str,
            variations: int = 1,
            items: list[dict] | None = None,
            links: list[dict | None] | None = None,
        ) -> tuple[dict, dict | None]:
            """Una tarjeta: una generación, N variaciones de la misma entrada o varias piezas (`items`), cada
            una validada y cotizada; el precio de la tarjeta es la suma."""
            model = catalog.get(model_id)
            if not model or model["output"] not in ("video", "image"):
                return {"error": f"Unknown model {model_id!r}; use find_models"}, None
            if items:
                inputs = [i["input"] for i in items]
                labels = [i.get("title") or f"{n}" for n, i in enumerate(items, 1)]
            else:
                inputs = sc.variation_inputs(model["input_schema"], arguments or {}, variations)
                labels = []
            errors, quotes = {}, []
            async with app.state.sessions() as s:
                for n, args in enumerate(inputs, 1):
                    filled, _ = fill_placeholders(model["input_schema"], args)
                    if found := catalog.validate(model["id"], filled):
                        errors[f"item {n}"] = found
                        continue
                    try:
                        quotes.append(estimate_body(await make_plan(request, s, owner, model, args, {})))
                    except ServiceError as exc:
                        errors[f"item {n}"] = exc.message
                    if not items:
                        quotes *= len(inputs)  # variaciones: misma entrada (salvo la semilla), mismo precio
                        break
            if errors:
                return {"errors": errors if items else next(iter(errors.values()))}, None
            if links:
                if not project_id:
                    return {"error": dr.NO_PROJECT}, None
                async with app.state.sessions() as s:
                    wanted = {link["shot_id"] for link in links if link}
                    found = {x.id: x for x in await s.scalars(select(Shot).where(Shot.id.in_(wanted)))}
                    missing = sorted(i for i in wanted if i not in found or found[i].project_id != project_id)
                    if missing:
                        return {"error": f"Unknown shot ids {missing}; call get_shot_list"}, None
                    for link in links:
                        shot = found[link["shot_id"]] if link else None
                        if (
                            shot
                            and link["role"] == "take"
                            and shot.status in ("planned", "boarded", "retake")
                        ):
                            shot.status, shot.updated_at = "proposed", utcnow()
                    await s.commit()
            usds = [q.get("usd") for q in quotes]
            reserves = [q.get("reserve_usd") or 0 for q in quotes]
            kinds = [q.get("kind") for q in quotes]
            brief = {
                "usd": round(sum(usds), 4) if None not in usds else None,
                "kind": next((k for k in ("unavailable", "formula", "approx") if k in kinds), kinds[0]),
                "provider": quotes[0].get("provider"),
                "reserve_usd": round(sum(reserves), 4) if any(reserves) else None,
                "missing": sorted({m for q in quotes for m in q.get("missing") or []}),
            }
            if len(inputs) > 1:
                brief["unit_usd"] = usds[0] if len(set(usds)) == 1 else None
            proposal = {"model": model["id"], "model_title": model["title"], "output": model["output"],
                        "title": title, "input": inputs[0], "inputs": inputs, "labels": labels,
                        "variations": len(inputs), "estimate": brief, "job_id": None, "job_ids": []}  # fmt: skip
            if links:
                proposal["shots"] = list(links)
            note = "Shown to the user as one card with a Generate button"
            if len(inputs) > 1:
                note += f" that launches all {len(inputs)} generations at once (total price shown)"
            return {"ok": True, "price": brief, "generations": len(inputs), "note": note}, proposal

        async def list_elements() -> dict:
            async with app.state.sessions() as s:
                rows = await s.scalars(
                    select(Element)
                    .where(Element.deleted_at.is_(None))
                    .order_by(Element.created_at.desc())
                    .limit(50)
                )
                out = []
                for e in rows:
                    try:
                        urls = await fresh_element_urls(e, settings.storage_dir, request.app.state.hf.upload)
                    except (OSError, ProviderError):
                        urls = []  # sin copia local o sin subida: el agente aún puede citarlo en Kling
                    out.append({"id": e.id, "name": e.name, "mention": f"@{e.name}",
                                "category": e.category or "other", "description": e.description,
                                "image_urls": urls})  # fmt: skip
                await s.commit()  # guarda las URLs renovadas
                return {"elements": out}

        async def list_skills_tool() -> dict:
            async with app.state.sessions() as s:
                rows = await s.scalars(select(Skill).order_by(Skill.slug))
                return {"skills": [{"name": r.slug, "description": r.description} for r in rows]}

        async def use_skill(name: str) -> dict:
            async with app.state.sessions() as s:
                skill = await s.scalar(select(Skill).where(Skill.slug == name))
            if skill is None:
                return {"error": f"Unknown skill {name!r}; call list_skills"}
            return {"name": skill.slug, "instructions": skill.body, "files": sorted(skill.files or {})}

        async def read_skill_file(name: str, path: str) -> dict:
            async with app.state.sessions() as s:
                skill = await s.scalar(select(Skill).where(Skill.slug == name))
            if skill is None:
                return {"error": f"Unknown skill {name!r}; call list_skills"}
            content = (skill.files or {}).get(path.strip().lstrip("./"))
            if content is None:
                return {"error": f"/{name} has no file {path!r}", "files": sorted(skill.files or {})}
            return {"name": skill.slug, "path": path, "content": content}

        return sc.Toolbox(
            find_models=find_models, get_model=get_model_info, propose=propose, list_elements=list_elements,
            list_skills=list_skills_tool, use_skill=use_skill, read_skill_file=read_skill_file,
            director=director_tools(request, owner, catalog, project_id),
        )  # fmt: skip

    @app.post("/v1/chats/{chat_id}/messages", tags=["supercomputer"])
    async def send_chat_message(
        chat_id: str,
        body: ChatMessageIn,
        request: Request,
        session: Session,
        owner: Owner,
        catalog: CatalogDep,
    ) -> StreamingResponse:
        """Envía un mensaje y responde en streaming (text/event-stream): eventos `text`, `tool`, `proposal`,
        `usage`, `error` y al final `done` con el chat completo. Cobra solo la API de Claude, nunca créditos de
        generación: las propuestas se generan desde la UI con su cotización."""
        jobs = app.state.assistant_jobs
        if not jobs.available:
            raise ServiceError(
                503, "anthropic_not_configured", "Set ANTHROPIC_API_KEY in .env to use Supercomputer"
            )
        chat = await get_owned_chat(session, owner, chat_id)
        busy: set[str] = app.state.chats_busy
        if chat.id in busy:
            raise ServiceError(409, "chat_busy", "This chat is still answering")
        for a in [*body.attachments, *body.refs]:
            if not await trusted_media(session, owner, a.url):
                raise ServiceError(
                    422, "untrusted_source", "Attach files from /v1/uploads or your generations"
                )
        updates, proposals = await generation_updates(session, chat.proposals)
        model = body.model or chat.model
        now, timezone = sc.studio_time(body.timezone)
        await seed_skills(session, owner)
        known = set(await session.scalars(select(Skill.slug)))
        called = skill_files.invoked(body.text, known)
        bodies = {r.slug: (r.body, sorted(r.files or {}))
                  for r in await session.scalars(select(Skill).where(Skill.slug.in_(called)))}  # fmt: skip
        project = await session.get(Project, chat.project_id) if chat.project_id else None
        context = [projects.brief_block(project.name, project.brief)] if project else []
        if project:
            context += await director_context(session, project.id)
        if chat.auto_budget_usd:
            left = max(0.0, chat.auto_budget_usd - (chat.auto_spent_usd or 0))
            context.append(sc.auto_note(left))
        user_msg = {"role": "user", "content": sc.user_content(
            body.text, body.mode, [a.model_dump() for a in body.attachments], updates, now,
            [(slug, *bodies[slug]) for slug in called if slug in bodies],
            [d.model_dump() for d in body.documents], context, [r.model_dump() for r in body.refs])}  # fmt: skip
        history = sc.with_user_turn(sc.strip_images(chat.messages), user_msg)
        first = not chat.messages
        chat_key, owner_id, project_key = chat.id, owner.id, chat.project_id
        busy.add(chat_key)

        async def save(turn: sc.Turn) -> Chat | None:
            async with chat_lock(chat_key), app.state.sessions() as s:
                row = await s.get(Chat, chat_key)
                if row is None:
                    return None
                row.messages = sc.strip_images([*history, *turn.messages])
                # Sobre lo vigente: los vínculos hechos mientras Claude respondía se conservan; del inicio del turno
                # solo se trae lo que el agente ya sabe de cada generación.
                merged = dict(row.proposals or {})
                for pid, p in proposals.items():
                    if pid in merged:
                        reported = {
                            **(merged[pid].get("reported_jobs") or {}),
                            **(p.get("reported_jobs") or {}),
                        }
                        ids = proposal_jobs(merged[pid])
                        merged[pid] = {**merged[pid], "reported_jobs": reported,
                                       "reported": reported.get(ids[0]) if ids else None}  # fmt: skip
                row.proposals = {**merged, **{p["tool_use_id"]: p for p in turn.proposals}}
                row.cost_usd = (row.cost_usd or 0) + turn.cost_usd
                row.model = model
                row.updated_at = utcnow()
                if first:
                    row.title = sc.chat_title(body.text)
                await s.commit()
                return row

        async def events() -> AsyncIterator[bytes]:
            turn = sc.Turn()
            client = anthropic.AsyncAnthropic(
                api_key=jobs.api_key,
                base_url=settings.secret("ANTHROPIC_BASE_URL") or None,
                http_client=jobs.http_client_factory() if jobs.http_client_factory else None,
            )
            toolbox = chat_toolbox(
                request, SimpleNamespace(id=owner_id, sees_all=owner.sees_all), catalog, project_key
            )
            try:
                async for event in sc.run_turn(
                    client,
                    model,
                    body.effort,
                    history,
                    toolbox,
                    turn,
                    body.timezone if timezone == body.timezone else None,
                ):
                    yield sc.sse(event)
            except anthropic.APIStatusError as exc:
                turn.error = f"Claude API error {exc.status_code}: {exc.message}"
            except anthropic.APIConnectionError:
                turn.error = "Could not reach the Claude API"
            finally:
                try:
                    row = await asyncio.shield(save(turn))
                finally:
                    busy.discard(chat_key)
                    await client.close()
            if turn.error:
                yield sc.sse({"type": "error", "message": turn.error})
            if row is not None:
                yield sc.sse({"type": "done", "chat": chat_view(row)})

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

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

        async def trusted(
            session: AsyncSession, owner: ApiClient, url: str, share: Share | None = None
        ) -> bool:
            return await trusted_media(session, owner, url, share)

        async def output_url(
            session: AsyncSession,
            owner: ApiClient,
            job_id: str,
            derive: str | None = None,
            share: Share | None = None,
        ) -> str:
            try:
                return (await fresh_output(session, owner, job_id, 0, derive, share))["url"]
            except ServiceError as exc:
                raise NodeInputError(f"A connected step has no usable output ({exc.message})") from None

        async def output_text(
            session: AsyncSession, owner: ApiClient, job_id: str, share: Share | None = None
        ) -> str:
            """Texto de un Assistant terminado (su copia local), para el prompt del paso siguiente."""
            job = await get_owned_job(session, owner, job_id, share)
            entry = next((f for f in job.files or [] if f.get("kind") == "text"), None)
            path = Path(settings.storage_dir) / "outputs" / job.id / entry["name"] if entry else None
            if job.status != "completed" or path is None or not path.is_file():
                raise NodeInputError("A connected step has no text output")
            return path.read_text(encoding="utf-8")

        def schema(model_id: str) -> dict | None:
            model = get_catalog().get(model_id)
            return model["input_schema"] if model else None

        def output_of(model_id: str) -> str | None:
            model = get_catalog().get(model_id)
            return model["output"] if model else None

        return Hooks(plan, create, output_url, trusted, schema, output_of, app.state.worker.wake, output_text)

    async def estimate_run(
        session: AsyncSession, owner: ApiClient, graph: dict, order: list[str], share: Share | None = None
    ) -> dict:
        """Cotiza cada paso con lo que hay hoy en el lienzo. Un paso que depende de otro de la corrida sin salida
        todavía se cotiza al llegar (`later`); si entonces no cabe en el tope, la corrida se pausa."""
        hooks = app.state.space_runner.hooks
        nodes = {n["id"]: n for n in graph["nodes"]}
        items, total, reserve_total = [], 0.0, 0.0
        for step in order:
            node_id, index = split_step(step)  # un elemento de un lote (Lista) es un paso propio
            model_id = nodes[node_id]["data"]["model"]
            item: dict[str, Any] = {"node_id": step, "model": model_id}
            in_run = step_deps(graph, order, step)
            try:
                arguments = await resolve_input(
                    graph, node_id, hooks.schema(model_id) or {}, hooks.output_of,
                    lambda src: selected_run(nodes[src]["data"]),
                    lambda job_id, derive=None: hooks.output_url(session, owner, job_id, derive, share),
                    index,
                    lambda job_id: hooks.output_text(session, owner, job_id, share),
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
        if run is None or (run.owner_id != owner.id and not owner.sees_all) or run.space_id != space_id:
            raise ServiceError(404, "not_found", "Run not found")
        return run

    @app.post("/v1/spaces/{space_id}/runs", tags=["spaces"])
    async def create_run(
        space_id: str,
        body: RunIn,
        session: Session,
        owner: Owner,
        idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
    ) -> JSONResponse:
        """Corre un nodo y lo que depende de él, o todo el lienzo, en el servidor. Primero `dry_run` (precio de
        cada paso y total); luego la misma petición con `max_total_usd`, el tope que aprobó el usuario.
        Con `Idempotency-Key`, repetirla (p. ej. tras perder la respuesta) devuelve la misma corrida, aunque ya
        haya terminado; con otra petición, 409."""
        owner_id = owner.id  # valor propio: un rollback expira los objetos del ORM (revisión 65)
        # Sin entradas de flujo, la huella es la misma de la fase 3a: una clave de antes de actualizar sigue
        # recuperando su corrida (revisión 69). Con entradas, forman parte de la identidad.
        fields = [space_id, body.mode, body.node_id, body.version, body.max_total_usd]
        request_hash = hashlib.sha256(
            (
                json.dumps(fields)
                if body.inputs is None
                else json.dumps([*fields, body.inputs], sort_keys=True)
            ).encode()
        ).hexdigest()

        async def same_request() -> JSONResponse | None:
            """La corrida que ya arrancó esta misma Idempotency-Key (o 409 si fue otra petición)."""
            if not idempotency_key or body.dry_run:
                return None
            same = await session.scalar(
                select(SpaceRun).where(
                    SpaceRun.owner_id == owner_id, SpaceRun.idempotency_key == idempotency_key
                )
            )
            if same is None:
                return None
            if same.request_hash != request_hash:
                raise ServiceError(
                    409, "idempotency_conflict", "This Idempotency-Key was already used for a different run"
                )
            return JSONResponse({**same.as_dict(), "deduplicated": True}, status_code=200)

        if found := await same_request():
            return found
        space = await get_owned_space(session, owner, space_id)
        if body.version != space.version:
            raise ServiceError(
                409, "space_changed", "Save the space before running it", {"version": space.version}
            )
        try:
            graph = space.graph
            if body.inputs is not None:
                # Un flujo corre sobre una copia del lienzo con sus entradas; el Space no cambia.
                if not space.flow:
                    raise NodeInputError("This space is not published as a flow")
                try:
                    graph = valid_graph(apply_inputs(space.graph, space.flow, body.inputs), get_catalog())
                except GraphError as exc:
                    raise NodeInputError(str(exc)) from None
            order = run_steps(graph, body.mode, body.node_id, app.state.space_runner.hooks.output_of)
        except NodeInputError as exc:
            raise ServiceError(422, "invalid_run", str(exc)) from None
        if not order:
            raise ServiceError(422, "nothing_to_run", "There are no generation nodes to run")
        if body.dry_run:
            # Lo que comparte el lienzo guardado (no las entradas de un flujo, que llegan en la petición).
            return JSONResponse(await estimate_run(session, owner, graph, order, Share.of(space.graph)))
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
            if (
                found := await same_request()
            ):  # la misma petición se coló entre la primera comprobación y esta
                return found
            raise ServiceError(
                409, "run_active", "This space already has a run in progress", {"run_id": active}
            )
        run = SpaceRun(
            space_id=space.id, owner_id=owner.id, mode=body.mode, start_node=body.node_id, graph=graph,
            order=order, nodes={i: {"status": "pending"} for i in order}, max_total_usd=body.max_total_usd,
            idempotency_key=idempotency_key, request_hash=request_hash if idempotency_key else None,
        )  # fmt: skip
        session.add(run)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if found := await same_request():  # la misma petición, a la vez: gana la primera
                return found
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
            # Aceptar un precio desconocido vale para el resto de la corrida: una lista de 9 imágenes del mismo
            # modelo no debe pedir 9 aprobaciones. El tope sigue mandando sobre lo que sí tiene precio.
            nodes = {k: dict(v) for k, v in run.nodes.items()}
            for step, state in nodes.items():
                if step == pause["node"] or state.get("status") == "pending":
                    state["accept_unknown"] = True
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

    @app.get("/v1/factory", tags=["content factory"])
    async def factory_info(_: Owner, lang: str = Query("es", pattern=r"^[a-z]{2}$")) -> dict:
        """Content Factory: estilos, plantillas de escena y qué hace falta para escribir guiones y renderizar."""
        from .factory_script import LAYOUTS

        return {
            "model": "hf-studio/content-factory",
            "styles": factory_styles(lang),
            "layouts": list(LAYOUTS),
            "max_episodes": MAX_EPISODES,
            "renderer": {"available": renderer_problem() is None, "reason": renderer_problem()},
            "scripts": {"available": app.state.assistant_jobs.available, "model": DEFAULT_CLAUDE},
            "elevenlabs": app.state.eleven.configured,
        }

    def factory_script_max(body: FactoryScriptIn) -> float:
        if body.style not in FACTORY_STYLES:
            raise ServiceError(422, "unknown_style", f"Unknown style: {body.style}")
        return factory_max_cost(body.topic, body.duration_seconds, body.episodes, body.language, body.style)

    @app.post("/v1/factory/scripts/estimate", tags=["content factory"])
    async def factory_scripts_estimate(body: FactoryScriptIn, _: Owner) -> dict:
        """Lo máximo que puede costar escribir ese guion con Claude (no llama a Claude). Se aprueba pasándolo como
        `max_usd` a /v1/factory/scripts."""
        return {"max_usd": factory_script_max(body), "model": DEFAULT_CLAUDE,
                "available": app.state.assistant_jobs.available}  # fmt: skip

    @app.post("/v1/factory/scripts", tags=["content factory"])
    async def factory_scripts(
        body: FactoryScriptIn,
        owner: Owner,
        idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
    ) -> dict:
        """Claude escribe el guion (uno por episodio, con arco y cliffhanger en series). Exige el tope aprobado
        (`max_usd` ≥ el de /estimate); devuelve el coste real (`cost_usd`). Repetir la petición con la misma
        Idempotency-Key devuelve el mismo guion sin volver a llamar a Claude."""
        jobs = app.state.assistant_jobs
        if not jobs.available:
            raise ServiceError(
                503, "anthropic_not_configured", "Set ANTHROPIC_API_KEY in .env to write scripts"
            )
        cap = factory_script_max(body)
        if body.max_usd is None or body.max_usd + 1e-9 < cap:
            raise ServiceError(
                409, "quote_required", f"Writing this script can cost up to {cap} USD: approve it as max_usd",
                {"max_usd": cap},
            )  # fmt: skip
        cache: dict = app.state.factory_scripts
        key = (owner.id, idempotency_key) if idempotency_key else None
        if key:
            entry = cache.setdefault(key, {"lock": asyncio.Lock(), "result": None, "error": None})
            async with entry["lock"]:
                if entry["result"] is not None:
                    return {**entry["result"], "deduplicated": True}
                if entry["error"] is not None:
                    # Ese intento ya pudo gastar tokens (o quedó incierto): no se repite con la misma clave. Un nuevo
                    # intento es una nueva aprobación con otra clave.
                    status, code, message = entry["error"]
                    raise ServiceError(
                        status, code, f"{message} (already attempted with this Idempotency-Key)"
                    )
                try:
                    result = await run_factory_script(jobs, body)
                except ServiceError as exc:
                    entry["error"] = (exc.status, exc.code, exc.message)
                    raise
                except BaseException as exc:  # también una cancelación: la llamada pudo gastar tokens
                    entry["error"] = (
                        502,
                        "script_uncertain",
                        f"The script request ended unexpectedly: {exc!r}",
                    )
                    raise
                entry["result"] = result
                if len(cache) > 200:  # solo las últimas peticiones: basta para reintentos
                    for old in list(cache)[:50]:
                        cache.pop(old, None)
                return result
        return await run_factory_script(jobs, body)

    async def run_factory_script(jobs, body: FactoryScriptIn) -> dict:
        try:
            return await write_scripts(
                jobs.api_key, body.topic, body.style, body.duration_seconds, body.episodes, body.language,
                base_url=settings.secret("ANTHROPIC_BASE_URL") or None, http_client_factory=jobs.http_client_factory,
            )  # fmt: skip
        except ScriptError as exc:
            raise ServiceError(exc.status, exc.code, exc.message) from None

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

    # --- Crear voces (ElevenLabs): clonar con muestras y diseñar con una descripción -------------

    @app.post("/v1/voice/clone", tags=["voz"], status_code=201)
    async def voice_clone(
        request: Request,
        session: Session,
        owner: Owner,
        name: Annotated[str, Form(min_length=1, max_length=100)],
        consent: Annotated[
            bool, Form(description="La persona dueña de la voz es quien clona o dio su permiso")
        ] = False,
        files: Annotated[list[UploadFile] | None, File(description="Muestras de audio o video")] = None,
        source_generation_ids: Annotated[list[str] | None, Form()] = None,
        source_urls: Annotated[list[str] | None, Form(description="URLs de /v1/uploads")] = None,
        description: Annotated[str | None, Form(max_length=1000)] = None,
        language: Annotated[str, Form(pattern=r"^[a-z]{2}$")] = "es",
        remove_background_noise: Annotated[bool, Form()] = False,
    ) -> dict:
        """Clonación instantánea: crea en la cuenta de ElevenLabs una voz con las muestras (1 a 2 minutos de voz
        limpia es lo ideal). No gasta créditos; ocupa un espacio de voces del plan."""
        if not request.app.state.eleven.configured:
            raise VoiceError(503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env")
        if not consent:
            raise ServiceError(
                422, "consent_required",
                "Confirm that the voice is yours or that its owner allowed cloning it (consent=true)",
            )  # fmt: skip
        with tempfile.TemporaryDirectory(prefix="hfs-clone-in-") as tmp:
            sources: list[str] = []
            for i, upload in enumerate(files or []):
                path = Path(tmp) / f"upload-{i}"
                size = 0
                with path.open("wb") as fh:
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise ServiceError(
                                413,
                                "too_large",
                                f"Maximum {settings.max_upload_bytes // (1024 * 1024)} MB per sample",
                            )
                        fh.write(chunk)
                if size:
                    sources.append(str(path))
            for gid in source_generation_ids or []:
                sources.append(
                    await audio_source(request, session, owner, IsolateIn(source_generation_id=gid))
                )
            for url in source_urls or []:
                sources.append(await audio_source(request, session, owner, IsolateIn(source_url=url)))
            return await clone_voice(
                request.app.state.eleven,
                sources,
                name.strip(),
                description,
                language,
                remove_background_noise,
            )

    @app.post("/v1/voice/design/estimate", tags=["voz"])
    async def voice_design_estimate(body: DesignVoiceIn, request: Request, owner: Owner) -> dict:
        """Costo de diseñar una voz (tres muestras; cobra el texto una vez), con un voice_quote de un solo uso."""
        est = design_estimate(body)
        quotes: dict = request.app.state.voice_quotes
        now = time.monotonic()
        for qid in [q for q, v in quotes.items() if v["expires"] < now]:
            del quotes[qid]
        qid = "dq_" + uuid.uuid4().hex
        digest = input_hash(DESIGN_MODEL, body.model_dump(exclude_none=True, exclude={"voice_quote"}))
        quotes[qid] = {"owner": owner.id, "digest": digest, "seconds": est["units"],
                       "expires": now + VOICE_QUOTE_TTL, "used": False}  # fmt: skip
        return {**est, "text": body.preview_text, "voice_quote": qid}

    @app.post("/v1/voice/design", tags=["voz"])
    async def voice_design(body: DesignVoiceIn, request: Request, owner: Owner) -> dict:
        """Genera tres muestras de la voz descrita (gasta créditos). Escúchalas en /v1/voice/previews/{id} y
        guarda la elegida con /v1/voice/design/save."""
        if not request.app.state.eleven.configured:
            raise VoiceError(503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env")
        digest = input_hash(DESIGN_MODEL, body.model_dump(exclude_none=True, exclude={"voice_quote"}))
        quote = request.app.state.voice_quotes.get(body.voice_quote or "")
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
                "Missing, expired, used or mismatched voice_quote. Quote first (POST /v1/voice/design/estimate)",
            )
        quote["used"] = True
        try:
            async with request.app.state.voice_slots:
                result = await design_voice(
                    request.app.state.eleven, body, Path(settings.storage_dir), owner.id
                )
        except VoiceError as exc:
            if exc.code in ("elevenlabs_network", "elevenlabs_rate_limit"):
                quote["used"] = False  # no llegó a cobrarse: la misma cotización sirve para reintentar
            raise
        est = design_estimate(body)
        return {
            **result,
            "cost_usd": est["usd"],
            "previews": [
                {**p, "preview_url": f"/v1/voice/previews/{p['generated_voice_id']}"}
                for p in result["previews"]
            ],
        }

    @app.get("/v1/voice/previews/{generated_voice_id}", tags=["voz"])
    async def voice_preview(generated_voice_id: str, owner: Owner) -> FileResponse:
        """MP3 de una muestra de diseño de voz de este cliente."""
        path = preview_path(Path(settings.storage_dir), owner.id, generated_voice_id)
        if not path:
            raise ServiceError(404, "not_found", "Voice sample not found")
        return FileResponse(
            path, media_type="audio/mpeg", filename=path.name, content_disposition_type="inline"
        )

    @app.post("/v1/voice/design/save", tags=["voz"], status_code=201)
    async def voice_design_save(body: SaveVoiceIn, request: Request, owner: Owner) -> dict:
        """Guarda en la cuenta la muestra elegida como voz nueva. No gasta créditos."""
        if not preview_path(Path(settings.storage_dir), owner.id, body.generated_voice_id):
            raise ServiceError(404, "not_found", "Design that voice first: the sample is not one of yours")
        return await save_designed_voice(request.app.state.eleven, body)

    @app.delete("/v1/voice/voices/{voice_id}", tags=["voz"])
    async def voice_delete(voice_id: str, request: Request, _: Owner) -> dict:
        """Borra de la cuenta de ElevenLabs una voz clonada o diseñada y libera su espacio. No se puede deshacer."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", voice_id):
            raise ServiceError(422, "invalid_voice", "Invalid voice_id")
        await request.app.state.eleven.delete_voice(voice_id)
        return {"deleted": voice_id}

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
