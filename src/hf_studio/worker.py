"""Worker en proceso: envía cada trabajo a su proveedor respetando la concurrencia de la cuenta, sondea
con backoff (https://docs.higgsfield.ai/docs/concepts/polling), aplica el timeout y guarda las salidas.
Solo habla con el contrato de `providers.base`."""

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
from sqlalchemy.orm.exc import StaleDataError

from .audio import SOURCE_KEY, apply_to_files
from .config import Settings
from .db import Job, utcnow
from .elevenlabs_audio import AUDIO_MODELS
from .media import cached_source
from .providers.base import TERMINAL_STATUSES, Polled, Provider, ProviderError
from .providers.registry import DEFAULT_PROVIDER
from .routing import requote, stale
from .voice import VOICE_MODEL

# Trabajos locales (ElevenLabs): no ocupan concurrencia de los proveedores.
LOCAL_MODELS = (VOICE_MODEL, *AUDIO_MODELS)

log = logging.getLogger("hf_studio.worker")

MAX_SUBMIT_ATTEMPTS = 5
FALLBACK_AFTER_ATTEMPTS = 2  # con otro proveedor disponible, reintentos de un error transitorio
POLL_BATCH = 25


class Worker:
    def __init__(self, sessions: async_sessionmaker, providers: dict[str, Provider], settings: Settings):
        self.sessions = sessions
        self.providers = providers
        self.settings = settings
        self.router = None  # routing.Router, lo pone la API: recotiza opciones viejas antes de enviarlas
        self._wake = asyncio.Event()
        self._submit_paused_until = utcnow()
        self._task: asyncio.Task | None = None

    def provider(self, job: Job) -> Provider:
        name = job.provider or DEFAULT_PROVIDER
        if name not in self.providers:
            raise ProviderError("unsupported", f"Unknown provider {name!r}", provider=name)
        return self.providers[name]

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
        """Un envío interrumpido por un reinicio pudo llegar al proveedor: no se repite a ciegas."""
        async with self.sessions() as session:
            stuck = (await session.scalars(select(Job).where(Job.status == "submitting"))).all()
            for job in stuck:
                self._finish(
                    job,
                    "failed",
                    "submission_ambiguous",
                    "The server restarted during submission; check your provider history before retrying",
                )
            await session.commit()

    async def tick(self) -> None:
        await self.expire()
        await self.submit_pending()
        await self.poll_due()

    # --- Envío ---------------------------------------------------------------------------------

    async def submit_pending(self) -> None:
        """Envía los pendientes. La concurrencia de la cuenta solo limita a Higgsfield; APIMart y KIE
        aceptan muchas tareas a la vez y su límite llega como error `concurrency` (se reintenta)."""
        async with self.sessions() as session:
            in_flight = await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status.in_(("submitting", "queued", "in_progress")),
                    Job.model.not_in(LOCAL_MODELS),
                    Job.provider == DEFAULT_PROVIDER,
                )
            )
            hf_slots = self.settings.hf_max_concurrency - (in_flight or 0)
            now = utcnow()
            rows = (
                await session.execute(
                    select(Job.id, Job.provider)
                    .where(
                        Job.status == "pending", (Job.next_check_at.is_(None)) | (Job.next_check_at <= now)
                    )
                    .order_by(Job.created_at)
                    .limit(POLL_BATCH)
                )
            ).all()
        hf_paused = utcnow() < self._submit_paused_until
        for job_id, provider in rows:
            on_hf = (provider or DEFAULT_PROVIDER) == DEFAULT_PROVIDER
            if on_hf:
                if hf_paused or hf_slots <= 0:
                    continue
                hf_slots -= 1
            if not await self.submit(job_id) and on_hf:
                hf_paused = True

    async def submit(self, job_id: str) -> bool:
        """Envía un trabajo. Devuelve False si hay que dejar de enviar en este ciclo."""
        async with self.sessions() as session:
            # Reclamo atómico: evita envíos dobles si corren varios procesos.
            claimed = await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "pending")
                .values(status="submitting", version=Job.version + 1)
            )
            await session.commit()
            if claimed.rowcount != 1:
                return True
            job = await session.get(Job, job_id)
            if not await self.refresh_quote(job):
                await self.commit(session, job_id)
                return True
            job.attempts += 1
            webhook = self.webhook_url(job)
            model, arguments = self.target(job)
            try:
                result = await self.provider(job).submit_job(model, arguments, webhook)
            except ProviderError as exc:
                keep_going = self._handle_submit_error(job, exc)
                await self.commit(session, job_id)
                return keep_going
            except Exception as exc:  # respuesta imprevista tras el POST: pudo crearse la tarea
                log.exception("Respuesta inesperada al enviar %s a %s", job_id, job.provider)
                error = ProviderError("ambiguous", f"Unexpected answer from {job.provider}: {exc!r}"[:300])
                self._handle_submit_error(job, error)
                await self.commit(session, job_id)
                return True
            job.hf_request_id = result.request_id
            job.status_url = result.status_url
            job.cancel_url = result.cancel_url
            job.correlation_id = result.correlation_id
            job.status = result.status if result.status in ("queued", "in_progress") else "queued"
            job.submitted_at = utcnow()
            job.poll_delay = 2.0
            job.next_check_at = job.submitted_at + timedelta(seconds=2)
            job.error = job.error_kind = None
            if not await self.commit(session, job_id):
                # Nadie más debería tocar un trabajo en `submitting`: si pasa, la tarea remota queda
                # registrada en el log para revisarla a mano (nunca se reenvía).
                log.error("Trabajo %s: tarea %s en %s sin guardar", job_id, result.request_id, job.provider)
                return True
            log.info("Trabajo %s enviado a %s como %s", job.id, job.provider, job.hf_request_id)
            if result.status in TERMINAL_STATUSES:
                final = result.polled or await self.provider(job).poll_job(
                    result.request_id, result.status_url
                )
                await self.apply_polled(session, job, final)
                await self.commit(session, job_id)
            return True

    async def commit(self, session: AsyncSession, job_id: str) -> bool:
        """Guarda si nadie cambió el trabajo desde que se leyó; si lo cambió, descarta esta escritura."""
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            log.info("Trabajo %s cambió mientras se procesaba: se descarta un resultado viejo", job_id)
            return False
        return True

    def webhook_url(self, job: Job) -> str | None:
        if not self.settings.public_base_url:
            return None
        base = self.settings.public_base_url.rstrip("/")
        return (
            f"{base}/v1/webhooks/{job.provider or DEFAULT_PROVIDER}/{job.id}?token={quote(job.webhook_token)}"
        )

    @staticmethod
    def target(job: Job) -> tuple[str, dict]:
        """Modelo y entrada para el proveedor actual: los del plan o, sin plan, los lógicos (Higgsfield)."""
        if job.plan:
            option = job.plan[job.plan_index]
            return option["model"], option["input"]
        return job.model, job.input

    def _handle_submit_error(self, job: Job, exc: ProviderError) -> bool:
        job.correlation_id = exc.correlation_id or job.correlation_id
        on_hf = (job.provider or DEFAULT_PROVIDER) == DEFAULT_PROVIDER
        if exc.kind == "concurrency" and on_hf:
            # Límite de la cuenta: el trabajo vuelve a la cola y se pausan los envíos un rato.
            job.status, job.attempts = "pending", job.attempts - 1
            self._submit_paused_until = utcnow() + timedelta(seconds=10 + random.uniform(0, 5))
            return False
        # Con respaldo disponible se reintenta menos: es mejor otro proveedor que esperar minutos.
        limit = MAX_SUBMIT_ATTEMPTS if not self.has_fallback(job) else FALLBACK_AFTER_ATTEMPTS
        if exc.retryable and job.attempts < limit:
            job.status = "pending"
            job.error, job.error_kind = exc.message, exc.kind
            job.next_check_at = utcnow() + timedelta(
                seconds=min(2**job.attempts * 2, 60) + random.uniform(0, 1)
            )
            return exc.kind != "unavailable"
        if exc.fallback_safe and self.has_fallback(job):
            self.fallback(job, exc.kind, exc.message)
            return True
        kind = "submission_ambiguous" if exc.kind == "ambiguous" else exc.kind
        message = exc.message
        if exc.kind == "ambiguous":
            message += "; not retried automatically to avoid a duplicate generation and charge"
        elif exc.kind == "auth":
            provider = self.providers.get(job.provider or DEFAULT_PROVIDER)
            env_var = provider.env_var if provider else "the provider key"
            title = provider.title if provider else job.provider
            message = f"Invalid {title} credentials on the server ({env_var}); run `hf-studio providers`"
        self._finish(job, "failed", kind, self._with_attempts(job, message))
        return exc.kind != "auth"

    # --- Respaldo entre proveedores --------------------------------------------------------------

    @staticmethod
    def has_fallback(job: Job) -> bool:
        return bool(job.plan) and job.plan_index + 1 < len(job.plan)

    def _title(self, name: str | None) -> str:
        provider = self.providers.get(name or DEFAULT_PROVIDER)
        return provider.title if provider else str(name)

    def fallback(self, job: Job, kind: str | None, message: str | None) -> None:
        """El proveedor actual falló sin cobrar: pasa al siguiente del plan. Corre solo si cuesta lo mismo
        o menos que lo aprobado (`max_usd`); si cuesta más o no tiene precio, espera aprobación. En los dos
        casos el trabajo apunta ya al siguiente (`plan_index`); el envío recotiza si la cotización es vieja."""
        failed = self._title(job.provider)
        job.attempts_log = [
            *(job.attempts_log or []),
            {"provider": job.provider, "request_id": job.hf_request_id, "error_kind": kind, "error": message,
             "at": utcnow().isoformat()},
        ]  # fmt: skip
        job.plan_index += 1
        option = job.plan[job.plan_index]
        job.provider = option["provider"]
        job.hf_request_id = job.status_url = job.cancel_url = None
        job.outputs, job.attempts, job.next_check_at = [], 0, None
        title = self._title(option["provider"])
        if self.within_budget(job, option):
            job.status, job.error_kind = "pending", None
            job.error = f"{failed} failed ({message}); trying {title}"
            log.info("Trabajo %s: %s falló (%s), pasa a %s", job.id, failed, kind, option["provider"])
            return
        self.ask_approval(job, f"{failed} failed ({message}).")

    @staticmethod
    def within_budget(job: Job, option: dict) -> bool:
        """Precio final dentro de lo aprobado y, si el proveedor retiene más al empezar, esa retención
        también aprobada (revisión 29)."""
        usd, reserve = option.get("usd"), option.get("reserve_usd")
        # Un tope numérico manda siempre que el precio se conozca; aceptar un desconocido solo cubre el precio
        # desconocido o, si se aceptó sin tope, cualquiera. Vale solo para la opción aceptada (revisiones 30-31).
        accepted = bool(option.get("unknown_accepted"))
        if usd is None:
            price_ok = accepted
        elif job.max_usd is not None:
            price_ok = usd <= job.max_usd + 1e-9
        else:
            price_ok = accepted
        reserve_ok = reserve is None or (
            job.max_reserve_usd is not None and reserve <= job.max_reserve_usd + 1e-9
        )
        return price_ok and reserve_ok

    def ask_approval(self, job: Job, reason: str) -> None:
        option = job.plan[job.plan_index]
        usd = option.get("usd")
        price = f"{usd:.4f} USD" if usd is not None else "an unknown price"
        if option.get("reserve_usd") is not None:
            price += f" (it first holds {option['reserve_usd']:.4f} USD and refunds the difference)"
        approved = f"{job.max_usd:.4f} USD" if job.max_usd is not None else "no price"
        job.status, job.error_kind, job.next_check_at = "awaiting_approval", "needs_approval", None
        job.error = (
            f"{reason} {self._title(option['provider'])} can do it for {price} (you approved {approved}). "
            f"Approve with POST /v1/generations/{job.id}/approve or cancel it."
        )

    async def refresh_quote(self, job: Job) -> bool:
        """Antes de enviar una opción cotizada hace más de 15 min, vuelve a cotizarla. False si el precio
        nuevo supera lo aprobado (o ya no hay precio): el trabajo queda esperando aprobación."""
        option = job.plan[job.plan_index] if job.plan else None
        if option is None or self.router is None:
            return True
        model = self.router.catalog.get(job.model)
        if model is None:
            return True
        first_try = job.plan_index == 0 and not job.attempts_log
        if first_try and not option.get("forced") and not option.get("unknown_accepted"):
            return await self.replan(job, model, option)
        provider = self.providers.get(option["provider"])
        # Con tabla local, recotizar es gratis: se hace siempre (una tarifa nueva ya conocida manda). Las
        # cotizaciones remotas (Higgsfield) solo si tienen más de 15 min.
        if not stale(option) and not (provider and provider.has_price_table):
            return True
        fresh = await requote(self.router, model, job.input, option)
        if fresh is None:
            if self.has_fallback(job):
                self.fallback(
                    job, "unavailable", f"{self._title(job.provider)} can no longer run this request"
                )
            else:
                self._finish(job, "failed", "unavailable", "No provider can run this request anymore")
            return False
        plan = list(job.plan)
        plan[job.plan_index] = fresh
        job.plan = plan
        if self.within_budget(job, fresh):
            return True
        self.ask_approval(job, "The price changed since it was quoted.")
        return False

    async def replan(self, job: Job, model: dict, option: dict) -> bool:
        """Primer envío automático: rehace el plan con las tarifas de ahora y elige el más barato que quepa
        en lo aprobado (precio y retención). Si ninguno cabe, pide aprobación del más barato (revisión 30)."""
        plan = (await self.router.plan(model, job.input, option.get("hints") or {})).stored()
        if not plan:
            self._finish(job, "failed", "unavailable", "No provider can run this request anymore")
            return False
        fits = next((i for i, o in enumerate(plan) if self.within_budget(job, o)), None)
        if fits is None:
            job.plan, job.plan_index, job.provider = plan, 0, plan[0]["provider"]
            self.ask_approval(job, "The price changed since it was quoted.")
            return False
        # Las más baratas que no caben quedan fuera: ya no se reintentan como respaldo sin aprobación.
        job.plan, job.plan_index, job.provider = plan[fits:], 0, plan[fits]["provider"]
        return True

    def _with_attempts(self, job: Job, message: str | None) -> str | None:
        if not job.attempts_log:
            return message
        tried = ", ".join(f"{self._title(a['provider'])} ({a.get('error_kind')})" for a in job.attempts_log)
        return f"{message} (also tried: {tried})"

    # --- Sondeo --------------------------------------------------------------------------------

    async def poll_due(self) -> None:
        async with self.sessions() as session:
            ids = (
                await session.scalars(
                    select(Job.id)
                    .where(Job.status.in_(("queued", "in_progress")), Job.next_check_at <= utcnow())
                    .order_by(Job.next_check_at)
                    .limit(POLL_BATCH)
                )
            ).all()
        for job_id in ids:
            # Una sesión por trabajo: un conflicto de versión en uno no deja caducados a los demás.
            async with self.sessions() as session:
                job = await session.get(Job, job_id)
                if job is not None and job.status in ("queued", "in_progress"):
                    await self.refresh(session, job)
                    await self.commit(session, job_id)

    async def refresh(self, session: AsyncSession, job: Job) -> None:
        """Consulta el estado autoritativo en el proveedor y lo aplica al trabajo."""
        if not job.hf_request_id:
            return
        try:
            result = await self.provider(job).poll_job(job.hf_request_id, job.status_url)
        except ProviderError as exc:
            if exc.kind == "not_found":
                self._finish(
                    job,
                    "failed",
                    "not_found",
                    f"{job.provider} does not recognize this request for this account",
                )
            else:
                # 5xx, red o credenciales: se sigue sondeando con backoff exponencial.
                job.attempts += 1
                wait = 60 if exc.kind == "auth" else min(2 ** min(job.attempts, 6), 60)
                job.next_check_at = utcnow() + timedelta(seconds=wait + random.uniform(0, 1))
                log.warning("Sondeo de %s falló (%s): %s", job.id, exc.kind, exc.message)
            return
        await self.apply_polled(session, job, result)

    async def apply_polled(self, session: AsyncSession, job: Job, result: Polled) -> None:
        status = result.status
        if status in TERMINAL_STATUSES:
            if job.status in TERMINAL_STATUSES and job.status != "timed_out":
                return  # webhook duplicado o sondeo tardío
            if status in ("failed", "nsfw") and self.has_fallback(job):
                # Los tres proveedores devuelven lo cobrado por una tarea fallida: se prueba el siguiente.
                self.fallback(job, status, result.error)
                return
            job.outputs = result.outputs
            error = result.error
            # Primero la copia local y después el estado final: quien vea `completed` ya tiene
            # `file_url`. Un fallo de descarga no bloquea (queda la URL remota).
            if status == "completed" and self.settings.download_outputs:
                await self.store_outputs(job)
            if status != "completed":
                error = self._with_attempts(job, error)
            self._finish(job, status, None if status == "completed" else status, error)
            return
        if status in ("queued", "in_progress"):
            job.status = status
            job.attempts = 0
            job.next_check_at = utcnow() + timedelta(seconds=job.poll_delay + random.uniform(0, 0.5))
            job.poll_delay = min(job.poll_delay * 1.5, 10.0)

    async def store_outputs(self, job: Job) -> None:
        """Copia las salidas a almacenamiento propio: los proveedores las guardan de 1 a 14 días."""
        files = []
        for i, out in enumerate(job.outputs):
            suffix = PurePosixPath(urlparse(out["url"]).path).suffix or (
                mimetypes.guess_extension(out.get("content_type") or "") or ""
            )
            name = f"{i}-{out['kind']}{suffix}"
            dest = Path(self.settings.storage_dir) / "outputs" / job.id / name
            try:
                size, content_type = await self.provider(job).download(out["url"], dest)
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
            # ffmpeg solo lee archivos locales: la fuente se descarga antes de forma controlada.
            local = await cached_source(
                source, Path(self.settings.storage_dir), self.providers[DEFAULT_PROVIDER].plain,
                self.settings.max_upload_bytes,
            )  # fmt: skip
            if local is not None:
                files = await apply_to_files(
                    files, Path(self.settings.storage_dir) / "outputs" / job.id, local
                )
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
                    f" The request may still finish at {job.provider}; a late webhook will update it."
                    if job.hf_request_id
                    else ""
                )
                self._finish(
                    job, "timed_out", "timeout", f"Exceeded {self.settings.job_timeout_seconds}s.{remote}"
                )
            try:
                await session.commit()
            except StaleDataError:  # alguno cambió a la vez: el siguiente ciclo lo vuelve a mirar
                await session.rollback()

    @staticmethod
    def _finish(job: Job, status: str, kind: str | None, error: str | None) -> None:
        job.status = status
        job.error_kind = kind
        job.error = error
        job.finished_at = utcnow()
        job.next_check_at = None
