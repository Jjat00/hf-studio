"""Contrato común de los proveedores de generación (Higgsfield, APIMart, KIE…).

Un proveedor es una clase que hereda de `Provider`, declara sus datos (variable de la clave,
enlaces de registro y de la clave) e implementa cinco operaciones: comprobar la clave, enviar,
consultar, cancelar y descargar. El worker, la API y el MCP solo hablan con este contrato, así que
añadir un proveedor es escribir un módulo y registrarlo (ver `registry.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from ..config import Settings

if TYPE_CHECKING:
    from .routes import Routes

# Estados normalizados que devuelve `poll`. Los activos son los de la cola remota.
ACTIVE_STATUSES = ("queued", "in_progress")
TERMINAL_STATUSES = ("completed", "failed", "nsfw", "canceled")

# Tipos de error comunes. Cada adaptador traduce los suyos a uno de estos.
#   auth          clave ausente o inválida
#   credits       saldo insuficiente
#   validation    parámetros rechazados por el proveedor
#   bad_request   petición rechazada por otro motivo
#   not_found     tarea o modelo desconocido
#   unsupported   el proveedor no ofrece esa operación o ese modelo
#   moderation    el filtro de contenido rechazó la entrada
#   concurrency   límite de tareas simultáneas de la cuenta
#   unavailable   modelo o servicio caído temporalmente
#   server        error 5xx del proveedor
#   network       no se pudo conectar (la petición no salió)
#   ambiguous     la petición pudo llegar pero no hubo respuesta: NUNCA se reintenta ni se salta
#   too_late      la tarea ya empezó y no se puede cancelar
RETRYABLE = frozenset({"concurrency", "unavailable", "server", "network"})
# Fallos de envío que garantizan que no se creó tarea ni hubo cobro: se puede probar otro proveedor.
FALLBACK_SAFE = frozenset(
    {"auth", "credits", "validation", "bad_request", "not_found", "unsupported", "moderation",
     "concurrency", "unavailable", "server", "network"}
)  # fmt: skip


class ProviderError(Exception):
    """Error de un proveedor ya clasificado en un tipo común."""

    def __init__(
        self,
        kind: str,
        message: str,
        status: int | None = None,
        correlation_id: str | None = None,
        provider: str | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.correlation_id = correlation_id
        self.provider = provider

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE

    @property
    def fallback_safe(self) -> bool:
        return self.kind in FALLBACK_SAFE


@dataclass
class Submitted:
    request_id: str
    status: str = "queued"  # normalizado; puede ser terminal si el proveedor respondió de inmediato
    status_url: str | None = None
    cancel_url: str | None = None
    correlation_id: str | None = None
    raw: dict = field(default_factory=dict)
    polled: Polled | None = None  # resultado ya terminal en la propia respuesta de envío


@dataclass
class Polled:
    status: str  # normalizado: ACTIVE_STATUSES o TERMINAL_STATUSES
    outputs: list[dict] = field(default_factory=list)  # [{kind, url, content_type}]
    error: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class KeyCheck:
    """Resultado de comprobar una clave sin gastar: `valid` es None si no se pudo comprobar."""

    valid: bool | None
    balance_usd: float | None = None
    message: str = ""


class Provider(ABC):
    # Identidad y enlaces que muestran `setup`, `hf-studio providers` y la UI.
    name: ClassVar[str]
    title: ClassVar[str]
    env_var: ClassVar[str]  # variable de la clave en .env
    base_url: ClassVar[str]
    signup_url: ClassVar[str]
    key_url: ClassVar[str]
    billing_url: ClassVar[str | None] = None
    docs_url: ClassVar[str | None] = None
    # Obligatorio: sin él HF Studio no arranca (Higgsfield guarda los medios de entrada).
    required: ClassVar[bool] = False
    # Línea breve para setup: para qué sirve y si cobra.
    blurb: ClassVar[str] = ""
    # True si el proveedor publica una tabla de precios que `fetch_prices` sabe leer (ver prices.py).
    has_price_table: ClassVar[bool] = False

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.base = (settings.secret(f"{self.name.upper()}_BASE_URL") or self.base_url).rstrip("/")
        self._plain = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), transport=transport)

    @classmethod
    def key_from(cls, settings: Settings) -> str:
        return settings.secret(cls.env_var).strip()

    @property
    def configured(self) -> bool:
        return bool(self.key_from(self.settings))

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "env_var": self.env_var,
            "configured": self.configured,
            "required": self.required,
            "signup_url": self.signup_url,
            "key_url": self.key_url,
            "billing_url": self.billing_url,
            "docs_url": self.docs_url,
            "blurb": self.blurb,
        }

    @property
    def plain(self) -> httpx.AsyncClient:
        """Cliente sin credenciales (descargas de CDN)."""
        return self._plain

    async def aclose(self) -> None:
        await self._plain.aclose()

    @abstractmethod
    async def check_key(self) -> KeyCheck:
        """Comprueba la clave sin gastar y, si el proveedor lo permite, devuelve el saldo en USD."""

    @abstractmethod
    async def submit_job(
        self, model: str, arguments: dict[str, Any], webhook_url: str | None = None
    ) -> Submitted:
        """Envía una generación con el id y la entrada ya traducidos al proveedor."""

    @abstractmethod
    async def poll_job(self, request_id: str, status_url: str | None = None) -> Polled:
        """Estado autoritativo de una tarea, normalizado."""

    @classmethod
    def routes(cls) -> Routes:
        """Modelos lógicos que ofrece este proveedor: `{id del catálogo: Route o tupla de Route}` (ver
        routes.py)."""
        return {}

    async def fetch_prices(self) -> dict[str, float]:
        """Tabla pública de precios en USD, `{clave: usd}`; las claves las definen sus `Route.price`."""
        return {}

    async def cancel_job(self, request_id: str, cancel_url: str | None = None) -> None:
        raise ProviderError("unsupported", f"{self.title} does not support canceling", provider=self.name)

    async def download(self, url: str, dest: Path) -> tuple[int, str | None]:
        """Descarga una salida (sin credenciales) de forma atómica; devuelve tamaño y tipo."""
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


def kind_for_status(status: int) -> str:
    """Clasificación por código HTTP para proveedores que lo usan de forma convencional."""
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "credits"
    if status == 404:
        return "not_found"
    if status in (400, 422):
        return "validation"
    if status == 429:
        return "concurrency"
    if status in (423, 503):
        return "unavailable"
    return "server" if status >= 500 else "bad_request"


def media_kind(url: str, default: str = "video") -> str:
    path = url.split("?", 1)[0].lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if path.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
        return "audio"
    return default
