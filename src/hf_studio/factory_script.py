"""Guiones de Content Factory: el formato de un episodio y el paso que los escribe con Claude.

Un episodio es un título, un gancho y de 1 a 48 escenas; cada escena trae lo que dice el narrador
(`narration`) y lo que se dibuja (`visual`: una plantilla de `LAYOUTS` con su titular, cifras y elementos).
Las plantillas técnicas traen sus propios campos: ecuaciones en LaTeX por pasos, curvas como expresiones de una
lista blanca (`factory_math`), señales como suma de senos, diagramas de nodos y flechas, código por líneas. El mismo
modelo valida la salida de Claude y la entrada de la generación (que el usuario puede haber editado): nada del
guion llega a la composición sin validar y escapar.

Escribir el guion solo cuesta tokens de Claude (`ANTHROPIC_API_KEY`) y, en los formatos que investigan, las
búsquedas web; el costo real sale del `usage` de la respuesta. Sin búsqueda la llamada usa salida estructurada (JSON
Schema); con búsqueda, Claude entrega el guion llamando a una herramienta estricta (`submit_script`), porque las
citas de la búsqueda no se pueden combinar con la salida estructurada. Después se valida estrictamente aquí.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlparse

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .factory_formats import CUSTOM, DEFAULT_FORMAT, FORMATS, format_prompt, scene_count
from .factory_math import CODE_LANGUAGES, ExprError, check_tex, parse_expr
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
    "equation",
    "plot",
    "signal",
    "spectrum",
    "surface3d",
    "objects3d",
    "globe3d",
    "bars3d",
    "particles3d",
    "diagram",
    "code",
    "sources",
)
Layout = Literal[
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
    "equation",
    "plot",
    "signal",
    "spectrum",
    "surface3d",
    "objects3d",
    "globe3d",
    "bars3d",
    "particles3d",
    "diagram",
    "code",
    "sources",
]
# Escenas «de texto»: el guion no debería encadenar más de dos.
TEXT_LAYOUTS = {"title", "quote", "list", "closing", "sources"}

log = logging.getLogger("hf_studio.factory")

MAX_SCENES = 48
MAX_ITEMS = 6
MAX_EPISODES = 5
MAX_STEPS = 8
MAX_CURVES = 4
MAX_WAVES = 5
MAX_NODES = 7
MAX_EDGES = 10
MAX_CODE_LINES = 16
MAX_CODE_CHARS = 60
MAX_SOURCES = 8
SCRIPT_MAX_TOKENS = 32000
TOKENS_PER_SCENE = 650  # una escena técnica con sus campos (los vacíos también cuentan)
WEB_SEARCH_USD = 0.01  # 10 USD por 1.000 búsquedas
WEB_MAX_USES = 4
SEARCH_RESULT_TOKENS = 15000  # cota de lo que añade cada búsqueda al contexto (se relee en cada vuelta)


def max_output_tokens(episodes: int, scenes: int = 14) -> int:
    per_episode = 2000 + TOKENS_PER_SCENE * max(3, scenes)
    return min(SCRIPT_MAX_TOKENS, per_episode * max(1, episodes))


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


class TexStep(BaseModel):
    """Un trozo de ecuación que aparece cuando el narrador dice `cue` (o repartido en la escena)."""

    model_config = ConfigDict(extra="forbid")
    tex: str = Field(min_length=1, max_length=160)
    cue: str | None = Field(None, max_length=40)
    note: str | None = Field(None, max_length=40)

    @field_validator("tex")
    @classmethod
    def _tex(cls, v: str) -> str:
        return check_tex(v)


class Curve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expr: str = Field(min_length=1, max_length=120)
    label: str | None = Field(None, max_length=30)

    @field_validator("expr")
    @classmethod
    def _expr(cls, v: str) -> str:
        try:
            return parse_expr(v, ("x", "t")).source
        except ExprError as exc:
            raise ValueError(str(exc)) from None


class Wave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    freq: float = Field(gt=0, le=1000)
    amp: float = Field(gt=0, le=100)
    phase: float | None = Field(None, ge=-7, le=7)


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=40)
    note: str | None = Field(None, max_length=50)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source: str = Field(alias="from", min_length=1, max_length=20)
    target: str = Field(alias="to", min_length=1, max_length=20)
    label: str | None = Field(None, max_length=24)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=400)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or any(c in v for c in " <>\"'"):
            raise ValueError("source url must be http(s)")
        return v


def _finite_range(v: list[float] | None, name: str) -> list[float] | None:
    if not v:
        return None
    if len(v) != 2 or not all(math.isfinite(x) and abs(x) <= 1e6 for x in v) or v[0] >= v[1]:
        raise ValueError(f"{name} must be [min, max] with min < max (|values| ≤ 1e6)")
    return [float(v[0]), float(v[1])]


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
    # Plantillas técnicas
    steps: list[TexStep] = Field(default_factory=list, max_length=MAX_STEPS)
    curves: list[Curve] = Field(default_factory=list, max_length=MAX_CURVES)
    x_range: list[float] | None = None
    y_range: list[float] | None = None
    t_range: list[float] | None = None
    x_label: str | None = Field(None, max_length=30)
    y_label: str | None = Field(None, max_length=30)
    waves: list[Wave] = Field(default_factory=list, max_length=MAX_WAVES)
    expr: str | None = Field(None, max_length=120)
    nodes: list[Node] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[Edge] = Field(default_factory=list, max_length=MAX_EDGES)
    code: list[str] = Field(default_factory=list, max_length=MAX_CODE_LINES)
    language: str | None = Field(None, max_length=20)
    highlight: list[int] = Field(default_factory=list, max_length=MAX_CODE_LINES)

    @field_validator("x_range", "y_range", "t_range")
    @classmethod
    def _ranges(cls, v, info):
        return _finite_range(v, info.field_name)

    @field_validator("expr")
    @classmethod
    def _surface(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return parse_expr(v, ("x", "y", "t")).source
        except ExprError as exc:
            raise ValueError(str(exc)) from None

    @field_validator("code")
    @classmethod
    def _code(cls, v: list[str]) -> list[str]:
        out = []
        for line in v:
            line = line.replace("\t", "    ").rstrip()
            if len(line) > MAX_CODE_CHARS or any(ord(c) < 32 for c in line):
                raise ValueError(f"code lines are at most {MAX_CODE_CHARS} printable characters")
            out.append(line)
        return out

    @field_validator("language")
    @classmethod
    def _language(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in CODE_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(CODE_LANGUAGES)}")
        return v

    @model_validator(mode="after")
    def _layout_data(self) -> Visual:
        """Cada plantilla técnica necesita sus datos: sin ellos no se dibuja nada útil."""
        lay = self.layout
        if lay == "equation" and not self.steps:
            raise ValueError("equation needs steps (LaTeX)")
        if lay == "plot":
            if not self.curves:
                raise ValueError("plot needs curves")
            if not self.x_range:
                raise ValueError("plot needs x_range")
        if lay in ("signal", "spectrum") and not self.waves:
            raise ValueError(f"{lay} needs waves")
        if lay == "surface3d" and not self.expr:
            raise ValueError("surface3d needs expr (z as a function of x, y and t)")
        if lay == "bars3d" and not [i for i in self.items if i.value is not None]:
            raise ValueError("bars3d needs items with values")
        if lay == "globe3d" and not [i for i in self.items if i.lat is not None and i.lon is not None]:
            raise ValueError("globe3d needs items with lat and lon")
        if lay == "diagram":
            if len(self.nodes) < 2:
                raise ValueError("diagram needs at least 2 nodes")
            ids = [n.id for n in self.nodes]
            if len(set(ids)) != len(ids):
                raise ValueError("diagram node ids must be unique")
            for e in self.edges:
                if e.source not in ids or e.target not in ids:
                    raise ValueError(f"edge {e.source}->{e.target} points to an unknown node")
        if lay == "code" and not self.code:
            raise ValueError("code needs lines")
        if self.highlight and any(not 1 <= h <= max(1, len(self.code)) for h in self.highlight):
            raise ValueError("highlight lists code line numbers (from 1)")
        return self


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
    sources: list[Source] = Field(default_factory=list, max_length=MAX_SOURCES)


def script_schema() -> dict:
    """JSON Schema de un episodio (para el `input_schema` del modelo de catálogo)."""
    return Script.model_json_schema(by_alias=True)


def narration_chars(script: dict | Script) -> int:
    s = script if isinstance(script, Script) else Script.model_validate(script)
    return sum(len(sc.narration) for sc in s.scenes)


# --- Paso 1: Claude escribe el guion -----------------------------------------------------------------------------


def _nullable(kind: str) -> dict:
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


_STR = {"type": "string"}
_NUM = {"type": "number"}

# Salida estructurada: sin límites de longitud ni numéricos (la API no los admite); se validan después. Los campos
# de las plantillas técnicas van juntos en `data`, una cadena con un objeto JSON: con un campo tipado por cada uno, la
# gramática compilada de la salida estricta pasa del tamaño que admite la API. `sanitize_visual` la lee y la valida.
_ITEM = _obj(
    {
        "label": _STR,
        "value": _nullable("number"),
        "note": _nullable("string"),
        "lat": _nullable("number"),
        "lon": _nullable("number"),
    }
)
_VISUAL = _obj(
    {
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "headline": _STR,
        "kicker": _nullable("string"),
        "value": _nullable("number"),
        "from_value": _nullable("number"),
        "unit": _nullable("string"),
        "prefix": _nullable("string"),
        "items": _arr(_ITEM),
        "data": _STR,
    }
)
_EPISODE = _obj(
    {
        "title": _STR,
        "hook": _STR,
        "scenes": _arr(_obj({"narration": _STR, "visual": _VISUAL})),
        "cliffhanger": _nullable("string"),
    }
)
_OUTPUT = _obj(
    {
        "series_title": _STR,
        "episodes": _arr(_EPISODE),
        "sources": _arr(_obj({"title": _STR, "url": _STR})),
    }
)
OUTPUT_FORMAT = {"type": "json_schema", "schema": _OUTPUT}
SUBMIT_TOOL = {
    "name": "submit_script",
    "description": "Deliver the finished script. Call it exactly once, after any research, with every episode.",
    "strict": True,
    "input_schema": _OUTPUT,
}

SYSTEM = """You write scripts for faceless narrated videos: one narrator, no people on screen, and every frame is \
a graphic drawn by code (no photos, no AI images). The voice carries the story; the graphic SHOWS the idea of that \
moment: one concrete fact, figure, equation, curve, mechanism or step per scene.

