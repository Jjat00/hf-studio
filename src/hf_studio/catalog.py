"""Catálogo de endpoints de Higgsfield con sus JSON Schema (generado por `hf-studio sync-catalog`)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

CATALOG_PATH = Path(__file__).with_name("catalog.json")

_formats = FormatChecker()


@_formats.checks("uri", raises=ValueError)
def _is_public_url(value: object) -> bool:
    # La API exige URLs públicas; asset:// y rutas locales se rechazan antes de gastar un envío.
    if not isinstance(value, str):
        return True
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be a public http(s) URL; upload local files with POST /v1/uploads")
    return True


class Catalog:
    def __init__(self, data: dict):
        self.synced_at: str = data["synced_at"]
        self.models: dict[str, dict] = {m["id"]: m for m in data["models"]}
        self._validators = {
            mid: Draft202012Validator(m["input_schema"], format_checker=_formats)
            for mid, m in self.models.items()
        }

    def get(self, model_id: str) -> dict | None:
        return self.models.get(model_id.strip("/"))

    def search(
        self, capability: str | None = None, output: str | None = None, query: str | None = None
    ) -> list[dict]:
        q = (query or "").lower()
        return [
            m
            for m in self.models.values()
            if (not capability or capability in m["capabilities"])
            and (not output or m["output"] == output)
            and (not q or q in m["id"].lower() or q in m["title"].lower())
        ]

    def validate(self, model_id: str, arguments: dict) -> list[dict]:
        """Devuelve los errores de validación como `[{path, message}]`; lista vacía si es válido."""
        errors = sorted(
            self._validators[model_id].iter_errors(arguments), key=lambda e: list(e.absolute_path)
        )
        return [
            {
                "path": "/".join(str(p) for p in e.absolute_path) or "(root)",
                "message": f"{e.message}: {e.cause}" if e.cause else e.message,
            }
            for e in errors
        ]


@lru_cache
def get_catalog() -> Catalog:
    return Catalog(json.loads(CATALOG_PATH.read_text()))
