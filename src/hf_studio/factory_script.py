"""Guiones de Content Factory: el formato de un episodio y el paso que los escribe con Claude.

Un episodio es un título, un gancho y de 3 a 20 escenas; cada escena trae lo que dice el narrador
(`narration`) y lo que se dibuja (`visual`: una plantilla de `LAYOUTS` con su titular, cifras y elementos).
El mismo modelo valida la salida de Claude y la entrada de la generación (que el usuario puede haber editado).

Escribir el guion solo cuesta tokens de Claude (`ANTHROPIC_API_KEY`); el costo real sale del `usage` de la
respuesta. La llamada usa salida estructurada (JSON Schema) y después se valida estrictamente aquí.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .factory_styles import STYLES
from .space_assistant import CLAUDE_PRICES, DEFAULT_CLAUDE

LAYOUTS = (
    "title",
    "counter",
    "timer",
    "map",
    "chart",
    "comparison",
    "list",
    "quote",
    "scale",
    "timeline",
    "closing",
)
Layout = Literal[
    "title", "counter", "timer", "map", "chart", "comparison", "list", "quote", "scale", "timeline", "closing"
]

log = logging.getLogger("hf_studio.factory")

MAX_SCENES = 20
MAX_ITEMS = 6
MAX_EPISODES = 5
SCRIPT_MAX_TOKENS = 32000
TOKENS_PER_EPISODE = 6000  # un episodio de 90 s con 14 escenas cabe con holgura


def max_output_tokens(episodes: int) -> int:
    return min(SCRIPT_MAX_TOKENS, TOKENS_PER_EPISODE * max(1, episodes))


def max_cost_usd(
    topic: str,
    duration_seconds: int,
    episodes: int,
    language: str,
    style_id: str,
    model: str = DEFAULT_CLAUDE,
) -> float:
    """Tope de lo que puede costar escribir el guion: la entrada (prompt y sistema, ~4 caracteres por token, con
    margen) más el máximo de salida permitido. El cobro real (`cost_usd`) suele ser bastante menor."""
    price_in, price_out = CLAUDE_PRICES.get(model, CLAUDE_PRICES[DEFAULT_CLAUDE])
    chars = len(SYSTEM) + len(build_prompt(topic, duration_seconds, episodes, language, style_id))
    tokens_in = int(chars / 3) + 500
    return round((tokens_in * price_in + max_output_tokens(episodes) * price_out) / 1_000_000, 4)


# Palabras por segundo de un narrador neutro (edge-tts a velocidad normal ronda 2,5 en español).
WORDS_PER_SECOND = {"es": 2.5, "en": 2.6}
LANGUAGES = {
    "es": "Spanish",
    "en": "English",
    "pt": "Portuguese",
    "fr": "French",
    "it": "Italian",
    "de": "German",
}


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=60)
    value: float | None = None
    note: str | None = Field(None, max_length=80)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class Visual(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: Layout
    headline: str = Field(min_length=1, max_length=110)
    kicker: str | None = Field(None, max_length=60)
    value: float | None = None
    from_value: float | None = None
    unit: str | None = Field(None, max_length=30)
    prefix: str | None = Field(None, max_length=8)
    items: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS)


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narration: str = Field(min_length=1, max_length=700)
    visual: Visual

    @field_validator("narration")
    @classmethod
    def _spoken(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("narration is empty")
        return v


class Script(BaseModel):
    """Un episodio listo para producir."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    hook: str = Field("", max_length=300)
    scenes: list[Scene] = Field(min_length=1, max_length=MAX_SCENES)
    cliffhanger: str | None = Field(None, max_length=300)
    episode: int | None = Field(None, ge=1, le=MAX_EPISODES)
    episodes: int | None = Field(None, ge=1, le=MAX_EPISODES)
    series_title: str | None = Field(None, max_length=120)


def script_schema() -> dict:
    """JSON Schema de un episodio (para el `input_schema` del modelo de catálogo)."""
    return Script.model_json_schema()


def narration_chars(script: dict | Script) -> int:
    s = script if isinstance(script, Script) else Script.model_validate(script)
    return sum(len(sc.narration) for sc in s.scenes)


# --- Paso 1: Claude escribe el guion -----------------------------------------------------------------------------