Rules:
- Open with a hook in the first scene that makes people stay.
- Each scene: `narration` is what the narrator says (1 to 3 short spoken sentences, no stage directions, no \
emojis, no markdown, numbers and symbols written as the narrator should say them). `visual` is the graphic.
- Pick the `layout` that shows the idea best and fill only the fields it uses. Unused fields are null, "" or [].
  title: headline (+ kicker). First scene, or a chapter card.
  counter: a number that counts up. value (+ from_value, unit, prefix like "$"); headline says what it counts.
  timer: elapsed time. value is the amount, unit the time unit, headline the event.
  map: places. items with label + lat + lon (real coordinates), 1 to 5 places.
  chart: 2 to 6 bars. items with label + value (same unit), unit in `unit`.
  comparison: exactly 2 items with label + value, headline the contrast.
  list: 2 to 5 short items (label, optional note).
  quote: headline is a short striking sentence (max 14 words), kicker who says it (real, attributed).
  scale: 2 to 5 items with values of very different magnitudes (log scale), unit in `unit`.
  timeline: 2 to 6 items, label = what happens, note = when.
- The technical templates take their fields in `data`: a string holding ONE JSON object with only the keys \
listed for that template ("" for every other layout). Example for a plot: \
{"curves": [{"expr": "sin(2*pi*x)", "label": "seno"}], "x_range": [0, 2], "y_range": [-1.5, 1.5]}
  equation: math in LaTeX revealed term by term. data.steps: 1 to 6 objects {tex, cue, note}: pieces that read left to right as ONE \
