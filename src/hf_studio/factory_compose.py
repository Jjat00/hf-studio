"""Composición HyperFrames de un episodio de Content Factory: HTML + CSS + animaciones WAAPI, todo determinista.

`build_composition` recibe el guion, el estilo, los tiempos de cada escena (salen de la voz) y las palabras con su
tiempo, y devuelve el `index.html` de un proyecto HyperFrames de 1080×1920. Sin GSAP ni red: las animaciones son
`element.animate(...)` con retardo absoluto y `fill: both`, que el adaptador WAAPI de HyperFrames busca fotograma
a fotograma; los contadores animan el `content` de un `::after`.

Zonas seguras del 9:16: nada de texto en los 210 px de arriba ni en los 400 de abajo (ahí van la interfaz de
TikTok, Reels y Shorts). El contenido vive entre y=300 y y=1300 y los subtítulos entre 1330 y 1510. El 16:9
(1920×1080) y el 1:1 (1080×1080) tienen su propio marco (`FRAMES`): las plantillas técnicas (`factory_rich`) usan el
escenario real y las de datos se dibujan en su caja de 920×1000 escalada al escenario.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field

from .factory_math import script_json
from .factory_styles import FONTS
from .factory_world import is_land

W, H = 1080, 1920
MARGIN = 80
STAGE_W = W - 2 * MARGIN  # 920
STAGE_TOP, STAGE_H = 300, 1000
CAPTION_TOP, CAPTION_H = 1330, 180
EASE = "cubic-bezier(0.16, 1, 0.3, 1)"
EASE_IN_OUT = "cubic-bezier(0.65, 0, 0.35, 1)"
# Ancho medio de un carácter respecto al tamaño de la fuente (para ajustar titulares sin medir en el navegador).
CHAR_W = {"Anton": 0.5, "Geist": 0.6, "JetBrains Mono": 0.62, "Poppins": 0.66, "Liberation Serif": 0.55}


@dataclass(frozen=True)
class Frame:
    """Geometría de un aspecto: lienzo, escenario (zona del contenido), banda de subtítulos y HUD."""

    aspect: str
    w: int
    h: int
    sx: int
    sy: int
    sw: int
    sh: int
    cap_top: int
    cap_h: int
    hud_top: int


FRAMES = {
    # 9:16: 210 px libres arriba y 400 abajo (interfaz de TikTok, Reels y Shorts).
    "9:16": Frame("9:16", 1080, 1920, 80, 300, 920, 1000, 1330, 180, 226),
    # 16:9 (YouTube): márgenes de título seguro del 6 % y subtítulos abajo, sobre la barra del reproductor.
    "16:9": Frame("16:9", 1920, 1080, 120, 150, 1680, 690, 860, 140, 62),
    # 1:1 (feed): HUD arriba, subtítulos abajo, márgenes de 80 px.
    "1:1": Frame("1:1", 1080, 1080, 80, 140, 920, 640, 800, 150, 52),
}
DESIGN_W, DESIGN_H = STAGE_W, STAGE_H  # caja de las plantillas de datos (se escala fuera del 9:16)


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class SceneTime:
    start: float
    duration: float


@dataclass
class _Ctx:
    style: dict
    lang: str
    anims: list = field(default_factory=list)
    n: int = 0
    frame: Frame = FRAMES["9:16"]
    width: float = STAGE_W  # ancho útil de la escena que se está construyendo
    words: list = field(default_factory=list)
    tex: list = field(default_factory=list)  # trozos de LaTeX que KaTeX dibuja al cargar
    gl: list = field(default_factory=list)  # escenas 3D (three.js)

    def uid(self, prefix: str = "e") -> str:
        self.n += 1
        return f"{prefix}{self.n}"

    def anim(
        self,
        el: str,
        frames: list[dict],
        t: float,
        dur: float,
        easing: str = EASE,
        pseudo: str | None = None,
        iterations: int = 1,
    ) -> None:
        self.anims.append(
            [
                el,
                frames,
                round(max(t, 0) * 1000),
                max(1, round(dur * 1000)),
                easing,
                pseudo,
                max(1, iterations),
            ]
        )

    def enter(self, el: str, t: float, dy: int = 40, dur: float = 0.7) -> None:
        self.anim(
            el,
            [
                {"opacity": 0, "transform": f"translateY({dy}px)"},
                {"opacity": 1, "transform": "translateY(0px)"},
            ],
            t,
            dur,
        )

    def reveal(self, el: str, t: float, dur: float = 0.8) -> None:
        self.anim(
            el,
            [
                {"clipPath": "inset(0 0 100% 0)", "transform": "translateY(30px)"},
                {"clipPath": "inset(0 0 -20% 0)", "transform": "translateY(0px)"},
            ],
            t,
            dur,
        )

    def pop(self, el: str, t: float, dur: float = 0.55) -> None:
        self.anim(
            el,
            [
                {"opacity": 0, "transform": "scale(0.4)"},
                {"opacity": 1, "transform": "scale(1.08)", "offset": 0.7},
                {"opacity": 1, "transform": "scale(1)"},
            ],
            t,
            dur,
        )

    def count(self, el: str, start: float, end: float, t: float, dur: float, fmt) -> None:
        """Cuenta de `start` a `end` (salida rápida y llegada suave) animando el `content` del `::after`."""
        steps = 36
        frames = []
        for i in range(steps + 1):
            p = i / steps
            eased = 1 - (1 - p) ** 3
            frames.append({"content": _css_string(fmt(start + (end - start) * eased)), "offset": round(p, 4)})
        self.anim(el, frames, t, dur, "linear", pseudo="::after")


def _css_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


# --- Números y texto ---------------------------------------------------------------------------------------------


def decimals_of(*values: float | None) -> int:
    best = 0
    for v in values:
        if v is None or float(v).is_integer():
            continue
        text = f"{abs(v):.6f}".rstrip("0")
        best = max(best, min(2, len(text.split(".")[1])))
    return best


def fmt_number(v: float, lang: str = "es", decimals: int = 0) -> str:
    """1234567.5 -> «1.234.567,5» en español y «1,234,567.5» en inglés."""
    text = f"{abs(v):,.{decimals}f}"
    if lang.startswith("es") or lang[:2] in ("pt", "fr", "it", "de"):
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("−" if v < 0 and round(abs(v), decimals) != 0 else "") + text


def wrap_lines(text: str, size: float, width: float, k: float) -> int:
    """Líneas que ocupa `text` con ajuste por palabras (aproximado con un ancho medio por carácter)."""
    per_line = max(1, int(width / (size * k)))
    lines, used = 1, 0
    for word in text.split():
        n = len(word)
        if n > per_line:  # una palabra que no cabe en la línea nunca se parte: este tamaño no sirve
            return 999
        if used and used + 1 + n > per_line:
            lines += 1
            used = n
        else:
            used = used + (1 if used else 0) + n
    return lines


def fit_size(
    text: str,
    font: str,
    max_size: float,
    min_size: float,
    max_lines: int,
    width: float = STAGE_W,
    upper: bool = False,
) -> int:
    k = CHAR_W.get(font, 0.6) * (1.08 if upper and font != "Anton" else 1.0)
    size = max_size
    while size > min_size and wrap_lines(text, size, width, k) > max_lines:
        size -= 2
    return int(size)


# --- Plantillas de escena ----------------------------------------------------------------------------------------


def _hl(
    ctx: _Ctx,
    text: str,
    t: float,
    max_size: int = 96,
    max_lines: int = 3,
    min_size: int = 44,
    cls: str = "hl",
) -> str:
    st = ctx.style
    font = st["fonts"]["display"]
    size = fit_size(
        text,
        font,
        max_size * st["display_scale"],
        min_size,
        max_lines,
        width=ctx.width,
        upper=st["uppercase"],
    )
    el = ctx.uid("h")
    ctx.reveal(el, t)
    return f'<div id="{el}" class="{cls}" style="font-size:{size}px">{esc(text)}</div>'


def _kicker(ctx: _Ctx, text: str | None, t: float) -> str:
    if not text:
        return ""
    el = ctx.uid("k")
    ctx.enter(el, t, dy=20, dur=0.5)
    return f'<div id="{el}" class="kicker">{esc(text)}</div>'


def _value_text(v: dict, value: float, lang: str, decimals: int) -> str:
    return f"{v.get('prefix') or ''}{fmt_number(value, lang, decimals)}"


def layout_title(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    kicker = v.get("kicker") or meta.get("series_label")
    bar = ctx.uid("b")
    ctx.anim(bar, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], t + 0.5, 0.9, EASE_IN_OUT)
    badge = ""
    if meta.get("episode_label"):
        b = ctx.uid("ep")
        ctx.pop(b, t + 0.9)
        badge = f'<div id="{b}" class="badge">{esc(meta["episode_label"])}</div>'
    return (
        f'<div class="col center">{_kicker(ctx, kicker, t + 0.1)}'
        f"{_hl(ctx, v['headline'], t + 0.2, max_size=150, max_lines=4, cls='hl hero')}"
        f'<div id="{bar}" class="bar"></div>{badge}</div>'
    )


def layout_counter(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    end = float(v.get("value") if v.get("value") is not None else 0)
    start = float(v.get("from_value") or 0)
    dec = decimals_of(start, end)
    final = _value_text(v, end, ctx.lang, dec)
    font = ctx.style["fonts"]["display"]
    size = fit_size(final, font, 230 * ctx.style["display_scale"], 70, 1)
    num = ctx.uid("n")
    run = min(max(1.2, d * 0.55), 3.5)
    ctx.enter(num, t + 0.3, dy=30, dur=0.5)
    ctx.count(num, start, end, t + 0.3, run, lambda x: _value_text(v, x, ctx.lang, dec))
    meter = ctx.uid("m")
    ctx.anim(
        meter,
        [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}],
        t + 0.3,
        run,
        "cubic-bezier(0,0,.2,1)",
    )
    unit = ""
    if v.get("unit"):
        u = ctx.uid("u")
        ctx.enter(u, t + 0.5, dy=20)
        unit = f'<div id="{u}" class="unit">{esc(v["unit"])}</div>'
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 84)}'
        f'<div class="spacer"></div><div id="{num}" class="num" style="font-size:{size}px"></div>{unit}'
        f'<div class="meter"><div id="{meter}" class="meter-fill"></div></div><div class="spacer"></div></div>'
    )


def layout_timer(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    end = float(v.get("value") if v.get("value") is not None else 0)
    start = float(v.get("from_value") or 0)
    dec = decimals_of(start, end)
    run = min(max(1.5, d * 0.6), 4.0)
    num = ctx.uid("n")
    ctx.count(num, start, end, t + 0.3, run, lambda x: _value_text(v, x, ctx.lang, dec))
    final = _value_text(v, end, ctx.lang, dec)
    size = fit_size(final, ctx.style["fonts"]["mono"], 150, 56, 1, width=520)
    r = 300
    circ = 2 * math.pi * r
    arc, hand, dial = ctx.uid("a"), ctx.uid("hd"), ctx.uid("dl")
    ctx.anim(arc, [{"strokeDashoffset": f"{circ:.1f}"}, {"strokeDashoffset": "0"}], t + 0.3, run, "linear")
    turns = max(1, min(8, round(run)))
    ctx.anim(
        hand,
        [{"transform": "rotate(0deg)"}, {"transform": f"rotate({360 * turns}deg)"}],
        t + 0.3,
        run,
        "cubic-bezier(0,0,.3,1)",
    )
    ctx.pop(dial, t + 0.1, 0.6)
    ticks = "".join(
        f'<line x1="0" y1="{-r + 18 if i % 5 else -r + 34}" x2="0" y2="{-r + 4}" transform="rotate({i * 6})" '
        f'class="{"tick-major" if i % 5 == 0 else "tick"}"/>'
        for i in range(60)
    )
    unit = esc(v.get("unit") or "")
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 76, 2)}'
        f'<div class="dial-wrap"><svg id="{dial}" class="dial" viewBox="-330 -330 660 660" width="660" height="660">'
        f'<circle r="{r}" class="dial-ring"/>{ticks}'
        f'<circle id="{arc}" r="{r - 50}" class="dial-arc" stroke-dasharray="{circ:.1f}" '
        f'transform="rotate(-90)" style="stroke-dashoffset:{circ:.1f}"/>'
        f'<g id="{hand}" class="hand"><line x1="0" y1="20" x2="0" y2="-{r - 70}"/></g><circle r="10" class="hub"/></svg>'
        f'<div class="dial-center"><div id="{num}" class="num mono" style="font-size:{size}px"></div>'
        f'<div class="unit">{unit}</div></div></div></div>'
    )


def _map_box(items: list[dict], width: float, height: float) -> tuple[float, float, float, float]:
    pts = [(i["lon"], i["lat"]) for i in items if i.get("lat") is not None and i.get("lon") is not None]
    if not pts:
        return -170.0, 190.0, -58.0, 82.0
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    span_lon = min(360.0, max(70.0, (max(lons) - min(lons)) * 1.5 + 40))
    span_lat = min(140.0, max(span_lon * height / width, (max(lats) - min(lats)) * 1.4 + 30))
    cx, cy = (max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2
    lat0 = min(max(cy - span_lat / 2, -60.0), 84.0 - span_lat)
    return cx - span_lon / 2, cx + span_lon / 2, lat0, lat0 + span_lat


def layout_map(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    mw = STAGE_W
    lon0, lon1, lat0, lat1 = _map_box(v.get("items") or [], mw, 680)
    mh = min(680, round(mw * (lat1 - lat0) / (lon1 - lon0)))
    cols = 46
    step = (lon1 - lon0) / cols
    dots = []
    lat = lat1 - step / 2
    while lat > lat0:
        lon = lon0 + step / 2
        while lon < lon1:
            if is_land(((lon + 180) % 360) - 180, lat):
                x = (lon - lon0) / (lon1 - lon0) * mw
                y = (lat1 - lat) / (lat1 - lat0) * mh
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{mw / cols * 0.3:.1f}"/>')
            lon += step
        lat -= step
    land = ctx.uid("land")
    ctx.anim(land, [{"opacity": 0}, {"opacity": 1}], t, 0.8)
    pins, labels, arcs = [], [], []
    taken: list[tuple[float, float, float]] = []
    placed = [i for i in (v.get("items") or []) if i.get("lat") is not None and i.get("lon") is not None][:5]
    gap = min(0.6, max(0.25, d * 0.5 / max(1, len(placed))))
    prev = None
    for n, it in enumerate(placed):
        x = (it["lon"] - lon0) / (lon1 - lon0) * mw
        y = (lat1 - it["lat"]) / (lat1 - lat0) * mh
        at = t + 0.5 + n * gap
        p, ring, lab = ctx.uid("p"), ctx.uid("r"), ctx.uid("l")
        ctx.pop(p, at)
        ctx.anim(
            ring,
            [{"transform": "scale(0.3)", "opacity": 0.9}, {"transform": "scale(2.4)", "opacity": 0}],
            at,
            1.4,
            "cubic-bezier(0,0,.2,1)",
            iterations=max(1, int((d - (at - t)) / 1.4)),
        )
        ctx.enter(lab, at + 0.15, dy=14, dur=0.4)
        pins.append(
            f'<g transform="translate({x:.1f},{y:.1f})"><circle id="{ring}" r="22" class="pin-ring"/>'
            f'<circle id="{p}" r="13" class="pin"/></g>'
        )
        left = x > mw * 0.62
        lx = max(0.0, min(mw - 20, x + (-24 if left else 24)))
        anchor = "right" if left else "left"
        pos = f"right:{mw - lx:.0f}px" if left else f"left:{lx:.0f}px"
        # Etiquetas que chocarían con la anterior (cerca en x) se alternan arriba y abajo del pin.
        width = len(it["label"]) * 19 + 30
        span = (lx - width, lx) if left else (lx, lx + width)
        clash = any(abs(ty - y) < 60 and span[0] < s1 and s0 < span[1] for s0, s1, ty in taken)
        top = y + 30 if clash else y - 26
        taken.append((span[0], span[1], top))
        labels.append(
            f'<div id="{lab}" class="pin-label {anchor}" style="{pos};top:{max(0.0, top):.0f}px">'
            f"{esc(it['label'])}</div>"
        )
        if prev:
            (px, py) = prev
            mx, my = (px + x) / 2, min(py, y) - abs(x - px) * 0.35 - 30
            a = ctx.uid("arc")
            length = math.hypot(x - px, y - py) * 1.4 + 60
            ctx.anim(a, [{"strokeDashoffset": f"{length:.0f}"}, {"strokeDashoffset": "0"}], at - 0.1, 0.6)
            arcs.append(
                f'<path id="{a}" d="M{px:.1f},{py:.1f} Q{mx:.1f},{my:.1f} {x:.1f},{y:.1f}" class="route" '
                f'stroke-dasharray="{length:.0f}" style="stroke-dashoffset:{length:.0f}"/>'
            )
        prev = (x, y)
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 76, 2)}'
        f'<div class="map" style="width:{mw}px;height:{mh}px"><svg width="{mw}" height="{mh}" '
        f'viewBox="0 0 {mw} {mh}"><g id="{land}" class="land">{"".join(dots)}</g>{"".join(arcs)}'
        f"{''.join(pins)}</svg>{''.join(labels)}</div></div>"
    )


def layout_chart(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = [i for i in (v.get("items") or []) if i.get("value") is not None][:6] or [
        {"label": "—", "value": 1}
    ]
    top = max(abs(float(i["value"])) for i in items) or 1
    dec = decimals_of(*[i["value"] for i in items])
    n = len(items)
    gap = 28
    bw = (STAGE_W - gap * (n - 1)) / n
    bars = []
    for k, it in enumerate(items):
        hgt = max(8.0, abs(float(it["value"])) / top * 480)
        at = t + 0.4 + k * min(0.25, d * 0.3 / n)
        b, val, lab = ctx.uid("bar"), ctx.uid("bv"), ctx.uid("bl")
        ctx.anim(b, [{"transform": "scaleY(0)"}, {"transform": "scaleY(1)"}], at, 0.8)
        ctx.enter(val, at + 0.5, dy=16, dur=0.4)
        ctx.enter(lab, at, dy=10, dur=0.4)
        hi = " hi" if abs(float(it["value"])) == top else ""
        size = fit_size(
            _value_text(v, float(it["value"]), ctx.lang, dec),
            ctx.style["fonts"]["mono"],
            44,
            22,
            1,
            width=bw + 10,
        )
        bars.append(
            f'<div class="bar-col" style="width:{bw:.0f}px"><div id="{val}" class="bar-val" style="font-size:{size}px">'
            f"{esc(_value_text(v, float(it['value']), ctx.lang, dec))}</div>"
            f'<div id="{b}" class="bar-fill{hi}" style="height:{hgt:.0f}px"></div>'
            f'<div id="{lab}" class="bar-label">{esc(it["label"])}</div></div>'
        )
    unit = f'<div class="unit small">{esc(v["unit"])}</div>' if v.get("unit") else ""
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 80, 2)}{unit}'
        f'<div class="chart">{"".join(bars)}</div></div>'
    )


def layout_comparison(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = (v.get("items") or [])[:2]
    while len(items) < 2:
        items.append({"label": "—"})
    vals = [abs(float(i["value"])) if i.get("value") is not None else 0.0 for i in items]
    top = max(vals) or 1
    dec = decimals_of(*[i.get("value") for i in items])
    cols = []
    for k, it in enumerate(items):
        at = t + 0.4 + k * 0.5
        c, b, nm = ctx.uid("c"), ctx.uid("cb"), ctx.uid("cn")
        ctx.enter(c, at, dy=40)
        ctx.anim(b, [{"transform": "scaleY(0)"}, {"transform": "scaleY(1)"}], at + 0.2, 0.9)
        txt = _value_text(v, float(it["value"]), ctx.lang, dec) if it.get("value") is not None else ""
        if it.get("value") is not None:
            ctx.count(nm, 0, float(it["value"]), at + 0.2, 1.0, lambda x: _value_text(v, x, ctx.lang, dec))
        size = fit_size(
            txt or "0", ctx.style["fonts"]["display"], 110 * ctx.style["display_scale"], 40, 1, width=400
        )
        sub = it.get("note") or v.get("unit")
        unit = f'<div class="unit small">{esc(sub)}</div>' if sub else ""
        cols.append(
            f'<div id="{c}" class="cmp-col{" hi" if k == 1 else ""}"><div class="cmp-label">{esc(it["label"])}</div>'
            f'<div id="{nm}" class="num" style="font-size:{size}px"></div>{unit}'
            f'<div class="cmp-track"><div id="{b}" class="cmp-fill" style="height:{max(6, vals[k] / top * 100):.0f}%">'
            f"</div></div></div>"
        )
    vs = ctx.uid("vs")
    ctx.pop(vs, t + 0.7)
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 80, 2)}'
        f'<div class="cmp">{cols[0]}<div id="{vs}" class="vs">VS</div>{cols[1]}</div></div>'
    )


def layout_list(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = (v.get("items") or [])[:5]
    rows = []
    for k, it in enumerate(items):
        at = t + 0.45 + k * min(0.9, d * 0.65 / max(1, len(items)))
        r = ctx.uid("li")
        ctx.enter(r, at, dy=0, dur=0.5)
        ctx.anim(r, [{"transform": "translateX(-60px)"}, {"transform": "translateX(0px)"}], at, 0.6)
        note = f'<div class="li-note">{esc(it["note"])}</div>' if it.get("note") else ""
        rows.append(
            f'<div id="{r}" class="li"><div class="li-n">{k + 1:02d}</div><div class="li-body">'
            f'<div class="li-label">{esc(it["label"])}</div>{note}</div></div>'
        )
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 84, 2)}'
        f'<div class="list">{"".join(rows)}</div></div>'
    )


def layout_quote(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    mark = ctx.uid("q")
    ctx.pop(mark, t)
    who = ""
    if v.get("kicker"):
        w = ctx.uid("w")
        ctx.enter(w, t + 0.9, dy=16)
        who = f'<div id="{w}" class="who">— {esc(v["kicker"])}</div>'
    return (
        f'<div class="col center"><div id="{mark}" class="qmark">“</div>'
        f"{_hl(ctx, v['headline'], t + 0.25, 104, 5, cls='hl quote')}{who}</div>"
    )


def layout_scale(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = [i for i in (v.get("items") or []) if i.get("value") is not None][:5] or [
        {"label": "—", "value": 1}
    ]
    vals = [max(abs(float(i["value"])), 1e-9) for i in items]
    lo, hi = math.floor(math.log10(min(vals))), math.ceil(math.log10(max(vals)))
    if hi - lo < 1:
        hi = lo + 1
    dec = decimals_of(*vals)
    rows = []
    for k, it in enumerate(sorted(items, key=lambda i: abs(float(i["value"])))):
        frac = (math.log10(max(abs(float(it["value"])), 1e-9)) - lo) / (hi - lo)
        at = t + 0.4 + k * min(0.6, d * 0.6 / len(items))
        b, row = ctx.uid("sb"), ctx.uid("sr")
        ctx.enter(row, at, dy=20, dur=0.5)
        ctx.anim(b, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], at + 0.1, 0.9)
        rows.append(
            f'<div id="{row}" class="sc-row"><div class="sc-head"><span class="sc-label">{esc(it["label"])}'
            f'</span><span class="sc-val">{esc(_value_text(v, float(it["value"]), ctx.lang, dec))}'
            f'{(" " + esc(v["unit"])) if v.get("unit") else ""}</span></div><div class="sc-track">'
            f'<div id="{b}" class="sc-fill" style="width:{max(2.0, frac * 100):.1f}%"></div></div></div>'
        )
    ticks = "".join(
        f'<span style="left:{(e - lo) / (hi - lo) * 100:.2f}%">10<sup>{e}</sup></span>'
        for e in range(lo, hi + 1)
        if (hi - lo) <= 12 or (e - lo) % 2 == 0
    )
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 80, 2)}'
        f'<div class="scale">{"".join(rows)}<div class="sc-axis">{ticks}</div></div></div>'
    )


def layout_timeline(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = (v.get("items") or [])[:6]
    line = ctx.uid("tl")
    run = min(max(1.0, d * 0.7), 4.0)
    ctx.anim(line, [{"transform": "scaleY(0)"}, {"transform": "scaleY(1)"}], t + 0.3, run, "linear")
    rows = []
    for k, it in enumerate(items):
        at = t + 0.35 + k * run / max(1, len(items))
        r, dot = ctx.uid("ti"), ctx.uid("td")
        ctx.enter(r, at, dy=0, dur=0.5)
        ctx.anim(r, [{"transform": "translateX(40px)"}, {"transform": "translateX(0px)"}], at, 0.6)
        ctx.pop(dot, at, 0.4)
        when = it.get("note") or (
            fmt_number(float(it["value"]), ctx.lang, decimals_of(it["value"]))
            if it.get("value") is not None
            else ""
        )
        rows.append(
            f'<div class="ti"><div id="{dot}" class="ti-dot"></div><div id="{r}" class="ti-body">'
            f'<div class="ti-when">{esc(when)}</div><div class="ti-label">{esc(it["label"])}</div></div></div>'
        )
    return (
        f'<div class="col">{_kicker(ctx, v.get("kicker"), t)}{_hl(ctx, v["headline"], t + 0.05, 80, 2)}'
        f'<div class="timeline"><div id="{line}" class="tl-line"></div>{"".join(rows)}</div></div>'
    )


def layout_closing(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    badge = ""
    if meta.get("to_be_continued"):
        b = ctx.uid("tbc")
        ctx.pop(b, t + 0.8)
        badge = f'<div id="{b}" class="badge big">{esc(meta["to_be_continued"])}</div>'
    bar = ctx.uid("b")
    ctx.anim(bar, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], t + 0.4, 0.9, EASE_IN_OUT)
    return (
        f'<div class="col center">{_kicker(ctx, v.get("kicker") or meta.get("series_label"), t)}'
        f'{_hl(ctx, v["headline"], t + 0.15, 130, 4, cls="hl hero")}<div id="{bar}" class="bar"></div>'
        f"{badge}</div>"
    )


LAYOUT_BUILDERS = {
    "title": layout_title,
    "counter": layout_counter,
    "timer": layout_timer,
    "map": layout_map,
    "chart": layout_chart,
    "comparison": layout_comparison,
    "list": layout_list,
    "quote": layout_quote,
    "scale": layout_scale,
    "timeline": layout_timeline,
    "closing": layout_closing,
}


# --- Subtítulos --------------------------------------------------------------------------------------------------


def caption_groups(words: list[Word], max_words: int = 3, max_chars: int = 20) -> list[list[Word]]:
    """Agrupa las palabras en páginas cortas: corta tras puntuación, en pausas y al llenarse."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (
            len(cur) >= max_words
            or len(" ".join(x.text for x in cur)) + 1 + len(w.text) > max_chars
            or w.start - cur[-1].end > 0.35
        ):
            groups.append(cur)
            cur = []
        cur.append(w)
        if w.text[-1:] in ".,;:?!…":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _captions(ctx: _Ctx, words: list[Word], total: float) -> str:
    groups = caption_groups(words)
    out = []
    for i, g in enumerate(groups):
        start = g[0].start
        nxt = groups[i + 1][0].start if i + 1 < len(groups) else total
        end = min(nxt, g[-1].end + 0.6)
        if end - start < 0.12:
            continue
        gid = ctx.uid("cg")
        box = ctx.uid("cb")
        ctx.anim(
            box,
            [{"transform": "scale(0.85)", "opacity": 0}, {"transform": "scale(1)", "opacity": 1}],
            start,
            0.18,
            EASE,
        )
        spans = []
        for w in g:
            wid = ctx.uid("w")
            ctx.anim(
                wid,
                [
                    {"color": "var(--cap-ink)", "transform": "scale(1)"},
                    {"color": "var(--hi)", "transform": "scale(1.06)"},
                ],
                w.start,
                0.08,
            )
            spans.append(f'<span id="{wid}" class="cw">{esc(w.text)}</span>')
        out.append(
            f'<div id="{gid}" class="cap clip" data-start="{start:.3f}" data-duration="{end - start:.3f}" '
            f'data-track-index="3"><div id="{box}" class="cap-box">{" ".join(spans)}</div></div>'
        )
    return "".join(out)


