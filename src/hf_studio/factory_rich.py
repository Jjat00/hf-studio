"""Plantillas técnicas de Content Factory: ecuaciones, gráficas, señales y espectro, 3D, diagramas y código.

Todo determinista y sin red: las curvas, señales, espectros y superficies se calculan aquí (`factory_math`, con su
evaluador de lista blanca) y llegan a la página como números; las animaciones 2D son WAAPI (como el resto de la
composición, incluido el `d` de los trazos para las curvas con parámetro animado) y las escenas 3D se dibujan con
three.js desde el tiempo de HyperFrames (evento `hf-seek`), nunca desde el reloj. Si el navegador no tiene WebGL,
cada escena 3D muestra su versión 2D en SVG, calculada aquí mismo.

Las ecuaciones las dibuja KaTeX (incluido en `factory_assets/vendor`) al cargar la página, con `trust: false`; el
LaTeX ya viene validado por `factory_math.check_tex`. Los textos del guion entran escapados en el HTML o como
`textContent` desde un JSON seguro para `<script>` (`script_json`).
"""

from __future__ import annotations

import itertools
import math
import unicodedata

import numpy as np

from .factory_compose import (
    CHAR_W,
    EASE,
    EASE_IN_OUT,
    _Ctx,
    _hl,
    _kicker,
    _rand,
    decimals_of,
    esc,
    fit_size,
    fmt_number,
    wrap_lines,
)
from .factory_math import (
    auto_range,
    highlight_code,
    nice_ticks,
    parse_expr,
    peaks,
    sample,
    script_json,
    signal_values,
    spectrum,
    svg_path,
)
from .factory_world import is_land

COLORS = ["var(--accent)", "var(--accent2)", "var(--ink)", "var(--muted)"]


# --- Piezas comunes ----------------------------------------------------------------------------------------------


def _header(ctx: _Ctx, v: dict, t: float, max_size: int = 72, max_lines: int = 2) -> tuple[str, float]:
    """Kicker y titular de una escena técnica, y la altura que ocupan (para repartir el resto)."""
    st = ctx.style
    font = st["fonts"]["display"]
    size = fit_size(
        v["headline"],
        font,
        max_size * st["display_scale"],
        34,
        max_lines,
        width=ctx.width,
        upper=st["uppercase"],
    )
    k = CHAR_W.get(font, 0.6) * (1.08 if st["uppercase"] and font != "Anton" else 1.0)
    lines = min(max_lines, wrap_lines(v["headline"], size, ctx.width, k))
    height = lines * size * 1.04 + 26
    if v.get("kicker"):
        height += 36 + 26
    return _kicker(ctx, v.get("kicker"), t) + _hl(ctx, v["headline"], t + 0.05, max_size, max_lines), height


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum())


def cue_times(ctx: _Ctx, t: float, d: float, cues: list[str | None], first: float = 0.35) -> list[float]:
    """Cuándo aparece cada paso: en la palabra `cue` de la narración de esta escena si se dice, y si no, repartido
    entre los pasos con palabra (o a lo largo de la escena)."""
    n = len(cues)
    if not n:
        return []
    words = [w for w in ctx.words if t <= w.start < t + d]
    known: list[float | None] = [None] * n
    j = 0
    for i, cue in enumerate(cues):
        target = _norm(cue or "")
        if not target:
            continue
        for k in range(j, len(words)):
            spoken = _norm(words[k].text)
            if spoken and (spoken.startswith(target) or (len(spoken) >= 4 and target.startswith(spoken))):
                known[i] = max(t + 0.1, words[k].start - 0.08)
                j = k + 1
                break
    lo, hi = t + first, t + max(first + 0.4, d * 0.72)
    idx = [i for i in range(n) if known[i] is not None]
    times: list[float] = [0.0] * n
    if not idx:
        times = [lo + (hi - lo) * i / max(1, n - 1) for i in range(n)]
    else:
        for i in idx:
            times[i] = known[i]  # type: ignore[assignment]
        f = idx[0]
        for i in range(f):
            times[i] = lo + (min(times[f], hi) - lo) * i / max(1, f)
        for a, b in itertools.pairwise(idx):
            for i in range(a + 1, b):
                times[i] = times[a] + (times[b] - times[a]) * (i - a) / (b - a)
        last = idx[-1]
        rest = n - 1 - last
        if rest:
            step = max(0.35, (hi - times[last]) / rest)
            for i in range(last + 1, n):
                times[i] = times[last] + step * (i - last)
    for i in range(1, n):
        times[i] = max(times[i], times[i - 1] + 0.12)
    return [round(min(x, t + d - 0.3), 3) for x in times]


def _draw(ctx: _Ctx, el: str, t: float, dur: float, easing: str = EASE_IN_OUT) -> None:
    """Dibuja un trazo con pathLength=1: el guion de 1 a 0."""
    ctx.anim(el, [{"strokeDashoffset": "1"}, {"strokeDashoffset": "0"}], t, dur, easing)


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 200, 200, 200


def _mix(a: str, b: str, u: float) -> str:
    ra, rb = _hex(a), _hex(b)
    u = min(1.0, max(0.0, u))
    return "#" + "".join(f"{round(x + (y - x) * u):02x}" for x, y in zip(ra, rb, strict=True))


def _fmt(x: float, lang: str, dec: int | None = None) -> str:
    if dec is None:
        ax = abs(x)
        dec = 0 if ax >= 100 or float(x).is_integer() else 1 if ax >= 10 else 2
    return fmt_number(x, lang, dec)


def _axes_svg(
    w: float,
    h: float,
    box: tuple[float, float, float, float],
    lang: str,
    x_ticks: bool = True,
    y_ticks: bool = True,
) -> str:
    """Rejilla, ejes en cero y marcas con sus números (en el idioma del video)."""
    x0, x1, y0, y1 = box
    out = []
    for xv in nice_ticks(x0, x1, max(3, min(6, int(w / 130)))) if x_ticks else []:
        px = (xv - x0) / (x1 - x0) * w
        out.append(f'<line x1="{px:.1f}" y1="0" x2="{px:.1f}" y2="{h:.1f}" class="grid"/>')
        out.append(
            f'<text x="{px:.1f}" y="{h + 34:.1f}" class="tick" text-anchor="middle">{_fmt(xv, lang)}</text>'
        )
    for yv in nice_ticks(y0, y1, 5) if y_ticks else []:
        py = h - (yv - y0) / (y1 - y0) * h
        out.append(f'<line x1="0" y1="{py:.1f}" x2="{w:.1f}" y2="{py:.1f}" class="grid"/>')
        out.append(f'<text x="-14" y="{py + 9:.1f}" class="tick" text-anchor="end">{_fmt(yv, lang)}</text>')
    if y0 < 0 < y1:
        py = h - (0 - y0) / (y1 - y0) * h
        out.append(f'<line x1="0" y1="{py:.1f}" x2="{w:.1f}" y2="{py:.1f}" class="axis"/>')
    else:
        out.append(f'<line x1="0" y1="{h:.1f}" x2="{w:.1f}" y2="{h:.1f}" class="axis"/>')
    if x0 < 0 < x1:
        px = (0 - x0) / (x1 - x0) * w
        out.append(f'<line x1="{px:.1f}" y1="0" x2="{px:.1f}" y2="{h:.1f}" class="axis"/>')
    else:
        out.append(f'<line x1="0" y1="0" x2="0" y2="{h:.1f}" class="axis"/>')
    return "".join(out)


# --- Ecuación ----------------------------------------------------------------------------------------------------


def layout_equation(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    steps = v.get("steps") or []
    times = cue_times(ctx, t, d, [s.get("cue") for s in steps])
    size = round(min(110, fr.sw / 8, fr.sh / 6))
    area_h = max(200, fr.sh - hh - 20)
    terms = []
    for k, s in enumerate(steps):
        el = ctx.uid("eq")
        idx = len(ctx.tex)
        ctx.tex.append("\\displaystyle " + s["tex"])
        at = times[k]
        ctx.anim(
            el,
            [
                {"opacity": 0.14, "transform": "translateY(0px) scale(0.96)", "filter": "blur(3px)"},
                {"opacity": 1, "transform": "translateY(0px) scale(1)", "filter": "blur(0px)"},
            ],
            at,
            0.65,
        )
        note = ""
        if s.get("note"):
            hl, nt = ctx.uid("eh"), ctx.uid("en")
            ctx.anim(
                hl, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], at + 0.35, 0.5, EASE_IN_OUT
            )
            ctx.enter(nt, at + 0.5, dy=18, dur=0.45)
            ctx.anim(el, [{"color": "var(--ink)"}, {"color": "var(--accent2)"}], at + 0.35, 0.4, "linear")
            note = f'<div id="{hl}" class="eq-hl"></div><div id="{nt}" class="eq-note">{esc(s["note"])}</div>'
        terms.append(
            f'<div class="eq-term{" noted" if note else ""}"><span id="{el}" class="eq-tex" data-tex="{idx}">'
            f"</span>{note}</div>"
        )
    glow = ctx.uid("eg")
    end = (times[-1] if times else t) + 0.9
    if end < t + d - 0.6:
        ctx.anim(
            glow,
            [{"opacity": 0, "transform": "scaleX(0.2)"}, {"opacity": 1, "transform": "scaleX(1)"}],
            end,
            0.7,
            EASE_IN_OUT,
        )
    return (
        f'<div class="col">{head}<div class="eq-area" style="height:{area_h:.0f}px">'
        f'<div class="eq" data-fit-w="{fr.sw - 20}" data-fit-h="{area_h - 60:.0f}" style="font-size:{size}px">'
        f'{"".join(terms)}</div><div id="{glow}" class="eq-under"></div></div></div>'
    )


