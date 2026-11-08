"""Katana, compositor: un EDL (lista de decisiones de edición) a una composición HyperFrames.

El EDL dice qué toma va en cada momento (clip generado, imagen o tramo de la referencia propia), cómo se mueve
la cámara dentro de la toma, el grado de color, las transiciones, los efectos de energía que la referencia usa
(destellos, sacudidas, golpes de zoom, separación RGB, glitch, estrobo, inversión), los textos con su animación y
las capas de acabado (grano, viñeta, líneas, franjas). Todo es HTML/CSS con animaciones WAAPI de tiempo absoluto,
que el adaptador WAAPI de HyperFrames busca cuadro a cuadro (igual que `factory_compose`).

Capas de la escena (de fuera adentro), para que los efectos no se pisen entre sí:
`#stage-shake` (traslación) > `#stage-zoom` (escala) > `#stage-fx` (filtros) > `#stage-cut` (recortes) > tomas.
Las animaciones de esas capas compartidas usan `fill: none`: solo existen mientras dura el efecto. Las de cada
toma y cada texto usan `fill: both` sobre su propio nodo.

El audio no pasa por aquí: el render sale mudo y `katana_edit` mezcla la música y los efectos con ffmpeg.
"""

from __future__ import annotations

import html
import json
import random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FRAMES = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "4:3": (1440, 1080),
    "3:4": (1080, 1440),
    "21:9": (2520, 1080),
}
MAX_SHOTS = 120
MAX_EFFECTS = 400
MAX_TEXTS = 80
MAX_DURATION = 90.0

FONTS = {
    # familia lógica del EDL -> (familia CSS, archivo, peso, estilo)
    "display": ("Anton", "Anton-Regular.woff2", 400, "normal"),
    "sans": ("Geist", "Geist-700.woff2", 700, "normal"),
    "sans_light": ("Geist", "Geist-400.woff2", 400, "normal"),
    "serif": ("LiberationSerif", "LiberationSerif-Bold.woff2", 700, "normal"),
    "serif_italic": ("LiberationSerif", "LiberationSerif-Italic.woff2", 400, "italic"),
    "mono": ("JetBrainsMono", "JetBrainsMono-Bold.woff2", 700, "normal"),
    "mono_light": ("JetBrainsMono", "JetBrainsMono-Regular.woff2", 400, "normal"),
    "rounded": ("Poppins", "Poppins-Bold.woff2", 700, "normal"),
}

CAMERA = (
    "none", "push_in", "pull_out", "pan_left", "pan_right", "pan_up", "pan_down", "drift", "whip_in",
    "crash_zoom", "rotate_in", "dutch",
)  # fmt: skip
GRADES = {
    "none": "",
    "bw": "grayscale(1) contrast(1.15)",
    "bw_crushed": "grayscale(1) contrast(1.6) brightness(0.92)",
    "high_contrast": "contrast(1.35) saturate(1.15)",
    "teal_orange": "contrast(1.12) saturate(1.2) sepia(0.18) hue-rotate(-12deg)",
    "warm": "sepia(0.25) saturate(1.25) contrast(1.05)",
    "cool": "saturate(0.9) hue-rotate(12deg) contrast(1.08) brightness(0.97)",
    "faded": "contrast(0.86) saturate(0.75) brightness(1.06)",
    "neon": "saturate(1.7) contrast(1.2)",
    "bleach": "saturate(0.45) contrast(1.4) brightness(1.04)",
    "dark": "brightness(0.78) contrast(1.25) saturate(0.9)",
    "red_mono": "grayscale(1) sepia(1) saturate(6) hue-rotate(-50deg) contrast(1.2)",
    "cyan_mono": "grayscale(1) sepia(1) saturate(4) hue-rotate(150deg) contrast(1.15)",
}
TRANSITIONS = (
    "cut",
    "fade",
    "flash",
    "white_dip",
    "black_dip",
    "whip",
    "zoom",
    "glitch",
    "slide_up",
    "slide_left",
)
EFFECTS = (
    "flash", "shake", "zoom_punch", "rgb_split", "glitch", "strobe", "invert", "bw_hit", "blur_pulse",
    "exposure_pulse", "letterbox_slam", "freeze",
)  # fmt: skip
TEXT_ANIMS = (
    "none", "pop", "slam", "type", "flicker", "slide_up", "slide_left", "word_stagger", "scale_down", "blur_in",
    "tracking_in",
)  # fmt: skip


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: str = "none"
    tint: str | None = None  # color con mezcla «color»
    tint_strength: float = Field(0.0, ge=0, le=1)

    @field_validator("preset")
    @classmethod
    def _preset(cls, v: str) -> str:
        return v if v in GRADES else "none"


