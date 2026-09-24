"""Cliente REST mínimo de Higgsfield (https://docs.higgsfield.ai).

Se usa REST directo en vez del SDK porque el servidor necesita controlar cada fase: el POST de
generación no se reintenta nunca tras un timeout ambiguo (la API no acepta clave de idempotencia),
el sondeo lo gobierna el worker con estado persistido y los webhooks se piden por query param.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings

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


class HiggsfieldError(Exception):
    """Error de la API clasificado según https://docs.higgsfield.ai/docs/concepts/errors."""

    def __init__(self, kind: str, message: str, status: int | None = None, correlation_id: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.correlation_id = correlation_id

    @property
    def retryable(self) -> bool:
        return self.kind in {"concurrency", "unavailable", "server", "network"}


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


class HiggsfieldClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = settings.hf_base_url.rstrip("/")
        auth = f"Key {settings.hf_api_key_id}:{settings.hf_api_key_secret.get_secret_value()}"
        timeout = httpx.Timeout(30.0, connect=10.0)
        self._api = httpx.AsyncClient(
            base_url=self.base_url, headers={"Authorization": auth}, timeout=timeout, transport=transport
        )
        # Sin credenciales: sube a URLs prefirmadas y descarga salidas de la CDN.
        self._plain = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), transport=transport)

    async def aclose(self) -> None:
        await self._api.aclose()
        await self._plain.aclose()

    def _own_url(self, url: str | None, fallback: str) -> str:
        """Usa la URL que devolvió la API, pero solo si apunta a la API (no filtrar credenciales)."""
        return url if url and url.startswith(self.base_url + "/") else self.base_url + fallback

    async def submit(self, model: str, arguments: dict[str, Any], webhook_url: str | None = None) -> dict:
        params = {"hf_webhook": webhook_url} if webhook_url else None
        try:
            response = await self._api.post(f"/{model}", json=arguments, params=params)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise HiggsfieldError("network", f"No se pudo conectar con Higgsfield: {exc}") from exc
        except httpx.TransportError as exc:
            # La petición pudo llegar: reintentarla podría duplicar la generación y el cobro.
            raise HiggsfieldError("ambiguous", f"Envío sin respuesta ({type(exc).__name__})") from exc
        _raise_for(response)
        return {**response.json(), "_correlation_id": response.headers.get("x-correlation-id")}

    async def status(self, request_id: str, status_url: str | None = None) -> dict:
        url = self._own_url(status_url, f"/requests/{quote(request_id)}/status")
        try:
            response = await self._api.get(url)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Fallo de red consultando estado: {exc}") from exc
        _raise_for(response)
        return response.json()

    async def cancel(self, request_id: str, cancel_url: str | None = None) -> None:
        url = self._own_url(cancel_url, f"/requests/{quote(request_id)}/cancel")
        try:
            response = await self._api.post(url)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Fallo de red cancelando: {exc}") from exc
        if response.status_code == 400:
            raise HiggsfieldError("too_late", "La generación ya empezó y no se puede cancelar", 400)
        _raise_for(response)

    async def estimate(self, model: str, arguments: dict[str, Any]) -> dict:
        try:
            response = await self._api.post(f"/estimate/{model}", json=arguments)
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Fallo de red estimando costo: {exc}") from exc
        _raise_for(response)
        return response.json()

    async def upload(self, data: bytes, content_type: str) -> str:
        """Sube un archivo por URL prefirmada y devuelve su `public_url` para usarla como entrada."""
        try:
            response = await self._api.post("/files/generate-upload-url", json={"content_type": content_type})
            _raise_for(response)
            ticket = response.json()
            put = await self._plain.put(
                ticket["upload_url"], content=data, headers=ticket.get("upload_headers") or {}
            )
        except httpx.TransportError as exc:
            raise HiggsfieldError("network", f"Fallo de red subiendo archivo: {exc}") from exc
        if not put.is_success:
            raise HiggsfieldError(
                "server", f"El almacenamiento rechazó la subida ({put.status_code})", put.status_code
            )
        return ticket["public_url"]

    async def download(self, url: str, dest: Path) -> tuple[int, str | None]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        async with self._plain.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            size = 0
            with tmp.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)
                    size += len(chunk)
            content_type = response.headers.get("content-type")
        tmp.replace(dest)
        return size, content_type


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
