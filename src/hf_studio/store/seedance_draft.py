"""Seedance 2.5 Draft: borrador barato a 480p y, del borrador elegido, el video final a 1080p con la misma escena.

El final reutiliza el prompt, las referencias, la duración, el formato, la semilla y el audio del borrador, así
que es la misma toma en alta calidad, no otra tirada. Solo lo ofrecen las tiendas (Higgsfield no):

- APIMart `seedance-2.5`: https://docs.apimart.ai/en/api-reference/videos/seedance-2-5/generation.md (sección
  «Draft mode»). Borrador con `draft: true` (solo 480p); final con `draft_task_id` (solo 1080p, sin reenviar
  prompt ni medios; `output_format` sí). El borrador vale 3 días. Se cobra como un video normal a 480p y el
  final a 1080p (`1080P-input` si el borrador llevaba videos de referencia), liquidado por tokens.
- KIE `bytedance/seedance-2-5` con `draft: true` (vale 7 días): https://docs.kie.ai/market/bytedance/seedance-2-5.md;
  final con `bytedance/seedance-2-5-draft` y `draft_task_id`:
  https://docs.kie.ai/market/bytedance/seedance-2-5-draft.md. La tabla de KIE no tiene fila del final: se cotiza
  como un video normal a 1080p (aproximado).

El final se envía al mismo proveedor que hizo el borrador (el router lo resuelve desde la generación, ver
`routing.Router.plan`) y con el id de tarea de ese proveedor.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..providers.routes import Route, per_second, unsupported

FAMILY = "bytedance/seedance-2.5-draft"
FINAL_ID = f"{FAMILY}/final"
MODES = ("text-to-video", "image-to-video", "reference-to-video")
DOCS = "https://docs.apimart.ai/en/api-reference/videos/seedance-2-5/generation"
# Cuánto vale un borrador en cada tienda para hacer su final.
EXPIRES = {"apimart": timedelta(days=3), "kie": timedelta(days=7)}
KIE_FINAL = "bytedance/seedance-2-5-draft"


def draft_id(mode: str) -> str:
    return f"{FAMILY}/{mode}"


def is_draft(model_id: str) -> bool:
    return model_id.startswith(f"{FAMILY}/") and model_id != FINAL_ID


def _seedance_25(mode: str) -> dict[str, Any]:
    """El modelo de Seedance 2.5 de Higgsfield (del catálogo sincronizado), base del borrador."""
    data = json.loads(Path(__file__).parent.with_name("catalog.json").read_text())["models"]
    return next(m for m in data if m["id"] == f"bytedance/seedance-2.5/{mode}")


def _models() -> list[dict[str, Any]]:
    found = []
    for mode in MODES:
        base = _seedance_25(mode)
        schema = json.loads(json.dumps(base["input_schema"]))
        for key in ("resolution", "bitrate_mode"):  # el borrador es siempre 480p con el bitrate de la tienda
            schema["properties"].pop(key, None)
        found.append(
            {
                **{k: base[k] for k in ("workflow", "output", "capabilities")},
                "id": draft_id(mode),
                "title": f"Seedance 2.5 Draft — {base['title'].split('—', 1)[-1].strip()}",
                "summary": (
                    "Cheap 480p draft of a Seedance 2.5 video. If you like it, turn it into the same scene at 1080p "
                    "with the Seedance 2.5 Draft final model."
                ),
                "family": "seedance-2-5-draft",
                "notes": [
                    "A 480p preview billed like a normal 480p Seedance 2.5 video, on APIMart or KIE (not Higgsfield).",
                    (
                        f"To get the 1080p video, run {FINAL_ID} with draft_generation_id = this generation's id. It "
                        "keeps the prompt, references, duration, aspect ratio, seed and audio, so it is the same shot."
                    ),
                    "The draft can be finished within 3 days on APIMart and 7 days on KIE.",
                    *base.get("notes", []),
                ],
                "docs_url": DOCS,
                "input_schema": schema,
            }
        )
    found.append(
        {
            "id": FINAL_ID,
            "title": "Seedance 2.5 Draft — Final 1080p API",
            "summary": "Renders a finished Seedance 2.5 draft as the same scene at 1080p.",
            "workflow": "draft-final",
            "family": "seedance-2-5-draft",
            "output": "video",
            "capabilities": ["draft-final"],
            "notes": [
                (
                    "Takes the id of a completed Seedance 2.5 Draft generation and renders it at 1080p with the "
                    "same prompt, references, duration, aspect ratio, seed and audio. Runs on the store that made "
                    "the draft."
                ),
                "Billed like a 1080p Seedance 2.5 video of the same duration (approximate: settled after generating).",
            ],
            "docs_url": DOCS,
            "input_schema": {
                "type": "object",
                "title": "Seedance 2.5 Draft final",
                "required": ["draft_generation_id"],
                "properties": {
                    "draft_generation_id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                        "description": "Id of a completed Seedance 2.5 Draft generation in HF Studio.",
                    },
                    "output_format": {"enum": ["mp4", "mov"], "type": "string", "default": "mp4"},
                },
                "additionalProperties": False,
            },
        }
    )
    return found


MODELS = _models()


def _as_draft(base: Route, provider: str) -> Route:
    """La ruta de Seedance 2.5 de la tienda, a 480p y con `draft: true`."""

    def translate(logical: dict[str, Any], explicit: frozenset[str] | None = None) -> dict[str, Any]:
        chosen = None if explicit is None else explicit | {"resolution"}
        return {**base.translate({**logical, "resolution": "480p"}, chosen), "draft": True}

    def price(i: dict, hints: dict, prices: dict) -> float | None:
        return base.price({**i, "resolution": "480p"}, hints, prices) if base.price else None

    notes = (
        *base.notes,
        f"Draft at 480p; finish it at 1080p within {EXPIRES[provider].days} days on {provider}.",
    )
    return Route(provider, base.model, translate, price, settles_later=base.settles_later, notes=notes)


def _info(source: dict[str, Any]) -> dict[str, Any]:
    """El borrador ya resuelto por el router (`hints["draft"]`, copiado en la entrada al traducir)."""
    info = source.get("draft_generation_id")
    if not isinstance(info, dict) or not info.get("task_id"):
        raise unsupported("store", "The draft could not be resolved; pick a completed Seedance 2.5 draft")
    return info


def _final_seconds(hints: dict) -> tuple[float, bool] | None:
    info = hints.get("draft") or {}
    duration = info.get("duration")
    if not isinstance(duration, int | float) or duration <= 0:
        return None
    videos = info.get("input_video_seconds") or 0
    return float(duration) + float(videos), bool(info.get("has_video"))


def apimart() -> dict[str, Route]:
    from ..providers.apimart_routes import seedance

    base = seedance()
    routes = {draft_id(m): _as_draft(base[f"bytedance/seedance-2.5/{m}"], "apimart") for m in MODES}

    def translate(logical: dict[str, Any], explicit: frozenset[str] | None = None) -> dict[str, Any]:
        out = {"draft_task_id": _info(logical)["task_id"]}
        if logical.get("output_format"):
            out["output_format"] = logical["output_format"]
        return out

    def price(i: dict, hints: dict, prices: dict) -> float | None:
        found = _final_seconds(hints)
        if found is None:
            return None
        seconds, video = found
        return per_second(prices, f"seedance-2.5|1080P{'-input' if video else ''}", seconds)

    routes[FINAL_ID] = Route(
        "apimart", "seedance-2.5", translate, price, settles_later=True,
        notes=("Same scene as the draft at 1080p; APIMart settles it by tokens after generating",),
    )  # fmt: skip
    return routes


def kie() -> dict[str, Route]:
    from ..providers.kie_routes import seedance

    base = seedance()
    routes = {draft_id(m): _as_draft(base[f"bytedance/seedance-2.5/{m}"], "kie") for m in MODES}

    def translate(logical: dict[str, Any], explicit: frozenset[str] | None = None) -> dict[str, Any]:
        return {
            "draft_task_id": _info(logical)["task_id"],
            "resolution": "1080p",
            "output_format": logical.get("output_format") or "mp4",
        }

    def price(i: dict, hints: dict, prices: dict) -> float | None:
        found = _final_seconds(hints)
        if found is None:
            return None
        seconds, video = found
        return per_second(
            prices, f"bytedance/seedance-2-5, 1080p {'with video' if video else 'no video'}", seconds
        )

    routes[FINAL_ID] = Route(
        "kie", KIE_FINAL, translate, price, settles_later=True,
        notes=("Same scene as the draft at 1080p; KIE lists no price for it, quoted like a normal 1080p video",),
    )  # fmt: skip
    return routes
