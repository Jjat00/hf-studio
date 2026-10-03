"""Proveedor APIMart (https://docs.apimart.ai).

Un solo endpoint de envío para todos los modelos (`POST /v1/videos/generations` con `model`) y uno de
estado (`GET /v1/tasks/{id}`). Las tareas que fallan se reembolsan. Con saldo por debajo de 0,05 USD la
API rechaza toda petición, incluida la de saldo, con 402 y el saldo en el texto.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..config import Settings
from .base import KeyCheck, Polled, Provider, ProviderError, Submitted, kind_for_status, media_kind

STATUS = {
    "submitted": "queued",
    "pending": "queued",
    "queued": "queued",
    "processing": "in_progress",
    "in_progress": "in_progress",
    "running": "in_progress",
    "completed": "completed",
    "succeeded": "completed",
    "success": "completed",
    "failed": "failed",
    "failure": "failed",
    "cancelled": "canceled",
    "canceled": "canceled",
}
MODERATION = re.compile(r"nsfw|moderat|sensitive|safety|content.?policy|violat", re.IGNORECASE)
BALANCE_IN_TEXT = re.compile(r"current:\s*([0-9.]+)\s*USD", re.IGNORECASE)


class APIMartProvider(Provider):
    name = "apimart"
    title = "APIMart"
    env_var = "APIMART_API_KEY"
    base_url = "https://api.apimart.ai"
    signup_url = "https://apimart.ai/register"
    key_url = "https://apimart.ai/keys"
    billing_url = "https://apimart.ai/billing"
    docs_url = "https://docs.apimart.ai/en"
    blurb = "Optional: usually the cheapest for Seedance and Wan. Failed tasks are refunded."
    has_price_table = True
    pricing_url = "https://apimart.ai/api/pricing/models/all"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(settings, transport)
        self._api = httpx.AsyncClient(
            base_url=self.base,
            headers={"Authorization": f"Bearer {self.key_from(settings)}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._api.aclose()
        await super().aclose()

    def _error(self, response: httpx.Response) -> ProviderError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        err = body.get("error") if isinstance(body, dict) else None
        message = (err or {}).get("message") if isinstance(err, dict) else None
        message = message or (body.get("message") if isinstance(body, dict) else None) or response.text[:300]
        kind = kind_for_status(response.status_code)
        if "invalid api key" in message.lower():
            kind = "auth"
        elif "insufficient balance" in message.lower():
            kind = "credits"
        elif kind == "validation" and MODERATION.search(message):
            kind = "moderation"
        return ProviderError(kind, message, response.status_code, provider=self.name)

    async def check_key(self) -> KeyCheck:
        if not self.configured:
            return KeyCheck(False, message=f"Missing {self.env_var}")
        try:
            response = await self._api.get("/v1/user/balance")
        except httpx.TransportError as exc:
            return KeyCheck(None, message=f"Could not reach APIMart ({type(exc).__name__})")
        if response.is_success:
            data = response.json()
            data = data.get("data", data) if isinstance(data, dict) else {}
            balance = data.get("remain_balance")
            return KeyCheck(True, float(balance) if balance is not None else None)
        error = self._error(response)
        if error.kind == "credits":
            # La clave es válida; la cuenta está por debajo del mínimo de 0,05 USD.
            found = BALANCE_IN_TEXT.search(error.message)
            return KeyCheck(
                True, float(found.group(1)) if found else 0.0, "Balance below APIMart's 0.05 USD minimum"
            )
        if error.kind == "auth":
            return KeyCheck(False, message="Invalid key")
        return KeyCheck(None, message=error.message)

    async def submit_job(
        self, model: str, arguments: dict[str, Any], webhook_url: str | None = None
    ) -> Submitted:
        body = {**arguments, "model": model}
        if webhook_url:
            body["webhook"] = webhook_url
        try:
            response = await self._api.post("/v1/videos/generations", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderError(
                "network", f"Could not connect to APIMart: {exc}", provider=self.name
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderError(
                "ambiguous", f"Submission got no response ({type(exc).__name__})", provider=self.name
            ) from exc
        if not response.is_success:
            error = self._error(response)
            if error.kind in ("server", "unavailable"):
                # Un 5xx genérico tras el POST no garantiza que no se creó la tarea (revisión 28).
                error.kind = "ambiguous"
            raise error
        try:
            data = response.json().get("data")
        except (ValueError, AttributeError):
            data = None
        task = data[0] if isinstance(data, list) and data else data
        task_id = (task.get("task_id") or task.get("id")) if isinstance(task, dict) else None
        if not task_id:
            # Aceptado sin id: pudo crearse y cobrarse; nunca se reintenta ni se salta de proveedor.
            raise ProviderError(
                "ambiguous", f"APIMart accepted the request without a task id: {response.text[:300]}",
                provider=self.name,
            )  # fmt: skip
        return Submitted(str(task_id), STATUS.get(str(task.get("status")), "queued"), raw={"data": data})

    @classmethod
    def routes(cls):
        from .apimart_routes import apimart_routes

        return apimart_routes()

    async def fetch_prices(self) -> dict[str, float]:
        """Precio de pago por uso (`after_discount`, nivel Gold) por `modelo|clave`. También los
        recargos por medio de entrada (`modelo|input:image`, `modelo|input:video:clave`) y el precio por
        millón de tokens (`modelo|token:clave`)."""
        response = await self._plain.get(self.pricing_url, headers={"User-Agent": "hf-studio"})
        response.raise_for_status()
        return parse_prices(response.json())

    async def poll_job(self, request_id: str, status_url: str | None = None) -> Polled:
        try:
            response = await self._api.get(f"/v1/tasks/{request_id}")
        except httpx.TransportError as exc:
            raise ProviderError(
                "network", f"Network error while checking status: {exc}", provider=self.name
            ) from exc
        if not response.is_success:
            raise self._error(response)
        return polled(response.json())


def polled(body: dict) -> Polled:
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    status = STATUS.get(str(data.get("status", "")).lower(), "in_progress")
    error = data.get("error")
    message = None
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
    elif error:
        message = str(error)
    if status == "failed" and message and MODERATION.search(f"{message} {error}"):
        status = "nsfw"
    outputs = extract_outputs(data.get("result") or {}) if status == "completed" else []
    return Polled(status, outputs, message if status in ("failed", "nsfw", "canceled") else None, body)


def extract_outputs(result: dict) -> list[dict]:
    """`result.videos[].url` (lista o texto), igual para `images` y `audios`."""
    outputs, seen = [], set()
    for key, kind in (("videos", "video"), ("images", "image"), ("audios", "audio")):
        for item in result.get(key) or []:
            urls = item.get("url") if isinstance(item, dict) else item
            for url in urls if isinstance(urls, list) else [urls]:
                if isinstance(url, str) and url not in seen:
                    seen.add(url)
                    outputs.append({"kind": media_kind(url, kind), "url": url, "content_type": None})
    return outputs


def parse_prices(body: dict) -> dict[str, float]:
    prices: dict[str, float] = {}

    def put(key: str, item: dict) -> None:
        value = item.get("after_discount", item.get("original_price"))
        if isinstance(value, int | float):
            prices[key] = float(value)

    for model in (body.get("data") or {}).get("models", {}).get("video", []):
        mid = model["id"]
        for item in (model.get("fixed_prices") or {}).get("items") or []:
            put(f"{mid}|{item['key']}", item)
        extra = model.get("input_material_prices") or {}
        if isinstance(extra.get("image"), dict):
            put(f"{mid}|input:image", extra["image"])
        video = extra.get("video") or {}
        for item in video.get("items") or ([video] if "original_price" in video else []):
            put(f"{mid}|input:video:{item.get('key', 'default')}", item)
        for item in (model.get("token_settlement_prices") or {}).get("items") or []:
            put(f"{mid}|token:{item['key']}", item)
    return prices
