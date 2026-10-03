"""Proveedor KIE (https://docs.kie.ai).

Casi todos los modelos usan la API unificada: `POST /api/v1/jobs/createTask` con `model` e `input`, y
`GET /api/v1/jobs/recordInfo?taskId=`. KIE responde HTTP 200 incluso a los errores: el código real va
en `code` dentro del cuerpo (un parámetro inválido llega como `code: 500`). Sin `taskId` no hubo
tarea ni cobro. 1 crédito = 0,005 USD.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import Settings
from .base import KeyCheck, Polled, Provider, ProviderError, Submitted, media_kind

USD_PER_CREDIT = 0.005
STATE = {
    "waiting": "queued",
    "queuing": "queued",
    "generating": "in_progress",
    "success": "completed",
    "fail": "failed",
}
MODERATION = re.compile(r"nsfw|moderat|sensitive|safety|content.?policy|violat|prohibit", re.IGNORECASE)


def _kind(code: int, message: str) -> str:
    if MODERATION.search(message):
        return "moderation"
    return {
        401: "auth",
        402: "credits",
        404: "not_found",
        422: "validation",
        429: "concurrency",
        433: "concurrency",
        455: "unavailable",
        500: "validation",  # en createTask, 500 es el error de parámetros (comprobado 2026-10-03)
        501: "server",
        505: "unavailable",
    }.get(code, "server" if code >= 500 else "bad_request")


class KIEProvider(Provider):
    name = "kie"
    title = "KIE"
    env_var = "KIE_API_KEY"
    base_url = "https://api.kie.ai"
    signup_url = "https://kie.ai"
    key_url = "https://kie.ai/api-key"
    billing_url = "https://kie.ai/billing"
    docs_url = "https://docs.kie.ai"
    blurb = "Optional: usually the cheapest for Hailuo, MiniMax and Wan Animate. New accounts get 80 free credits."
    has_price_table = True
    pricing_url = "https://api.kie.ai/client/v1/model-pricing/page"

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

    def _body(self, response: httpx.Response) -> dict:
        """Cuerpo de una respuesta de KIE; lanza ProviderError si `code` no es 200."""
        try:
            body = response.json()
        except ValueError:
            body = {"code": response.status_code, "msg": response.text[:300]}
        code = body.get("code", response.status_code) if isinstance(body, dict) else response.status_code
        if response.is_success and code == 200:
            return body
        message = str(body.get("msg") or response.reason_phrase)
        raise ProviderError(_kind(int(code), message), message, int(code), provider=self.name)

    async def check_key(self) -> KeyCheck:
        if not self.configured:
            return KeyCheck(False, message=f"Missing {self.env_var}")
        try:
            body = self._body(await self._api.get("/api/v1/chat/credit"))
        except httpx.TransportError as exc:
            return KeyCheck(None, message=f"Could not reach KIE ({type(exc).__name__})")
        except ProviderError as exc:
            return KeyCheck(False if exc.kind == "auth" else None, message=exc.message)
        credits = body.get("data")
        return KeyCheck(True, round(float(credits) * USD_PER_CREDIT, 4) if credits is not None else None)

    async def submit_job(
        self, model: str, arguments: dict[str, Any], webhook_url: str | None = None
    ) -> Submitted:
        body: dict[str, Any] = {"model": model, "input": arguments}
        if webhook_url:
            body["callBackUrl"] = webhook_url
        try:
            response = await self._api.post("/api/v1/jobs/createTask", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderError("network", f"Could not connect to KIE: {exc}", provider=self.name) from exc
        except httpx.TransportError as exc:
            raise ProviderError(
                "ambiguous", f"Submission got no response ({type(exc).__name__})", provider=self.name
            ) from exc
        data = self._body(response).get("data") or {}
        task_id = data.get("taskId")
        if not task_id:
            raise ProviderError("server", "KIE returned no taskId", provider=self.name)
        return Submitted(task_id, "queued", raw=data)

    @classmethod
    def routes(cls):
        from .kie_routes import kie_routes

        return kie_routes()

    async def fetch_prices(self) -> dict[str, float]:
        """Tabla pública (sin clave), paginada: `{modelDescription normalizado: usd por unidad}`. La
        unidad (por segundo o por video) la conoce la ruta de cada modelo."""
        prices: dict[str, float] = {}
        page, pages = 1, 1
        while page <= pages:
            response = await self._plain.post(self.pricing_url, json={"pageNum": page, "pageSize": 100})
            response.raise_for_status()
            data = response.json().get("data") or {}
            pages = int(data.get("pages") or 1)
            for row in data.get("records") or []:
                # Créditos × 0,005: la columna usdPrice tiene erratas (Wan 3.0 720p decía 0,09 por 0,08).
                credits = parse_usd(row.get("creditPrice"))
                usd = (
                    round(credits * USD_PER_CREDIT, 6)
                    if credits is not None
                    else parse_usd(row.get("usdPrice"))
                )
                if usd is not None and row.get("modelDescription"):
                    prices[price_key(row["modelDescription"])] = usd
            page += 1
        return prices

    async def poll_job(self, request_id: str, status_url: str | None = None) -> Polled:
        try:
            response = await self._api.get("/api/v1/jobs/recordInfo", params={"taskId": request_id})
        except httpx.TransportError as exc:
            raise ProviderError(
                "network", f"Network error while checking status: {exc}", provider=self.name
            ) from exc
        try:
            body = self._body(response)
        except ProviderError as exc:
            if exc.message == "recordInfo is null":
                raise ProviderError(
                    "not_found", "KIE does not know this task", 422, provider=self.name
                ) from exc
            raise
        return polled(body.get("data") or {})


def polled(data: dict) -> Polled:
    status = STATE.get(str(data.get("state", "")).lower(), "in_progress")
    if status == "completed":
        return Polled(status, extract_outputs(data), raw=data)
    if status == "failed":
        message = data.get("failMsg") or data.get("failCode") or "Generation failed"
        return Polled("nsfw" if MODERATION.search(str(message)) else "failed", error=str(message), raw=data)
    return Polled(status, raw=data)


def extract_outputs(data: dict) -> list[dict]:
    """`resultJson` (texto JSON) o `response`, con `resultUrls`."""
    result = data.get("response")
    if not isinstance(result, dict):
        try:
            result = json.loads(data.get("resultJson") or "{}")
        except ValueError:
            result = {}
    urls = result.get("resultUrls") or []
    return [{"kind": media_kind(u), "url": u, "content_type": None} for u in urls if isinstance(u, str)]


def price_key(description: str) -> str:
    """Normaliza `modelDescription` (espacios, mayúsculas y paréntesis varían entre filas)."""
    return re.sub(r"\s+", " ", description.replace("（", "(").replace("）", ")")).strip().lower()


def parse_usd(value) -> float | None:
    """`"0,325"`, `"$0.30"`, `0.3` → float."""
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.replace("$", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
