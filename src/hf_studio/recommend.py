"""Recomendador de modelos: de una tarea en lenguaje natural (es/en) a candidatos del catálogo."""

from __future__ import annotations

import asyncio
import re

from .catalog import Catalog
from .pricing import quote

# (patrón, capacidad exigida, explicación)
INTENTS = [
    (
        r"two (images|photos|frames)|start.{0,20}end|first.{0,20}last|dos (fotos|im[aá]genes|fotogramas)|inicio.{0,20}fin|morph|transici",
        "first-last-frame",
        "uses a start and an end frame",
    ),
    (
        r"motion (transfer|control)|dance|baile|bail|copy (the )?moves|copiar (el )?movimiento",
        "motion-transfer",
        "transfers motion from a video",
    ),
    (
        r"swap|replace|reemplaz|sustitu|cambiar (el |un )?(objeto|producto)",
        "object-swap",
        "swaps an object in a video",
    ),
    (r"extend|continu|alarg|prolong", "video-extend", "extends an existing clip"),
    (
        r"edit(ar)? (the |a |my |el |un |mi )?(video|clip)|restyle|re-?style",
        "video-edit",
        "edits an existing video",
    ),
    (
        r"reference videos?|videos? de referencia|copy (the )?(camera|style)|copiar (la )?c[aá]mara",
        "video-input",
        "accepts reference videos",
    ),
    (
        r"character|personaje|consistent|consistente|references?|referencias?",
        "image-references",
        "accepts reference images",
    ),
    (
        r"anima|photo to video|image to video|foto a video|imagen a video|bring .* to life|dar vida",
        "image-to-video",
        "animates an image",
    ),
]
VIDEO_WORDS = r"video|clip|animat|anima|shot|toma|plano|reel|movimiento|motion|dance|baile"
IMAGE_WORDS = r"image|imagen|photo|foto|poster|p[oó]ster|cover|portada|logo|packshot|retrato|portrait"
CHEAP = r"cheap|barat|budget|econ[oó]mic|low cost|bajo costo|poco"
QUALITY = r"best|mejor|highest|m[aá]xima|premium|4k|1080p|cinematic|cinematogr"
AUDIO = r"audio|sound|sonido|voice|voz|music|m[uú]sica"


def _version(model_id: str) -> float:
    nums = re.findall(r"v?(\d+(?:\.\d+)?)", model_id)
    return max((float(n) for n in nums if float(n) < 50), default=0.0)


def parse_task(task: str) -> dict:
    t = task.lower()
    caps, reasons = [], []
    for pattern, cap, why in INTENTS:
        if re.search(pattern, t) and cap not in caps:
            caps.append(cap)
            reasons.append(why)
    if "motion-transfer" in caps and "image-references" in caps:
        caps.remove("image-references")  # «personaje» en una tarea de movimiento es la imagen del sujeto
        reasons.remove("accepts reference images")
    wants_video = bool(re.search(VIDEO_WORDS, t)) or any(
        c in caps
        for c in (
            "first-last-frame",
            "motion-transfer",
            "object-swap",
            "video-extend",
            "video-edit",
            "video-input",
            "image-to-video",
        )
    )
    wants_image = bool(re.search(IMAGE_WORDS, t)) and not wants_video
    output = "video" if wants_video else "image" if wants_image else None
    if "image-references" in caps and output == "image":
        caps.remove("image-references")
        if re.search(r"edit|retoca|cambia", t):
            caps.append("edit")
    return {
        "output": output,
        "capabilities": caps,
        "reasons": reasons,
        "cheap": bool(re.search(CHEAP, t)),
        "quality": bool(re.search(QUALITY, t)),
        "audio": bool(re.search(AUDIO, t)),
    }


def _standard_input(model: dict) -> dict:
    """Entrada típica para cotizar y comparar: 5 s, 720p si existe, formato por defecto."""
    props = model["input_schema"].get("properties", {})
    args: dict = {}
    if "duration" in props:
        d = props["duration"]
        args["duration"] = (
            min(max(5, d.get("minimum", 5)), d.get("maximum", 5)) if "enum" not in d else d["enum"][0]
        )
    if "resolution" in props and "720p" in (props["resolution"].get("enum") or []):
        args["resolution"] = "720p"
    return args


async def recommend(hf, catalog: Catalog, task: str, limit: int = 5, output: str | None = None) -> dict:
    parsed = parse_task(task)
    out = output or parsed["output"]
    pool = [m for m in catalog.models.values() if m["output"] in ("video", "image")]
    if out:
        pool = [m for m in pool if m["output"] == out]
    required = parsed["capabilities"]
    if not required and out:
        required = [f"text-to-{out}"]
    matches = [m for m in pool if all(c in m["capabilities"] for c in required)]
    relaxed = False
    if not matches and required:  # sin coincidencia completa: al menos la capacidad principal
        matches = [m for m in pool if required[0] in m["capabilities"]]
        relaxed = True

    def score(m: dict) -> float:
        s = _version(m["id"])
        props = m["input_schema"].get("properties", {})
        res = props.get("resolution", {}).get("enum") or []
        if parsed["quality"]:
            s += 3 * ("4k" in res) + 2 * ("1080p" in res) + ("pro" in m["id"])
        if parsed["audio"]:
            s += 4 * ("generate_audio" in props or "sound" in props)
        s -= 0.5 * max(0, len(m["capabilities"]) - len(required) - 2)  # más específico, mejor
        return s

    ranked = sorted(matches, key=score, reverse=True)[: max(limit * 2, limit)]
    quotes = await asyncio.gather(*(quote(hf, catalog, m, _standard_input(m), {}) for m in ranked))
    items = []
    for m, q in zip(ranked, quotes, strict=True):
        items.append({
            "id": m["id"], "title": m["title"], "output": m["output"], "capabilities": m["capabilities"],
            "standard_input": _standard_input(m), "estimate": q,
        })  # fmt: skip
    if parsed["cheap"]:
        items.sort(key=lambda i: (i["estimate"]["usd"] is None, i["estimate"]["usd"] or 0))
    return {
        "task": task,
        "understood": {
            "output": out,
            "capabilities": required,
            "cheap": parsed["cheap"],
            "quality": parsed["quality"],
            "audio": parsed["audio"],
        },
        "why": parsed["reasons"],
        "relaxed_match": relaxed,
        "models": items[:limit],
    }
