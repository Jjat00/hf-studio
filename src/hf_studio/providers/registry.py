"""Registro de proveedores.

Para añadir uno: escribe un módulo con una subclase de `Provider` y añádela a `PROVIDERS`. Setup,
`hf-studio providers`, `/v1/providers`, el worker y el MCP la recogen de aquí; el mapa de modelos dice
qué modelos ofrece y con qué id.
"""

from __future__ import annotations

import httpx

from ..config import Settings
from ..higgsfield import HiggsfieldClient
from .apimart import APIMartProvider
from .base import Provider
from .kie import KIEProvider

# Orden de presentación; el orden de envío lo decide el precio.
PROVIDERS: dict[str, type[Provider]] = {
    cls.name: cls for cls in (HiggsfieldClient, APIMartProvider, KIEProvider)
}
DEFAULT_PROVIDER = HiggsfieldClient.name


def build(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Provider]:
    """Una instancia por proveedor registrado, con o sin clave (sin clave fallan con `auth`)."""
    return {name: cls(settings, transport) for name, cls in PROVIDERS.items()}


def configured(settings: Settings) -> list[str]:
    return [name for name, cls in PROVIDERS.items() if cls.key_from(settings)]