# --- Fondos ------------------------------------------------------------------------------------------------------


def _rand(seed: int):
    state = seed & 0xFFFFFFFF or 1

    def nxt() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        return (state & 0xFFFFFFFF) / 0xFFFFFFFF

    return nxt


def _background(ctx: _Ctx, total: float) -> str:
    motif = ctx.style["motif"]
    loops = max(1, int(total / 2.0))
    if motif == "neon":
        floor, sun = ctx.uid("fl"), ctx.uid("sun")
        ctx.anim(
            floor,
            [{"backgroundPosition": "0px 0px"}, {"backgroundPosition": "0px 120px"}],
            0,
            2.0,
            "linear",
            iterations=loops,
        )
        ctx.anim(
            sun, [{"transform": "translateY(30px)"}, {"transform": "translateY(0px)"}], 0, total, "linear"
        )
        return (
            f'<div class="sky"></div><div id="{sun}" class="sun"></div>'
            f'<div class="horizon"></div><div class="floor-wrap"><div id="{floor}" class="floor"></div></div>'
        )
    if motif == "atlas":
        lines = "".join(
            f'<path d="M{x},0 Q{x + (540 - x) * 0.25},960 {x},1920"/>' for x in range(-180, 1300, 180)
        )
        lines += "".join(f'<line x1="0" y1="{y}" x2="1080" y2="{y}"/>' for y in range(160, 1920, 220))
        rose = ctx.uid("rose")
        ctx.anim(rose, [{"transform": "rotate(-20deg)"}, {"transform": "rotate(15deg)"}], 0, total, "linear")
        star = "".join(
            f'<polygon points="0,-120 14,-14 0,0 -14,-14" transform="rotate({a})"/>'
            for a in range(0, 360, 90)
        )
        star += "".join(
            f'<polygon points="0,-70 9,-9 0,0 -9,-9" transform="rotate({a})" class="minor"/>'
            for a in range(45, 360, 90)
        )
        return (
            f'<svg class="paper" width="1080" height="1920"><filter id="grain"><feTurbulence type="fractalNoise" '
            f'baseFrequency="0.8" numOctaves="3" seed="7"/><feColorMatrix values="0 0 0 0 0.35 0 0 0 0 0.25 0 0 0 0 '
            f'0.1 0 0 0 0.35 0"/></filter><rect width="1080" height="1920" filter="url(#grain)"/></svg>'
            f'<svg class="graticule" width="1080" height="1920">{lines}</svg>'
            f'<svg class="rose" width="320" height="320" viewBox="-160 -160 320 320"><g id="{rose}">'
            f'<circle r="140"/><circle r="128" class="thin"/>{star}</g></svg>'
            f'<div class="vignette"></div>'
        )
    if motif == "blueprint":
        marks = "".join(
            f'<div class="reg" style="left:{x}px;top:{y}px"></div>'
            for x, y in ((40, 230), (1000, 230), (40, 1540), (1000, 1540))
        )
        return (
            f'<div class="grid-minor"></div><div class="grid-major"></div>{marks}'
            f'<div class="titleblock"><span>HF STUDIO · CONTENT FACTORY</span><span>ESC 1:1</span></div>'
        )
    if motif == "phosphor":
        return '<div class="glowbg"></div><div class="scan"></div><div class="vignette"></div>'
    if motif == "swiss":
        cols = "".join(f'<div class="rule" style="left:{80 + i * 184}px"></div>' for i in range(6))
        blk = ctx.uid("blk")
        ctx.anim(blk, [{"transform": "translateX(-100%)"}, {"transform": "translateX(0%)"}], 0, 0.9)
        return f'{cols}<div id="{blk}" class="block"></div><div class="dot-red"></div>'
    if motif == "chalk":
        rnd = _rand(11)
        smudges = "".join(
            f'<div class="smudge" style="left:{rnd() * 1000:.0f}px;top:{rnd() * 1800:.0f}px;'
            f'width:{200 + rnd() * 400:.0f}px;height:{120 + rnd() * 260:.0f}px"></div>'
            for _ in range(9)
        )
        return f'{smudges}<div class="frame"></div>'
    if motif == "riso":
        dots, ink = ctx.uid("dots"), ctx.uid("ink")
        ctx.anim(
            dots,
            [{"transform": "rotate(0deg) scale(1)"}, {"transform": "rotate(20deg) scale(1.1)"}],
            0,
            total,
            "linear",
        )
        ctx.anim(
            ink,
            [{"transform": "translate(0px,0px)"}, {"transform": "translate(-40px,60px)"}],
            0,
            total,
            "linear",
        )
        return (
            f'<div id="{dots}" class="halftone"></div><div id="{ink}" class="ink-blob"></div>'
            f'<svg class="paper" width="1080" height="1920"><filter id="grain"><feTurbulence type="fractalNoise" '
            f'baseFrequency="0.9" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 0.1 0 0 0 0 0.2 0 0 0 0 '
            f'0.25 0 0 0 0.18 0"/></filter><rect width="1080" height="1920" filter="url(#grain)"/></svg>'
        )
    if motif == "orbital":
        rnd = _rand(42)
        stars = []
        for i in range(170):
            x, y, r = rnd() * 1080, rnd() * 1920, 0.6 + rnd() * 1.8
            sid = ""
            if i % 9 == 0:
                sid = ctx.uid("tw")
                ctx.anim(
                    sid,
                    [{"opacity": 1}, {"opacity": 0.2}, {"opacity": 1}],
                    rnd() * 2,
                    2.5 + rnd() * 2,
                    "ease-in-out",
                    iterations=max(1, int(total / 4)),
                )
            stars.append(
                f'<circle {f"id={chr(34)}{sid}{chr(34)} " if sid else ""}cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}"/>'
            )
        orbit = ctx.uid("orb")
        ctx.anim(orbit, [{"transform": "rotate(0deg)"}, {"transform": "rotate(40deg)"}], 0, total, "linear")
        return (
            f'<svg class="stars" width="1080" height="1920">{"".join(stars)}</svg>'
            f'<svg class="orbits" width="1080" height="1920" viewBox="-540 -960 1080 1920"><g id="{orbit}">'
            f'<ellipse rx="520" ry="210" transform="rotate(-18)"/><ellipse rx="760" ry="330" transform="rotate(-18)"/>'
            f'<circle cx="520" cy="0" r="9" transform="rotate(-18)" class="moon"/></g></svg>'
            f'<div class="planet"></div>'
        )
    if motif == "concrete":
        top, bot = ctx.uid("hz"), ctx.uid("hz")
        for el, dx in ((top, 120), (bot, -120)):
            ctx.anim(
                el,
                [{"backgroundPosition": "0px 0px"}, {"backgroundPosition": f"{dx}px 0px"}],
                0,
                2.0,
                "linear",
                iterations=loops,
            )
        return (
            f'<svg class="paper" width="1080" height="1920"><filter id="grain"><feTurbulence type="fractalNoise" '
            f'baseFrequency="1.4" numOctaves="2" seed="9"/><feColorMatrix values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 '
            f'0 0.35 0"/></filter><rect width="1080" height="1920" filter="url(#grain)"/></svg>'
            f'<div id="{top}" class="hazard top"></div><div id="{bot}" class="hazard bottom"></div>'
            f'<div class="slab"></div>'
        )
    if motif == "lab":
        rnd = _rand(23)
        pts = []
        for cx, cy in ((830, 420), (240, 1560)):
            for _ in range(26):
                pts.append((cx + (rnd() - 0.5) * 520, cy + (rnd() - 0.5) * 420))
        links = "".join(
            f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}"/>'
            for i, a in enumerate(pts)
            for b in pts[i + 1 :]
            if math.hypot(a[0] - b[0], a[1] - b[1]) < 120
        )
        dots = "".join(
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{2 + (k % 3) * 0.6:.1f}" class="c{k % 3}"/>'
            for k, (x, y) in enumerate(pts)
        )
        net = ctx.uid("net")
        ctx.anim(
            net,
            [{"transform": "translate(0px,0px)"}, {"transform": "translate(-30px,24px)"}],
            0,
            total,
            "linear",
        )
        return (
            f'<div class="labglow"></div><svg id="{net}" class="net" width="1080" height="1920">{links}{dots}</svg>'
            f'<div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div>'
            f'<div class="corner br"></div>'
        )
    if motif == "manim":
        grid = "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="1920"/>' for x in range(0, 1081, 90))
        grid += "".join(f'<line x1="0" y1="{y}" x2="1080" y2="{y}"/>' for y in range(30, 1920, 90))
        plane = ctx.uid("plane")
        ctx.anim(plane, [{"opacity": 0}, {"opacity": 1}], 0, 1.2)
        return (
            f'<svg id="{plane}" class="plane" width="1080" height="1920">{grid}'
            f'<line x1="540" y1="0" x2="540" y2="1920" class="axis"/>'
            f'<line x1="0" y1="1020" x2="1080" y2="1020" class="axis"/></svg><div class="vignette"></div>'
        )
    return ""


