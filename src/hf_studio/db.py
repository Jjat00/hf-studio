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
    Index,
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
    # Una sola copia vigente por dueño y salida reutilizada (revisión 47).
    __table_args__ = (Index("ix_uploads_owner_source", "owner_id", "source", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Solo el servidor lo escribe: `generation:<job>:<índice>` si es la copia de una salida propia (None en
    # las subidas normales; el nombre de archivo lo elige el cliente y no sirve como prueba).
    source: Mapped[str | None] = mapped_column(String(80))


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
    # Retención inicial aprobada (algunos proveedores retienen más de lo que cobran y devuelven la diferencia).
    max_reserve_usd: Mapped[float | None] = mapped_column(Float)
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
    # Oculta del historial y de los listados (se ve solo en /history/hidden); sigue accesible por su id.
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # Marcada como favorita en la biblioteca (filtro «Favoritas»).
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # Proyecto y carpeta de la biblioteca (`projects`, `folders`); sin clave foránea porque se añadieron con
    # ALTER TABLE a bases existentes. Borrar un proyecto o una carpeta deja la generación suelta.
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    folder_id: Mapped[str | None] = mapped_column(String(36), index=True)
    # Bloqueo optimista: cada escritura exige la versión leída. Así un sondeo o webhook tardío no pisa un
    # trabajo que otro proceso ya movió (p. ej. al proveedor de respaldo) y no se envía dos veces.
    # Las actualizaciones directas (`update(Job)`) deben subirla a mano: `version=Job.version + 1`.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Space(Base):
    """Lienzo de nodos (Spaces): un grafo de pasos que se generan uno a uno. El grafo es JSON validado en
    `spaces.check_graph`; las salidas de cada nodo son trabajos (`jobs`) referenciados por su id. `version`
    evita que dos pestañas se pisen: cada guardado exige la versión leída."""

    __tablename__ = "spaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    graph: Mapped[dict] = mapped_column(JSON)
    cover: Mapped[str | None] = mapped_column(Text)
    # Publicado como flujo: {title, description, inputs: [{node_id, label}]} (spaces.check_flow), o None.
    flow: Mapped[dict | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def summary(self) -> dict:
        nodes = self.graph.get("nodes", [])
        return {"id": self.id, "title": self.title, "cover": self.cover, "version": self.version, "flow": self.flow,
                "nodes": len(nodes), "created_at": self.created_at.replace(tzinfo=UTC).isoformat(),
                "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip

    def as_dict(self) -> dict:
        return {**self.summary(), "graph": self.graph}


class Chat(Base):
    """Conversación con Supercomputer. `messages` está en el formato de la API de Claude (con bloques de
    pensamiento) y solo crece por el final; `proposals` guarda cada propuesta de generación por el id de su
    llamada (`tool_use_id`), con la generación que lanzó el usuario (`job_id`) y el último estado que se le contó
    al agente (`reported`)."""

    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(60))
    messages: Mapped[list] = mapped_column(JSON, default=list)
    proposals: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # Proyecto del chat: el agente recibe su brief y lo que se genere desde aquí va a ese proyecto.
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    # Generación automática: las propuestas que quepan en lo que queda del tope se lanzan sin clic.
    auto_budget_usd: Mapped[float | None] = mapped_column(Float)
    auto_spent_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "model": self.model, "cost_usd": round(self.cost_usd, 6),
                "project_id": self.project_id, "auto_budget_usd": self.auto_budget_usd,
                "auto_spent_usd": round(self.auto_spent_usd or 0, 4),
                "created_at": self.created_at.replace(tzinfo=UTC).isoformat(),
                "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip


class Project(Base):
    """Proyecto de la biblioteca (como en Cinema Studio): agrupa generaciones en carpetas y guarda un brief en
    Markdown que Supercomputer lee como contexto en los chats del proyecto."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300), default="")
    brief: Mapped[str] = mapped_column(Text, default="")
    cover: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def out(self, full: bool = False) -> dict:
        data = {"id": self.id, "name": self.name, "description": self.description, "cover": self.cover,
                "created_at": self.created_at.replace(tzinfo=UTC).isoformat(),
                "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip
        return {**data, "brief": self.brief} if full else data


class Shot(Base):
    """Toma de la lista de tomas de un proyecto (AI Director). `take_job_ids` son todas las generaciones de la toma,
    `board_job_id` su fotograma de storyboard y `selected_job_id` la toma buena. Estados: planned, boarded,
    proposed, generating, review, approved, retake y cut."""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    scene: Mapped[str] = mapped_column(String(20), default="1")
    number: Mapped[str] = mapped_column(String(20), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    purpose: Mapped[str] = mapped_column(Text, default="")
    shot_size: Mapped[str | None] = mapped_column(String(20))
    duration_s: Mapped[float | None] = mapped_column(Float)
    screen_direction: Mapped[str] = mapped_column(String(200), default="")
    element_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_id: Mapped[str | None] = mapped_column(String(200))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")
    board_job_id: Mapped[str | None] = mapped_column(String(36))
    take_job_ids: Mapped[list] = mapped_column(JSON, default=list)
    selected_job_id: Mapped[str | None] = mapped_column(String(36))
    verdict: Mapped[str] = mapped_column(Text, default="")
    # Fotograma de entrada que dejó `chain_shot` (último fotograma de la toma anterior): URL pública.
    start_frame_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def out(self) -> dict:
        return {"id": self.id, "project_id": self.project_id, "scene": self.scene, "number": self.number,
                "order": self.order, "purpose": self.purpose, "shot_size": self.shot_size,
                "duration_s": self.duration_s, "screen_direction": self.screen_direction,
                "element_ids": list(self.element_ids or []), "model_id": self.model_id,
                "params": dict(self.params or {}), "prompt": self.prompt, "notes": self.notes,
                "status": self.status, "board_job_id": self.board_job_id,
                "take_job_ids": list(self.take_job_ids or []), "selected_job_id": self.selected_job_id,
                "verdict": self.verdict, "start_frame_url": self.start_frame_url,
                "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip


class ProjectDocument(Base):
    """Documento vivo de un proyecto (tratamiento, desglose, biblia, lookbook…) en Markdown. `version` es un bloqueo
    optimista: guardar exige la versión leída; la anterior pasa a `project_document_versions`."""

    __tablename__ = "project_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="notes")
    title: Mapped[str] = mapped_column(String(120))
    markdown: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(10), default="user")  # agent | user
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def summary(self) -> dict:
        first = next((line.strip("# ").strip() for line in self.markdown.splitlines() if line.strip()), "")
        return {"id": self.id, "project_id": self.project_id, "kind": self.kind, "title": self.title,
                "version": self.version, "updated_by": self.updated_by, "chars": len(self.markdown),
                "excerpt": first[:160], "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip

    def out(self) -> dict:
        return {**self.summary(), "markdown": self.markdown}


class ProjectDocumentVersion(Base):
    """Versión anterior de un documento de proyecto (se guarda una por cada cambio)."""

    __tablename__ = "project_document_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    markdown: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Folder(Base):
    """Carpeta de un proyecto. Borrarla deja sus generaciones en el proyecto, sin carpeta."""

    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def out(self) -> dict:
        return {"id": self.id, "project_id": self.project_id, "name": self.name}


class Skill(Base):
    """Skill de Supercomputer: instrucciones en Markdown con nombre (`slug`, se llama con `/slug`) y una
    descripción que dice cuándo usarla, como un SKILL.md de Claude. Se comparten en toda la instalación."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    # Archivos de referencia de la skill (`{ruta: texto}`, como references/ en un SKILL.md): el agente lee solo el
    # que necesita con `read_skill_file`, en vez de cargarlos todos en cada mensaje.
    files: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("api_clients.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def out(self, full: bool = True) -> dict:
        files = [{"path": k, "chars": len(v)} for k, v in sorted((self.files or {}).items())]
        data = {"slug": self.slug, "description": self.description, "files": files,
                "updated_at": self.updated_at.replace(tzinfo=UTC).isoformat()}  # fmt: skip
        return {**data, "body": self.body} if full else data


class SpaceRun(Base):
    """Corrida de un Space en el servidor: un nodo y lo que depende de él (`downstream`) o todo el lienzo
    (`workflow`). Trabaja sobre una copia del grafo tomada al empezar. `nodes` guarda el estado de cada
    generador: `{id: {status, job_id?, usd?, reserve_usd?, error?, accept_unknown?}}`, con status pending,
    running, done, failed, skipped o canceled. `max_total_usd` es el tope aprobado y `committed_usd` lo ya
    comprometido (el mayor entre el precio y la retención inicial de cada paso enviado). Si un paso no cabe en
    el tope o no tiene precio, la corrida queda en `awaiting_approval` con el motivo en `pause`."""

    __tablename__ = "space_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    space_id: Mapped[str] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_clients.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    start_node: Mapped[str | None] = mapped_column(String(64))
    # Idempotency-Key de quien la arrancó: repetir la petición devuelve esta misma corrida (revisión 64).
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    # Huella inmutable de esa petición (lienzo, versión, modo, nodo y tope original): no cambia al aprobar.
    request_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), index=True, default="running")
    graph: Mapped[dict] = mapped_column(JSON)
    order: Mapped[list] = mapped_column(JSON)
    nodes: Mapped[dict] = mapped_column(JSON)
    max_total_usd: Mapped[float] = mapped_column(Float)
    committed_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pause: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    # El motor y las rutas (aprobar, detener) escriben la misma fila: bloqueo optimista como en `jobs`.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    def as_dict(self) -> dict:
        def iso(dt: datetime | None) -> str | None:
            return dt.replace(tzinfo=UTC).isoformat() if dt else None

        return {"id": self.id, "space_id": self.space_id, "mode": self.mode, "start_node": self.start_node,
                "status": self.status, "order": self.order, "nodes": self.nodes,
                "max_total_usd": self.max_total_usd, "committed_usd": self.committed_usd, "pause": self.pause,
                "error": self.error, "created_at": iso(self.created_at), "finished_at": iso(self.finished_at)}  # fmt: skip


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
        "hidden": "BOOLEAN NOT NULL DEFAULT 0",
        "favorite": "BOOLEAN NOT NULL DEFAULT 0",
        "provider": "VARCHAR(30) NOT NULL DEFAULT 'higgsfield'",
        "plan": "JSON",
        "plan_index": "INTEGER NOT NULL DEFAULT 0",
        "max_usd": "FLOAT",
        "max_reserve_usd": "FLOAT",
        "attempts_log": "JSON",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "project_id": "VARCHAR(36)",
        "folder_id": "VARCHAR(36)",
    },
    "elements": {"deleted_at": "DATETIME", "category": "VARCHAR(20) NOT NULL DEFAULT 'other'"},
    "chats": {
        "project_id": "VARCHAR(36)",
        "auto_budget_usd": "FLOAT",
        "auto_spent_usd": "FLOAT NOT NULL DEFAULT 0",
    },
    "uploads": {"source": "VARCHAR(80)"},
    "space_runs": {"idempotency_key": "VARCHAR(200)", "request_hash": "VARCHAR(64)"},
    "spaces": {"flow": "JSON"},
    "skills": {"files": "JSON"},
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
        # Bases creadas antes de la columna `source`: create_all no añade índices a tablas existentes.
        await conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_uploads_owner_source ON uploads (owner_id, source)")
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_space_runs_key ON space_runs (owner_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
        )
        # Una sola corrida activa por Space, también frente a dos peticiones simultáneas.
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_space_runs_active ON space_runs (space_id) "
                "WHERE status IN ('running', 'awaiting_approval')"
            )
        )


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


class Element(Base):
    """Elemento de referencia (personaje, lugar, prop): un nombre que se cita con `@nombre`, una descripción y
    de 1 a 4 imágenes. En Kling 3.0 (APIMart y KIE) va por su id en `elements` y necesita 2 o más; en el resto
    de modelos sus imágenes entran como referencias. Las imágenes viven en local
    (`storage_dir/elements/<id>/`); `images[].url` es su copia en Higgsfield, que caduca a los ~7 días y se
    renueva antes de usarla (`elements.fresh_urls`). Se comparten entre todos los clientes de la instalación."""

    __tablename__ = "elements"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # el_ + 12 hex
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str] = mapped_column(Text)
    # character, location, prop u other: con qué pestaña sale en Elementos y cómo lo presenta el agente.
    category: Mapped[str] = mapped_column(String(20), default="other", server_default=text("'other'"))
    images: Mapped[list] = mapped_column(JSON)  # [{file, content_type, url}]
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(ForeignKey("api_clients.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # Borrado lógico: deja de ofrecerse, pero sus imágenes siguen hasta que no lo use ningún trabajo activo.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
