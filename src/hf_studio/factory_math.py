"""Matemática segura para las escenas ricas de Content Factory: expresiones, muestreo, FFT, LaTeX y código.

Nada de lo que escribe el guion se ejecuta como código: las expresiones (`sin(2*pi*x)`) pasan por un analizador
propio con una lista cerrada de operadores, funciones, constantes y variables, y se evalúan aquí con numpy. A la
composición solo llegan números (trazos SVG ya muestreados, rejillas de alturas, el espectro calculado), texto
escapado y LaTeX validado que KaTeX dibuja sin `trust` (sin enlaces, sin HTML, sin macros nuevas).
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass

import numpy as np

# --- Expresiones -------------------------------------------------------------------------------------------------

MAX_EXPR = 120
MAX_TOKENS = 80
MAX_DEPTH = 24
FUNCTIONS = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "exp": np.exp,
    "log": np.log,
    "ln": np.log,
    "sqrt": np.sqrt,
    "abs": np.abs,
}
CONSTANTS = {"pi": math.pi, "e": math.e}
_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d*)?|\.\d+)|([A-Za-z]+)|(\*\*|[-+*/^(),]))")


class ExprError(ValueError):
    pass


@dataclass(frozen=True)
class Expr:
    """Una expresión ya analizada: el árbol y el texto normalizado."""

    tree: tuple
    source: str
    variables: frozenset[str]

    def __call__(self, **env: np.ndarray | float) -> np.ndarray:
        with np.errstate(all="ignore"):
            out = _eval(self.tree, env)
        return np.asarray(out, dtype=float)


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprError(f"Unexpected character {text[pos]!r} in expression")
        num, name, op = m.groups()
        if num is not None:
            out.append(("num", num))
        elif name is not None:
            out.append(("name", name.lower()))
        else:
            out.append(("op", "^" if op == "**" else op))
        pos = m.end()
        if len(out) > MAX_TOKENS:
            raise ExprError("Expression is too long")
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], allowed: frozenset[str]):
        self.toks, self.i, self.allowed, self.used = tokens, 0, allowed, set()

    def peek(self) -> tuple[str, str] | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ExprError("Expression ends too early")
        self.i += 1
        return tok

    def expect(self, op: str) -> None:
        tok = self.take()
        if tok != ("op", op):
            raise ExprError(f"Expected {op!r}")

    def parse(self) -> tuple:
        tree = self.expr(0)
        if self.peek() is not None:
            raise ExprError(f"Unexpected {self.peek()[1]!r}")
        return tree

    def expr(self, depth: int) -> tuple:
        if depth > MAX_DEPTH:
            raise ExprError("Expression is nested too deeply")
        node = self.term(depth + 1)
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            node = (op, node, self.term(depth + 1))
        return node

    def term(self, depth: int) -> tuple:
        node = self.unary(depth + 1)
        while True:
            tok = self.peek()
            if tok in (("op", "*"), ("op", "/")):
                op = self.take()[1]
                node = (op, node, self.unary(depth + 1))
            elif tok is not None and (tok[0] in ("num", "name") or tok == ("op", "(")):
                node = ("*", node, self.unary(depth + 1))  # multiplicación implícita: 2pi, 3x, 2(x+1)
            else:
                return node

    def unary(self, depth: int) -> tuple:
        if depth > MAX_DEPTH:
            raise ExprError("Expression is nested too deeply")
        tok = self.peek()
        if tok in (("op", "-"), ("op", "+")):
            self.take()
            inner = self.unary(depth + 1)
            return ("neg", inner) if tok[1] == "-" else inner
        return self.power(depth + 1)

    def power(self, depth: int) -> tuple:
        base = self.atom(depth + 1)
        if self.peek() == ("op", "^"):
            self.take()
            return ("^", base, self.unary(depth + 1))
        return base

    def atom(self, depth: int) -> tuple:
        if depth > MAX_DEPTH:
            raise ExprError("Expression is nested too deeply")
        kind, val = self.take()
        if kind == "num":
            num = float(val)
            if not math.isfinite(num) or num > 1e9:
                raise ExprError("Numbers in expressions must be at most 1e9")
            return ("num", num)
        if kind == "name":
            if val in FUNCTIONS:
                self.expect("(")
                arg = self.expr(depth + 1)
                self.expect(")")
                return ("fn", val, arg)
            if val in CONSTANTS:
                return ("num", CONSTANTS[val])
            if val in self.allowed:
                self.used.add(val)
                return ("var", val)
            raise ExprError(f"Unknown name {val!r} (allowed: {', '.join(sorted(self.allowed))})")
        if val == "(":
            node = self.expr(depth + 1)
            self.expect(")")
            return node
        raise ExprError(f"Unexpected {val!r}")


def parse_expr(text: str, allowed: tuple[str, ...] = ("x", "t")) -> Expr:
    """Analiza una expresión de la lista blanca. Lanza ExprError si sale de ella."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError("Empty expression")
    if len(text) > MAX_EXPR:
        raise ExprError(f"Expression longer than {MAX_EXPR} characters")
    parser = _Parser(_tokens(text), frozenset(allowed))
    tree = parser.parse()
    return Expr(tree, " ".join(text.split()), frozenset(parser.used))