class Camera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move: str = "none"
    amount: float = Field(0.08, ge=0, le=0.6)  # fracción de escala o de recorrido
    ease: Literal["linear", "in", "out", "in_out"] = "out"

    @field_validator("move")
    @classmethod
    def _move(cls, v: str) -> str:
        return v if v in CAMERA else "none"


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["video", "image", "color"] = "video"
    source: int = Field(0, ge=0, le=99)  # índice en video_urls o image_urls
    start: float = Field(ge=0)
    duration: float = Field(gt=0, le=60)
    media_start: float = Field(0.0, ge=0)  # desde dónde se toma el clip
    rate: float = Field(1.0, ge=0.25, le=4)
    fit: Literal["cover", "contain"] = "cover"
    focus_x: float = Field(0.5, ge=0, le=1)
    focus_y: float = Field(0.5, ge=0, le=1)
    flip: bool = False
    color: str = "#000000"  # para kind=color
    camera: Camera = Camera()
    grade: Grade = Grade()
    transition_in: str = "cut"
    transition_s: float = Field(0.2, ge=0.04, le=1.5)

    @field_validator("transition_in")
    @classmethod
    def _tr(cls, v: str) -> str:
        return v if v in TRANSITIONS else "cut"


class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    t: float = Field(ge=0)
    duration: float = Field(0.15, gt=0, le=8)
    intensity: float = Field(0.7, ge=0, le=1)
    color: str = "#ffffff"

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in EFFECTS:
            raise ValueError(f"unknown effect {v!r}")
        return v


class Text(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=160)
    start: float = Field(ge=0)
    duration: float = Field(gt=0, le=30)
    font: str = "display"
    size: float = Field(0.08, gt=0.01, le=0.5)  # fracción del lado corto del cuadro
    color: str = "#ffffff"
    accent: str | None = None  # color de la palabra marcada con *asteriscos*
    uppercase: bool = True
    tracking: float = Field(0.0, ge=-0.1, le=0.6)  # em
    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)
    align: Literal["left", "center", "right"] = "center"
    max_width: float = Field(0.86, gt=0.1, le=1)
    animation: str = "pop"
    exit: Literal["none", "fade", "cut", "glitch"] = "cut"
    stroke: str | None = None
    shadow: bool = True
    blend: Literal["normal", "difference", "overlay", "screen"] = "normal"
    background: str | None = None  # caja detrás del texto

    @field_validator("font")
    @classmethod
    def _font(cls, v: str) -> str:
        return v if v in FONTS else "display"

    @field_validator("animation")
    @classmethod
    def _anim(cls, v: str) -> str:
        return v if v in TEXT_ANIMS else "pop"


class Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grain: float = Field(0.0, ge=0, le=1)
    vignette: float = Field(0.0, ge=0, le=1)
    scanlines: float = Field(0.0, ge=0, le=1)
    letterbox: float = Field(0.0, ge=0, le=0.25)  # alto de cada franja (fracción)
    chroma: float = Field(0.0, ge=0, le=1)  # separación RGB constante
    border: str | None = None  # color de un marco fino
    blur_edges: float = Field(0.0, ge=0, le=1)


class SoundCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: int = Field(ge=0, le=29)  # índice en sfx_urls
    t: float = Field(ge=0)
    volume: float = Field(0.8, ge=0, le=2)


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    music_start: float = Field(0.0, ge=0)  # desde dónde se toma la música
    music_volume: float = Field(1.0, ge=0, le=2)
    fade_in: float = Field(0.0, ge=0, le=5)
    fade_out: float = Field(0.6, ge=0, le=8)
    clip_audio: float = Field(0.0, ge=0, le=2)  # volumen del sonido propio de los clips (0 = mudo)
    sfx: list[SoundCue] = Field(default_factory=list, max_length=120)


