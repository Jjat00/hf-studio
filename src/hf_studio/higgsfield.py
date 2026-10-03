"""Cliente REST mínimo de Higgsfield (https://docs.higgsfield.ai).

Se usa REST directo en vez del SDK porque el servidor necesita controlar cada fase: el POST de
generación no se reintenta nunca tras un timeout ambiguo (la API no acepta clave de idempotencia),
el sondeo lo gobierna el worker con estado persistido y los webhooks se piden por query param.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .providers.base import KeyCheck, Polled, Provider, ProviderError, Submitted

TERMINAL_STATUSES = {"completed", "failed", "nsfw", "canceled"}
UPLOAD_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "audio/wav",
    "audio/x-wav",
    "video/mp4",
}


class HiggsfieldError(ProviderError):
    """Error de la API clasificado según https://docs.higgsfield.ai/docs/concepts/errors."""

    def __init__(self, kind: str, message: str, status: int | None = None, correlation_id: str | None = None):
        super().__init__(kind, message, status, correlation_id, provider="higgsfield")


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text[:500] or response.reason_phrase
    if isinstance(detail, list):
        return "; ".join(
            f"{'.'.join(str(p) for p in d.get('loc', [])[1:])}: {d.get('msg')}"
            if isinstance(d, dict)
            else str(d)
            for d in detail
        )
    return str(detail or response.reason_phrase)


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    status, message = response.status_code, _detail(response)
    if status == 400 and "concurrent" in message.lower():
        # La API no publica un código propio para esto; el texto solo decide un reintento, nunca un fallo.
        kind = "concurrency"
    else:
        kind = {400: "bad_request", 401: "auth", 403: "credits", 404: "not_found", 422: "validation"}.get(
            status, "unavailable" if status in (423, 503) else "server" if status >= 500 else "bad_request"
        )
    raise HiggsfieldError(kind, message, status, response.headers.get("x-correlation-id"))