# --- CSS ---------------------------------------------------------------------------------------------------------


def _font_faces() -> str:
    return "".join(
        f'@font-face{{font-family:"{fam}";src:url("fonts/{file}") format("woff2");font-weight:{w};font-style:{s};}}'
        for fam, files in FONTS.items()
        for file, w, s in files
    )


BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{overflow:hidden;background:var(--bg)}
#root{position:relative;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--ink);
  font-family:var(--body),sans-serif}
.bg-clip{position:absolute;inset:0;overflow:hidden}
.bg{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;transform-origin:0 0}
.bg>*{position:absolute}
.scene{position:absolute}
.design{position:absolute;left:0;top:0;width:920px;height:1000px;transform-origin:0 0}
.col{display:flex;flex-direction:column;gap:26px;width:100%;height:100%}
.col.center{justify-content:center;align-items:flex-start}
.spacer{flex:1}
.kicker{font-family:var(--mono),monospace;font-size:30px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);font-weight:700}
.hl{font-family:var(--display),sans-serif;font-weight:var(--dw);line-height:1.02;text-transform:var(--case);
  color:var(--ink);overflow-wrap:anywhere;width:100%}
.hl.hero{line-height:.98}
.bar{width:260px;height:14px;background:var(--accent);transform-origin:left center}
.badge{display:inline-block;font-family:var(--mono),monospace;font-weight:700;font-size:30px;letter-spacing:.12em;
  padding:12px 22px;border:3px solid var(--accent);color:var(--accent);text-transform:uppercase}
