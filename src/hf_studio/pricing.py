"""Estimación de costo antes de generar, normalizada para la UI y los agentes.

Higgsfield responde `/estimate` de dos formas: un costo exacto (`credits`, `usd`, `discount`) o, en los
modelos medidos por uso, solo la fórmula en texto (`pricing_description`). Aquí:

- se rellenan con URLs de ejemplo los medios obligatorios que aún no se subieron, para poder
  cotizar antes de subir nada (el precio no depende del contenido de una imagen);
- se interpretan las fórmulas conocidas (a 2026-09) para dar un aproximado en USD, con la
  base del cálculo y lo que falte para afinarlo (p. ej. la duración del video de entrada).
"""

from __future__ import annotations

import math
import re
from typing import Any

PLACEHOLDER = {
    "image": "https://example.com/hf-studio-placeholder.png",
    "video": "https://example.com/hf-studio-placeholder.mp4",
    "audio": "https://example.com/hf-studio-placeholder.wav",
}
SHORT_SIDE = {"480p": 480, "720p": 720, "1080p": 1080, "2k": 1440, "4k": 2160}
MONEY = r"\$(\d+(?:\.\d+)?)"  # sin el punto final de la frase


def _media_kind(key: str) -> str | None:
    if not (key.endswith(("_url", "_urls")) or key == "input_images"):
        return None
    if key.startswith("video"):
        return "video"
    if key.startswith("audio"):
        return "audio"
    return "image"