class HiggsfieldClient(Provider):
    """Proveedor Higgsfield. Es obligatorio: además de generar, guarda los medios de entrada
    (subir no cobra créditos) y sus URLs públicas las leen los demás proveedores."""

    name = "higgsfield"
    title = "Higgsfield"
    env_var = "HF_API_KEY"
    base_url = "https://api.higgsfield.ai"
    signup_url = "https://higgsfield.ai"
    key_url = "https://console.higgsfield.ai"
    billing_url = "https://console.higgsfield.ai"
    docs_url = "https://docs.higgsfield.ai"
    required = True
    blurb = "Required: stores your input files (free) and generates every model, including its own (Soul…)."

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(settings, transport)
        self.base_url = settings.hf_base_url.rstrip("/")
        auth = f"Key {settings.hf_credential}"
        timeout = httpx.Timeout(30.0, connect=10.0)
        self._api = httpx.AsyncClient(
            base_url=self.base_url, headers={"Authorization": auth}, timeout=timeout, transport=transport
        )

    @classmethod
    def key_from(cls, settings: Settings) -> str:
        return settings.hf_credential

    async def aclose(self) -> None:
        await self._api.aclose()
        await super().aclose()

    # --- Contrato de proveedor -----------------------------------------------------------------

    async def check_key(self) -> KeyCheck:
        if not self.configured:
            return KeyCheck(False, message="Missing HF_API_KEY")
        try:
            ok = await self.check_credentials()
        except httpx.TransportError as exc:
            return KeyCheck(None, message=f"Could not reach Higgsfield ({type(exc).__name__})")
        except HiggsfieldError as exc:
            return KeyCheck(None, message=exc.message)
        # La API no expone el saldo; cotizar y subir no lo necesitan.
        return KeyCheck(ok, message="" if ok else "Invalid key (401)")

    async def submit_job(
        self, model: str, arguments: dict[str, Any], webhook_url: str | None = None
    ) -> Submitted:
        result = await self.submit(model, arguments, webhook_url)
        status = result.get("status")
        return Submitted(
            request_id=result["request_id"],
            status=status if status in ("queued", "in_progress", *TERMINAL_STATUSES) else "queued",
            status_url=result.get("status_url"),
            cancel_url=result.get("cancel_url"),
            correlation_id=result.get("_correlation_id"),
            raw=result,
            polled=polled(result) if status in TERMINAL_STATUSES else None,
        )

    async def poll_job(self, request_id: str, status_url: str | None = None) -> Polled:
        return polled(await self.status(request_id, status_url))

    async def cancel_job(self, request_id: str, cancel_url: str | None = None) -> None:
        await self.cancel(request_id, cancel_url)

    # --- API de Higgsfield ---------------------------------------------------------------------

    def _own_url(self, url: str | None, fallback: str) -> str:
        """Usa la URL que devolvió la API, pero solo si apunta a la API (no filtrar credenciales)."""
        return url if url and url.startswith(self.base_url + "/") else self.base_url + fallback

    async def submit(self, model: str, arguments: dict[str, Any], webhook_url: str | None = None) -> dict:
        params = {"hf_webhook": webhook_url} if webhook_url else None
        try:
            response = await self._api.post(f"/{model}", json=arguments, params=params)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise HiggsfieldError("network", f"Could not connect to Higgsfield: {exc}") from exc
        except httpx.TransportError as exc:
            # La petición pudo llegar: reintentarla podría duplicar la generación y el cobro.
            raise HiggsfieldError("ambiguous", f"Submission got no response ({type(exc).__name__})") from exc
        _raise_for(response)
        return {**response.json(), "_correlation_id": response.headers.get("x-correlation-id")}

    async def status(self, request_id: str, status_url: str | None = None) -> dict:
        url = self._own_url(status_url, f"/requests/{quote(request_id)}/status")
        try:
            response = await self._api.get(url)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Network error while checking status: {exc}") from exc
        _raise_for(response)
        return response.json()

    async def check_credentials(self) -> bool:
        """Comprueba la clave sin gastar créditos: el estado de una solicitud inexistente
        responde 404 con credenciales válidas y 401 con inválidas."""
        response = await self._api.get("/requests/00000000-0000-0000-0000-000000000000/status")
        if response.status_code == 401:
            return False
        if response.status_code == 404:
            return True
        _raise_for(response)
        return True

    async def cancel(self, request_id: str, cancel_url: str | None = None) -> None:
        url = self._own_url(cancel_url, f"/requests/{quote(request_id)}/cancel")
        try:
            response = await self._api.post(url)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Network error while canceling: {exc}") from exc
        if response.status_code == 400:
            raise HiggsfieldError("too_late", "Generation already started and can no longer be canceled", 400)
        _raise_for(response)

    async def estimate(self, model: str, arguments: dict[str, Any]) -> dict:
        try:
            response = await self._api.post(f"/estimate/{model}", json=arguments)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Network error while estimating cost: {exc}") from exc
        _raise_for(response)
        return response.json()

    async def upload(self, data: bytes, content_type: str, attempts: int = 3) -> str:
        """Sube un archivo por URL prefirmada y devuelve su `public_url` para usarla como entrada.

        Reintenta los fallos transitorios (5xx, red): Higgsfield a veces responde 500 a
        `generate-upload-url` durante un minuto. Subir es gratis, así que repetir no cobra nada."""
        for attempt in range(attempts):
            try:
                return await self._upload_once(data, content_type)
            except HiggsfieldError as exc:
                if not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(2**attempt)
        raise AssertionError("unreachable")

    async def _upload_once(self, data: bytes, content_type: str) -> str:
        try:
            response = await self._api.post("/files/generate-upload-url", json={"content_type": content_type})
            _raise_for(response)
            ticket = response.json()
            put = await self._plain.put(
                ticket["upload_url"], content=data, headers=ticket.get("upload_headers") or {}
            )
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Network error while uploading: {exc}") from exc
        if not put.is_success:
            raise HiggsfieldError(
                "server", f"Storage rejected the upload ({put.status_code})", put.status_code
            )
        return ticket["public_url"]


def extract_outputs(result: dict) -> list[dict]:
    """Normaliza `images`, `video`, `audio`, `audios` y artefactos extra (zip, mov, fbx…) a una lista."""
    outputs, seen = [], set()
    skip = {"status", "request_id", "status_url", "cancel_url", "error", "_correlation_id"}
    for key, value in result.items():
        if key in skip:
            continue
        items = value if isinstance(value, list) else [value]
        kind = {"images": "image", "audios": "audio"}.get(key, key)
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"] not in seen:
                seen.add(item["url"])
                outputs.append({"kind": kind, "url": item["url"], "content_type": item.get("content_type")})
    return outputs


def polled(result: dict) -> Polled:
    """Normaliza una respuesta de estado de Higgsfield."""
    status = result.get("status")
    if status in TERMINAL_STATUSES:
        error = result.get("error")
        if status == "nsfw":
            error = error or "Content moderation rejected the input or output (not charged)"
        return Polled(status, extract_outputs(result), error, result)
    return Polled(status if status in ("queued", "in_progress") else "queued", raw=result)