def _eval(node: tuple, env: dict) -> np.ndarray | float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        return env.get(node[1], 0.0)
    if kind == "neg":
        return -_eval(node[1], env)
    if kind == "fn":
        return FUNCTIONS[node[1]](_eval(node[2], env))
    a, b = _eval(node[1], env), _eval(node[2], env)
    if kind == "+":
        return a + b
    if kind == "-":
        return a - b
    if kind == "*":
        return a * b
    if kind == "/":
        return np.divide(a, b)
    if kind == "^":
        return np.power(np.asarray(a, dtype=float), b)
    raise ExprError(f"Bad node {kind}")


# --- Muestreo y trazos -------------------------------------------------------------------------------------------


def sample(expr: Expr, x0: float, x1: float, n: int = 240, t: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(x0, x1, n)
    ys = expr(x=xs, t=t)
    if ys.ndim == 0:
        ys = np.full_like(xs, float(ys))
    return xs, ys


LIMIT = 1e12  # |y| mayor no se dibuja


def auto_range(values: list[np.ndarray]) -> tuple[float, float]:
    """Rango vertical que no deja que una asíntota (tan, 1/x) aplaste la curva: percentiles y un margen."""
    # Solo valores que el trazo puede dibujar (svg_path descarta |y| > 1e12): sin ellos, un rango por defecto.
    finite = (
        np.concatenate([v[np.isfinite(v) & (np.abs(v) <= LIMIT)] for v in values]) if values else np.array([])
    )
    if finite.size == 0:
        return -1.0, 1.0
    lo, hi = float(np.percentile(finite, 2)), float(np.percentile(finite, 98))
    if not hi - lo > max(1e-9, abs(hi) * 1e-9):
        # Curva constante (también enorme: sumar 1 a 1e18 no la mueve): margen relativo a su magnitud.
        delta = max(1.0, abs(hi) * 0.1)
        lo, hi = lo - delta, hi + delta
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad
    return (lo, hi) if math.isfinite(lo) and math.isfinite(hi) and hi > lo else (-1.0, 1.0)


def svg_path(
    xs: np.ndarray,
    ys: np.ndarray,
    box: tuple[float, float, float, float],
    w: float,
    h: float,
    continuous: bool = False,
) -> str:
    """Trazo SVG de (xs, ys) en un rectángulo de w×h. Sin `continuous`, corta en los huecos (NaN, saltos de
    asíntota); con él, recorta al marco y nunca corta, para que todas las versiones animadas tengan los mismos
    comandos (WAAPI interpola `d` solo así)."""
    x0, x1, y0, y1 = box
    if not (x1 > x0 and y1 > y0):  # un marco sin área no se puede dibujar: se ensancha
        x1, y1 = max(x1, x0 + 1.0), max(y1, y0 + 1.0)
    sx = w / (x1 - x0)
    sy = h / (y1 - y0)
    parts: list[str] = []
    pen = False
    prev_y = None
    for x, y in zip(xs, ys, strict=True):
        bad = not math.isfinite(float(y)) or abs(float(y)) > 1e12
        if continuous:
            yy = 0.0 if bad else float(y)
            py = h - (min(max(yy, y0 - (y1 - y0)), y1 + (y1 - y0)) - y0) * sy
            parts.append(f"{'L' if parts else 'M'}{(x - x0) * sx:.1f},{py:.1f}")
            continue
        if bad:
            pen = False
            prev_y = None
            continue
        py = h - (float(y) - y0) * sy
        jump = prev_y is not None and abs(py - prev_y) > h * 1.5
        if py < -h or py > 2 * h:
            pen = False
            prev_y = None
            continue
        parts.append(f"{'L' if pen and not jump else 'M'}{(x - x0) * sx:.1f},{py:.1f}")
        pen = True
        prev_y = py
    return "".join(parts) or f"M0,{h:.1f}"


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    span = hi - lo
    if span <= 0 or not math.isfinite(span):
        return [lo]
    raw = span / max(1, count)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step) * step
    ticks = []
    v = first
    while v <= hi + step * 1e-6 and len(ticks) < 12:
        ticks.append(round(v, 10))
        v += step
    return ticks


