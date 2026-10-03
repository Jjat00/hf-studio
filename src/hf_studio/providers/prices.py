"""Tablas de precios públicas de los proveedores, en caché local y refrescadas una vez al día.

Ningún revendedor tiene endpoint de cotización: el costo se calcula con su tabla pública (sin clave).
Cada proveedor que la tenga implementa `fetch_prices()` y devuelve `{clave: usd}`; sus `Route.price`
leen de aquí. Higgsfield no la necesita: cotiza con `/estimate`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from .base import Provider

log = logging.getLogger("hf_studio.prices")

MAX_AGE_SECONDS = 24 * 3600


class PriceBook:
    """Precios por proveedor: `{proveedor: {"synced_at": epoch, "prices": {clave: usd}}}`."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._tables: dict[str, dict[str, Any]] = {}

    def path(self, provider: str) -> Path:
        return self.directory / f"{provider}.json"

    def load(self, provider: str) -> dict[str, Any] | None:
        if provider not in self._tables:
            file = self.path(provider)
            if not file.is_file():
                return None
            try:
                self._tables[provider] = json.loads(file.read_text())
            except (OSError, ValueError):
                return None
        return self._tables[provider]

    def prices(self, provider: str) -> dict[str, float]:
        table = self.load(provider)
        return table["prices"] if table else {}

    def synced_at(self, provider: str) -> float | None:
        table = self.load(provider)
        return table["synced_at"] if table else None

    def stale(self, provider: str) -> bool:
        synced = self.synced_at(provider)
        return synced is None or time.time() - synced > MAX_AGE_SECONDS

    def store(self, provider: str, prices: dict[str, float]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        table = {"synced_at": time.time(), "prices": prices}
        tmp = self.path(provider).with_suffix(".tmp")
        tmp.write_text(json.dumps(table, indent=0, sort_keys=True))
        tmp.replace(self.path(provider))
        self._tables[provider] = table

    async def refresh(self, providers: dict[str, Provider], force: bool = False) -> dict[str, str]:
        """Descarga las tablas viejas. Un fallo deja la tabla anterior (precio algo viejo > sin precio)."""
        results = {}
        for name, provider in providers.items():
            if not provider.has_price_table or (not force and not self.stale(name)):
                continue
            try:
                prices = await provider.fetch_prices()
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                # red o formato cambiado: se sigue con la tabla anterior
                log.warning("No se pudo actualizar la tabla de precios de %s: %s", name, exc)
                results[name] = f"error: {exc}"
                continue
            if prices:
                self.store(name, prices)
                results[name] = f"{len(prices)} prices"
        return results
