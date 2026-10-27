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
PLACEHOLDER_PRESET = "c2143317-f28d-4c3c-a0b8-39bd547e08a7"  # el de ejemplo de la documentación de Restyle
SHORT_SIDE = {"480p": 480, "720p": 720, "1080p": 1080, "2k": 1440, "4k": 2160}
MONEY = r"\$(\d+(?:\.\d+)?)"  # sin el punto final de la frase
RESTYLE = "higgsfield/genjutsu/restyle/v1.0"
RESTYLE_MAX_SECONDS = 30  # Restyle recorta el video de origen a sus primeros 30 s (y cobra solo esos)
GENJUTSU_LIGHT_MAX_SECONDS = 15  # Genjutsu Light usa solo los primeros 15 s del video de origen


def _media_kind(key: str) -> str | None:
    if not (key.endswith(("_url", "_urls")) or key == "input_images"):
        return None
    if key.startswith("video"):
        return "video"
    if key.startswith("audio"):
        return "audio"
    return "image"


def _branch_required(schema: dict, args: dict) -> set[str]:
    """Campos que exigen las ramas if/then/else que aplican a `args`, también anidadas (Seedance 2.5:
    si no hay imágenes, videos; si no hay videos, audios)."""
    cond = set(schema.get("if", {}).get("required", []))
    branch = schema.get("then" if cond and cond <= args.keys() else "else", {})
    return set(branch.get("required", [])) | (_branch_required(branch, args) if "if" in branch else set())


def fill_placeholders(schema: dict, args: dict) -> tuple[dict, list[str]]:
    """Devuelve (entrada con medios de ejemplo, campos rellenados). Respeta if/then/else."""
    props = schema.get("properties", {})
    required = set(schema.get("required", [])) | _branch_required(schema, args)
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
        elif key == "preset_id" and props.get(key, {}).get("format") == "uuid":
            # Genjutsu Restyle: el estilo no cambia el precio; se cotiza antes de elegirlo.
            filled[key] = PLACEHOLDER_PRESET
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