equation (e.g. tex "X_k =", then "\\sum_{n=0}^{N-1}", "x_n", "e^{-2\\pi i k n / N}"; inside `data` the JSON escapes each \\ as \\\\); each piece must be valid \
LaTeX on its own (balanced braces, never split a \\frac or a group). `cue` = one word of THIS scene's narration \
that triggers that piece (or ""); `note` = 1 to 3 words that annotate that term (or "", max 3 notes). KaTeX \
syntax; no \\href, \\def, \\newcommand, <, >, # or $ (use \\lt, \\gt).
  plot: function graphs drawn progressively. data.curves 1 to 3 with `expr` in x (and optionally t) using only \
+ - * / ^ ( ), sin cos tan exp log sqrt abs, pi, e, numbers, x, t (no other names; write 2*pi*x). \
data.x_range [min,max] required, data.y_range [min,max] optional, data.x_label/y_label short. If an expr uses t, \
the curve animates while t sweeps data.t_range [from,to] (e.g. a phase or frequency changing).
  signal: a signal as a sum of sinusoids: data.waves 1 to 4 with freq (Hz), amp, phase (radians). Shows each \
component, then their sum, then its frequency spectrum (computed with a real FFT). Use small integer frequencies \
for clarity (e.g. 3 Hz and 7 Hz).
  spectrum: the same data.waves, but focused on the transition from the time signal to its spectrum bars.
  surface3d: a 3D surface z = data.expr in x, y (and optionally t for motion) over x, y in [-3, 3], with an \