def _nullable(kind: str) -> dict:
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


# Salida estructurada: sin límites de longitud ni numéricos (la API no los admite); se validan después.
_ITEM = _obj(
    {
        "label": {"type": "string"},
        "value": _nullable("number"),
        "note": _nullable("string"),
        "lat": _nullable("number"),
        "lon": _nullable("number"),
    }
)
_VISUAL = _obj(
    {
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "headline": {"type": "string"},
        "kicker": _nullable("string"),
        "value": _nullable("number"),
        "from_value": _nullable("number"),
        "unit": _nullable("string"),
        "prefix": _nullable("string"),
        "items": {"type": "array", "items": _ITEM},
    }
)
_EPISODE = _obj(
    {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "scenes": {"type": "array", "items": _obj({"narration": {"type": "string"}, "visual": _VISUAL})},
        "cliffhanger": _nullable("string"),
    }
)
OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": _obj({"series_title": {"type": "string"}, "episodes": {"type": "array", "items": _EPISODE}}),
}

SYSTEM = """You write scripts for faceless vertical shorts (9:16) in the "What if...?" genre: one narrator, no \
people on screen, and every frame is a data graphic drawn by code (no photos, no AI images). The voice carries \
the story; the graphic shows one concrete fact per scene.

Rules:
- Open with a hook in the first scene that makes people stay (a surprising number or consequence).
- Each scene: `narration` is what the narrator says (1 to 3 short spoken sentences, no stage directions, no \
emojis, no markdown, numbers written as the narrator should say them). `visual` is the graphic for that moment.
- Pick the `layout` that shows the fact best and fill only the fields it uses:
  title: headline (+ kicker). Use for the first scene.
  counter: a number that counts up. value (+ from_value, unit, prefix like "$"), headline says what it counts.
  timer: elapsed time. value is the amount, unit the time unit ("días", "years"...), headline the event.
  map: places. items with label + lat + lon (real coordinates), 1 to 5 places; headline the point.
  chart: 2 to 6 bars. items with label + value (same unit), unit in `unit`.
  comparison: exactly 2 items with label + value, headline the contrast.
  list: 2 to 5 short items (label, optional note).
  quote: headline is a short striking sentence (max 14 words), kicker who or what says it.
  scale: 2 to 5 items with values of very different magnitudes (shown on a log scale), unit in `unit`.
  timeline: 2 to 6 items, label = what happens, note = when ("2031", "día 3").
  closing: the last scene; headline the takeaway or, in a series, the cliffhanger.
- Headlines are short (max 8 words). Labels max 3 words. Use plausible, internally consistent figures; when \
something is speculative, the narration says so ("según algunas estimaciones").
- Vary layouts; never use the same layout three times in a row.
- Unused fields are null; `items` is [] when not used."""


def build_prompt(topic: str, duration_seconds: int, episodes: int, language: str, style_id: str) -> str:
    lang = LANGUAGES.get(language, language)
    words = round(duration_seconds * WORDS_PER_SECOND.get(language, 2.5))
    scenes = max(6, min(14, round(duration_seconds / 6)))
    style = STYLES[style_id]
    parts = [
        f"Topic: {topic.strip()}",
        f"Language of everything you write: {lang}.",
        (
            f"Each episode lasts about {duration_seconds} seconds: about {words} spoken words in total, in about "
            f"{scenes} scenes."
        ),
        f"Visual style (for tone only): {style['name']['en']}: {style['description']['en']}",
    ]
    if episodes > 1:
        parts.append(
            f"Write a series of {episodes} episodes with one arc: each episode covers a new stage of the scenario, "
            "starts with a 1-sentence recap hook and ends on a cliffhanger in `cliffhanger` and in the closing "
            "scene. Keep names, numbers and tone consistent across episodes. The last episode resolves the arc."
        )
    else:
        parts.append("Write exactly 1 episode; `cliffhanger` is null.")
    parts.append("`series_title` is a short title for the whole thing.")
    return "\n".join(parts)


