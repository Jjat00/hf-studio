"""Estilos de los modelos que eligen uno por id (Genjutsu Restyle: `preset_id`).

Higgsfield publica el catálogo en `GET /models/<id>/presets` y lo cambia sin aviso: se guarda 10 min en
memoria. Un `preset_id` que ya no está falla en Higgsfield después de aceptar el pedido, así que se
comprueba antes de cotizar o generar.
"""

from __future__ import annotations

import time

from .higgsfield import HiggsfieldError
from .service import ServiceError

STYLE_MODELS = frozenset({"higgsfield/genjutsu/restyle/v1.0"})
TTL_SECONDS = 600
FAILURE_SECONDS = (
    60  # tras un fallo de red no se reintenta en cada cotización: no la frena un timeout cada vez
)


class StyleCatalog:
    def __init__(self, hf) -> None:
        self.hf = hf
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._failed_at: dict[str, float] = {}

    async def list(self, model_id: str, fresh: bool = False) -> list[dict]:
        if model_id not in STYLE_MODELS:
            raise ServiceError(404, "no_styles", f"{model_id} has no style catalog")
        cached = self._cache.get(model_id)
        if cached and not fresh and time.monotonic() - cached[0] < TTL_SECONDS:
            return cached[1]
        body = await self.hf.model_presets(model_id)
        items = [
            {"id": i["id"], "name": str(i.get("name") or i["id"]), "preview_url": i.get("preview_url")}
            for i in (body.get("items") if isinstance(body, dict) else None) or []
            if isinstance(i, dict) and isinstance(i.get("id"), str)
        ]
        self._cache[model_id] = (time.monotonic(), items)
        return items

    async def check(self, model_id: str, arguments: dict) -> None:
        """422 si `preset_id` no es un estilo vigente. Si Higgsfield no responde, no se bloquea: lo valida él."""
        preset = arguments.get("preset_id")
        if model_id not in STYLE_MODELS or not isinstance(preset, str):
            return
        if time.monotonic() - self._failed_at.get(model_id, -FAILURE_SECONDS) < FAILURE_SECONDS:
            return
        try:
            ids = {s["id"] for s in await self.list(model_id)}
            if preset not in ids:  # quizá es un estilo recién publicado
                ids = {s["id"] for s in await self.list(model_id, fresh=True)}
        except HiggsfieldError as exc:
            if exc.kind == "auth":
                raise
            self._failed_at[model_id] = time.monotonic()
            return
        if preset not in ids:
            message = f"preset_id {preset} is not an available style; list them with list_styles"
            raise ServiceError(422, "unknown_style", message, [{"path": "preset_id", "message": message}])
