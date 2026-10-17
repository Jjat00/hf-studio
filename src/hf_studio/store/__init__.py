"""Modelos que solo ofrecen las tiendas (APIMart, KIE) y no Higgsfield: Nano Banana, GPT Image, Veo, Seedream…

Cada módulo de este paquete es una familia y exporta:

- `MODELS`: entradas con la forma del catálogo (`id`, `title`, `summary`, `workflow`, `family`, `output`,
  `capabilities`, `notes`, `docs_url`, `input_schema`). El id lógico sigue el estilo del catálogo
  (`google/nano-banana-2/text-to-image`) y no debe chocar con un id de Higgsfield.
- `apimart()` y/o `kie()`: `Routes` como las de `providers/*_routes.py`, una por id lógico de `MODELS`.
- `APIMART_IMAGE_MODELS` (opcional): ids de APIMart que se envían a `/v1/images/generations`.
- `APIMART_PATHS` (opcional): `{id de APIMart: ruta}` para los que tienen su propia ruta de envío (Midjourney).
  El estado se lee igual, con `GET /v1/tasks/{id}`.
- `KIE_ENDPOINTS` (opcional): `{id del modelo en KIE: KIEEndpoint}` para los modelos de KIE que no usan la
  API unificada (`jobs/createTask`), como Veo o GPT-4o Image.

El catálogo los añade con `store: True`, el router no se los ofrece a Higgsfield y cada tienda los recoge en
sus rutas. Así un modelo nuevo de una tienda es un módulo nuevo, sin tocar el resto.
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import cache
from types import ModuleType
from typing import Any


@cache
def modules() -> tuple[ModuleType, ...]:
    return tuple(
        importlib.import_module(f"{__name__}.{info.name}")
        for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name)
        if not info.name.startswith("_")
    )


@cache
def models() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for module in modules():
        for model in getattr(module, "MODELS", ()):
            if model["id"] in found:
                raise ValueError(f"store model {model['id']} is defined twice")
            found[model["id"]] = {**model, "store": True}
    return found


def routes(provider: str) -> dict:
    """Rutas de una tienda para los modelos de este paquete (`provider`: apimart | kie)."""
    merged: dict = {}
    for module in modules():
        builder = getattr(module, provider, None)
        if builder is not None:
            merged.update(builder())
    return merged


@cache
def apimart_image_models() -> frozenset[str]:
    return frozenset().union(*(getattr(m, "APIMART_IMAGE_MODELS", frozenset()) for m in modules()))


@cache
def apimart_paths() -> dict[str, str]:
    merged: dict[str, str] = {}
    for module in modules():
        merged.update(getattr(module, "APIMART_PATHS", {}))
    return merged


@cache
def kie_endpoints() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for module in modules():
        merged.update(getattr(module, "KIE_ENDPOINTS", {}))
    return merged