class ScriptError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def usage_usd(model: str, usage: Any) -> float:
    price_in, price_out = CLAUDE_PRICES.get(model, CLAUDE_PRICES[DEFAULT_CLAUDE])
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def parse_episodes(raw: dict, episodes: int) -> tuple[str, list[dict]]:
    """Valida la salida de Claude: limpia nulos y vacíos, y la pasa por `Script`. Lanza ScriptError."""
    series = str(raw.get("series_title") or "").strip()[:120]
    out: list[dict] = []
    for n, ep in enumerate((raw.get("episodes") or [])[:episodes], start=1):
        scenes = []
        for sc in (ep.get("scenes") or [])[:MAX_SCENES]:
            visual = {k: v for k, v in (sc.get("visual") or {}).items() if v not in (None, "")}
            visual["items"] = [
                {k: v for k, v in it.items() if v not in (None, "")}
                for it in (visual.get("items") or [])[:MAX_ITEMS]
                if isinstance(it, dict) and str(it.get("label") or "").strip()
            ]
            for key, limit in (("headline", 110), ("kicker", 60), ("unit", 30), ("prefix", 8)):
                if isinstance(visual.get(key), str):
                    visual[key] = visual[key].strip()[:limit]
            for it in visual["items"]:
                it["label"] = str(it["label"]).strip()[:60]
                if isinstance(it.get("note"), str):
                    it["note"] = it["note"].strip()[:80]
            scenes.append({"narration": str(sc.get("narration") or "").strip()[:700], "visual": visual})
        episode = {
            "title": str(ep.get("title") or series or "Episode").strip()[:120],
            "hook": str(ep.get("hook") or "").strip()[:300],
            "scenes": scenes,
            "cliffhanger": (str(ep["cliffhanger"]).strip()[:300] or None) if ep.get("cliffhanger") else None,
            "series_title": series or None,
        }
        if episodes > 1:
            episode.update(episode=n, episodes=episodes)
        try:
            out.append(Script.model_validate(episode).model_dump(exclude_none=True))
        except ValidationError as exc:
            first = exc.errors()[0]
            where = "/".join(str(p) for p in first["loc"])
            raise ScriptError(
                502, "bad_script", f"Claude wrote an invalid script ({where}: {first['msg']})"
            ) from None
    if len(out) != episodes:
        raise ScriptError(502, "bad_script", f"Claude wrote {len(out)} of {episodes} episodes")
    return series, out


async def write_scripts(
    api_key: str,
    topic: str,
    style_id: str,
    duration_seconds: int,
    episodes: int,
    language: str,
    base_url: str | None = None,
    http_client_factory: Callable[[], Any] | None = None,
    model: str = DEFAULT_CLAUDE,
) -> dict:
    """Una llamada a Claude con salida estructurada. Devuelve {series_title, episodes, cost_usd, usage, model}."""
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        max_retries=0,
        base_url=base_url or None,
        http_client=http_client_factory() if http_client_factory else None,
    )
    try:
        # En streaming: un guion de varios episodios tarda; sin stream la conexión puede cortarse a mitad.
        async with client.messages.stream(
            model=model,
            max_tokens=max_output_tokens(episodes),
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": build_prompt(topic, duration_seconds, episodes, language, style_id),
                }
            ],
            output_config={"effort": "medium", "format": OUTPUT_FORMAT},
        ) as stream:
            response = await stream.get_final_message()
    except anthropic.APIStatusError as exc:
        raise ScriptError(502, "claude_error", f"Claude API error {exc.status_code}: {exc.message}") from None
    except anthropic.APIConnectionError as exc:
        log.warning("Claude no respondió al escribir un guion: %r", exc.__cause__ or exc)
        raise ScriptError(502, "claude_unreachable", "Could not reach the Claude API") from None
    finally:
        await client.close()
    cost = round(usage_usd(model, response.usage), 6)
    if response.stop_reason == "refusal":
        raise ScriptError(422, "claude_refused", "Claude declined to write this script; try another topic")
    if response.stop_reason == "max_tokens":
        raise ScriptError(502, "script_too_long", "The script did not fit; ask for fewer episodes or seconds")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        raw = json.loads(text)
    except ValueError:
        raise ScriptError(502, "bad_script", "Claude did not return JSON") from None
    series, eps = parse_episodes(raw if isinstance(raw, dict) else {}, episodes)
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return {"series_title": series, "episodes": eps, "cost_usd": cost, "usage": usage, "model": model}