orbiting camera; e.g. "sin(x)*cos(y)" or "sin(sqrt(x^2+y^2) - 2*t)". Keep |z| about 0 to 2.
  objects3d: rotating 3D primitives (cubes, spheres, torus...), one per item (label = name), 1 to 5.
  globe3d: a rotating 3D globe with items as points (label + lat + lon), 1 to 5.
  bars3d: extruded 3D bars, items with label + value (2 to 6), unit in `unit`.
  particles3d: a 3D particle field; with data.expr (z of x, y, t) the particles ripple as that wave, otherwise a \
spiral galaxy.
  diagram: boxes and arrows that build up (pipeline or block diagram, e.g. signal -> FFT -> spectrum). data.nodes \
2 to 6 {id, label (max 3 words), note}; data.edges {from, to, label} with node ids.
  code: a code snippet revealed line by line. data.code up to 12 lines (max 46 characters each), data.language \
one of python, javascript, typescript, c, cpp, java, go, rust, bash, sql, matlab, text; data.highlight the line \
numbers (from 1) to emphasise.
  sources: a closing card listing the script's `sources` (only when you list sources).
  closing: the last scene; headline the takeaway (or, in a series, the cliffhanger).
- For math, science and engineering topics, SHOW the idea: equations, plots, signals, spectra, 3D surfaces and \
diagrams beat text cards; in explainers of ~45 s or more include at least one 3D scene (surface3d for a \
function of two variables or a spectrogram, bars3d for magnitudes, globe3d for places). Never put more than 2 text-only scenes (title, quote, list, closing, sources) in a row, \
and never use the same layout three times in a row.
- Headlines, kickers and labels are plain text (never LaTeX or markdown); math goes only in equation steps.
- Headlines are short (max 8 words). Labels max 3 words. Keep every number and every equation mathematically \
correct and consistent with the narration; when something is speculative or illustrative, the narration says so.
- `sources`: the pages you took facts from (title + url), only real pages you actually read; [] if none."""


def build_prompt(
    topic: str,
    duration_seconds: int,
    episodes: int,
    language: str,
    style_id: str,
    format_id: str = DEFAULT_FORMAT,
    custom: str | None = None,
    aspect: str = "9:16",
    research: bool = False,
) -> str:
    fmt = FORMATS.get(format_id, FORMATS[DEFAULT_FORMAT])
    lang = LANGUAGES.get(language, language)
    scenes = scene_count(fmt, duration_seconds)
    # Cada escena suma ~0,6 s de silencio (entrada y respiro) y el final 1 s más: no caben palabras ahí.
    speech = max(10.0, duration_seconds - scenes * 0.6 - 1.0)
    words = round(speech * WORDS_PER_SECOND.get(language, 2.5))
    style = STYLES[style_id]
    parts = [
        f"Topic: {topic.strip()}",
        f"Language of everything you write: {lang}.",
        format_prompt(fmt, duration_seconds, custom),
        (
            f"Each episode lasts about {duration_seconds} seconds: at most {words} spoken words in total (count them: "
            f"the narrator cannot speak faster), in about {scenes} scenes."
        ),
        f"Frame: {aspect} ({'vertical' if aspect == '9:16' else 'horizontal' if aspect == '16:9' else 'square'}).",
        f"Visual style (for tone only): {style['name']['en']}: {style['description']['en']}",
    ]
    if research:
        parts.append(
            f"Before writing, use web_search (at most {WEB_MAX_USES} searches) to check the key figures, dates and "
            "facts; then call submit_script once with the whole script and the pages you used in `sources`."
        )
    if episodes > 1:
        parts.append(
            f"Write a series of {episodes} episodes with one arc: each episode covers a new stage, starts with a "
            "1-sentence recap hook and ends on a cliffhanger in `cliffhanger` and in the closing scene. Keep names, "
            "numbers and tone consistent across episodes. The last episode resolves the arc."
        )
    else:
        parts.append("Write exactly 1 episode; `cliffhanger` is null.")
    parts.append("`series_title` is a short title for the whole thing.")
    return "\n".join(parts)


def max_cost_usd(
    topic: str,
    duration_seconds: int,
    episodes: int,
    language: str,
    style_id: str,
    model: str = DEFAULT_CLAUDE,
    format_id: str = DEFAULT_FORMAT,
    custom: str | None = None,
    aspect: str = "9:16",
    research: bool = False,
) -> float:
    """Tope de lo que puede costar escribir el guion: la entrada (prompt y sistema, ~3 caracteres por token, con
    margen) más el máximo de salida permitido y, con búsqueda web, cada búsqueda y lo que sus resultados añaden al
    contexto en cada vuelta del bucle del servidor. El cobro real (`cost_usd`) suele ser bastante menor."""
    price_in, price_out = CLAUDE_PRICES.get(model, CLAUDE_PRICES[DEFAULT_CLAUDE])
    prompt = build_prompt(
        topic, duration_seconds, episodes, language, style_id, format_id, custom, aspect, research
    )
    tokens_in = int((len(SYSTEM) + len(prompt) + (len(json.dumps(SUBMIT_TOOL)) if research else 0)) / 3) + 500
    fmt = FORMATS.get(format_id, FORMATS[DEFAULT_FORMAT])
    out = max_output_tokens(episodes, scene_count(fmt, duration_seconds))
    usd = tokens_in * price_in + out * price_out
    if research:
        uses = WEB_MAX_USES
        # Cada vuelta relee el contexto: el prompt (uses + 1 veces) y los resultados acumulados.
        usd += tokens_in * price_in * uses + SEARCH_RESULT_TOKENS * price_in * uses * (uses + 1) / 2
        usd += uses * WEB_SEARCH_USD * 1_000_000
    return round(usd / 1_000_000, 4)


class ScriptError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def usage_usd(model: str, usage: Any) -> float:
    price_in, price_out = CLAUDE_PRICES.get(model, CLAUDE_PRICES[DEFAULT_CLAUDE])
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    tokens = tokens_in * price_in + written * price_in * 1.25 + read * price_in * 0.1 + tokens_out * price_out
    return tokens / 1_000_000 + searches * WEB_SEARCH_USD


RICH_KEYS = (
    "steps",
    "curves",
    "x_range",
    "y_range",
    "t_range",
    "x_label",
    "y_label",
    "waves",
    "expr",
    "nodes",
    "edges",
    "code",
    "language",
    "highlight",
)


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def sanitize_visual(raw: dict) -> dict:
    """Limpia la escena que escribió Claude: quita vacíos, recorta textos y descarta los elementos inválidos (una
    expresión fuera de la lista blanca, un LaTeX con una orden prohibida). Si a una plantilla técnica le quedan
    pocos datos, la escena pasa a otra plantilla que sí se puede dibujar en vez de tumbar todo el guion."""
    v = dict(raw or {})
    data = v.pop("data", None)
    if isinstance(data, str) and data.strip():
        try:
            data = json.loads(data)
        except ValueError:
            data = None
    if isinstance(data, dict):
        for key in RICH_KEYS:
            if key in data and v.get(key) in (None, "", []):
                v[key] = data[key]
    v = _clean(v)
    v["items"] = [
        _clean(it)
        for it in (v.get("items") or [])[:MAX_ITEMS]
        if isinstance(it, dict) and str(it.get("label") or "").strip()
    ]
    for key, limit in (
        ("headline", 110),
        ("kicker", 60),
        ("unit", 30),
        ("prefix", 8),
        ("x_label", 30),
        ("y_label", 30),
    ):
        if isinstance(v.get(key), str):
            v[key] = v[key].strip()[:limit]
    for it in v["items"]:
        it["label"] = str(it["label"]).strip()[:60]
        if isinstance(it.get("note"), str):
            it["note"] = it["note"].strip()[:80]
    steps = []
    for st in (v.get("steps") or [])[:MAX_STEPS]:
        if not isinstance(st, dict):
            continue
        st = _clean(st)
        try:
            steps.append(
                TexStep.model_validate({**st, **{k: str(st[k])[:40] for k in ("cue", "note") if k in st}})
            )
        except ValidationError:
            continue
    v["steps"] = [s.model_dump(exclude_none=True) for s in steps]
    curves = []
    for c in (v.get("curves") or [])[:MAX_CURVES]:
        try:
            c = _clean(c)
            if "label" in c:
                c["label"] = str(c["label"])[:30]
            curves.append(Curve.model_validate(c).model_dump(exclude_none=True))
        except (ValidationError, TypeError, AttributeError):
            continue
    v["curves"] = curves
    waves = []
    for w in (v.get("waves") or [])[:MAX_WAVES]:
        try:
            waves.append(Wave.model_validate(_clean(w)).model_dump(exclude_none=True))
        except (ValidationError, TypeError, AttributeError):
            continue
    v["waves"] = waves
    for key in ("x_range", "y_range", "t_range"):
        try:
            if _finite_range(v.get(key), key) is None:
                v.pop(key, None)
        except (ValueError, TypeError):
            v.pop(key, None)
    if v.get("expr"):
        try:
            v["expr"] = parse_expr(str(v["expr"]), ("x", "y", "t")).source
        except ExprError:
            v.pop("expr")
    nodes, seen = [], set()
    for n in (v.get("nodes") or [])[:MAX_NODES]:
        try:
            n = _clean(n)
            n["label"] = str(n.get("label", ""))[:40]
            if "note" in n:
                n["note"] = str(n["note"])[:50]
            node = Node.model_validate(n)
        except (ValidationError, TypeError, AttributeError):
            continue
        if node.id not in seen:
            seen.add(node.id)
            nodes.append(node.model_dump(exclude_none=True))
    v["nodes"] = nodes
    v["edges"] = [
        _clean({"from": e.get("from"), "to": e.get("to"), "label": str(e.get("label") or "")[:24]})
        for e in (v.get("edges") or [])[:MAX_EDGES]
        if isinstance(e, dict) and e.get("from") in seen and e.get("to") in seen
    ]
    v["code"] = [
        str(line).replace("\t", "    ").rstrip()[:MAX_CODE_CHARS]
        for line in (v.get("code") or [])[:MAX_CODE_LINES]
        if isinstance(line, str)
    ]
    v["code"] = ["".join(c for c in line if ord(c) >= 32) for line in v["code"]]
    if v.get("language") is not None and str(v["language"]).strip().lower() not in CODE_LANGUAGES:
        v["language"] = "text"
    v["highlight"] = [
        h for h in (v.get("highlight") or []) if isinstance(h, int) and 1 <= h <= max(1, len(v["code"]))
    ][:MAX_CODE_LINES]
    v = {k: val for k, val in v.items() if val not in (None, "", [])} | {"items": v["items"]}
    try:
        Visual.model_validate(v)
    except ValidationError:
        if v.get("layout") in LAYOUTS:  # un layout desconocido sí es un guion inválido
            v["layout"] = "list" if len(v["items"]) >= 2 else "title"
    return v


def parse_episodes(raw: dict, episodes: int) -> tuple[str, list[dict]]:
    """Valida la salida de Claude: limpia nulos y vacíos, y la pasa por `Script`. Lanza ScriptError."""
    series = str(raw.get("series_title") or "").strip()[:120]
    sources = []
    for s in (raw.get("sources") or [])[:MAX_SOURCES]:
        try:
            sources.append(
                Source.model_validate(
                    {"title": str(s.get("title") or s.get("url") or "")[:120], "url": s.get("url")}
                ).model_dump()
            )
        except (ValidationError, AttributeError):
            continue
    out: list[dict] = []
    for n, ep in enumerate((raw.get("episodes") or [])[:episodes], start=1):
        scenes = []
        for sc in (ep.get("scenes") or [])[:MAX_SCENES]:
            visual = sanitize_visual(sc.get("visual") or {})
            if visual.get("layout") == "sources" and not sources:
                visual["layout"] = "closing"
            scenes.append({"narration": str(sc.get("narration") or "").strip()[:700], "visual": visual})
        episode = {
            "title": str(ep.get("title") or series or "Episode").strip()[:120],
            "hook": str(ep.get("hook") or "").strip()[:300],
            "scenes": scenes,
            "cliffhanger": (str(ep["cliffhanger"]).strip()[:300] or None) if ep.get("cliffhanger") else None,
            "series_title": series or None,
            "sources": sources,
        }
        if episodes > 1:
            episode.update(episode=n, episodes=episodes)
        try:
            out.append(Script.model_validate(episode).model_dump(exclude_none=True, by_alias=True))
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
    format_id: str = DEFAULT_FORMAT,
    custom: str | None = None,
    aspect: str = "9:16",
    research: bool = False,
) -> dict:
    """Una llamada a Claude (con búsqueda web si `research`). Devuelve {series_title, episodes, sources, cost_usd,
    usage, model, searches}. Hace una sola llamada (la que cubre la cotización aprobada): si la búsqueda se pausa,
    se detiene en vez de continuar."""
    if format_id == CUSTOM and not (custom or "").strip():
        raise ScriptError(422, "format_required", "Describe the custom format")
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        max_retries=0,
        base_url=base_url or None,
        http_client=http_client_factory() if http_client_factory else None,
    )
    fmt = FORMATS.get(format_id, FORMATS[DEFAULT_FORMAT])
    prompt = build_prompt(
        topic, duration_seconds, episodes, language, style_id, format_id, custom, aspect, research
    )
    request: dict = {
        "model": model,
        "max_tokens": max_output_tokens(episodes, scene_count(fmt, duration_seconds)),
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    if research:
        request["tools"] = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_MAX_USES},
            SUBMIT_TOOL,
        ]
        request["output_config"] = {"effort": "medium"}
    else:
        request["output_config"] = {"effort": "medium", "format": OUTPUT_FORMAT}
    cost = 0.0
    tokens = {"input_tokens": 0, "output_tokens": 0}
    searches = 0
    try:
        # En streaming: un guion largo tarda; sin stream la conexión puede cortarse a mitad. Con búsqueda, el bucle
        # del servidor puede pausar el turno (`pause_turn`): no se reanuda (ver abajo).
        async with client.messages.stream(**request) as stream:
            response = await stream.get_final_message()
        cost += usage_usd(model, response.usage)
        tokens["input_tokens"] += response.usage.input_tokens or 0
        tokens["output_tokens"] += response.usage.output_tokens or 0
        used = getattr(getattr(response.usage, "server_tool_use", None), "web_search_requests", 0)
        searches += used or 0
        if response.stop_reason == "pause_turn":
            # Una pausa del bucle de búsqueda no se continúa: la continuación relee todo lo acumulado y podría
            # pasarse del tope aprobado. Se detiene con lo gastado (una sola llamada, la que cubre la cotización).
            raise ScriptError(
                502, "script_incomplete", "The web research took too long; try again or turn off web search"
            )
    except anthropic.APIStatusError as exc:
        raise ScriptError(502, "claude_error", f"Claude API error {exc.status_code}: {exc.message}") from None
    except anthropic.APIConnectionError as exc:
        log.warning("Claude no respondió al escribir un guion: %r", exc.__cause__ or exc)
        raise ScriptError(502, "claude_unreachable", "Could not reach the Claude API") from None
    finally:
        await client.close()
    cost = round(cost, 6)
    if response.stop_reason == "refusal":
        raise ScriptError(422, "claude_refused", "Claude declined to write this script; try another topic")
    if response.stop_reason == "max_tokens":
        raise ScriptError(502, "script_too_long", "The script did not fit; ask for fewer episodes or seconds")
    raw: Any = None
    if research:
        raw = next(
            (b.input for b in response.content if b.type == "tool_use" and b.name == "submit_script"), None
        )
        if raw is None:
            raise ScriptError(502, "bad_script", "Claude did not deliver the script")
    else:
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            raw = json.loads(text)
        except ValueError:
            raise ScriptError(502, "bad_script", "Claude did not return JSON") from None
    series, eps = parse_episodes(raw if isinstance(raw, dict) else {}, episodes)
    return {
        "series_title": series,
        "episodes": eps,
        "sources": eps[0].get("sources", []) if eps else [],
        "cost_usd": cost,
        "usage": tokens,
        "searches": searches,
        "model": model,
    }