def fill_placeholders(schema: dict, args: dict) -> tuple[dict, list[str]]:
    """Devuelve (entrada con medios de ejemplo, campos rellenados). Respeta if/then/else."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    cond_if = set(schema.get("if", {}).get("required", []))
    if cond_if:
        branch = "then" if cond_if <= args.keys() else "else"
        required |= set(schema.get(branch, {}).get("required", []))
    else:
        required |= set(schema.get("else", {}).get("required", []))
    filled = dict(args)
    added = []
    for key in sorted(required - args.keys()):
        kind = _media_kind(key)
        if kind:
            url = PLACEHOLDER[kind]
            filled[key] = [url] if props.get(key, {}).get("type") == "array" or key == "input_images" else url
            added.append(key)
        elif key in ("prompt", "multi_prompt") and props.get(key, {}).get("type") == "string":
            filled[key] = "cost preview"
            added.append(key)
    return filled, added


def _output_size(args: dict) -> tuple[int, int, bool]:
    """(ancho, alto, supuesto): el formato puede venir de la imagen de entrada; si no, 16:9."""
    res = str(args.get("resolution") or args.get("quality") or "720p").lower()
    short = SHORT_SIDE.get(res, 720)
    ratio = str(args.get("aspect_ratio") or "")
    assumed = False
    try:
        a, b = (float(x) for x in ratio.split(":"))
    except ValueError:
        a, b, assumed = 16.0, 9.0, True
    long = round(short * max(a, b) / min(a, b))
    return (long, short, assumed) if a >= b else (short, long, assumed)


def _count_video_inputs(args: dict) -> int:
    n = 0
    for key, value in args.items():
        if key.startswith("video") and _media_kind(key):
            n += len(value) if isinstance(value, list) else 1
    return n


def approximate(description: str, args: dict, hints: dict) -> dict:
    """Interpreta la fórmula de precio. Devuelve usd (o None), base del cálculo y datos que faltan."""
    seconds = float(args.get("duration") or 5)
    res = str(args.get("resolution") or "720p").lower()
    input_secs = hints.get("input_video_seconds")
    has_video_input = _count_video_inputs(args) > 0
    missing: list[str] = []
    text = description

    # A) Por segundo generado según resolución.
    if m := re.search(r"per generated second by resolution: (.*?)\. ", text):
        rates = dict(re.findall(r"(\d+p) " + MONEY, m.group(1)))
        if res in rates:
            return {
                "usd": seconds * float(rates[res]),
                "basis": f"{seconds:g}s × ${rates[res]}/s at {res}",
                "missing": [],
            }

    # B) Tokens de video: segundos × ancho × alto × 24 / 1024.
    if "video tokens" in text.lower():
        billable = seconds
        if "input video seconds" in text and has_video_input:
            if input_secs is None:
                missing.append("input video duration")
            else:
                billable += float(input_secs)
        width, height, assumed = _output_size(args)
        tokens = math.ceil(billable * width * height * 24 / 1024)
        big = res == "4k"
        # Tarifas por 1.000 tokens, de la más específica a la más general.
        patterns = [
            (
                has_video_input,
                r"with video input — 480p/720p/1080p " + MONEY + r", 4K " + MONEY,
                1 if not big else 2,
            ),
            (True, r"480p/720p/1080p " + MONEY + r", 4K " + MONEY, 1 if not big else 2),
            (
                True,
                r"cost " + MONEY + r" without video input or " + MONEY + r" with video input",
                2 if has_video_input else 1,
            ),
            (True, r"each 1,000 video tokens cost " + MONEY, 1),
        ]
        rate = None
        for applies, pattern, group in patterns:
            if applies and (m := re.search(pattern, text)):
                rate = float(m.group(group))
                break
        if rate is not None:
            basis = f"{billable:g}s × {width}×{height} → {tokens:,} tokens × ${rate}/1K"
            if assumed:
                basis += " (16:9 assumed)"
            return {"usd": tokens / 1000 * rate, "basis": basis, "missing": missing}

    # C) Por segundo de video de entrada.
    if m := re.search(
        r"Each second of input video costs " + MONEY + r" at 480p or " + MONEY + r" at 720p", text
    ):
        rate = float(m.group(2) if res == "720p" else m.group(1))
        if input_secs is None:
            return {
                "usd": None,
                "basis": f"${rate}/s of input video at {res}",
                "missing": ["input video duration"],
            }
        secs = math.ceil(float(input_secs))
        return {"usd": secs * rate, "basis": f"{secs}s of input video × ${rate}/s", "missing": []}

    # D) Salida 2K por segundo + imágenes de referencia extra.
    if m := re.search(
        r"costs "
        + MONEY
        + r" per generated second\. The first (\w+) reference images are included; each additional reference image costs "
        + MONEY,
        text,
    ):
        refs = len(args.get("image_urls") or [])
        included = {"five": 5}.get(m.group(2), 5)
        extra = max(0, refs - included)
        usd = seconds * float(m.group(1)) + extra * float(m.group(3))
        return {
            "usd": usd,
            "basis": f"{seconds:g}s × ${m.group(1)}/s + {extra} extra refs × ${m.group(3)}",
            "missing": [],
        }

    # E) Por tokens de texto/imagen (uso real): no se puede anticipar con precisión.
    return {"usd": None, "basis": "usage-based pricing (final cost depends on actual tokens)", "missing": []}


def normalize(raw: dict[str, Any], args: dict, hints: dict, placeholders: list[str]) -> dict:
    if raw.get("type") == "estimate" or "credits" in raw:
        discount = raw.get("discount") or {}
        return {
            "kind": "exact",
            "credits": float(raw["credits"]),
            "usd": float(raw["usd"]),
            "discount_pct": float(discount["percentage"]) if discount.get("percentage") else None,
            "basis": "Higgsfield estimate" + (" (media not uploaded yet)" if placeholders else ""),
            "missing": [],
            "description": None,
        }
    desc = raw.get("pricing_description", "")
    approx = approximate(desc, args, hints)
    return {
        "kind": "approx" if approx["usd"] is not None else "formula",
        "credits": None,
        "usd": round(approx["usd"], 4) if approx["usd"] is not None else None,
        "discount_pct": None,
        "basis": approx["basis"] + " · before discounts",
        "missing": approx["missing"],
        "description": desc,
    }


async def quote(hf, catalog, model: dict, args: dict, hints: dict) -> dict:
    """Cotiza una entrada (con medios de ejemplo si faltan). Lanza HiggsfieldError solo si es de credenciales."""
    from .higgsfield import HiggsfieldError

    filled, placeholders = fill_placeholders(model["input_schema"], args)
    errors = catalog.validate(model["id"], filled)
    if errors:
        return {"kind": "unavailable", "credits": None, "usd": None, "discount_pct": None,
                "basis": "Invalid input: " + "; ".join(f"{e['path']}: {e['message']}" for e in errors[:3]),
                "missing": [], "description": None, "errors": errors}  # fmt: skip
    try:
        raw = await hf.estimate(model["id"], filled)
    except HiggsfieldError as exc:
        if exc.kind == "auth":
            raise
        reason = (
            "Higgsfield needs the real media to price this model; upload it first"
            if placeholders
            else f"Higgsfield could not price this request ({exc.message})"
        )
        return {"kind": "unavailable", "credits": None, "usd": None, "discount_pct": None,
                "basis": reason, "missing": placeholders, "description": None}  # fmt: skip
    return normalize(raw, filled, hints, placeholders)


def total(quotes: list[dict], counts: list[int]) -> dict:
    """Suma de USD y créditos; `complete` es False si algún ítem no tiene precio."""
    usd = credits = 0.0
    complete = True
    for q, n in zip(quotes, counts, strict=True):
        if q.get("usd") is None or q.get("missing"):
            complete = False
            continue
        usd += q["usd"] * n
        credits += (q.get("credits") or 0) * n
    return {"usd": round(usd, 4), "credits": round(credits, 3) or None, "complete": complete}