class Edl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aspect: str = "9:16"
    duration: float = Field(gt=0.5, le=MAX_DURATION)
    background: str = "#000000"
    shots: list[Shot] = Field(min_length=1, max_length=MAX_SHOTS)
    effects: list[Effect] = Field(default_factory=list, max_length=MAX_EFFECTS)
    texts: list[Text] = Field(default_factory=list, max_length=MAX_TEXTS)
    finish: Finish = Finish()
    audio: AudioPlan = AudioPlan()
    seed: int = 7

    @field_validator("aspect")
    @classmethod
    def _aspect(cls, v: str) -> str:
        if v not in FRAMES:
            raise ValueError(f"aspect must be one of {', '.join(FRAMES)}")
        return v

    @model_validator(mode="after")
    def _within(self) -> Edl:
        for s in self.shots:
            if s.start >= self.duration:
                raise ValueError(f"a shot starts at {s.start:.2f} s, after the end ({self.duration:.2f} s)")
        return self


def edl_schema() -> dict:
    return Edl.model_json_schema()


# --------------------------------------------------------------------------------------------- utilidades


def esc(s: str) -> str:
    return html.escape(s, quote=True)


_COLOR_OK = set("0123456789abcdefABCDEF#")


def color(v: str | None, default: str = "#ffffff") -> str:
    """Solo #rgb/#rrggbb/#rrggbbaa: nada que pueda escapar del CSS."""
    if isinstance(v, str) and v.startswith("#") and len(v) in (4, 7, 9) and set(v) <= _COLOR_OK:
        return v
    return default


def _ms(s: float) -> float:
    return round(s * 1000, 1)


class Anims:
    def __init__(self) -> None:
        self.items: list[list[Any]] = []

    def add(self, el: str, frames: list[dict], start: float, dur: float, easing: str = "linear",
            fill: str = "both") -> None:  # fmt: skip
        self.items.append([el, frames, _ms(start), max(1.0, _ms(dur)), easing, fill])


EASE = {
    "linear": "linear",
    "in": "cubic-bezier(.55,0,1,.45)",
    "out": "cubic-bezier(0,.55,.45,1)",
    "in_out": "cubic-bezier(.65,0,.35,1)",
}
SNAP = "cubic-bezier(.2,1.6,.4,1)"  # rebote de los textos


def _camera_frames(c: Camera, rng: random.Random) -> list[dict]:
    a = c.amount
    base = 1 + a  # escala mínima para que una traslación no deje bordes
    pct = a * 50
    m = c.move
    if m == "push_in":
        return [{"transform": "scale(1)"}, {"transform": f"scale({1 + a:.4f})"}]
    if m == "pull_out":
        return [{"transform": f"scale({1 + a:.4f})"}, {"transform": "scale(1)"}]
    if m in ("pan_left", "pan_right"):
        d = -pct if m == "pan_left" else pct
        return [
            {"transform": f"scale({base:.4f}) translateX({-d / base:.3f}%)"},
            {"transform": f"scale({base:.4f}) translateX({d / base:.3f}%)"},
        ]
    if m in ("pan_up", "pan_down"):
        d = -pct if m == "pan_up" else pct
        return [
            {"transform": f"scale({base:.4f}) translateY({-d / base:.3f}%)"},
            {"transform": f"scale({base:.4f}) translateY({d / base:.3f}%)"},
        ]
    if m == "drift":
        dx, dy = rng.uniform(-1, 1) * pct * 0.6, rng.uniform(-1, 1) * pct * 0.6
        return [
            {"transform": f"scale({base:.4f}) translate({-dx:.3f}%,{-dy:.3f}%)"},
            {"transform": f"scale({base + a * 0.3:.4f}) translate({dx:.3f}%,{dy:.3f}%)"},
        ]
    if m == "whip_in":
        return [
            {"transform": f"scale({1 + a * 2:.4f}) translateX(18%)", "filter": "blur(14px)", "offset": 0},
            {"transform": f"scale({1 + a:.4f}) translateX(0)", "filter": "blur(0px)", "offset": 0.25},
            {"transform": "scale(1) translateX(0)", "filter": "blur(0px)", "offset": 1},
        ]
    if m == "crash_zoom":
        return [
            {"transform": "scale(1)", "offset": 0},
            {"transform": f"scale({1 + a * 2.5:.4f})", "offset": 0.35},
            {"transform": f"scale({1 + a * 2.7:.4f})", "offset": 1},
        ]
    if m == "rotate_in":
        return [
            {"transform": f"scale({1.2 + a:.4f}) rotate(-6deg)"},
            {"transform": f"scale({1 + a:.4f}) rotate(0deg)"},
        ]
    if m == "dutch":
        return [
            {"transform": f"scale({1.12 + a:.4f}) rotate(-4deg)"},
            {"transform": f"scale({1.12 + a:.4f}) rotate(-6deg)"},
        ]
    return []