.badge.big{font-size:40px;padding:16px 30px;background:var(--accent);color:var(--bg)}
.num{font-family:var(--display),sans-serif;font-weight:var(--dw);line-height:1;color:var(--accent);
  white-space:nowrap;font-variant-numeric:tabular-nums}
.num.mono{font-family:var(--mono),monospace;font-weight:700;color:var(--ink)}
.num::after{content:""}
.unit{font-family:var(--mono),monospace;font-size:44px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.06em}
.unit.small{font-size:30px}
.meter{width:100%;height:22px;border:3px solid var(--line);margin-top:10px}
.meter-fill{width:100%;height:100%;background:var(--accent);transform-origin:left center}
.dial-wrap{position:relative;width:660px;height:660px;align-self:center;margin-top:10px}
.dial{position:absolute;inset:0}
.dial-ring{fill:none;stroke:var(--line);stroke-width:4}
.tick{stroke:var(--muted);stroke-width:3}
.tick-major{stroke:var(--ink);stroke-width:6}
.dial-arc{fill:none;stroke:var(--accent);stroke-width:26}
.hand line{stroke:var(--accent2);stroke-width:8;stroke-linecap:round}
.hub{fill:var(--accent2)}
.dial-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding-top:300px}
.dial-center .num{background:var(--bg);padding:4px 16px}
.dial-center .unit{background:var(--bg);padding:2px 12px}
.map{position:relative;margin:auto 0}
.map svg{position:absolute;inset:0;overflow:visible}
.land circle{fill:var(--line);opacity:.75}
.pin{fill:var(--accent2);stroke:var(--bg);stroke-width:4}
.pin-ring{fill:none;stroke:var(--accent2);stroke-width:4}
.route{fill:none;stroke:var(--accent);stroke-width:5;stroke-linecap:round}
.pin-label{position:absolute;font-family:var(--mono),monospace;font-weight:700;font-size:28px;padding:6px 12px;
  background:var(--ink);color:var(--bg);white-space:nowrap;text-transform:uppercase}
