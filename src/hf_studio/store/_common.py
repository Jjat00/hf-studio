"""Piezas comunes para describir un modelo de tienda con la forma del catálogo."""

from __future__ import annotations

from typing import Any


def model(
    model_id: str,
    *,
    name: str,
    workflow: str,
    family: str,
    output: str,
    capabilities: list[str],
    properties: dict[str, Any],
    required: list[str],
    docs_url: str,
    notes: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Entrada del catálogo. `name` y `workflow` forman el título «Nombre — Flujo API» que la UI separa."""
    return {
        "id": model_id,
        "title": f"{name} — {workflow} API",
        "summary": summary or f"{workflow} with {name} through APIMart or KIE (not offered by Higgsfield).",
        "workflow": workflow.lower().replace(" ", "-"),
        "family": family,
        "output": output,
        "capabilities": capabilities,
        "notes": notes or [],
        "docs_url": docs_url,
        "input_schema": {
            "type": "object",
            "title": name,
            "required": required,
            "properties": properties,
            "additionalProperties": False,
        },
    }


def prompt(max_length: int | None = None, description: str = "What to generate.") -> dict[str, Any]:
    field: dict[str, Any] = {"type": "string", "minLength": 1, "description": description}
    if max_length:
        field["maxLength"] = max_length
    return field


def choice(values: list[Any], default: Any, description: str) -> dict[str, Any]:
    kind = "integer" if all(isinstance(v, int) for v in values) else "string"
    return {"enum": values, "type": kind, "default": default, "description": description}


def urls(min_items: int, max_items: int, description: str) -> dict[str, Any]:
    field: dict[str, Any] = {
        "type": "array",
        "items": {"type": "string", "format": "uri"},
        "maxItems": max_items,
        "description": description,
    }
    if min_items:
        field["minItems"] = min_items
    return field


def url(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "uri", "description": description}


def upper(value: str) -> str:
    return value.upper()
