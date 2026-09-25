"""Worker en proceso: envía trabajos respetando la concurrencia de la cuenta, sondea con backoff
(https://docs.higgsfield.ai/docs/concepts/polling), aplica el timeout y guarda las salidas."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import random
from datetime import timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .audio import SOURCE_KEY, apply_to_files
from .config import Settings
from .db import Job, utcnow
from .elevenlabs_audio import AUDIO_MODELS
from .higgsfield import TERMINAL_STATUSES, HiggsfieldClient, HiggsfieldError, extract_outputs
from .voice import VOICE_MODEL

# Trabajos locales (ElevenLabs): no ocupan concurrencia de Higgsfield.
LOCAL_MODELS = (VOICE_MODEL, *AUDIO_MODELS)

log = logging.getLogger("hf_studio.worker")

MAX_SUBMIT_ATTEMPTS = 5
POLL_BATCH = 25


class Worker:
    def __init__(self, sessions: async_sessionmaker, client: HiggsfieldClient, settings: Settings):
        self.sessions = sessions
        self.client = client
        self.settings = settings
        self._wake = asyncio.Event()
        self._submit_paused_until = utcnow()
        self._task: asyncio.Task | None = None

    def wake(self) -> None:
        self._wake.set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="hf-studio-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        await self.recover()
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Fallo en el ciclo del worker")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=1.0)
            except TimeoutError:
                pass
            self._wake.clear()

    async def recover(self) -> None:
        """Un envío interrumpido por un reinicio pudo llegar a Higgsfield: no se repite a ciegas."""
        async with self.sessions() as session:
            stuck = (await session.scalars(select(Job).where(Job.status == "submitting"))).all()
            for job in stuck:
                self._finish(
                    job,
                    "failed",
                    "submission_ambiguous",
                    "The server restarted during submission; check your Higgsfield history before retrying",
                )
            await session.commit()

    async def tick(self) -> None:
        await self.expire()
        await self.submit_pending()
        await self.poll_due()

    # --- Envío ---------------------------------------------------------------------------------

    async def submit_pending(self) -> None:
        if utcnow() < self._submit_paused_until:
            return
        async with self.sessions() as session:
            in_flight = await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status.in_(("submitting", "queued", "in_progress")), Job.model.not_in(LOCAL_MODELS)
                )
            )
            slots = self.settings.hf_max_concurrency - (in_flight or 0)
            if slots <= 0:
                return
            now = utcnow()
            ids = (
                await session.scalars(
                    select(Job.id)
                    .where(
                        Job.status == "pending", (Job.next_check_at.is_(None)) | (Job.next_check_at <= now)
                    )
                    .order_by(Job.created_at)
                    .limit(slots)
                )
            ).all()
        for job_id in ids:
            if not await self.submit(job_id):
                break

    async def submit(self, job_id: str) -> bool:
        """Envía un trabajo. Devuelve False si hay que dejar de enviar en este ciclo."""
        async with self.sessions() as session:
            # Reclamo atómico: evita envíos dobles si corren varios procesos.
            claimed = await session.execute(
                update(Job).where(Job.id == job_id, Job.status == "pending").values(status="submitting")
            )
            await session.commit()
            if claimed.rowcount != 1:
                return True
            job = await session.get(Job, job_id)
            job.attempts += 1
            webhook = None
            if self.settings.public_base_url:
                base = self.settings.public_base_url.rstrip("/")
                webhook = f"{base}/v1/webhooks/higgsfield/{job.id}?token={quote(job.webhook_token)}"
            try:
                result = await self.client.submit(job.model, job.input, webhook)
            except HiggsfieldError as exc:
                keep_going = self._handle_submit_error(job, exc)
                await session.commit()
                return keep_going
            job.hf_request_id = result["request_id"]
            job.status_url = result.get("status_url")
            job.cancel_url = result.get("cancel_url")
            job.correlation_id = result.get("_correlation_id")
            job.status = (
                result.get("status") if result.get("status") in ("queued", "in_progress") else "queued"
            )
            job.submitted_at = utcnow()
            job.poll_delay = 2.0
            job.next_check_at = job.submitted_at + timedelta(seconds=2)
            job.error = job.error_kind = None
            await session.commit()
            log.info("Trabajo %s enviado como %s", job.id, job.hf_request_id)
            if result.get("status") in TERMINAL_STATUSES:
                await self.apply_status(session, job, result)
                await session.commit()
            return True

    def _handle_submit_error(self, job: Job, exc: HiggsfieldError) -> bool:
        job.correlation_id = exc.correlation_id or job.correlation_id
        if exc.kind == "concurrency":
            # Límite de la cuenta: el trabajo vuelve a la cola y se pausan los envíos un rato.
            job.status, job.attempts = "pending", job.attempts - 1
            self._submit_paused_until = utcnow() + timedelta(seconds=10 + random.uniform(0, 5))
            return False
        if exc.retryable and job.attempts < MAX_SUBMIT_ATTEMPTS:
            job.status = "pending"
            job.error, job.error_kind = exc.message, exc.kind
            job.next_check_at = utcnow() + timedelta(
                seconds=min(2**job.attempts * 2, 60) + random.uniform(0, 1)
            )
            return exc.kind != "unavailable"
        kind = "submission_ambiguous" if exc.kind == "ambiguous" else exc.kind
        message = exc.message
        if exc.kind == "ambiguous":
            message += "; not retried automatically to avoid a duplicate generation and charge"
        elif exc.kind == "auth":
            message = (
                "Invalid Higgsfield credentials on the server (HF_API_KEY); run `hf-studio check-credentials`"
            )
        self._finish(job, "failed", kind, message)
        return exc.kind != "auth"

    # --- Sondeo --------------------------------------------------------------------------------

    async def poll_due(self) -> None:
        async with self.sessions() as session:
            jobs = (
                await session.scalars(
                    select(Job)
                    .where(Job.status.in_(("queued", "in_progress")), Job.next_check_at <= utcnow())
                    .order_by(Job.next_check_at)
                    .limit(POLL_BATCH)
                )
            ).all()
            for job in jobs:
                await self.refresh(session, job)
                await session.commit()

    async def refresh(self, session: AsyncSession, job: Job) -> None:
        """Consulta el estado autoritativo en Higgsfield y lo aplica al trabajo."""
        if not job.hf_request_id:
            return
        try:
            result = await self.client.status(job.hf_request_id, job.status_url)
        except HiggsfieldError as exc:
            if exc.kind == "not_found":
                self._finish(
                    job, "failed", "not_found", "Higgsfield does not recognize this request for this account"
                )
            else:
                # 5xx, red o credenciales: se sigue sondeando con backoff exponencial.
                job.attempts += 1
                wait = 60 if exc.kind == "auth" else min(2 ** min(job.attempts, 6), 60)
                job.next_check_at = utcnow() + timedelta(seconds=wait + random.uniform(0, 1))
                log.warning("Sondeo de %s falló (%s): %s", job.id, exc.kind, exc.message)
            return
        await self.apply_status(session, job, result)

    async def apply_status(self, session: AsyncSession, job: Job, result: dict) -> None:
        status = result.get("status")
        if status in TERMINAL_STATUSES:
            if job.status in TERMINAL_STATUSES and job.status != "timed_out":
                return  # webhook duplicado o sondeo tardío
            job.outputs = extract_outputs(result)
            error = result.get("error")
            if status == "nsfw":
                error = error or "Content moderation rejected the input or output (not charged)"
            # Primero la copia local y después el estado final: quien vea `completed` ya tiene
            # `file_url`. Un fallo de descarga no bloquea (queda la URL remota).
            if status == "completed" and self.settings.download_outputs:
                await self.store_outputs(job)
            self._finish(job, status, None if status == "completed" else status, error)
            return
        if status in ("queued", "in_progress"):
            job.status = status
            job.attempts = 0
            job.next_check_at = utcnow() + timedelta(seconds=job.poll_delay + random.uniform(0, 0.5))
            job.poll_delay = min(job.poll_delay * 1.5, 10.0)

    async def store_outputs(self, job: Job) -> None:
        """Copia las salidas a almacenamiento propio: Higgsfield las garantiza solo 7 días."""
        files = []
        for i, out in enumerate(job.outputs):
            suffix = PurePosixPath(urlparse(out["url"]).path).suffix or (
                mimetypes.guess_extension(out.get("content_type") or "") or ""
            )
            name = f"{i}-{out['kind']}{suffix}"
            dest = Path(self.settings.storage_dir) / "outputs" / job.id / name
            try:
                size, content_type = await self.client.download(out["url"], dest)
            except (
                httpx.HTTPError,
                OSError,
            ) as exc:  # la salida remota sigue disponible; no se falla el trabajo
                log.warning("No se pudo guardar %s de %s: %s", out["url"], job.id, exc)
                continue
            files.append(
                {"name": name, "kind": out["kind"], "size": size, "content_type": content_type, "index": i}
            )
        source = job.input.get(SOURCE_KEY)
        if job.keep_source_audio and isinstance(source, str):
            files = await apply_to_files(files, Path(self.settings.storage_dir) / "outputs" / job.id, source)
        job.files = files

    # --- Timeout -------------------------------------------------------------------------------

    async def expire(self) -> None:
        limit = utcnow() - timedelta(seconds=self.settings.job_timeout_seconds)
        async with self.sessions() as session:
            jobs = (
                await session.scalars(
                    select(Job).where(
                        Job.status.in_(("pending", "queued", "in_progress")), Job.created_at < limit
                    )
                )
            ).all()
            for job in jobs:
                remote = (
                    " The request may still finish at Higgsfield; a late webhook will update it."
                    if job.hf_request_id
                    else ""
                )
                self._finish(
                    job, "timed_out", "timeout", f"Exceeded {self.settings.job_timeout_seconds}s.{remote}"
                )
            await session.commit()

    @staticmethod
    def _finish(job: Job, status: str, kind: str | None, error: str | None) -> None:
        job.status = status
        job.error_kind = kind
        job.error = error
        job.finished_at = utcnow()
        job.next_check_at = None