# --- Gráfica de funciones ----------------------------------------------------------------------------------------


def layout_plot(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    curves = (v.get("curves") or [])[:4]
    exprs = [parse_expr(c["expr"], ("x", "t")) for c in curves]
    x0, x1 = v.get("x_range") or [-5.0, 5.0]
    t_range = v.get("t_range")
    animated = bool(t_range) and any("t" in e.variables for e in exprs)
    frames = max(8, min(48, int(d * 4))) if animated else 1
    tvals = (
        list(np.linspace(t_range[0], t_range[1], frames)) if animated else [t_range[0] if t_range else 0.0]
    )
    data = [[sample(e, x0, x1, 260, tv)[1] for tv in tvals] for e in exprs]
    if v.get("y_range"):
        y0, y1 = v["y_range"]
    else:
        y0, y1 = auto_range([ys for per in data for ys in per])
    legend = len(curves) > 1 or any(c.get("label") for c in curves)
    left, bottom, top = 96, 56, 16
    w = fr.sw - left - 24
    h = max(220.0, min(fr.sh - hh - bottom - top - (70 if legend else 10) - 20, w * 1.05))
    xs = np.linspace(x0, x1, 260)
    box = (x0, x1, y0, y1)
    clip = ctx.uid("clip")
    grid = ctx.uid("grid")
    ctx.anim(grid, [{"opacity": 0}, {"opacity": 1}], t + 0.15, 0.6)
    paths, keys = [], []
    draw_at = t + 0.45
    draw_dur = min(2.0, max(1.0, d * 0.3))
    for k, (c, per) in enumerate(zip(curves, data, strict=True)):
        el = ctx.uid("cv")
        d0 = svg_path(xs, per[0], box, w, h, continuous=animated)
        start = draw_at + k * 0.45
        _draw(ctx, el, start, draw_dur)
        if animated:
            sweep_at = start + draw_dur + 0.1
            sweep = max(0.5, t + d - 0.4 - sweep_at)
            frames_d = [{"d": f'path("{svg_path(xs, ys, box, w, h, continuous=True)}")'} for ys in per]
            ctx.anim(el, frames_d, sweep_at, sweep, "linear")
        paths.append(
            f'<path id="{el}" d="{d0}" class="curve" pathLength="1" stroke-dasharray="1" '
            f'style="stroke:{COLORS[k % 4]};stroke-dashoffset:1"/>'
        )
        sw = ctx.uid("lg")
        ctx.enter(sw, start + 0.2, dy=12, dur=0.4)
        label = esc(c.get("label") or f"y = {c['expr']}")
        keys.append(
            f'<div id="{sw}" class="lg-item"><span class="lg-sw" style="background:{COLORS[k % 4]}"></span>'
            f"{label}</div>"
        )
    param = ""
    if animated:
        pv = ctx.uid("pv")
        sweep_at = draw_at + draw_dur + 0.1
        dec = 2 if abs(t_range[1] - t_range[0]) < 20 else 0
        ctx.enter(pv, sweep_at - 0.2, dy=10, dur=0.3)
        ctx.count(
            pv,
            t_range[0],
            t_range[1],
            sweep_at,
            max(0.5, t + d - 0.4 - sweep_at),
            lambda x: f"t = {fmt_number(x, ctx.lang, dec)}",
        )
        param = f'<div id="{pv}" class="pl-param num mono"></div>'
    xl = f'<div class="ax-label x">{esc(v["x_label"])}</div>' if v.get("x_label") else ""
    yl = f'<div class="ax-label y">{esc(v["y_label"])}</div>' if v.get("y_label") else ""
    return (
        f'<div class="col">{head}<div class="plot" style="height:{h + bottom + top:.0f}px">{yl}{param}'
        f'<svg class="pl-svg" width="{w:.0f}" height="{h + bottom:.0f}" style="left:{left}px;top:{top}px" '
        f'viewBox="0 0 {w:.0f} {h + bottom:.0f}" overflow="visible"><defs><clipPath id="{clip}"><rect x="-4" y="-4" '
        f'width="{w + 8:.0f}" height="{h + 8:.0f}"/></clipPath></defs><g id="{grid}">'
        f"{_axes_svg(w, h, box, ctx.lang)}</g>"
        f'<g clip-path="url(#{clip})">{"".join(paths)}</g></svg>{xl}</div>'
        f"{f'<div class=legend>{"".join(keys)}</div>' if legend else ''}</div>"
    )


# --- Señal y espectro --------------------------------------------------------------------------------------------


def _hz(f: float, lang: str) -> str:
    return f"{fmt_number(f, lang, 0 if float(f).is_integer() else 1)} Hz"


def _signal(ctx: _Ctx, v: dict, t: float, d: float, focus: str) -> str:
    """`focus` = "signal": componentes → suma → espectro. "spectrum": la suma primero, de ella salen sus componentes
    y cada una se pliega en su barra del espectro."""
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    lang = ctx.lang
    waves = (v.get("waves") or [])[:4]
    fmax = max(float(w["freq"]) for w in waves)
    window = 1.0 if fmax <= 8 else 8.0 / fmax  # como mucho ~8 ciclos del componente más rápido
    ts = np.linspace(0, window, 420)
    freqs, mags, _ = spectrum(waves)
    span = max(5.0, fmax * 1.3)
    keep = freqs <= span
    freqs, mags = freqs[keep], mags[keep]
    found = peaks(freqs, mags)
    amp_max = max(float(mags.max()) if mags.size else 1.0, 1e-9)
    total_amp = sum(float(w["amp"]) for w in waves) or 1.0
    W, H = fr.sw, max(400.0, fr.sh - hh - 10)
    wide = W > 1.3 * H
    gap = 22
    k_n = len(waves)
    if wide:
        col_w = W * 0.5
        spec = (W * 0.55, 0.0, W * 0.45, H)
        sum_h = H * 0.36
        row_h = max(60.0, (H - sum_h - gap * 2) / k_n)
        rows_y = 0.0 if focus == "signal" else sum_h + gap
        sum_y = k_n * row_h + gap if focus == "signal" else 0.0
        row_w = col_w
    else:
        spec_h = H * 0.34
        sum_h = H * 0.24
        row_h = max(56.0, min(120.0, (H - spec_h - sum_h - gap * 3) / k_n))
        rows_y = 0.0 if focus == "signal" else sum_h + gap
        sum_y = k_n * row_h + gap if focus == "signal" else 0.0
        top_block = k_n * row_h + sum_h + gap * 2
        spec = (0.0, top_block, W, H - top_block)
        row_w = W
    label_w = 150
    pw = row_w - label_w
    t_rows = t + 0.4 if focus == "signal" else t + max(1.4, d * 0.28)
    t_sum = t + max(1.6, d * 0.3) if focus == "signal" else t + 0.35
    t_spec = t + max(2.8, d * 0.55)
    parts = []
    # Componentes
    row_ids = []
    sx0, sy0, sw_, sh_ = spec
    s_left, s_bottom = 70, 52
    s_w, s_h = sw_ - s_left - 20, sh_ - s_bottom - 50
    for k, w in enumerate(waves):
        y = rows_y + k * row_h
        ys = float(w["amp"]) * np.sin(2 * np.pi * float(w["freq"]) * ts + float(w.get("phase") or 0))
        amp = max(total_amp, 1e-9)
        p = svg_path(ts, ys, (0, window, -amp, amp), pw, row_h - 12)
        row, path, lab = ctx.uid("sr"), ctx.uid("sp"), ctx.uid("sl")
        row_ids.append(row)
        start = t_rows + k * 0.35
        if focus == "spectrum":
            # Sale de la suma: aparece sobre ella y baja a su fila.
            ctx.anim(
                row,
                [
                    {"opacity": 0, "transform": f"translateY({sum_y - y:.0f}px)"},
                    {"opacity": 1, "transform": "translateY(0px)"},
                ],
                start,
                0.7,
            )
            ctx.anim(path, [{"strokeDashoffset": "0"}, {"strokeDashoffset": "0"}], start, 0.1)
        else:
            ctx.anim(row, [{"opacity": 0}, {"opacity": 1}], start, 0.3)
            _draw(ctx, path, start, 0.9)
        ctx.enter(lab, start + 0.1, dy=10, dur=0.35)
        # Al pasar al espectro, cada componente se pliega en su barra.
        stem_x = sx0 + s_left + float(w["freq"]) / span * s_w
        stem_y = sy0 + 50 + s_h - float(w["amp"]) / (amp_max * 1.2) * s_h / 2
        dx = stem_x - (label_w + pw / 2)
        dy = stem_y - (y + row_h / 2)
        fold = t_spec + 0.25 + k * 0.3
        ctx.anim(
            row,
            [
                {"opacity": 1, "transform": "translate(0px,0px) scale(1,1)"},
                {"opacity": 0, "transform": f"translate({dx:.0f}px,{dy:.0f}px) scale(0.03,0.5)"},
            ],
            fold,
            0.8,
            EASE_IN_OUT,
        )
        color = COLORS[k % 2] if k_n > 1 else "var(--accent)"
        parts.append(
            f'<div id="{row}" class="sig-row" style="left:0;top:{y:.0f}px;width:{row_w:.0f}px;height:{row_h:.0f}px">'
            f'<div id="{lab}" class="sig-lab" style="color:{color}">{_hz(float(w["freq"]), lang)}'
            f"<span>A {fmt_number(float(w['amp']), lang, decimals_of(float(w['amp'])))}</span></div>"
            f'<svg width="{pw:.0f}" height="{row_h - 12:.0f}" style="left:{label_w}px;top:6px" overflow="visible">'
            f'<line x1="0" y1="{(row_h - 12) / 2:.1f}" x2="{pw:.0f}" y2="{(row_h - 12) / 2:.1f}" class="axis thin"/>'
            f'<path id="{path}" d="{p}" class="curve thin" pathLength="1" stroke-dasharray="1" '
            f'style="stroke:{color};stroke-dashoffset:1"/></svg>'
            + ('<div class="sig-plus">+</div>' if k < k_n - 1 and focus == "signal" and row_h >= 70 else "")
            + "</div>"
        )
    # Suma
    total = signal_values(waves, ts)
    amp = max(total_amp, 1e-9)
    sp = svg_path(ts, total, (0, window, -amp, amp), pw, sum_h - 40)
    srow, spath, slab = ctx.uid("ss"), ctx.uid("sp"), ctx.uid("sl")
    ctx.anim(srow, [{"opacity": 0}, {"opacity": 1}], t_sum - 0.1, 0.3)
    _draw(ctx, spath, t_sum, 1.2)
    ctx.enter(slab, t_sum, dy=10, dur=0.35)
    sum_label = "Suma" if lang.startswith("es") else "Sum"
    parts.append(
        f'<div id="{srow}" class="sig-row sum" style="left:0;top:{sum_y:.0f}px;width:{row_w:.0f}px;'
        f'height:{sum_h:.0f}px"><div id="{slab}" class="sig-lab">{sum_label}<span>x(t)</span></div>'
        f'<svg width="{pw:.0f}" height="{sum_h - 40:.0f}" style="left:{label_w}px;top:20px" overflow="visible">'
        f'<line x1="0" y1="{(sum_h - 40) / 2:.1f}" x2="{pw:.0f}" y2="{(sum_h - 40) / 2:.1f}" class="axis thin"/>'
        f'<path id="{spath}" d="{sp}" class="curve" pathLength="1" stroke-dasharray="1" '
        f'style="stroke:var(--ink);stroke-dashoffset:1"/></svg>'
        f'<div class="sig-axis">{"tiempo (s)" if lang.startswith("es") else "time (s)"} · 0 → '
        f"{fmt_number(window, lang, 2 if window < 1 else 0)}</div></div>"
    )
    # Espectro (FFT real)
    panel, line, badge = ctx.uid("spc"), ctx.uid("spl"), ctx.uid("fft")
    ctx.anim(panel, [{"opacity": 0}, {"opacity": 1}], t_spec - 0.2, 0.5)
    ctx.pop(badge, t_spec - 0.35, 0.5)
    ybox = (0.0, span, 0.0, amp_max * 1.2)
    spec_line = svg_path(freqs, mags, ybox, s_w, s_h)
    _draw(ctx, line, t_spec + 0.1, 1.4, "linear")
    stems = []
    for k, (f, a) in enumerate(found[:6]):
        px = f / span * s_w
        top = s_h - a / (amp_max * 1.2) * s_h
        g, lab = ctx.uid("st"), ctx.uid("stl")
        at = t_spec + 0.45 + k * 0.3
        ctx.anim(g, [{"transform": "scaleY(0)"}, {"transform": "scaleY(1)"}], at, 0.7)
        ctx.enter(lab, at + 0.4, dy=12, dur=0.35)
        stems.append(
            f'<g id="{g}" class="stem" style="transform-box:fill-box;transform-origin:50% 100%">'
            f'<line x1="{px:.1f}" y1="{s_h:.1f}" x2="{px:.1f}" y2="{top:.1f}"/>'
            f'<circle cx="{px:.1f}" cy="{top:.1f}" r="9"/></g>'
            f'<text id="{lab}" x="{px:.1f}" y="{top - 22:.1f}" class="stem-lab" text-anchor="middle">'
            f"{_hz(round(f, 2), lang)}</text>"
        )
    axes = _axes_svg(s_w, s_h, ybox, lang, y_ticks=False)
    fx = "frecuencia (Hz)" if lang.startswith("es") else "frequency (Hz)"
    amp_word = "amplitud" if lang.startswith("es") else "amplitude"
    parts.append(
        f'<div id="{panel}" class="spec" style="left:{sx0:.0f}px;top:{sy0:.0f}px;width:{sw_:.0f}px;'
        f'height:{sh_:.0f}px"><div id="{badge}" class="fft-badge">FFT</div>'
        f'<div class="spec-y">{amp_word}</div>'
        f'<svg width="{s_w:.0f}" height="{s_h + s_bottom:.0f}" style="left:{s_left}px;top:50px" overflow="visible">'
        f'{axes}<path id="{line}" d="{spec_line}" class="spec-line" pathLength="1" stroke-dasharray="1" '
        f'style="stroke-dashoffset:1"/>{"".join(stems)}</svg><div class="sig-axis right">{fx}</div></div>'
    )
    return f'<div class="col">{head}<div class="sig" style="height:{H:.0f}px">{"".join(parts)}</div></div>'


def layout_signal(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    return _signal(ctx, v, t, d, "signal")


def layout_spectrum(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    return _signal(ctx, v, t, d, "spectrum")


# --- 3D ----------------------------------------------------------------------------------------------------------

SURF_N = 40


def _grid_frames(expr_text: str, d: float, n: int) -> tuple[list[list[float]], float, float, float]:
    """Alturas z = f(x, y, t) en una rejilla n×n sobre [-3, 3]² (filas de y=3 a y=-3, como el plano de three.js) en
    varios instantes de la escena. Devuelve (fotogramas, paso entre fotogramas, z mínima, z máxima)."""
    expr = parse_expr(expr_text, ("x", "y", "t"))
    gx = np.linspace(-3, 3, n)
    gy = np.linspace(3, -3, n)
    xx, yy = np.meshgrid(gx, gy)
    moving = "t" in expr.variables
    count = max(2, min(36, int(d * 5) + 1)) if moving else 1
    step = d / max(1, count - 1) if moving else 1.0
    frames = []
    for i in range(count):
        z = expr(x=xx, y=yy, t=i * step)
        if z.ndim == 0:
            z = np.full_like(xx, float(z))
        frames.append(z)
    stack = np.stack(frames)
    finite = stack[np.isfinite(stack)]
    lo, hi = (
        (float(np.percentile(finite, 1)), float(np.percentile(finite, 99))) if finite.size else (-1.0, 1.0)
    )
    if hi - lo < 1e-6:
        lo, hi = lo - 1, hi + 1
    stack = np.clip(np.nan_to_num(stack, nan=0.0, posinf=hi, neginf=lo), lo, hi)
    out = [[round(float(x), 3) for x in f.ravel()] for f in stack]
    return out, step, lo, hi


def _palette(ctx: _Ctx) -> dict:
    p = ctx.style["palette"]
    return {k: p[k] for k in ("bg", "bg2", "ink", "muted", "accent", "accent2", "line")}


def _fallback_svg(ctx: _Ctx, kind: str, w: float, h: float, data: dict) -> str:
    """Versión 2D de una escena 3D para un navegador sin WebGL (o un render que falle al crear el contexto)."""
    p = _palette(ctx)
    out = []
    if kind == "surface" and data.get("frames"):
        n = data["n"]
        z = data["frames"][0]
        lo, hi = data["zmin"], data["zmax"]
        cell = min(w, h) * 0.8 / n
        ox, oy = (w - cell * n) / 2, (h - cell * n) / 2
        for i in range(n):
            for j in range(n):
                u = (z[i * n + j] - lo) / ((hi - lo) or 1)
                out.append(
                    f'<rect x="{ox + j * cell:.1f}" y="{oy + i * cell:.1f}" width="{cell + 0.6:.1f}" '
                    f'height="{cell + 0.6:.1f}" fill="{_mix(p["accent"], p["accent2"], u)}"/>'
                )
    elif kind == "globe":
        r = min(w, h) * 0.38
        cx, cy = w / 2, h / 2
        lon0 = data["items"][0]["lon"] if data.get("items") else 0
        out.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{p["bg2"]}" stroke="{p["line"]}"/>'
        )
        for lat, lon in data.get("land", []):
            la, lo = math.radians(lat), math.radians(lon - lon0)
            if math.cos(la) * math.cos(lo) <= 0:
                continue
            out.append(
                f'<circle cx="{cx + r * math.cos(la) * math.sin(lo):.1f}" cy="{cy - r * math.sin(la):.1f}" r="2.2" '
                f'fill="{p["ink"]}" opacity=".6"/>'
            )
        for it in data.get("items", []):
            la, lo = math.radians(it["lat"]), math.radians(it["lon"] - lon0)
            if math.cos(la) * math.cos(lo) > 0:
                x, y = cx + r * math.cos(la) * math.sin(lo), cy - r * math.sin(la)
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{p["accent"]}"/>')
    elif kind == "bars" and data.get("bars"):
        n = len(data["bars"])
        bw = w * 0.7 / n
        for k, b in enumerate(data["bars"]):
            bh = b["h"] / 3.6 * h * 0.7
            x = w * 0.15 + k * bw
            out.append(
                f'<rect x="{x + bw * 0.15:.0f}" y="{h * 0.85 - bh:.0f}" width="{bw * 0.7:.0f}" height="{bh:.0f}" '
                f'fill="{p["accent2"] if b.get("hi") else p["accent"]}"/>'
            )
    else:
        rnd = _rand(5)
        for k in range(160 if kind == "particles" else max(1, len(data.get("items", [])))):
            if kind == "particles":
                out.append(
                    f'<circle cx="{rnd() * w:.0f}" cy="{rnd() * h:.0f}" r="{1 + rnd() * 3:.1f}" '
                    f'fill="{p["accent"] if k % 2 else p["accent2"]}" opacity=".8"/>'
                )
            else:
                n = max(1, len(data.get("items", [])))
                out.append(
                    f'<circle cx="{w * (k + 0.5) / n:.0f}" cy="{h / 2:.0f}" r="{min(w / n, h) * 0.3:.0f}" '
                    f'fill="{p["accent"] if k % 2 == 0 else p["accent2"]}"/>'
                )
    return f'<svg width="{w:.0f}" height="{h:.0f}">{"".join(out)}</svg>'


def _gl_scene(ctx: _Ctx, v: dict, t: float, d: float, kind: str, data: dict) -> str:
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    w, h = fr.sw, round(max(300.0, fr.sh - hh - 10))
    canvas, labels, fallback, wrap = ctx.uid("gl"), ctx.uid("gll"), ctx.uid("glf"), ctx.uid("glw")
    ctx.anim(wrap, [{"opacity": 0}, {"opacity": 1}], t + 0.1, 0.5)
    ctx.gl.append(
        {
            "kind": kind,
            "canvas": canvas,
            "labels": labels,
            "fallback": fallback,
            "start": round(t, 3),
            "dur": round(d, 3),
            "w": w,
            "h": h,
            **data,
        }
    )
    return (
        f'<div class="col">{head}<div id="{wrap}" class="gl-wrap" style="height:{h}px">'
        f'<canvas id="{canvas}" class="gl" width="{w}" height="{h}" style="width:{w}px;height:{h}px"></canvas>'
        f'<div id="{labels}" class="gl-labels"></div>'
        f'<div id="{fallback}" class="gl-fallback">{_fallback_svg(ctx, kind, w, h, data)}</div></div></div>'
    )


def _label_items(ctx: _Ctx, v: dict) -> list[dict]:
    items = v.get("items") or []
    dec = decimals_of(*[i.get("value") for i in items])
    out = []
    for it in items[:6]:
        value = it.get("value")
        text = it["label"]
        if value is not None:
            text += f" · {v.get('prefix') or ''}{fmt_number(float(value), ctx.lang, dec)}"
            if v.get("unit"):
                text += f" {v['unit']}"
        out.append({**it, "text": text})
    return out


def layout_surface3d(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    frames, step, lo, hi = _grid_frames(v["expr"], d, SURF_N)
    data = {"n": SURF_N, "frames": frames, "step": round(step, 4), "zmin": lo, "zmax": hi, "expr": v["expr"]}
    return _gl_scene(ctx, v, t, d, "surface", data)


def layout_objects3d(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = _label_items(ctx, v)[:5] or [{"text": ""}]
    return _gl_scene(ctx, v, t, d, "objects", {"items": [{"text": i["text"]} for i in items]})


_LAND: list[list[float]] | None = None


def _land_points() -> list[list[float]]:
    global _LAND
    if _LAND is None:
        pts = []
        lat = -84.0
        while lat <= 84:
            step = 3.0 / max(0.25, math.cos(math.radians(lat)))
            lon = -180.0
            while lon < 180:
                if is_land(lon, lat):
                    pts.append([round(lat, 1), round(lon, 1)])
                lon += step
            lat += 3.0
        _LAND = pts
    return _LAND


def layout_globe3d(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = [
        {"text": i["label"], "lat": float(i["lat"]), "lon": float(i["lon"])}
        for i in (v.get("items") or [])
        if i.get("lat") is not None and i.get("lon") is not None
    ][:5]
    return _gl_scene(ctx, v, t, d, "globe", {"items": items, "land": _land_points()})


def layout_bars3d(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    items = [i for i in _label_items(ctx, v) if i.get("value") is not None][:6]
    top = max(abs(float(i["value"])) for i in items) or 1.0
    bars = [
        {
            "text": i["text"],
            "h": round(0.25 + 3.3 * abs(float(i["value"])) / top, 3),
            "hi": abs(i["value"]) == top,
        }
        for i in items
    ]
    return _gl_scene(ctx, v, t, d, "bars", {"bars": bars})


def layout_particles3d(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    data: dict = {"seed": 7}
    if v.get("expr"):
        frames, step, lo, hi = _grid_frames(v["expr"], d, 48)
        data.update(n=48, frames=frames, step=round(step, 4), zmin=lo, zmax=hi)
    return _gl_scene(ctx, v, t, d, "particles", data)


# --- Diagrama ----------------------------------------------------------------------------------------------------


def _layers(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Profundidad de cada nodo (camino más largo desde una fuente), a prueba de ciclos."""
    depth = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for e in edges:
            a, b = e["from"], e["to"]
            if a in depth and b in depth and a != b and depth[b] < depth[a] + 1 and depth[a] + 1 < len(nodes):
                depth[b] = depth[a] + 1
                changed = True
        if not changed:
            break
    return depth


def layout_diagram(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    nodes = (v.get("nodes") or [])[:7]
    # Las aristas llegan como from/to (alias del guion); también se aceptan source/target por si vienen sin alias.
    edges = [
        {
            "from": e.get("from") or e.get("source"),
            "to": e.get("to") or e.get("target"),
            "label": e.get("label"),
        }
        for e in (v.get("edges") or [])
    ]
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids][:10]
    depth = _layers(nodes, edges)
    n_layers = max(depth.values()) + 1
    by_layer: dict[int, list[dict]] = {}
    for n in nodes:
        by_layer.setdefault(depth[n["id"]], []).append(n)
    W, H = fr.sw, max(300.0, fr.sh - hh - 10)
    horizontal = fr.w > fr.h and W > H * 1.3
    widest = max(len(x) for x in by_layer.values())
    if horizontal:
        bw = min(360.0, (W - 90 * (n_layers - 1)) / n_layers)
        bh = min(170.0, (H - 40 * (widest - 1)) / widest)
    else:
        bw = min(560.0, (W - 40 * (widest - 1)) / widest)
        bh = min(150.0, (H - 70 * (n_layers - 1)) / n_layers)
    pos: dict[str, tuple[float, float]] = {}
    for layer, members in by_layer.items():
        for k, n in enumerate(members):
            if horizontal:
                x = layer * (W - bw) / max(1, n_layers - 1) if n_layers > 1 else (W - bw) / 2
                y = (H - len(members) * bh - (len(members) - 1) * 40) / 2 + k * (bh + 40)
            else:
                y = layer * (H - bh) / max(1, n_layers - 1) if n_layers > 1 else (H - bh) / 2
                x = (W - len(members) * bw - (len(members) - 1) * 40) / 2 + k * (bw + 40)
            pos[n["id"]] = (x, y)
    order = sorted(nodes, key=lambda n: (depth[n["id"]], pos[n["id"]][0], pos[n["id"]][1]))
    span = max(1.0, d * 0.7 - 0.5)
    appear = {n["id"]: t + 0.45 + i * span / max(1, len(order)) for i, n in enumerate(order)}
    parts, arrows = [], []
    mark = ctx.uid("arr")
    for n in order:
        x, y = pos[n["id"]]
        el = ctx.uid("dn")
        ctx.pop(el, appear[n["id"]], 0.55)
        note = f'<div class="dg-note">{esc(n["note"])}</div>' if n.get("note") else ""
        size = fit_size(n["label"], ctx.style["fonts"]["display"], 46 * ctx.style["display_scale"], 24, 2,
                        width=bw - 40, upper=ctx.style["uppercase"])  # fmt: skip
        parts.append(
            f'<div id="{el}" class="dg-node" style="left:{x:.0f}px;top:{y:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px">'
            f'<div class="dg-label" style="font-size:{size}px">{esc(n["label"])}</div>{note}</div>'
        )
    for e in edges:
        (ax, ay), (bx, by) = pos[e["from"]], pos[e["to"]]
        if horizontal:
            x1, y1, x2, y2 = ax + bw, ay + bh / 2, bx, by + bh / 2
            mid = (x1 + x2) / 2
            path = f"M{x1:.1f},{y1:.1f} C{mid:.1f},{y1:.1f} {mid:.1f},{y2:.1f} {x2 - 6:.1f},{y2:.1f}"
        else:
            x1, y1, x2, y2 = ax + bw / 2, ay + bh, bx + bw / 2, by
            if y2 <= y1:  # arista hacia atrás o en la misma capa: rodea por un lado
                x1, y1, x2, y2 = ax + bw, ay + bh / 2, bx + bw, by + bh / 2
                side = max(x1, x2) + 70
                path = f"M{x1:.1f},{y1:.1f} C{side:.1f},{y1:.1f} {side:.1f},{y2:.1f} {x2 + 6:.1f},{y2:.1f}"
            else:
                mid = (y1 + y2) / 2
                path = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{mid:.1f} {x2:.1f},{mid:.1f} {x2:.1f},{y2 - 6:.1f}"
        el = ctx.uid("de")
        at = max(appear[e["from"]], appear[e["to"]] - 0.35)
        _draw(ctx, el, at, 0.55)
        arrows.append(
            f'<path id="{el}" d="{path}" class="dg-edge" pathLength="1" stroke-dasharray="1" '
            f'style="stroke-dashoffset:1" marker-end="url(#{mark})"/>'
        )
        if e.get("label"):
            lab = ctx.uid("dl")
            ctx.enter(lab, at + 0.4, dy=8, dur=0.35)
            parts.append(
                f'<div id="{lab}" class="dg-elab" style="left:{(x1 + x2) / 2:.0f}px;top:{(y1 + y2) / 2:.0f}px">'
                f"{esc(e['label'])}</div>"
            )
    defs = (
        f'<defs><marker id="{mark}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="dg-head"/></marker></defs>'
    )
    return (
        f'<div class="col">{head}<div class="dg" style="height:{H:.0f}px"><svg class="dg-svg" width="{W:.0f}" '
        f'height="{H:.0f}" overflow="visible">{defs}{"".join(arrows)}</svg>{"".join(parts)}</div></div>'
    )


# --- Código ------------------------------------------------------------------------------------------------------


def layout_code(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    head, hh = _header(ctx, v, t)
    fr = ctx.frame
    lines = (v.get("code") or [])[:16]
    lang_name = v.get("language") or "text"
    longest = max([len(x) for x in lines] + [12])
    gutter = 70
    box_w = fr.sw
    size = round(max(18, min(40, (box_w - gutter - 60) / (longest * 0.62))))
    line_h = size * 1.5
    avail = fr.sh - hh - 90
    if len(lines) * line_h > avail:
        size = round(max(16, avail / len(lines) / 1.5))
        line_h = size * 1.5
    win = ctx.uid("cw")
    ctx.enter(win, t + 0.15, dy=30, dur=0.6)
    span = max(0.6, d * 0.68 - 0.7)
    rows = []
    hl = set(v.get("highlight") or [])
    for k, line in enumerate(lines):
        el = ctx.uid("cl")
        at = t + 0.6 + k * span / max(1, len(lines))
        dur = min(0.5, max(0.15, len(line) * 0.025))
        ctx.anim(el, [{"clipPath": "inset(0 100% 0 0)"}, {"clipPath": "inset(0 0% 0 0)"}], at, dur, "linear")
        mark = ""
        if k + 1 in hl:
            m = ctx.uid("ch")
            ctx.anim(m, [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}], t + 0.6 + span + 0.2, 0.5)
            mark = f'<div id="{m}" class="code-hl"></div>'
        rows.append(
            f'<div class="code-row" style="height:{line_h:.0f}px">{mark}<span class="code-n">{k + 1}</span>'
            f'<span id="{el}" class="code-text">{highlight_code(line, lang_name) or "&#8203;"}</span></div>'
        )
    return (
        f'<div class="col">{head}<div id="{win}" class="code-win" style="font-size:{size}px">'
        f'<div class="code-bar"><i></i><i></i><i></i><span>{esc(lang_name)}</span></div>'
        f'<div class="code-body">{"".join(rows)}</div></div></div>'
    )


# --- Fuentes -----------------------------------------------------------------------------------------------------


def layout_sources(ctx: _Ctx, v: dict, t: float, d: float, meta: dict) -> str:
    from urllib.parse import urlparse

    head, _ = _header(ctx, v, t, 76, 2)
    rows = []
    sources = meta.get("sources") or []
    for k, s in enumerate(sources[:6]):
        el = ctx.uid("src")
        ctx.enter(el, t + 0.4 + k * min(0.4, d * 0.5 / max(1, len(sources))), dy=20, dur=0.45)
        host = urlparse(s["url"]).netloc.removeprefix("www.")
        rows.append(
            f'<div id="{el}" class="src-row"><div class="src-n">{k + 1:02d}</div><div><div class="src-title">'
            f'{esc(s["title"])}</div><div class="src-host">{esc(host)}</div></div></div>'
        )
    return f'<div class="col">{head}<div class="src-list">{"".join(rows)}</div></div>'


RICH_BUILDERS = {
    "equation": layout_equation,
    "plot": layout_plot,
    "signal": layout_signal,
    "spectrum": layout_spectrum,
    "surface3d": layout_surface3d,
    "objects3d": layout_objects3d,
    "globe3d": layout_globe3d,
    "bars3d": layout_bars3d,
    "particles3d": layout_particles3d,
    "diagram": layout_diagram,
    "code": layout_code,
    "sources": layout_sources,
}


# --- CSS ---------------------------------------------------------------------------------------------------------

RICH_CSS = """
.eq-area{position:relative;display:flex;align-items:center;justify-content:center;width:100%}
.eq{display:flex;flex:none;width:max-content;flex-wrap:nowrap;justify-content:center;align-items:center;row-gap:.5em;column-gap:.28em;
  transform-origin:50% 50%;color:var(--ink)}
.eq-term{position:relative;display:inline-flex;flex-direction:column;align-items:center}
.eq-tex{display:inline-block;padding:.05em .04em}
.eq-tex .katex{font-size:1em}
.eq-hl{position:absolute;left:-.08em;right:-.08em;bottom:-.12em;height:calc(var(--stroke) * 1.6px);
  background:var(--accent2);transform-origin:left center;border-radius:var(--radius)}
.eq-note{position:absolute;top:calc(100% + .35em);left:50%;margin-left:-6em;width:12em;text-align:center;
  font-family:var(--mono),monospace;font-size:max(24px,.3em);font-weight:700;color:var(--accent2);
  text-transform:uppercase;letter-spacing:.06em;line-height:1.15}
.eq-under{position:absolute;left:10%;right:10%;bottom:0;height:3px;background:var(--line);transform-origin:center}
.plot{position:relative;width:100%;margin-top:auto;margin-bottom:auto}
.pl-svg{position:absolute;overflow:visible}
.grid{stroke:var(--line);stroke-width:1;opacity:.45}
.axis{stroke:var(--muted);stroke-width:3}
.axis.thin{stroke-width:1.5;opacity:.6}
.tick{fill:var(--muted);font-family:var(--mono),monospace;font-size:26px}
.curve{fill:none;stroke-width:calc(var(--stroke) * 1.3px);stroke-linecap:round;stroke-linejoin:round}
.curve.thin{stroke-width:calc(var(--stroke) * 0.8px)}
.ax-label{position:absolute;font-family:var(--mono),monospace;font-size:26px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.08em}
.ax-label.x{right:24px;bottom:-48px}
.ax-label.y{left:0;top:-30px}
.pl-param{position:absolute;right:24px;top:-34px;font-size:40px;color:var(--accent2);background:var(--bg);
  padding:2px 10px}
.legend{display:flex;flex-wrap:wrap;gap:12px 30px;justify-content:center}
.lg-item{display:flex;align-items:center;gap:12px;font-family:var(--mono),monospace;font-size:28px;color:var(--ink)}
.lg-sw{width:34px;height:8px;border-radius:4px}
.sig{position:relative;width:100%}
.sig-row{position:absolute}
.sig-row svg{position:absolute;overflow:visible}
.sig-lab{position:absolute;left:0;top:50%;transform:translateY(-50%);width:140px;font-family:var(--mono),monospace;
  font-weight:700;font-size:30px;line-height:1.1}
.sig-lab span{display:block;font-weight:400;font-size:22px;color:var(--muted)}
.sig-row.sum .sig-lab{color:var(--ink)}
.sig-plus{position:absolute;left:52px;bottom:-26px;font-family:var(--mono),monospace;font-size:34px;color:var(--muted)}
.sig-axis{position:absolute;right:0;bottom:-6px;font-family:var(--mono),monospace;font-size:22px;color:var(--muted)}
.sig-axis.right{bottom:auto;top:12px}
.spec{position:absolute;border-top:2px solid var(--line)}
.spec svg{position:absolute;overflow:visible}
.spec-y{position:absolute;left:0;top:12px;font-family:var(--mono),monospace;font-size:22px;color:var(--muted);
  text-transform:uppercase}
.spec-line{fill:none;stroke:var(--muted);stroke-width:2;opacity:.8}
.stem line{stroke:var(--accent);stroke-width:calc(var(--stroke) * 2px);stroke-linecap:butt}
.stem circle{fill:var(--accent2)}
.stem-lab{fill:var(--ink);font-family:var(--mono),monospace;font-weight:700;font-size:28px}
.fft-badge{position:absolute;left:50%;margin-left:-52px;top:-26px;font-family:var(--mono),monospace;font-weight:700;font-size:30px;
  padding:6px 16px;background:var(--accent);color:var(--bg);border-radius:var(--radius)}
.gl-wrap{position:relative;width:100%;margin-top:auto}
.gl{position:absolute;left:0;top:0;display:block}
.gl-labels{position:absolute;inset:0;pointer-events:none}
.gl-label{position:absolute;left:0;top:0;white-space:nowrap;font-family:var(--mono),monospace;font-weight:700;
  font-size:28px;padding:6px 12px;background:var(--ink);color:var(--bg);border-radius:var(--radius)}
.gl-fallback{position:absolute;inset:0;display:none}
.dg{position:relative;width:100%;margin-top:auto}
.dg-svg{position:absolute;left:0;top:0;overflow:visible}
.dg-edge{fill:none;stroke:var(--muted);stroke-width:calc(var(--stroke) * 1px)}
.dg-head{fill:var(--muted)}
.dg-node{position:absolute;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  padding:10px 18px;text-align:center;border:calc(var(--stroke) * 0.8px) solid var(--accent);border-radius:var(--radius);
  background:color-mix(in srgb,var(--bg) 82%,var(--accent))}
.dg-label{font-family:var(--display),sans-serif;font-weight:var(--dw);text-transform:var(--case);line-height:1.05;
  color:var(--ink)}
.dg-note{font-family:var(--mono),monospace;font-size:22px;color:var(--muted);line-height:1.15}
.dg-elab{position:absolute;transform:translate(-50%,-50%);font-family:var(--mono),monospace;font-size:24px;
  padding:4px 10px;background:var(--bg);color:var(--accent2);white-space:nowrap}
.code-win{margin-top:auto;margin-bottom:auto;border:2px solid var(--line);border-radius:var(--radius);
  background:color-mix(in srgb,var(--bg) 90%,var(--ink));overflow:hidden}
.code-bar{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:2px solid var(--line);
  font-family:var(--mono),monospace;font-size:22px;color:var(--muted)}
.code-bar i{width:14px;height:14px;border-radius:50%;background:var(--line)}
.code-bar span{margin-left:auto;text-transform:uppercase;letter-spacing:.1em}
.code-body{padding:18px 0}
.code-row{position:relative;display:flex;align-items:center;font-family:var(--mono),monospace;white-space:pre;
  color:var(--ink)}
.code-n{width:70px;flex:none;text-align:right;padding-right:22px;color:var(--muted);opacity:.6;font-size:.7em}
.code-text{display:block}
.code-hl{position:absolute;left:0;right:0;top:0;bottom:0;background:color-mix(in srgb,var(--accent2) 18%,transparent);
  border-left:6px solid var(--accent2);transform-origin:left center}
.tk-k{color:var(--accent2);font-weight:700}
.tk-s{color:var(--accent)}
.tk-n{color:var(--accent)}
.tk-f{color:var(--ink);text-decoration:underline;text-decoration-color:color-mix(in srgb,var(--accent) 60%,transparent)}
.tk-c{color:var(--muted);font-style:italic}
.src-list{display:flex;flex-direction:column;gap:34px;margin:auto 0}
.src-row{display:flex;gap:24px;align-items:flex-start}
.src-n{font-family:var(--mono),monospace;font-weight:700;font-size:34px;color:var(--accent);min-width:64px}
.src-title{font-size:34px;line-height:1.2;color:var(--ink)}
.src-host{font-family:var(--mono),monospace;font-size:24px;color:var(--muted);margin-top:6px}
"""

# Cómo cada estilo viste las plantillas técnicas (además de colores y fuentes, que vienen de las variables).
RICH_STYLE_CSS = {
    "neon": ".curve,.stem line{filter:drop-shadow(0 0 10px currentColor)}.eq{text-shadow:0 0 24px var(--accent2)}"
    ".dg-node{box-shadow:0 0 30px color-mix(in srgb,var(--accent) 45%,transparent)}",
    "atlas": ".grid{stroke-dasharray:4 6}.dg-node{background:transparent;border-style:double;border-width:6px}"
    ".code-win{background:color-mix(in srgb,var(--bg) 85%,#000)}",
    "blueprint": ".grid{opacity:.25}.dg-node{background:transparent;border-style:dashed}"
    ".code-win{background:rgba(0,20,60,.5)}.eq-hl{background:var(--accent2)}",
    "phosphor": ".curve,.spec-line{filter:drop-shadow(0 0 6px var(--ink))}.dg-node{background:transparent}"
    ".code-win{background:#000}",
    "swiss": ".grid{opacity:.2}.dg-node{border-radius:0;background:var(--bg)}.code-win{border-radius:0}"
    ".gl-label{border-radius:0}",
    "chalk": ".curve,.dg-edge,.eq,.stem line{filter:url(#chalk)}.dg-node{background:transparent;"
    "border-style:solid}.code-win{background:rgba(0,0,0,.25)}",
    "riso": ".curve{filter:drop-shadow(4px 3px 0 color-mix(in srgb,var(--accent) 60%,transparent))}"
    ".dg-node{box-shadow:8px 6px 0 color-mix(in srgb,var(--accent) 60%,transparent)}",
    "orbital": ".curve{filter:drop-shadow(0 0 8px currentColor)}.dg-node{background:rgba(11,20,48,.7)}",
    "concrete": ".dg-node{border-radius:0;background:var(--accent);border-color:var(--ink)}"
    ".code-win{border-radius:0;border-width:5px;border-color:var(--ink)}.fft-badge{color:var(--ink)}",
    "lab": ".dg-node{background:#111110;border-width:2px}.code-win{background:#111110}"
    ".curve{filter:drop-shadow(0 0 8px color-mix(in srgb,currentColor 40%,transparent))}",
    "manim": ".dg-node{background:transparent}.eq{color:var(--ink)}.code-win{background:#101215}",
}


# --- Lo que se ejecuta en la página ------------------------------------------------------------------------------

KATEX_JS = """
<script src="vendor/katex/katex.min.js"></script>
<script>
(function () {
  var T = %s;
  var nodes = document.querySelectorAll("[data-tex]");
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i], tex = T[+el.getAttribute("data-tex")];
    try {
      katex.render(tex, el, { throwOnError: false, trust: false, strict: "ignore", maxExpand: 100, maxSize: 10,
        output: "html", displayMode: false });
    } catch (e) { el.textContent = tex; }
  }
  function fit() {
    var boxes = document.querySelectorAll("[data-fit-w]");
    for (var j = 0; j < boxes.length; j++) {
      var b = boxes[j], w = +b.getAttribute("data-fit-w"), h = +b.getAttribute("data-fit-h");
      var s = Math.min(1, w / Math.max(1, b.scrollWidth), h / Math.max(1, b.scrollHeight));
      b.style.transform = s < 1 ? "scale(" + s.toFixed(4) + ")" : "";
    }
  }
  fit();
  window.__hf = window.__hf || {};
  window.__hf.buildReady = window.__hf.buildReady || {};
  window.__hf.buildReady.factoryTex = document.fonts.ready.then(fit);
})();
</script>
"""

THREE_JS = """
<script>
window.__hf = window.__hf || {};
window.__hf.buildReady = window.__hf.buildReady || {};
window.__hf.buildReady.factory3d = new Promise(function (r) { window.__factory3dReady = r; });
</script>
<script type="module">
import * as THREE from "./vendor/three/three.module.min.js";
const S = %s;
const P = %s;
const C = (c) => new THREE.Color(c);
const ease = (x) => { x = Math.min(1, Math.max(0, x)); return 1 - Math.pow(1 - x, 3); };
const back = (x) => { x = Math.min(1, Math.max(0, x)); const c = 1.7; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
function mulberry(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function fitDistance(camera, radius) {
  const v = THREE.MathUtils.degToRad(camera.fov) / 2;
  const h = Math.atan(Math.tan(v) * camera.aspect);
  return radius / Math.sin(Math.min(v, h));
}
function heightFrames(s) {
  return function (lt) {
    const F = s.frames, n = F.length;
    if (n === 1) return [F[0], F[0], 0];
    const x = Math.min(n - 1, Math.max(0, lt / s.step));
    const f = Math.min(n - 2, Math.floor(x));
    return [F[f], F[f + 1], x - f];
  };
}
function addLabel(b, text, obj, offset) {
  const el = document.createElement("div");
  el.className = "gl-label";
  el.textContent = text;
  document.getElementById(b.s.labels).appendChild(el);
  b.labels.push({ el, obj, offset: new THREE.Vector3(...offset), alpha: () => 1 });
  return b.labels[b.labels.length - 1];
}
const BUILD = {
  surface(b) {
    const s = b.s, N = s.n, scene = b.scene;
    const geo = new THREE.PlaneGeometry(6, 6, N - 1, N - 1);
    geo.rotateX(-Math.PI / 2);
    const colors = new Float32Array(N * N * 3);
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.5, metalness: 0.05 }));
    const wire = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: C(P.ink), wireframe: true, transparent: true, opacity: 0.16 }));
    scene.add(mesh, wire);
    const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(6, 3, 6)), new THREE.LineBasicMaterial({ color: C(P.line), transparent: true, opacity: 0.6 }));
    scene.add(box);
    const at = heightFrames(s), pos = geo.attributes.position;
    const lo = s.zmin, hi = s.zmax, k = 2.6 / Math.max(1e-6, hi - lo), mid = (lo + hi) / 2;
    const ca = C(P.accent).lerp(C(P.bg2), 0.55), cb = C(P.accent2), tmp = new THREE.Color();
    const dist = fitDistance(b.camera, 4.3);
    return (lt) => {
      const [A, B, a] = at(lt), grow = ease((lt - 0.2) / 1.4);
      for (let i = 0; i < N * N; i++) {
        const z = A[i] * (1 - a) + B[i] * a;
        pos.setY(i, (z - mid) * k * grow);
        tmp.copy(ca).lerp(cb, (z - lo) / Math.max(1e-6, hi - lo));
        colors[i * 3] = tmp.r; colors[i * 3 + 1] = tmp.g; colors[i * 3 + 2] = tmp.b;
      }
      pos.needsUpdate = true; geo.attributes.color.needsUpdate = true; geo.computeVertexNormals();
      const ang = 0.7 + lt * 0.22;
      b.camera.position.set(Math.cos(ang) * dist * 0.8, dist * 0.55, Math.sin(ang) * dist * 0.8);
      b.camera.lookAt(0, -0.2, 0);
    };
  },
  objects(b) {
    const s = b.s, scene = b.scene, n = s.items.length;
    const makers = [
      () => new THREE.BoxGeometry(1.3, 1.3, 1.3), () => new THREE.SphereGeometry(0.85, 48, 32),
      () => new THREE.TorusGeometry(0.7, 0.28, 32, 96), () => new THREE.IcosahedronGeometry(0.95, 0),
      () => new THREE.ConeGeometry(0.8, 1.5, 48), () => new THREE.TorusKnotGeometry(0.55, 0.2, 128, 16),
    ];
    const group = new THREE.Group(); scene.add(group);
    const R = n > 1 ? 1.9 + 0.25 * n : 0;
    const meshes = s.items.map((it, i) => {
      const geo = makers[i %% makers.length]();
      const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: C(i %% 2 ? P.accent2 : P.accent), roughness: 0.35, metalness: 0.15 }));
      m.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: C(P.ink), transparent: true, opacity: 0.35 })));
      const a = (i / n) * Math.PI * 2;
      m.position.set(Math.sin(a) * R, 0, Math.cos(a) * R);
      group.add(m);
      if (it.text) { const l = addLabel(b, it.text, m, [0, 1.35, 0]); l.alpha = (lt) => ease((lt - 0.8 - i * 0.3) / 0.4); }
      return m;
    });
    const dist = fitDistance(b.camera, R + 1.0);
    return (lt) => {
      meshes.forEach((m, i) => {
        const g = Math.max(0.0001, back((lt - 0.3 - i * 0.3) / 0.7));
        m.scale.setScalar(g);
        m.rotation.set(lt * 0.6 + i, lt * 0.9 + i * 0.7, 0);
      });
      group.rotation.y = lt * 0.32;
      b.camera.position.set(0, dist * 0.35, dist);
      b.camera.lookAt(0, 0, 0);
    };
  },
  globe(b) {
    const s = b.s, scene = b.scene, R = 2;
    const group = new THREE.Group(); scene.add(group);
    group.add(new THREE.Mesh(new THREE.SphereGeometry(R * 0.995, 64, 48), new THREE.MeshStandardMaterial({ color: C(P.bg2).lerp(C(P.line), 0.5), roughness: 0.8 })));
    const xyz = (lat, lon, r) => {
      const phi = (90 - lat) * Math.PI / 180, th = (lon + 180) * Math.PI / 180;
      return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th));
    };
    const land = new Float32Array(s.land.length * 3);
    s.land.forEach(([la, lo], i) => { const p = xyz(la, lo, R * 1.003); land[i * 3] = p.x; land[i * 3 + 1] = p.y; land[i * 3 + 2] = p.z; });
    const lg = new THREE.BufferGeometry(); lg.setAttribute("position", new THREE.BufferAttribute(land, 3));
    group.add(new THREE.Points(lg, new THREE.PointsMaterial({ color: C(P.accent), size: 0.07, transparent: true, opacity: 0.9 })));
    const halo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.12, 48, 32), new THREE.MeshBasicMaterial({ color: C(P.accent), transparent: true, opacity: 0.08, side: THREE.BackSide }));
    scene.add(halo);
    const markers = s.items.map((it, i) => {
      const m = new THREE.Mesh(new THREE.SphereGeometry(0.07, 24, 16), new THREE.MeshBasicMaterial({ color: C(P.accent2) }));
      m.position.copy(xyz(it.lat, it.lon, R * 1.01));
      group.add(m);
      const l = addLabel(b, it.text, m, [0, 0.25, 0]);
      l.normal = m.position.clone().normalize();
      return m;
    });
    const arcs = [];
    for (let i = 1; i < s.items.length; i++) {
      const a = xyz(s.items[i - 1].lat, s.items[i - 1].lon, 1), c = xyz(s.items[i].lat, s.items[i].lon, 1);
      const pts = [];
      for (let k = 0; k <= 64; k++) { const u = k / 64; const p = a.clone().lerp(c, u).normalize().multiplyScalar(R * (1.01 + 0.18 * Math.sin(Math.PI * u))); pts.push(p); }
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: C(P.accent) }));
      group.add(line); arcs.push(g);
    }
    const target = (it) => { const p = xyz(it.lat, it.lon, 1); return [Math.atan2(-p.x, p.z), it.lat * Math.PI / 180 * 0.55]; };
    const tg = s.items.length ? s.items.map(target) : [[0, 0]];
    const seg = Math.max(0.8, (s.dur - 0.8) / tg.length);
    const dist = fitDistance(b.camera, R * 1.15);
    const tmp = new THREE.Vector3();
    b.labels.forEach((l, i) => { l.alpha = (lt) => { l.obj.getWorldPosition(tmp); return ease((lt - 0.4 - i * seg) / 0.4) * (tmp.z > 0.3 ? 1 : 0); }; });
    return (lt) => {
      const x = Math.max(0, lt - 0.3) / seg, i = Math.min(tg.length - 1, Math.floor(x)), u = ease((x - i) / 0.6);
      const from = i === 0 ? [tg[0][0] - 0.9, 0] : tg[i - 1], to = tg[i];
      group.rotation.y = from[0] + (to[0] - from[0]) * (i === 0 ? ease(x / 0.8) : u);
      group.rotation.x = from[1] + (to[1] - from[1]) * (i === 0 ? ease(x / 0.8) : u);
      markers.forEach((m, k) => m.scale.setScalar(Math.max(0.001, back((lt - 0.4 - k * seg) / 0.5))));
      arcs.forEach((g, k) => g.setDrawRange(0, Math.round(65 * ease((lt - 0.2 - (k + 1) * seg) / 0.7))));
      b.camera.position.set(0, 0, dist);
      b.camera.lookAt(0, 0, 0);
    };
  },
  bars(b) {
    const s = b.s, scene = b.scene, n = s.bars.length, gap = 1.45;
    const grid = new THREE.GridHelper(gap * n + 2, (n + 2) * 2, C(P.line), C(P.line));
    grid.material.transparent = true; grid.material.opacity = 0.5; scene.add(grid);
    const meshes = s.bars.map((bar, i) => {
      const geo = new THREE.BoxGeometry(0.95, 1, 0.95); geo.translate(0, 0.5, 0);
      const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: C(bar.hi ? P.accent2 : P.accent), roughness: 0.4 }));
      m.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: C(P.ink), transparent: true, opacity: 0.3 })));
      m.position.x = (i - (n - 1) / 2) * gap; scene.add(m);
      const anchor = new THREE.Object3D(); anchor.position.set(m.position.x, bar.h, 0); scene.add(anchor);
      const l = addLabel(b, bar.text, anchor, [0, 0.45, 0]);
      l.alpha = (lt) => ease((lt - 1.0 - i * 0.25) / 0.4);
      l.grow = (lt) => anchor.position.y = Math.max(0.001, bar.h * ease((lt - 0.4 - i * 0.25) / 0.9));
      return m;
    });
    const dist = fitDistance(b.camera, (gap * n) / 2 + 1.2);
    return (lt) => {
      meshes.forEach((m, i) => m.scale.y = Math.max(0.001, s.bars[i].h * ease((lt - 0.4 - i * 0.25) / 0.9)));
      b.labels.forEach((l) => l.grow && l.grow(lt));
      const ang = -0.45 + lt * 0.08;
      b.camera.position.set(Math.sin(ang) * dist, dist * 0.42 + 1, Math.cos(ang) * dist);
      b.camera.lookAt(0, 1.3, 0);
    };
  },
  particles(b) {
    const s = b.s, scene = b.scene, rnd = mulberry(s.seed || 7);
    let count, positions, colors, update;
    const ca = C(P.accent), cb = C(P.accent2), tmp = new THREE.Color();
    const group = new THREE.Group(); scene.add(group);
    if (s.frames) {
      const N = s.n; count = N * N; positions = new Float32Array(count * 3); colors = new Float32Array(count * 3);
      const at = heightFrames(s), lo = s.zmin, hi = s.zmax, k = 2.4 / Math.max(1e-6, hi - lo), mid = (lo + hi) / 2;
      update = (lt) => {
        const [A, B, a] = at(lt), grow = ease((lt - 0.2) / 1.2);
        for (let i = 0; i < count; i++) {
          const ix = i %% N, iy = Math.floor(i / N), z = A[i] * (1 - a) + B[i] * a;
          positions[i * 3] = -3 + 6 * ix / (N - 1); positions[i * 3 + 2] = -3 + 6 * iy / (N - 1);
          positions[i * 3 + 1] = (z - mid) * k * grow;
          tmp.copy(ca).lerp(cb, (z - lo) / Math.max(1e-6, hi - lo)); colors[i * 3] = tmp.r; colors[i * 3 + 1] = tmp.g; colors[i * 3 + 2] = tmp.b;
        }
      };
    } else {
      count = 5000; positions = new Float32Array(count * 3); colors = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        const arm = i %% 3, r = Math.pow(rnd(), 0.6) * 3.4, a = arm * 2 * Math.PI / 3 + r * 1.25 + (rnd() - 0.5) * 0.5;
        positions[i * 3] = Math.cos(a) * r; positions[i * 3 + 1] = (rnd() - 0.5) * 0.35 * (3.6 - r); positions[i * 3 + 2] = Math.sin(a) * r;
        tmp.copy(ca).lerp(cb, r / 3.4); colors[i * 3] = tmp.r; colors[i * 3 + 1] = tmp.g; colors[i * 3 + 2] = tmp.b;
      }
      update = (lt) => { group.rotation.y = lt * 0.3; group.scale.setScalar(0.25 + 0.75 * ease(lt / 1.4)); };
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    group.add(new THREE.Points(geo, new THREE.PointsMaterial({ size: s.frames ? 0.07 : 0.045, vertexColors: true, transparent: true, opacity: 0.95 })));
    const dist = fitDistance(b.camera, 3.6);
    return (lt) => {
      update(lt); geo.attributes.position.needsUpdate = true; geo.attributes.color.needsUpdate = true;
      const ang = 0.6 + lt * 0.18;
      b.camera.position.set(Math.cos(ang) * dist * 0.85, dist * 0.5, Math.sin(ang) * dist * 0.85);
      b.camera.lookAt(0, 0, 0);
    };
  },
};
const built = [];
const v = new THREE.Vector3();
try {
  for (const s of S) {
    const canvas = document.getElementById(s.canvas);
    let renderer = null;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch (e) { renderer = null; }
    if (!renderer) { canvas.style.display = "none"; document.getElementById(s.fallback).style.display = "block"; continue; }
    renderer.setPixelRatio(1);
    renderer.setSize(s.w, s.h, false);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, s.w / s.h, 0.1, 200);
    scene.add(new THREE.HemisphereLight(0xffffff, C(P.bg2), 0.75));
    const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(5, 9, 7); scene.add(key);
    const rim = new THREE.DirectionalLight(C(P.accent), 1.2); rim.position.set(-6, 3, -6); scene.add(rim);
    const b = { s, renderer, scene, camera, labels: [] };
    b.update = BUILD[s.kind](b);
    built.push(b);
  }
} finally {
  renderAt(window.__hfThreeTime || 0);
  if (window.__factory3dReady) window.__factory3dReady();
}
function renderAt(time) {
  for (const b of built) {
    const lt = time - b.s.start;
    if (lt < -0.05 || lt > b.s.dur + 0.05) continue;
    b.update(Math.max(0, lt));
    b.renderer.render(b.scene, b.camera);
    for (const l of b.labels) {
      l.obj.getWorldPosition(v); v.add(l.offset); v.project(b.camera);
      const x = (v.x + 1) / 2 * b.s.w, y = (1 - v.y) / 2 * b.s.h;
      l.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(-50%%,-100%%)";
      l.el.style.opacity = String(v.z < 1 ? l.alpha(Math.max(0, lt)) : 0);
    }
  }
}
window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
</script>
"""


def runtime(ctx: _Ctx) -> tuple[str, str]:
    """(lo que va en <head>, lo que va al final de <body>) según lo que usen las escenas."""
    head, body = "", ""
    if ctx.tex:
        head += '<link rel="stylesheet" href="vendor/katex/katex.min.css" />\n'
        body += KATEX_JS % script_json(ctx.tex)
    if ctx.gl:
        body += THREE_JS % (script_json(ctx.gl), script_json(_palette(ctx)))
    return head, body


def assets_needed(html: str) -> set[str]:
    """Qué carpetas de `factory_assets/vendor` necesita una composición."""
    return {name for name in ("katex", "three") if f"vendor/{name}/" in html}


_ = EASE  # reexportado para quien componga escenas nuevas