.chart{display:flex;align-items:flex-end;gap:28px;height:680px;margin-top:auto}
.bar-col{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:12px}
.bar-val{font-family:var(--mono),monospace;font-weight:700;color:var(--ink);white-space:nowrap}
.bar-fill{width:100%;background:var(--accent);transform-origin:bottom center}
.bar-fill.hi{background:var(--accent2)}
.bar-label{font-family:var(--mono),monospace;font-size:26px;text-align:center;color:var(--muted);height:70px;
  text-transform:uppercase;overflow-wrap:anywhere;line-height:1.1}
.cmp{display:flex;align-items:stretch;gap:20px;height:700px;margin-top:auto;position:relative}
.cmp-col{flex:1;display:flex;flex-direction:column;gap:12px;min-width:0}
.cmp-label{font-family:var(--mono),monospace;font-size:32px;font-weight:700;text-transform:uppercase;color:var(--muted);
  min-height:76px;overflow-wrap:anywhere;line-height:1.15}
.cmp-track{flex:1;position:relative;border-bottom:4px solid var(--line)}
.cmp-fill{position:absolute;left:0;right:0;bottom:0;background:var(--accent);transform-origin:bottom center}
.cmp-col.hi .cmp-fill{background:var(--accent2)}
.cmp-col.hi .num{color:var(--accent2)}
.vs{position:absolute;left:50%;top:44%;width:110px;height:110px;margin-left:-55px;border-radius:50%;
  background:var(--ink);color:var(--bg);display:flex;align-items:center;justify-content:center;
  font-family:var(--mono),monospace;font-weight:700;font-size:40px;z-index:2}