# --- Señales y espectro ------------------------------------------------------------------------------------------


def spectrum(waves: list[dict], seconds: float = 4.0) -> tuple[np.ndarray, np.ndarray, float]:
    """FFT de verdad de la suma de senos: (frecuencias en Hz, amplitud de un lado, frecuencia de muestreo).

    Se muestrea a 8 veces la frecuencia más alta (al menos 256 Hz) durante `seconds`: con frecuencias que caben un
    número entero de veces en la ventana, cada pico mide exactamente la amplitud del componente."""
    fmax = max(float(w["freq"]) for w in waves)
    fs = max(256.0, 8.0 * fmax)
    n = round(fs * seconds)
    ts = np.arange(n) / fs
    sig = signal_values(waves, ts)
    mags = np.abs(np.fft.rfft(sig)) * 2.0 / n
    mags[0] /= 2.0  # la componente continua no se duplica
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    return freqs, mags, fs


def signal_values(waves: list[dict], ts: np.ndarray) -> np.ndarray:
    out = np.zeros_like(ts, dtype=float)
    for w in waves:
        out += float(w["amp"]) * np.sin(2 * np.pi * float(w["freq"]) * ts + float(w.get("phase") or 0.0))
    return out


def peaks(freqs: np.ndarray, mags: np.ndarray, rel: float = 0.05) -> list[tuple[float, float]]:
    """Máximos locales del espectro por encima de `rel` del mayor: (frecuencia, amplitud)."""
    top = float(mags.max()) if mags.size else 0.0
    out = []
    for i in range(1, len(mags) - 1):
        if mags[i] >= top * rel and mags[i] >= mags[i - 1] and mags[i] > mags[i + 1]:
            out.append((float(freqs[i]), float(mags[i])))
    return out


# --- LaTeX -------------------------------------------------------------------------------------------------------

MAX_TEX = 160
# KaTeX corre con trust=false (sin \href, \url, \html…); además se rechazan aquí las órdenes que definen macros,
# leen archivos o tocan HTML, para que un guion no pueda colar nada ni colgar el render con expansiones.
_TEX_DENY = {
    "href",
    "url",
    "includegraphics",
    "def",
    "gdef",
    "edef",
    "xdef",
    "let",
    "futurelet",
    "newcommand",
    "renewcommand",
    "providecommand",
    "newenvironment",
    "input",
    "include",
    "write",
    "immediate",
    "catcode",
    "csname",
    "endcsname",
    "expandafter",
    "htmlclass",
    "htmlid",
    "htmlstyle",
    "htmldata",
    "char",
    "globallet",
    "global",
    "long",
    "verb",
}