def _shake_frames(rng: random.Random, amp_px: float, steps: int) -> list[dict]:
    frames = []
    for i in range(steps + 1):
        k = 1 - i / max(1, steps) * 0.6  # decae un poco
        x, y = rng.uniform(-1, 1) * amp_px * k, rng.uniform(-1, 1) * amp_px * k
        r = rng.uniform(-1, 1) * amp_px * 0.02
        frames.append({"transform": f"translate({x:.1f}px,{y:.1f}px) rotate({r:.2f}deg)"})
    frames[-1] = {"transform": "translate(0px,0px) rotate(0deg)"}
    return frames


def _slices(rng: random.Random, n: int) -> list[dict]:
    """Recortes en bandas horizontales (glitch), con saltos laterales."""
    frames = []
    for _ in range(n):
        top = rng.uniform(0, 80)
        h = rng.uniform(4, 22)
        frames.append(
            {
                "clipPath": f"inset({top:.1f}% 0 {max(0, 100 - top - h):.1f}% 0)",
                "transform": f"translateX({rng.uniform(-6, 6):.1f}%)",
            }
        )
    return frames


# --------------------------------------------------------------------------------------------- composición


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{overflow:hidden;background:var(--bg)}
#root{position:relative;width:100%;height:100%;overflow:hidden;background:var(--bg)}
.layer{position:absolute;inset:0;transform-origin:50% 50%}
.shot{position:absolute;inset:0;overflow:hidden}
.cam{position:absolute;inset:0;transform-origin:50% 50%;will-change:transform}
.cam>video,.cam>img{position:absolute;inset:0;width:100%;height:100%;display:block}
.solid{position:absolute;inset:0}
.tint{position:absolute;inset:0;mix-blend-mode:color;pointer-events:none}
.flash{position:absolute;inset:0;opacity:0;pointer-events:none}
.txt{position:absolute;display:flex;pointer-events:none}
.txt .in{display:block;line-height:0.95;white-space:pre-wrap;word-break:normal;overflow-wrap:anywhere}
.txt .w{display:inline-block;white-space:pre}
.txt .acc{color:var(--acc)}
.bar{position:absolute;left:0;right:0;background:#000}
.vig{position:absolute;inset:0;pointer-events:none}
.scan{position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.35) 0 2px,transparent 2px 5px)}
.grain{position:absolute;inset:-20%;pointer-events:none;mix-blend-mode:overlay}
.border{position:absolute;inset:0;pointer-events:none}
"""


def _font_faces(used: set[str]) -> str:
    out = []
    for key in sorted(used):
        fam, file, w, s = FONTS[key]
        out.append(
            f'@font-face{{font-family:"{fam}";src:url("fonts/{file}") format("woff2");font-weight:{w};font-style:{s};}}'
        )
    return "".join(out)


def font_files(edl: Edl) -> set[str]:
    return {FONTS[t.font][1] for t in edl.texts}


def _text_html(t: Text, i: int, w: int, h: int, anims: Anims, rng: random.Random) -> str:
    short = min(w, h)
    fam, _, weight, style = FONTS[t.font]
    size = t.size * short
    raw = t.text.upper() if t.uppercase else t.text
    # *palabra* = acento de color
    parts: list[tuple[str, bool]] = []
    for k, seg in enumerate(raw.split("*")):
        if seg:
            parts.append((seg, k % 2 == 1))
    words: list[tuple[str, bool]] = []
    for seg, acc in parts:
        for tok in seg.split(" "):
            if tok:
                words.append((tok, acc))
    tid = f"t{i}"
    spans = []
    for j, (tok, acc) in enumerate(words):
        cls = "w acc" if acc else "w"
        spans.append(f'<span id="{tid}w{j}" class="{cls}">{esc(tok)}</span>')
    inner = " ".join(spans)
    justify = {"left": "flex-start", "center": "center", "right": "flex-end"}[t.align]
    box_w = t.max_width * w
    left = t.x * w - (box_w / 2 if t.align == "center" else (box_w if t.align == "right" else 0))
    shadow = "text-shadow:0 4px 24px rgba(0,0,0,.45);" if t.shadow else ""
    stroke = f"-webkit-text-stroke:{max(1, size * 0.03):.1f}px {color(t.stroke)};" if t.stroke else ""
    bg = (
        f"background:{color(t.background, '#000000')};padding:{size * 0.12:.0f}px {size * 0.25:.0f}px;"
        if t.background
        else ""
    )
    style_in = (
        f'font-family:"{fam}";font-weight:{weight};font-style:{style};font-size:{size:.1f}px;'
        f"letter-spacing:{t.tracking:.3f}em;color:{color(t.color)};--acc:{color(t.accent, color(t.color))};"
        f"text-align:{t.align};{shadow}{stroke}{bg}mix-blend-mode:{t.blend};"
    )
    wrap = (
        f'<div id="{tid}box" class="txt clip" data-start="{t.start:.3f}" data-duration="{t.duration:.3f}" '
        f'style="left:{left:.0f}px;width:{box_w:.0f}px;top:{t.y * h:.0f}px;transform:translateY(-50%);'
        f'justify-content:{justify};mix-blend-mode:{t.blend}">'
        f'<span id="{tid}" class="in" style="{style_in}">{inner}</span></div>'
    )
    a, s = t.animation, t.start
    el = tid
    if a == "pop":
        anims.add(
            el,
            [{"transform": "scale(.6)", "opacity": 0}, {"transform": "scale(1)", "opacity": 1}],
            s,
            0.22,
            SNAP,
        )
    elif a == "slam":
        anims.add(el, [{"transform": "scale(2.4)", "opacity": 0, "filter": "blur(8px)"},
                       {"transform": "scale(1)", "opacity": 1, "filter": "blur(0px)"}], s, 0.14, EASE["in"])  # fmt: skip
    elif a == "scale_down":
        anims.add(el, [{"transform": "scale(1.25)"}, {"transform": "scale(1)"}], s, t.duration, EASE["out"])
    elif a == "slide_up":
        anims.add(
            el,
            [{"transform": "translateY(60%)", "opacity": 0}, {"transform": "translateY(0)", "opacity": 1}],
            s,
            0.3,
            EASE["out"],
        )
    elif a == "slide_left":
        anims.add(
            el,
            [{"transform": "translateX(30%)", "opacity": 0}, {"transform": "translateX(0)", "opacity": 1}],
            s,
            0.3,
            EASE["out"],
        )
    elif a == "blur_in":
        anims.add(
            el,
            [{"filter": "blur(18px)", "opacity": 0}, {"filter": "blur(0px)", "opacity": 1}],
            s,
            0.35,
            EASE["out"],
        )
    elif a == "tracking_in":
        anims.add(el, [{"letterSpacing": f"{t.tracking + 0.5:.2f}em", "opacity": 0},
                       {"letterSpacing": f"{t.tracking:.2f}em", "opacity": 1}], s, 0.6, EASE["out"])  # fmt: skip
    elif a == "flicker":
        frames = [{"opacity": 1 if rng.random() > 0.45 else 0} for _ in range(8)] + [{"opacity": 1}]
        anims.add(el, frames, s, 0.32, "steps(1,end)")
    elif a in ("type", "word_stagger"):
        n = len(words)
        step = min(0.12, t.duration * 0.6 / max(1, n))
        for j in range(n):
            frames = (
                [{"opacity": 0}, {"opacity": 1}]
                if a == "type"
                else [
                    {"opacity": 0, "transform": "translateY(35%)"},
                    {"opacity": 1, "transform": "translateY(0)"},
                ]
            )
            anims.add(f"{tid}w{j}", frames, s + j * step, 0.01 if a == "type" else 0.18, EASE["out"])
    if t.exit == "fade":
        anims.add(el, [{"opacity": 1}, {"opacity": 0}], s + t.duration - 0.2, 0.2, "linear", fill="none")
    elif t.exit == "glitch":
        frames = [
            {"transform": f"translateX({rng.uniform(-8, 8):.1f}%)", "opacity": rng.choice([0, 1])}
            for _ in range(5)
        ]
        anims.add(el, frames, s + t.duration - 0.15, 0.15, "steps(1,end)", fill="none")
    return wrap


def _effect(e: Effect, i: int, w: int, h: int, anims: Anims, rng: random.Random, svg_defs: list[str]) -> str:
    """Anima la capa que toca; devuelve HTML extra (capas de destello) si hace falta."""
    k = e.intensity
    t, d = e.t, e.duration
    short = min(w, h)
    if e.type == "flash":
        fid = f"fl{i}"
        anims.add(
            fid,
            [{"opacity": 0}, {"opacity": round(0.4 + 0.6 * k, 2), "offset": 0.15}, {"opacity": 0}],
            t,
            d,
            "linear",
            "none",
        )
        return f'<div id="{fid}" class="flash" style="background:{color(e.color)}"></div>'
    if e.type == "strobe":
        fid = f"fl{i}"
        n = max(2, int(d / 0.05))
        frames = [{"opacity": (k if j % 2 == 0 else 0)} for j in range(n)] + [{"opacity": 0}]
        anims.add(fid, frames, t, d, "steps(1,end)", "none")
        return f'<div id="{fid}" class="flash" style="background:{color(e.color)}"></div>'
    if e.type == "shake":
        amp = short * (0.006 + 0.03 * k)
        steps = max(4, int(d * 30))
        anims.add("stage-shake", _shake_frames(rng, amp, steps), t, d, "steps(1,end)", "none")
    elif e.type == "zoom_punch":
        sc = 1 + 0.05 + 0.2 * k
        anims.add(
            "stage-zoom",
            [
                {"transform": "scale(1)"},
                {"transform": f"scale({sc:.3f})", "offset": 0.2},
                {"transform": "scale(1)"},
            ],
            t,
            d,
            EASE["out"],
            "none",
        )
    elif e.type == "rgb_split":
        fid = f"rgb{i}"
        off = 4 + 18 * k
        svg_defs.append(
            f'<filter id="{fid}" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
            '<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r"/>'
            '<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" result="gb"/>'
            f'<feOffset in="r" dx="{off:.1f}" dy="0" result="r2"/>'
            f'<feOffset in="gb" dx="{-off:.1f}" dy="0" result="gb2"/>'
            '<feBlend in="r2" in2="gb2" mode="screen"/></filter>'
        )
        anims.add(
            "stage-fx", [{"filter": f"url(#{fid})"}, {"filter": f"url(#{fid})"}], t, d, "linear", "none"
        )
    elif e.type == "glitch":
        n = max(3, int(d / 0.04))
        anims.add(
            "stage-cut",
            _slices(rng, n) + [{"clipPath": "inset(0 0 0 0)", "transform": "translateX(0)"}],
            t,
            d,
            "steps(1,end)",
            "none",
        )
        frames = [
            {"filter": f"hue-rotate({rng.choice([0, 90, 180, 270])}deg) saturate({rng.uniform(1, 3):.1f})"}
            for _ in range(n)
        ]
        anims.add("stage-fx", frames + [{"filter": "none"}], t, d, "steps(1,end)", "none")
    elif e.type == "invert":
        anims.add("stage-fx", [{"filter": "invert(1)"}, {"filter": "invert(1)"}], t, d, "linear", "none")
    elif e.type == "bw_hit":
        anims.add(
            "stage-fx",
            [{"filter": "grayscale(1) contrast(1.6)"}, {"filter": "grayscale(1) contrast(1.6)"}],
            t,
            d,
            "linear",
            "none",
        )
    elif e.type == "blur_pulse":
        px = 4 + 20 * k
        anims.add(
            "stage-fx",
            [
                {"filter": "blur(0px)"},
                {"filter": f"blur({px:.0f}px)", "offset": 0.3},
                {"filter": "blur(0px)"},
            ],
            t,
            d,
            EASE["out"],
            "none",
        )
    elif e.type == "exposure_pulse":
        b = 1.3 + 1.2 * k
        anims.add(
            "stage-fx",
            [
                {"filter": "brightness(1)"},
                {"filter": f"brightness({b:.2f}) contrast(1.2)", "offset": 0.15},
                {"filter": "brightness(1)"},
            ],
            t,
            d,
            "linear",
            "none",
        )
    elif e.type == "letterbox_slam":
        hb = 0.08 + 0.12 * k
        for side in ("top", "bottom"):
            anims.add(
                f"lb-{side}",
                [
                    {"height": "0%"},
                    {"height": f"{hb * 100:.1f}%", "offset": 0.15},
                    {"height": f"{hb * 100:.1f}%"},
                ],
                t,
                d,
                EASE["out"],
                "none",
            )
    elif e.type == "freeze":
        pass  # se resuelve en el EDL (una toma de imagen con el último fotograma); aquí no hace nada
    return ""


def _transition(s: Shot, idx: int, anims: Anims, rng: random.Random, prev_end: float) -> Effect | None:
    """La transición de entrada de una toma: anima su propio nodo o devuelve un efecto global equivalente."""
    t, d = s.start, s.transition_s
    sid = f"sh{idx}"
    tr = s.transition_in
    if tr == "fade":
        anims.add(sid, [{"opacity": 0}, {"opacity": 1}], t, d, "linear")
    elif tr == "slide_up":
        anims.add(sid, [{"transform": "translateY(100%)"}, {"transform": "translateY(0)"}], t, d, EASE["out"])
    elif tr == "slide_left":
        anims.add(sid, [{"transform": "translateX(100%)"}, {"transform": "translateX(0)"}], t, d, EASE["out"])
    elif tr == "whip":
        anims.add(
            sid,
            [
                {"transform": "translateX(40%)", "filter": "blur(24px)"},
                {"transform": "translateX(0)", "filter": "blur(0px)"},
            ],
            t,
            d,
            EASE["out"],
        )
    elif tr == "zoom":
        anims.add(
            sid,
            [
                {"transform": "scale(1.6)", "filter": "blur(12px)"},
                {"transform": "scale(1)", "filter": "blur(0px)"},
            ],
            t,
            d,
            EASE["out"],
        )
    elif tr == "flash":
        return Effect(type="flash", t=max(0.0, t - 0.03), duration=max(0.08, d), intensity=0.9)
    elif tr == "white_dip":
        return Effect(type="flash", t=max(0.0, t - d / 2), duration=d, intensity=1.0)
    elif tr == "black_dip":
        return Effect(type="flash", t=max(0.0, t - d / 2), duration=d, intensity=1.0, color="#000000")
    elif tr == "glitch":
        return Effect(type="glitch", t=max(0.0, t - 0.04), duration=max(0.12, d), intensity=0.7)
    return None


def build(edl: Edl, video_files: list[str], image_files: list[str]) -> str:
    """HTML de la composición. `video_files`/`image_files`: rutas relativas al proyecto, en el orden de las
    entradas (el EDL las cita por índice)."""
    w, h = FRAMES[edl.aspect]
    rng = random.Random(edl.seed)
    anims = Anims()
    svg_defs: list[str] = []
    extra: list[str] = []
    shots_html: list[str] = []
    effects = list(edl.effects)
    ordered = sorted(enumerate(edl.shots), key=lambda p: p[1].start)
    for n, (_, s) in enumerate(ordered):
        idx = n
        end = min(edl.duration, s.start + s.duration)
        # Una transición con fundido necesita que la toma anterior siga debajo: se alarga la previa.
        dur = end - s.start
        if dur <= 0:
            continue
        nxt = ordered[n + 1][1] if n + 1 < len(ordered) else None
        if nxt and nxt.transition_in in ("fade", "slide_up", "slide_left", "whip", "zoom"):
            dur = min(edl.duration - s.start, max(dur, nxt.start + nxt.transition_s - s.start))
        sid, cid = f"sh{idx}", f"cam{idx}"
        grade = GRADES[s.grade.preset]
        flip = "transform:scaleX(-1);" if s.flip else ""
        obj = f"object-fit:{s.fit};object-position:{s.focus_x * 100:.0f}% {s.focus_y * 100:.0f}%;{flip}"
        filt = f"filter:{grade};" if grade else ""
        if s.kind == "video" and s.source < len(video_files):
            media = (
                f'<video id="v{idx}" class="clip" src="{esc(video_files[s.source])}" muted playsinline '
                f'data-start="{s.start:.3f}" data-duration="{dur:.3f}" data-media-start="{s.media_start:.3f}" '
                f'data-playback-rate="{s.rate:g}" data-track-index="{n % 2}" style="{obj}{filt}"></video>'
            )
        elif s.kind == "image" and s.source < len(image_files):
            media = (
                f'<img id="i{idx}" class="clip" src="{esc(image_files[s.source])}" alt="" '
                f'data-start="{s.start:.3f}" data-duration="{dur:.3f}" data-track-index="{n % 2}" style="{obj}{filt}"/>'
            )
        else:
            media = (
                f'<div id="c{idx}" class="solid clip" data-start="{s.start:.3f}" data-duration="{dur:.3f}" '
                f'style="background:{color(s.color, "#000000")}"></div>'
            )
        tint = ""
        if s.grade.tint and s.grade.tint_strength > 0:
            tint = (
                f'<div class="tint clip" data-start="{s.start:.3f}" data-duration="{dur:.3f}" '
                f'style="background:{color(s.grade.tint)};opacity:{s.grade.tint_strength:.2f}"></div>'
            )
        shots_html.append(
            f'<div id="{sid}" class="shot"><div id="{cid}" class="cam">{media}</div>{tint}</div>'
        )
        frames = _camera_frames(s.camera, rng)
        if frames:
            anims.add(cid, frames, s.start, dur, EASE[s.camera.ease])
        fx = _transition(s, idx, anims, rng, end)
        if fx:
            effects.append(fx)
    for i, e in enumerate(sorted(effects, key=lambda e: e.t)):
        if e.t < edl.duration:
            extra.append(_effect(e, i, w, h, anims, rng, svg_defs))
    texts = [_text_html(t, i, w, h, anims, rng) for i, t in enumerate(edl.texts) if t.start < edl.duration]
    f = edl.finish
    finish = []
    if f.chroma > 0:
        off = 1 + 5 * f.chroma
        svg_defs.append(
            '<filter id="chroma" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
            '<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r"/>'
            '<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" result="gb"/>'
            f'<feOffset in="r" dx="{off:.1f}" result="r2"/><feOffset in="gb" dx="{-off:.1f}" result="gb2"/>'
            '<feBlend in="r2" in2="gb2" mode="screen"/></filter>'
        )
    if f.vignette > 0:
        finish.append(
            f'<div class="vig" style="background:radial-gradient(ellipse at center,transparent 45%,rgba(0,0,0,{0.35 + 0.6 * f.vignette:.2f}) 100%)"></div>'
        )
    if f.scanlines > 0:
        finish.append(f'<div class="scan" style="opacity:{f.scanlines:.2f}"></div>')
    if f.grain > 0:
        svg_defs.append(
            '<filter id="noise"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="3"/>'
            '<feColorMatrix type="saturate" values="0"/></filter>'
        )
        finish.append(
            f'<svg id="grain" class="grain" style="opacity:{0.08 + 0.4 * f.grain:.2f}" width="100%" height="100%">'
            '<rect width="100%" height="100%" filter="url(#noise)"/></svg>'
        )
        steps = max(2, int(edl.duration * 12))
        frames = [
            {"transform": f"translate({rng.uniform(-8, 8):.1f}%,{rng.uniform(-8, 8):.1f}%)"}
            for _ in range(steps)
        ]
        anims.add("grain", frames, 0, edl.duration, "steps(1,end)")
    lb = f.letterbox
    finish.append(f'<div id="lb-top" class="bar" style="top:0;height:{lb * 100:.1f}%"></div>')
    finish.append(f'<div id="lb-bottom" class="bar" style="bottom:0;height:{lb * 100:.1f}%"></div>')
    if f.border:
        finish.append(
            f'<div class="border" style="box-shadow:inset 0 0 0 {max(4, min(w, h) * 0.012):.0f}px {color(f.border)}"></div>'
        )
    fonts = {t.font for t in edl.texts}
    css = f":root{{--bg:{color(edl.background, '#000000')}}}" + _font_faces(fonts) + CSS
    chroma = ' style="filter:url(#chroma)"' if f.chroma > 0 else ""
    defs = (
        f'<svg width="0" height="0" style="position:absolute">{"".join(svg_defs)}</svg>' if svg_defs else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={w}, height={h}" />
<title>Katana edit</title>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="katana" data-no-timeline data-start="0" data-width="{w}" data-height="{h}" data-duration="{edl.duration:.3f}">
{defs}
<div id="stage-shake" class="layer"><div id="stage-zoom" class="layer"><div id="stage-fx" class="layer"{chroma}><div id="stage-cut" class="layer">
{"".join(shots_html)}
</div></div></div></div>
{"".join(x for x in extra if x)}
{"".join(texts)}
{"".join(finish)}
</div>
<script>
(function () {{
  var A = {json.dumps(anims.items, separators=(",", ":"))};
  for (var i = 0; i < A.length; i++) {{
    var a = A[i];
    var el = document.getElementById(a[0]);
    if (!el) continue;
    el.animate(a[1], {{ delay: a[2], duration: a[3], easing: a[4], fill: a[5] }}).pause();
  }}
}})();
</script>
</body>
</html>
"""


def snap_to_grid(times: list[float], fps: float = 30.0) -> list[float]:
    return [round(round(t * fps) / fps, 4) for t in times]


def frame_size(aspect: str) -> tuple[int, int]:
    return FRAMES.get(aspect, FRAMES["9:16"])
