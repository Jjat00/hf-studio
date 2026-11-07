"""AI Director: lo que convierte el chat de un proyecto en una producción. Lista de tomas (`shots`), documentos
vivos del proyecto (tratamiento, desglose, biblia…), secciones del brief y fotogramas de un video para que el
agente vea los resultados (dailies) o encadene tomas.

Aquí solo vive la lógica sin estado (validar, editar el brief, extraer fotogramas); las herramientas y las rutas
que leen la base están en `api.py`.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from typing import Any

from .audio import _run as run_ffmpeg
from .audio import duration as media_duration
from .audio import guarded

SHOT_STATUSES = ("planned", "boarded", "proposed", "generating", "review", "approved", "retake", "cut")
SHOT_SIZES = ("EWS", "WS", "MS", "MCU", "CU", "ECU", "OTS", "insert", "cutaway", "POV", "two-shot")
DOC_KINDS = (
    "treatment",
    "breakdown",
    "bible",
    "lookbook",
    "color_script",
    "blocking",
    "script",
    "notes",
    "other",
)
BRIEF_SECTIONS = ("Contexto", "Narrativa", "Visuales", "Producción", "Estado")
MAX_SHOTS = 60  # por llamada
MAX_SHOTS_PER_PROJECT = 300
MAX_DOCUMENT = 60_000
MAX_DOCUMENTS_IN_CONTEXT = 30
MAX_FRAMES = 8
FRAME_SIDE = 1024  # lado mayor de cada fotograma que ve el agente

NO_PROJECT = (
    "This chat has no project. Ask the user to open a Cinema Studio project (AI Director inside the project) or "
    "pick a project in the chat options, then try again."
)


class DirectorError(Exception):
    """Entrada inválida de una herramienta del director: vuelve al agente como error."""


def _text(value: Any, limit: int) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def shot_fields(raw: dict, partial: bool = False) -> dict:
    """Campos limpios de una toma (de `upsert_shots`). Con `partial`, solo los que vienen."""
    if not isinstance(raw, dict):
        raise DirectorError("Each shot is an object")
    out: dict = {}
    texts = {
        "scene": 20,
        "number": 20,
        "purpose": 2000,
        "screen_direction": 200,
        "prompt": 20000,
        "notes": 4000,
    }
    for key, limit in texts.items():
        if key in raw:
            out[key] = _text(raw[key], limit)
    if "order" in raw:
        if not isinstance(raw["order"], int):
            raise DirectorError("`order` must be an integer")
        out["order"] = raw["order"]
    if "shot_size" in raw:
        size = raw["shot_size"]
        if size is not None and size not in SHOT_SIZES:
            raise DirectorError(f"`shot_size` must be one of {', '.join(SHOT_SIZES)}")
        out["shot_size"] = size
    if "duration_s" in raw:
        d = raw["duration_s"]
        if d is not None and (not isinstance(d, int | float) or not 0 < d <= 600):
            raise DirectorError("`duration_s` must be a number of seconds")
        out["duration_s"] = float(d) if d is not None else None
    if "element_ids" in raw:
        ids = raw["element_ids"]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise DirectorError("`element_ids` must be a list of element ids")
        out["element_ids"] = ids[:8]
    if "model_id" in raw:
        out["model_id"] = _text(raw["model_id"], 200) or None
    if "params" in raw:
        if not isinstance(raw["params"], dict):
            raise DirectorError("`params` must be an object with the model's fields")
        out["params"] = {k: v for k, v in raw["params"].items() if k != "prompt"}
    if "status" in raw:
        if raw["status"] not in SHOT_STATUSES:
            raise DirectorError(f"`status` must be one of {', '.join(SHOT_STATUSES)}")
        out["status"] = raw["status"]
    if not partial:
        out.setdefault("scene", "1")
    return out


def shot_input(shot: dict) -> dict:
    """La entrada del modelo de una toma: sus parámetros más el prompt."""
    return {**(shot.get("params") or {}), **({"prompt": shot["prompt"]} if shot.get("prompt") else {})}


def sort_key(shot: Any) -> tuple:
    """Orden natural: escena (2 antes que 10), `order` y número."""

    def natural(value: str) -> tuple:
        return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", value or "") if p)

    return (natural(shot.scene), shot.order or 0, natural(shot.number))


def replace_section(brief: str, section: str, markdown: str, mode: str = "replace") -> str:
    """Cambia una sola sección `## Sección` del brief (o la añade al final si no existe)."""
    body = markdown.strip()
    lines = brief.splitlines()
    heading = re.compile(rf"^##\s+{re.escape(section)}\s*$", re.IGNORECASE)
    start = next((i for i, line in enumerate(lines) if heading.match(line.strip())), None)
    if start is None:
        return brief.rstrip() + f"\n\n## {section}\n{body}\n"
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,2}\s", lines[i])), len(lines))
    current = "\n".join(lines[start + 1 : end]).strip()
    new = f"{current}\n\n{body}".strip() if mode == "append" and current else body
    out = [*lines[: start + 1], *new.splitlines(), "", *lines[end:]]
    return "\n".join(out).rstrip() + "\n"


def documents_block(docs: list[dict]) -> str:
    """Índice de los documentos del proyecto para el contexto del agente (no su contenido)."""
    if not docs:
        return ""
    lines = [
        f'- {d["id"]} · {d["kind"]} · "{d["title"]}" (v{d["version"]}){": " + d["excerpt"] if d.get("excerpt") else ""}'
        for d in docs[:MAX_DOCUMENTS_IN_CONTEXT]
    ]
    return (
        "<studio_project_documents>\nDocuments of this project (open one with read_document):\n"
        + "\n".join(lines)
        + "\n</studio_project_documents>"
    )


def shots_block(counts: dict[str, int]) -> str:
    """Resumen de la lista de tomas (cuántas por estado) para el contexto del agente."""
    if not counts:
        return ""
    parts = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    return f"<studio_shot_list>{sum(counts.values())} shots: {parts}. Read them with get_shot_list.</studio_shot_list>"


def frame_times(length: float | None, count: int) -> list[float]:
    """`count` instantes equiespaciados de un video, incluidos el primero y (casi) el último."""
    count = max(1, min(int(count), MAX_FRAMES))
    if not length or length <= 0:
        return [0.0]
    last = max(0.0, length - 0.05)
    if count == 1:
        return [0.0]
    return [round(last * i / (count - 1), 2) for i in range(count)]


async def video_frames(path: Path, count: int) -> tuple[list[tuple[float, bytes]], float | None]:
    """Fotogramas JPEG (lado mayor <= FRAME_SIDE) de un video local, con su instante, y la duración."""
    length = await media_duration(str(path))
    frames: list[tuple[float, bytes]] = []
    scale = f"scale='min({FRAME_SIDE},iw)':'min({FRAME_SIDE},ih)':force_original_aspect_ratio=decrease"
    with tempfile.TemporaryDirectory(prefix="hfs-frames-") as tmp:
        for n, t in enumerate(frame_times(length, count)):
            out = Path(tmp) / f"{n}.jpg"
            last = n > 0 and length and t >= length - 0.1
            if last:  # buscar justo al final falla: desde el último segundo, cada fotograma reescribe y queda el último
                args = ["-sseof", "-1", *guarded(str(path)), "-update", "1", "-vf", scale, "-q:v", "5"]
            else:
                args = ["-ss", f"{t:.2f}", *guarded(str(path)), "-frames:v", "1", "-vf", scale, "-q:v", "5"]
            code, _ = await run_ffmpeg("ffmpeg", "-y", "-v", "error", *args, str(out))
            if code == 0 and out.is_file() and out.stat().st_size:
                frames.append((t, out.read_bytes()))
    return frames, length


async def small_image(path: Path) -> bytes | None:
    """Copia JPEG reducida (lado mayor <= FRAME_SIDE) de una imagen local, para el agente."""
    with tempfile.TemporaryDirectory(prefix="hfs-img-") as tmp:
        out = Path(tmp) / "small.jpg"
        scale = f"scale='min({FRAME_SIDE},iw)':'min({FRAME_SIDE},ih)':force_original_aspect_ratio=decrease"
        code, _ = await run_ffmpeg(
            "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file", "-i", str(path),
            "-frames:v", "1", "-vf", scale, "-q:v", "5", str(out),
        )  # fmt: skip
        return out.read_bytes() if code == 0 and out.is_file() and out.stat().st_size else None


def image_block(data: bytes, media_type: str = "image/jpeg") -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()},
    }


def url_block(url: str) -> dict:
    return {"type": "image", "source": {"type": "url", "url": url}}