def check_tex(tex: str) -> str:
    """Valida un trozo de LaTeX para KaTeX: largo, llaves equilibradas, sin órdenes peligrosas ni HTML."""
    tex = tex.strip()
    if not tex:
        raise ValueError("empty LaTeX")
    if len(tex) > MAX_TEX:
        raise ValueError(f"LaTeX longer than {MAX_TEX} characters")
    if any(c in tex for c in "<>\x00") or any(ord(c) < 32 and c not in "\t" for c in tex):
        raise ValueError("LaTeX cannot contain <, > or control characters (use \\lt and \\gt)")
    for name in re.findall(r"\\([A-Za-z]+)", tex):
        if name.lower() in _TEX_DENY:
            raise ValueError(f"LaTeX command \\{name} is not allowed")
    depth = 0
    escaped = False
    for c in tex:
        if escaped:
            escaped = False
            continue
        if c == "\\":
            escaped = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                break
    if depth != 0:
        raise ValueError("unbalanced braces in LaTeX")
    if tex.count("#") or tex.count("$"):
        raise ValueError("LaTeX cannot contain # or $")
    return tex


# --- Código ------------------------------------------------------------------------------------------------------

CODE_LANGUAGES = {
    "python": "py",
    "javascript": "js",
    "typescript": "js",
    "c": "c",
    "cpp": "c",
    "java": "c",
    "go": "c",
    "rust": "c",
    "bash": "sh",
    "sql": "sql",
    "matlab": "m",
    "text": "",
}
_KEYWORDS = {
    "py": "and as assert async await break class continue def del elif else except False finally for from global if "
    "import in is lambda None nonlocal not or pass raise return True try while with yield",
    "js": "async await break case catch class const continue default delete do else export extends false finally for "
    "function if import in instanceof let new null of return super switch this throw true try typeof undefined var "
    "void while yield interface type",
    "c": "auto bool break case char class const continue default do double else enum extern false float for fn func "
    "go if impl import int let long loop match mut new nil package pub return self short signed sizeof static "
    "struct switch true typedef union unsigned use var void while public private final",
    "sh": "if then else fi for in do done while case esac function return export echo local",
    "sql": "select from where group by order having join left right inner outer on as and or not insert into values "
    "update set delete create table limit with",
    "m": "function end if else elseif for while return break switch case otherwise",
}
_COMMENT = {"py": "#", "sh": "#", "js": "//", "c": "//", "sql": "--", "m": "%"}
_CODE_TOKEN = re.compile(
    r"(?P<str>\"(?:[^\"\\]|\\.)*\"?|'(?:[^'\\]|\\.)*'?|`[^`]*`?)|(?P<num>\b\d+(?:\.\d+)?\b)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<other>.)"
)


def highlight_code(line: str, language: str) -> str:
    """Una línea de código en HTML escapado con <span class="tk-…"> por token (palabra clave, texto, número,
    comentario, función). Todo lo que viene del guion pasa por html.escape."""
    family = CODE_LANGUAGES.get(language.lower(), "")
    keywords = set(_KEYWORDS.get(family, "").split())
    if family == "sql":
        keywords |= {k.upper() for k in keywords}
    marker = _COMMENT.get(family)
    comment = ""
    if marker:
        # El comentario empieza en el primer marcador fuera de comillas.
        quote = None
        for i, c in enumerate(line):
            if quote:
                if c == quote:
                    quote = None
            elif c in "\"'`":
                quote = c
            elif line.startswith(marker, i):
                line, comment = line[:i], line[i:]
                break
    out: list[str] = []
    tokens = list(_CODE_TOKEN.finditer(line))
    for k, m in enumerate(tokens):
        text = html.escape(m.group(0), quote=True)
        if m.lastgroup == "str":
            out.append(f'<span class="tk-s">{text}</span>')
        elif m.lastgroup == "num":
            out.append(f'<span class="tk-n">{text}</span>')
        elif m.lastgroup == "word" and family and m.group(0) in keywords:
            out.append(f'<span class="tk-k">{text}</span>')
        elif m.lastgroup == "word" and k + 1 < len(tokens) and tokens[k + 1].group(0) == "(":
            out.append(f'<span class="tk-f">{text}</span>')
        else:
            out.append(text)
    if comment:
        out.append(f'<span class="tk-c">{html.escape(comment, quote=True)}</span>')
    return "".join(out)


# --- JSON dentro de <script> -------------------------------------------------------------------------------------


def script_json(data: object) -> str:
    """JSON que se puede poner dentro de un <script> sin que un texto del guion lo cierre (`</script>`, `<!--`)."""
    import json

    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
