"""Proveedores de generación intercambiables. Ver `base.py` (contrato) y `registry.py` (alta)."""

from .base import (
    FALLBACK_SAFE,
    KeyCheck,
    Polled,
    Provider,
    ProviderError,
    Submitted,
)

__all__ = ["FALLBACK_SAFE", "KeyCheck", "Polled", "Provider", "ProviderError", "Submitted"]