.list{display:flex;flex-direction:column;gap:44px;margin:auto 0}
.li{display:flex;gap:28px;align-items:flex-start}
.li-n{font-family:var(--mono),monospace;font-weight:700;font-size:44px;color:var(--accent);min-width:80px;line-height:1.1}
.li-label{font-family:var(--display),sans-serif;font-weight:var(--dw);font-size:calc(54px * var(--ds));
  text-transform:var(--case);line-height:1.05;overflow-wrap:anywhere}
.li-note{font-size:32px;color:var(--muted);margin-top:8px;line-height:1.2}
.qmark{font-family:"Liberation Serif",serif;font-weight:700;font-size:300px;line-height:.6;color:var(--accent);
  height:140px}
.hl.quote{text-transform:none}
.who{font-family:var(--mono),monospace;font-size:34px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.scale{display:flex;flex-direction:column;gap:40px;margin:auto 0}
.sc-head{display:flex;justify-content:space-between;gap:20px;font-family:var(--mono),monospace;font-size:32px;
  font-weight:700;margin-bottom:10px}
.sc-label{text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sc-val{color:var(--accent);white-space:nowrap}
.sc-track{height:34px;background:color-mix(in srgb,var(--line) 25%,transparent)}
.sc-fill{height:100%;background:var(--accent);transform-origin:left center}
.sc-axis{position:relative;height:40px;border-top:3px solid var(--line);font-family:var(--mono),monospace;
  font-size:24px;color:var(--muted)}
.sc-axis span{position:absolute;top:8px;transform:translateX(-50%)}
.sc-axis span:first-child{transform:none}
.sc-axis span:last-child{transform:translateX(-100%)}
.timeline{position:relative;flex:1;display:flex;flex-direction:column;justify-content:space-around;padding-left:90px;
  margin-top:20px}
.tl-line{position:absolute;left:28px;top:0;bottom:0;width:6px;background:var(--line);transform-origin:top center}
.ti{position:relative}
.ti-dot{position:absolute;left:-76px;top:12px;width:30px;height:30px;border-radius:50%;background:var(--accent);
  border:5px solid var(--bg)}
.ti-when{font-family:var(--mono),monospace;font-weight:700;font-size:34px;color:var(--accent)}
.ti-label{font-family:var(--display),sans-serif;font-weight:var(--dw);font-size:calc(48px * var(--ds));
  text-transform:var(--case);line-height:1.08;overflow-wrap:anywhere}
.hud{position:absolute;height:56px;display:flex;justify-content:space-between;
  align-items:center;font-family:var(--mono),monospace;font-size:26px;letter-spacing:.12em;color:var(--muted);
  text-transform:uppercase}
.hud-title{max-width:640px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hud-n{color:var(--ink);font-weight:700}
.hud-n::after{content:""}
.progress{position:absolute;height:4px;background:color-mix(in srgb,var(--line) 35%,transparent)}
.progress div{width:100%;height:100%;background:var(--accent);transform-origin:left center}
.cap{position:absolute;display:flex;align-items:center;
  justify-content:center}
.cap-box{max-width:960px;text-align:center;font-family:var(--cap-font),sans-serif;font-weight:var(--cap-weight);
  font-size:var(--cap-size);line-height:1.12;text-transform:uppercase;padding:14px 26px;background:var(--cap-bg);
  color:var(--cap-ink);border-radius:var(--cap-radius)}
.cw{display:inline-block;margin:0 .13em}
"""

STYLE_CSS = {
    "neon": """
.sky{inset:0;background:linear-gradient(180deg,var(--bg) 0%,var(--bg2) 62%,#5a0f63 76%,var(--bg) 76.2%)}
.sun{left:330px;top:1200px;width:420px;height:420px;border-radius:50%;opacity:.38;
  background:repeating-linear-gradient(180deg,#ffcf3f 0 34px,transparent 34px 46px),
  linear-gradient(180deg,#ffcf3f,#ff3ea5);-webkit-mask:linear-gradient(#000 0 0);
  background-blend-mode:normal}
.horizon{left:0;right:0;top:1460px;height:4px;background:var(--accent2);box-shadow:0 0 30px var(--accent2)}
.floor-wrap{left:0;right:0;top:1462px;bottom:0;overflow:hidden;background:var(--bg)}
.floor{position:absolute;left:-1080px;right:-1080px;top:0;height:1400px;transform:perspective(260px) rotateX(58deg);
  transform-origin:50% 0;
  background-image:linear-gradient(var(--accent2) 3px,transparent 3px),linear-gradient(90deg,var(--accent2) 3px,transparent 3px);
  background-size:120px 120px;opacity:.75}
.hl,.num{text-shadow:0 0 28px color-mix(in srgb,var(--accent2) 55%,transparent)}
.num{color:var(--accent);text-shadow:0 0 30px var(--accent)}
""",
    "atlas": """
.paper{inset:0;opacity:1}
.graticule{inset:0}
.graticule path,.graticule line{fill:none;stroke:var(--line);stroke-width:1.5;opacity:.28}
.rose{left:740px;top:1560px;opacity:.55}
.rose circle{fill:none;stroke:var(--ink);stroke-width:3}
.rose circle.thin{stroke-width:1;stroke-dasharray:4 6}
.rose polygon{fill:var(--ink)}
.rose polygon.minor{fill:var(--accent)}
.vignette{inset:0;background:radial-gradient(ellipse at center,transparent 55%,rgba(90,60,20,.35) 100%)}
.hl{font-style:normal;letter-spacing:-.01em}
.kicker{font-family:"Liberation Serif",serif;font-style:italic;font-weight:400;letter-spacing:.04em;font-size:36px}
.route{stroke-dasharray:14 12 !important;stroke-dashoffset:0 !important}
.land circle{fill:var(--accent2);opacity:.55}
.badge{border-style:double;border-width:6px}
""",
    "blueprint": """
.grid-minor{inset:0;background-image:linear-gradient(rgba(255,255,255,.08) 1px,transparent 1px),
  linear-gradient(90deg,rgba(255,255,255,.08) 1px,transparent 1px);background-size:40px 40px}
.grid-major{inset:0;background-image:linear-gradient(rgba(255,255,255,.18) 2px,transparent 2px),
  linear-gradient(90deg,rgba(255,255,255,.18) 2px,transparent 2px);background-size:200px 200px}
.reg{width:40px;height:40px;border:3px solid var(--ink);border-radius:50%;
  background:linear-gradient(var(--ink),var(--ink)) center/3px 100% no-repeat,linear-gradient(var(--ink),var(--ink)) center/100% 3px no-repeat}
.titleblock{left:600px;top:1600px;width:420px;height:110px;border:3px solid var(--line);display:flex;
  flex-direction:column;justify-content:space-around;padding:10px 18px;font-family:var(--mono),monospace;
  font-size:20px;color:var(--muted);letter-spacing:.1em}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:repeating-linear-gradient(45deg,var(--accent) 0 10px,transparent 10px 18px);
  outline:3px solid var(--accent)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:repeating-linear-gradient(45deg,var(--accent2) 0 10px,transparent 10px 18px);
  outline-color:var(--accent2)}
.num{color:var(--accent2)}
""",
    "phosphor": """
.glowbg{inset:0;background:radial-gradient(ellipse at 50% 45%,var(--bg2),var(--bg) 70%)}
.scan{inset:0;z-index:50;background:repeating-linear-gradient(180deg,rgba(0,0,0,.28) 0 2px,transparent 2px 5px)}
.vignette{inset:0;z-index:51;background:radial-gradient(ellipse at center,transparent 60%,rgba(0,0,0,.65) 100%)}
#root{text-shadow:0 0 14px color-mix(in srgb,var(--ink) 60%,transparent)}
.hl::before{content:"> ";color:var(--accent2)}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:repeating-linear-gradient(90deg,var(--ink) 0 18px,transparent 18px 26px)}
.cap-box{border:2px solid var(--ink)}
""",
    "swiss": """
.rule{top:0;bottom:0;width:1px;background:rgba(0,0,0,.12)}
.block{left:0;top:0;width:520px;height:190px;background:var(--accent)}
.dot-red{right:-140px;top:1560px;width:420px;height:420px;border-radius:50%;background:var(--accent)}
.hl{letter-spacing:-.03em}
.kicker{color:var(--accent)}
.num{color:var(--ink);letter-spacing:-.04em}
.cmp-col.hi .num{color:var(--accent)}
.bar-fill{background:var(--ink)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:var(--accent)}
.cmp-fill,.sc-fill,.meter-fill{background:var(--ink)}
.cap-box{border-radius:0}
""",
    "chalk": """
#root{background:radial-gradient(ellipse at 40% 35%,var(--bg2),var(--bg) 75%)}
.smudge{border-radius:50%;background:radial-gradient(ellipse,rgba(255,255,255,.07),transparent 70%)}
.frame{inset:0;border:22px solid #6b4a2b;box-shadow:inset 0 0 0 6px #4a3119}
.hl,.li-label,.ti-label{filter:url(#chalk)}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:repeating-linear-gradient(-30deg,var(--accent) 0 6px,transparent 6px 12px);
  filter:url(#chalk)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:repeating-linear-gradient(-30deg,var(--accent2) 0 6px,transparent 6px 12px)}
.num{filter:url(#chalk)}
.bar{border-radius:8px;filter:url(#chalk)}
""",
    "riso": """
.halftone{left:-200px;top:200px;width:1300px;height:1300px;border-radius:50%;opacity:.3;
  background-image:radial-gradient(var(--accent) 34%,transparent 36%);background-size:22px 22px}
.ink-blob{left:520px;top:1380px;width:760px;height:760px;border-radius:50%;background:var(--accent2);opacity:.28;
  mix-blend-mode:multiply}
.paper{inset:0}
.hl,.num,.li-label,.ti-label{text-shadow:5px 4px 0 color-mix(in srgb,var(--accent) 75%,transparent)}
.num{color:var(--ink)}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:var(--accent2);box-shadow:8px 6px 0 color-mix(in srgb,var(--accent) 70%,transparent)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:var(--accent)}
.cap-box{transform:rotate(-1.5deg)}
""",
    "orbital": """
#root{background:radial-gradient(ellipse at 50% 30%,var(--bg2),var(--bg) 70%)}
.stars{inset:0}
.stars circle{fill:#fff;opacity:.8}
.orbits{inset:0;opacity:.55}
.orbits ellipse{fill:none;stroke:var(--line);stroke-width:2;stroke-dasharray:6 10}
.orbits .moon{fill:var(--accent2)}
.planet{left:-460px;top:1520px;width:2000px;height:2000px;border-radius:50%;
  background:radial-gradient(circle at 50% 8%,#2a4a8f,#0b1430 40%,#03050c 70%);
  box-shadow:0 -10px 80px rgba(127,216,255,.45),inset 0 20px 40px rgba(127,216,255,.35)}
.hl{font-weight:700;letter-spacing:-.02em}
.kicker{color:var(--accent2)}
.num{font-weight:400;font-family:var(--mono),monospace}
""",
    "lab": """
#root{background:var(--bg)}
.labglow{inset:0;background:radial-gradient(ellipse at 70% 20%,rgba(159,227,245,.08),transparent 55%),
  radial-gradient(ellipse at 20% 85%,rgba(196,181,253,.08),transparent 55%)}
.net{left:0;top:0;opacity:.38}
.net line{stroke:#9fe3f5;stroke-width:1;opacity:.5}
.net .c0{fill:#9fe3f5}.net .c1{fill:#c4b5fd}.net .c2{fill:#a8c5ff}
.corner{width:44px;height:44px;border-color:#9fe3f5;border-style:solid;border-width:0;opacity:.7}
.corner.tl{left:40px;top:250px;border-left-width:2px;border-top-width:2px}
.corner.tr{right:40px;top:250px;border-right-width:2px;border-top-width:2px}
.corner.bl{left:40px;top:1480px;border-left-width:2px;border-bottom-width:2px}
.corner.br{right:40px;top:1480px;border-right-width:2px;border-bottom-width:2px}
.kicker::before{content:"";display:inline-block;width:18px;height:18px;margin-right:14px;vertical-align:1px;
  background:linear-gradient(135deg,var(--accent),var(--accent2))}
.num{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;
  color:transparent}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:linear-gradient(90deg,var(--accent),var(--accent2))}
.cap-box{border-radius:0}
.badge{border-radius:0}
""",
    "manim": """
#root{background:radial-gradient(ellipse at 50% 40%,var(--bg2),var(--bg) 75%)}
.plane{left:0;top:0}
.plane line{stroke:#58c4dd;stroke-width:1;opacity:.12}
.plane line.axis{stroke:#f2f2f2;stroke-width:2;opacity:.18}
.vignette{inset:0;background:radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,.5) 100%)}
.hl{letter-spacing:-.01em}
.kicker{color:var(--accent2);font-family:var(--mono),monospace}
.num{color:var(--accent2)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:var(--accent2)}
""",
    "concrete": """
.paper{inset:0}
.hazard{left:0;right:0;height:70px;background:repeating-linear-gradient(-45deg,var(--accent) 0 30px,var(--ink) 30px 60px);
  background-size:85px 70px}
.hazard.top{top:120px;height:40px}
.hazard.bottom{bottom:300px;height:40px}
.slab{left:0;right:0;top:160px;height:140px;background:var(--ink)}
.hud{color:var(--accent)}
.hud-n{color:#fff}
.num{color:var(--ink);background:var(--accent);padding:6px 18px;align-self:flex-start}
.bar-fill,.meter-fill,.sc-fill,.cmp-fill{background:var(--ink)}
.bar-fill.hi,.cmp-col.hi .cmp-fill{background:var(--accent);outline:5px solid var(--ink)}
.kicker{color:var(--ink);background:var(--accent);align-self:flex-start;padding:4px 12px}
.cap-box{border-radius:0}
.pin-label{background:var(--accent);color:var(--ink)}
""",
}

CHALK_FILTER = (
    '<svg width="0" height="0" style="position:absolute"><filter id="chalk"><feTurbulence '
    'type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="n"/><feDisplacementMap '
    'in="SourceGraphic" in2="n" scale="5"/></filter></svg>'
)


def _vars(style: dict) -> str:
    p, f = style["palette"], style["fonts"]
    display = f["display"]
    cap_font = f["mono"] if display == "JetBrains Mono" else display
    cap_size = {"Anton": 76, "JetBrains Mono": 54, "Liberation Serif": 64}.get(cap_font, 62)
    cap_weight = 400 if cap_font == "Anton" else 700
    values = {
        "--bg": p["bg"],
        "--bg2": p["bg2"],
        "--ink": p["ink"],
        "--muted": p["muted"],
        "--accent": p["accent"],
        "--accent2": p["accent2"],
        "--line": p["line"],
        "--cap-bg": p["cap_bg"],
        "--cap-ink": p["cap_ink"],
        "--hi": p["hi"],
        "--display": f'"{display}"',
        "--body": f'"{f["body"]}"',
        "--mono": f'"{f["mono"]}"',
        "--dw": str(style["display_weight"]),
        "--case": "uppercase" if style["uppercase"] else "none",
        "--ds": str(style["display_scale"]),
        "--cap-font": f'"{cap_font}"',
        "--cap-size": f"{cap_size}px",
        "--cap-weight": str(cap_weight),
        "--cap-radius": "14px",
        "--stroke": str(style.get("stroke", 5)),
        "--radius": f"{style.get('radius', 14)}px",
    }
    return ":root{" + ";".join(f"{k}:{v}" for k, v in values.items()) + "}"


def _geometry(fr: Frame) -> str:
    """Posiciones que dependen del aspecto: lienzo, escenario, HUD, barra de progreso, subtítulos y fondo."""
    cover = max(fr.w / 1080, fr.h / 1920)
    bx, by = (fr.w - 1080 * cover) / 2, (fr.h - 1920 * cover) / 2
    cap_size = "" if fr.aspect == "9:16" else ".cap-box{font-size:calc(var(--cap-size) * 0.82)}"
    return (
        f"html,body{{width:{fr.w}px;height:{fr.h}px}}"
        f".scene{{left:{fr.sx}px;top:{fr.sy}px;width:{fr.sw}px;height:{fr.sh}px}}"
        f".hud{{left:{fr.sx}px;right:{fr.w - fr.sx - fr.sw}px;top:{fr.hud_top}px}}"
        f".progress{{left:{fr.sx}px;right:{fr.w - fr.sx - fr.sw}px;top:{fr.hud_top + 58}px}}"
        f".cap{{left:{fr.sx - 20}px;right:{fr.w - fr.sx - fr.sw - 20}px;top:{fr.cap_top}px;height:{fr.cap_h}px}}"
        f".bg{{transform:translate({bx:.1f}px,{by:.1f}px) scale({cover:.4f})}}{cap_size}"
    )


def _design_box(fr: Frame) -> str:
    """Estilo de la caja de 920×1000 de las plantillas de datos, escalada y centrada en el escenario."""
    if fr.aspect == "9:16":
        return ""
    s = min(fr.sw / DESIGN_W, fr.sh / DESIGN_H)
    left = (fr.sw - DESIGN_W * s) / 2
    return f"left:{left:.1f}px;transform:scale({s:.4f})"


def build_composition(
    script: dict,
    style: dict,
    times: list[SceneTime],
    words: list[Word],
    lang: str = "es",
    total: float | None = None,
    aspect: str = "9:16",
) -> str:
    """El `index.html` del episodio. `times` va en el orden de `script["scenes"]`."""
    from . import factory_rich as rich

    fr = FRAMES.get(aspect, FRAMES["9:16"])
    ctx = _Ctx(style=style, lang=lang, frame=fr, words=list(words))
    total = total or (times[-1].start + times[-1].duration if times else 1.0)
    es = lang.startswith("es")
    episode, episodes = script.get("episode"), script.get("episodes")
    meta = {
        "series_label": script.get("series_title")
        if script.get("series_title") != script.get("title")
        else None,
        "episode_label": (
            f"{'Episodio' if es else 'Episode'} {episode}/{episodes}" if episode and episodes else None
        ),
        "to_be_continued": (
            ("Continuará" if es else "To be continued")
            if episode and episodes and episode < episodes
            else None
        ),
        "sources": script.get("sources") or [],
    }
    scenes = []
    counter = ctx.uid("hudn")
    n_scenes = len(script["scenes"])
    steps = []
    design = _design_box(fr)
    for i, (sc, tm) in enumerate(zip(script["scenes"], times, strict=True)):
        layout = sc["visual"]["layout"]
        if layout in rich.RICH_BUILDERS:
            ctx.width = fr.sw
            body = rich.RICH_BUILDERS[layout](ctx, sc["visual"], tm.start, tm.duration, meta)
        else:
            ctx.width = STAGE_W
            body = LAYOUT_BUILDERS.get(layout, layout_title)(ctx, sc["visual"], tm.start, tm.duration, meta)
            if design:
                body = f'<div class="design" style="{design}">{body}</div>'
        scenes.append(
            f'<section id="s{i + 1}" class="scene clip" data-start="{tm.start:.3f}" '
            f'data-duration="{tm.duration:.3f}" data-track-index="2" data-layout="{esc(layout)}">{body}</section>'
        )
        # Pasos discretos: cada valor se repite justo antes del siguiente (un `content` animado cambia a mitad de
        # camino entre dos fotogramas clave, así el cambio cae en el inicio de la escena).
        label = _css_string(f"{i + 1:02d} / {n_scenes:02d}")
        end = (tm.start + tm.duration) / total
        steps.append({"content": label, "offset": round(tm.start / total, 5)})
        steps.append({"content": label, "offset": round(max(tm.start / total, min(1.0, end) - 0.0005), 5)})
    steps[-1]["offset"] = 1
    ctx.anim(counter, steps, 0, total, "linear", pseudo="::after")
    progress = ctx.uid("pg")
    ctx.anim(progress, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], 0, total, "linear")
    background = _background(ctx, total)
    captions = _captions(ctx, words, total)
    hud_title = script.get("series_title") or script["title"]
    css = (
        _font_faces()
        + _vars(style)
        + BASE_CSS
        + _geometry(fr)
        + rich.RICH_CSS
        + STYLE_CSS.get(style["motif"], "")
        + rich.RICH_STYLE_CSS.get(style["motif"], "")
    )
    anims = script_json(ctx.anims)
    head_extra, body_extra = rich.runtime(ctx)
    return f"""<!doctype html>
<html lang="{esc(lang[:2])}">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={fr.w}, height={fr.h}" />
<title>{esc(script["title"])}</title>
{head_extra}<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="factory" data-start="0" data-width="{fr.w}" data-height="{fr.h}" data-duration="{total:.3f}">
{CHALK_FILTER if style["motif"] == "chalk" else ""}
<div class="bg-clip"><div class="bg">{background}</div></div>
<div class="hud"><span class="hud-title">{esc(hud_title)}</span><span id="{counter}" class="hud-n"></span></div>
<div class="progress"><div id="{progress}"></div></div>
{"".join(scenes)}
{captions}
</div>
<script>
(function () {{
  var A = {anims};
  for (var i = 0; i < A.length; i++) {{
    var a = A[i];
    var el = document.getElementById(a[0]);
    if (!el) continue;
    var opts = {{ delay: a[2], duration: a[3], easing: a[4], fill: "both", iterations: a[6] }};
    if (a[5]) opts.pseudoElement = a[5];
    el.animate(a[1], opts).pause();
  }}
}})();
</script>
{body_extra}
</body>
</html>
"""