def approximate(
    description: str, args: dict, hints: dict, model_id: str | None = None, output_follows_input: bool = False
) -> dict:
    """Interpreta la fórmula de precio. Devuelve usd (o None), base del cálculo y datos que faltan.
    `output_follows_input`: el modelo no tiene `duration` y su salida dura lo que el video de entrada
    (Seedance 2.5 video-edit); sin esto se cotizarían 5 s de salida."""
    seconds = float(args.get("duration") or 5)
    res = str(args.get("resolution") or "720p").lower()
    input_secs = hints.get("input_video_seconds")
    has_video_input = _count_video_inputs(args) > 0
    if output_follows_input and has_video_input and input_secs is not None:
        seconds = float(input_secs)
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

    # A2) Por segundo total (salida + videos de referencia), según resolución (Wan 3.0 reference-to-video).
    if m := re.search(r"Priced per total video second: (.*?)\. Total billable", text):
        rates = dict(re.findall(r"(\d+p) " + MONEY + r"/s", m.group(1)))
        if res in rates:
            billable, basis = seconds, f"{seconds:g}s"
            if has_video_input:
                if input_secs is None:
                    missing.append("input video duration")
                else:
                    billable += float(input_secs)
                    basis = f"({seconds:g}s + {float(input_secs):g}s of input video)"
            return {"usd": billable * float(rates[res]), "basis": f"{basis} × ${rates[res]}/s at {res}",
                    "missing": missing}  # fmt: skip

    # A3) Kling 4.0 (reference-to-video y video-edit, a 2026-10): «Without input video: 720p $0.157/s, 1080p $0.235/s,
    # charged on output duration. With input video: 720p $0.094/s, …, charged on output duration + max(total input
    # video duration, output duration)».
    if m := re.search(
        r"Without input video: (.*?), charged on output duration\. With input video: (.*?), charged", text
    ):
        rates = dict(re.findall(r"(\d+p) " + MONEY + r"/s", m.group(2 if has_video_input else 1)))
        if res in rates:
            billable, basis = seconds, f"{seconds:g}s"
            if has_video_input:
                if input_secs is None:
                    missing.append("input video duration")
                    billable = 2 * seconds
                    basis = f"({seconds:g}s + {seconds:g}s assumed for the input video)"
                else:
                    # El recorte a 30 s es por video y aquí solo se conoce la suma: se usa entera (por lo alto).
                    billable = seconds + max(float(input_secs), seconds)
                    basis = f"({seconds:g}s + max({float(input_secs):g}s of input video, {seconds:g}s))"
            return {"usd": billable * float(rates[res]), "basis": f"{basis} × ${rates[res]}/s at {res}",
                    "missing": missing}  # fmt: skip

    # A4) Genjutsu Light (a 2026-10): «Priced per total second by resolution: 480p $0.05, …. Billable seconds = output
    # duration + the sum of input reference video durations … trims the source to 15 seconds; output duration is
    # rounded up». La salida dura lo que el video de origen recortado a 15 s; la entrada se cuenta entera (por lo alto:
    # la doc no dice si se cobra antes o después del recorte).
    if m := re.search(r"Priced per total second by resolution: (.*?)\. ", text):
        rates = dict(re.findall(r"(\d+p) " + MONEY, m.group(1)))
        if res not in rates:
            return {"usd": None, "basis": f"no published rate for {res}", "missing": []}
        rate = float(rates[res])
        if input_secs is None:
            return {"usd": None, "basis": f"${rate}/s of output + input video at {res}",
                    "missing": ["input video duration"]}  # fmt: skip
        out_secs = math.ceil(min(float(input_secs), GENJUTSU_LIGHT_MAX_SECONDS))
        billable = out_secs + float(input_secs)
        return {"usd": billable * rate, "basis": f"({out_secs}s output + {float(input_secs):g}s of input video) × ${rate}/s at {res}",
                "missing": []}  # fmt: skip

    # B) Tokens de video: segundos × ancho × alto × 24 / 1024.
    if "video tokens" in text.lower():
        billable = seconds
        if ("input video seconds" in text or "input video duration" in text) and has_video_input:
            if input_secs is None:
                missing.append("input video duration")
            else:
                billable += float(input_secs)
        width, height, assumed = _output_size(args)
        tokens = math.ceil(billable * width * height * 24 / 1024)
        big = res == "4k"
        # Tarifas por 1.000 tokens, de la más específica a la más general.
        patterns = [
            # Seedance 2.5 (a 2026-10): «Each 1,000 video tokens costs $A at 480p or 720p and $B at 1080p», y en
            # reference-to-video además «If video inputs are provided, … $C per 1,000 tokens at 480p or 720p and
            # $D at 1080p».
            (
                has_video_input and res != "4k",
                r"If video inputs are provided.*?"
                + MONEY
                + r" per 1,000 tokens at 480p or 720p and "
                + MONEY
                + r" at 1080p",
                2 if res == "1080p" else 1,
            ),
            (
                res != "4k",
                r"[Ee]ach 1,000 video tokens costs? "
                + MONEY
                + r" at 480p or 720p and "
                + MONEY
                + r" at 1080p",
                2 if res == "1080p" else 1,
            ),
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

    # C) Por segundo de video de entrada (Genjutsu): «costs $0.318 at 480p, $0.681 at 720p, $1.632 at 1080p».
    # C2) Restyle: «Roughly costs $0.318 per second at 480p, …»; se cobra por segundo del video de origen,
    # recortado a 30 s y redondeado hacia arriba.
    per_input = re.search(r"Each second of input video costs (.*?)(?:\.\s|\.$)", text)
    per_source = (
        re.search(r"costs (" + MONEY + r" per second at \d+p.*)", text)
        if has_video_input and model_id == RESTYLE
        else None
    )
    if found := per_input or per_source:
        rates = {
            r: float(usd) for usd, r in re.findall(MONEY + r"(?: per second)? at (\d+p)", found.group(1))
        }
        if res not in rates:
            return {"usd": None, "basis": f"no published rate for {res}", "missing": []}
        rate = rates[res]
        if input_secs is None:
            return {
                "usd": None,
                "basis": f"${rate}/s of input video at {res}",
                "missing": ["input video duration"],
            }
        secs = float(input_secs) if per_input else min(float(input_secs), RESTYLE_MAX_SECONDS)
        secs = math.ceil(secs)
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

    # E) Imagen por tokens (Marketing Studio 2.5): tarifa publicada por millón de tokens. El uso real se conoce
    # al terminar, pero la imagen de salida domina y depende de la calidad y la resolución: se cotiza por lo alto.
    if (out := re.search(r"image output " + MONEY, text)) and (
        estimate := _image_tokens_estimate(text, args, out)
    ):
        return estimate

    # F) Por tokens de texto/imagen (uso real): no se puede anticipar con precisión.
    return {"usd": None, "basis": "usage-based pricing (final cost depends on actual tokens)", "missing": []}


# Tokens de una imagen de salida «1k» por calidad: la tabla publicada de los modelos de imagen por tokens en su
# formato base (1024×1024), que es lo que cobra Higgsfield también en 9:16. Cada salto de resolución cuadruplica los
# píxeles. Calidades sin tabla (xhigh, max) no se cotizan: quedan sin precio y piden aprobación.
# Calibrado con el cobro real del 2026-10-07: 22 imágenes Flare/Sunburst 1k media con 43 referencias costaron
# ~$0,85 y esta fórmula da ~$0,90 (un 6 % por lo alto). Con la tabla de 1024×1536 y 1.600 tokens por referencia
# daba el doble.
IMAGE_OUTPUT_TOKENS = {"low": 272, "medium": 1056, "high": 4160}
RESOLUTION_AREA = {"1k": 1, "2k": 4, "4k": 16}
# Una imagen de referencia de entrada (se normaliza antes de enviarse).
IMAGE_INPUT_TOKENS = 600


def _image_tokens_estimate(text: str, args: dict, out: re.Match) -> dict | None:
    quality = str(args.get("quality") or ("high" if "defaults to high" in text.lower() else "")).lower()
    resolution = str(args.get("resolution") or "2k").lower()
    if quality not in IMAGE_OUTPUT_TOKENS or resolution not in RESOLUTION_AREA:
        return None
    out_tokens = IMAGE_OUTPUT_TOKENS[quality] * RESOLUTION_AREA[resolution]
    refs = len(args.get("image_urls") or [])
    in_rate = float(m.group(1)) if (m := re.search(r"image input " + MONEY, text)) else 0.0
    text_rate = float(m.group(1)) if (m := re.search(r"text input " + MONEY, text)) else 0.0
    prompt_tokens = len(str(args.get("prompt") or "")) // 3 + 1
    usd = (
        out_tokens * float(out.group(1)) + refs * IMAGE_INPUT_TOKENS * in_rate + prompt_tokens * text_rate
    ) / 1e6
    basis = f"≈{out_tokens:,} image tokens ({quality}, {resolution}) × ${out.group(1)}/1M"
    if refs:
        basis += f" + {refs} refs × ${in_rate:g}/1M"
    # Ads Studio: cada concepto del lote es una imagen (2k y calidad alta fijas) y se cobra la suma. Higgsfield
    # publica ≈$0.084 por imagen como ejemplo, sin ser un tope: se cotiza por lo alto, igual que Marketing Studio.
    if (n := int(args.get("batch_size") or 1)) > 1:
        usd, basis = usd * n, f"{n} images × ({basis})"
    return {"usd": usd, "basis": basis + " (upper estimate; billed by actual tokens)", "missing": []}


def normalize(
    raw: dict[str, Any],
    args: dict,
    hints: dict,
    placeholders: list[str],
    model_id: str | None = None,
    output_follows_input: bool = False,
) -> dict:
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
    approx = approximate(desc, args, hints, model_id, output_follows_input)
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
    props = model["input_schema"].get("properties", {})
    follows = model.get("output") == "video" and "duration" not in props
    # Las fórmulas de video se aplican a lo que el modelo hará: si faltan duración o resolución, sus valores por
    # defecto (Kling 4.0 dura 10 s y sale en 1080p si no se dice otra cosa).
    defaults = ("duration", "resolution") if model.get("output") == "video" else ()
    priced = {k: props[k]["default"] for k in defaults if k not in filled and "default" in props.get(k, {})}
    return normalize(raw, {**priced, **filled}, hints, placeholders, model["id"], follows)


def total(quotes: list[dict], counts: list[int]) -> dict:
    """Suma de USD y créditos; `complete` es False si algún ítem no tiene precio."""
    usd = credits = reserve = 0.0
    complete = True
    for q, n in zip(quotes, counts, strict=True):
        if q.get("usd") is None or q.get("missing"):
            complete = False
            continue
        usd += q["usd"] * n
        credits += (q.get("credits") or 0) * n
        reserve += (q.get("reserve_usd") or 0) * n
    return {"usd": round(usd, 4), "credits": round(credits, 3) or None, "complete": complete,
            "reserve_usd": round(reserve, 4) or None}  # fmt: skip
