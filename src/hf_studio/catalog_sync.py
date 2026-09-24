"""Regenera src/hf_studio/catalog.json a partir de la documentación oficial de Higgsfield.

Recorre las categorías de modelos, abre cada página de workflow y extrae el endpoint,
el JSON Schema completo de entrada y el tipo de salida. Solo usa la biblioteca estándar.

    uv run hf-studio sync-catalog
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

DOCS = "https://docs.higgsfield.ai"
CATEGORIES = ["/docs/models/video-generation", "/docs/models/image-generation"]
OUT = Path(__file__).resolve().parent / "catalog.json"

LINK_RE = re.compile(r"(?:href=\"|\]\()(/docs/models/[a-z0-9._/-]+?)(?:\.md)?[\")#]")
ENDPOINT_RE = re.compile(r"\*\*Endpoint:\*\*\s*`POST\s+https://api\.higgsfield\.ai/([^`]+)`")
TITLE_RE = re.compile(r"^# (.+)$", re.MULTILINE)
SUMMARY_RE = re.compile(r"^> (?!##|Fetch|Use this)(.+)$", re.MULTILINE)
SCHEMA_RE = re.compile(r"Complete JSON schema\">\s*```json[^\n]*\n(.*?)```", re.DOTALL)
OUTPUT_RE = re.compile(r"completed response includes.*?```json[^\n]*\n(.*?)```", re.DOTALL)
NOTES_RE = re.compile(r"## Usage notes\s*\n(.*?)\n## ", re.DOTALL)


def fetch(path: str) -> str:
    url = DOCS + (path if path.endswith(".md") else path + ".md")
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode()


def links(markdown: str) -> set[str]:
    return {m.rstrip("/") for m in LINK_RE.findall(markdown)}


START_FRAME = {"image_url", "first_frame_url"}
END_FRAME = {"end_image_url", "last_frame_url", "last_image_url"}


def capabilities(workflow: str, output: str, schema: dict) -> list[str]:
    """Etiquetas de búsqueda derivadas de los campos del esquema (no de nombres de marketing)."""
    props = set(schema.get("properties", {}))
    # Los esquemas condicionales (if/then/else) exigen medios en las ramas, no en `required`.
    required = set(schema.get("required", []))
    for branch in ("if", "then", "else"):
        required |= set(schema.get(branch, {}).get("required", []))
    media = {p for p in props if p.endswith(("_url", "_urls")) or p == "input_images"}
    caps = set()
    if "prompt" in props and not (required & media):
        caps.add(f"text-to-{output}")
    if props & START_FRAME:
        caps.add("image-to-video" if output == "video" else "image-edit")
    if props & END_FRAME:
        caps.add("first-last-frame")
    if props & {"video_url", "video_urls"}:
        caps.add("video-input")
    if props & {"image_urls", "input_images"}:
        caps.add("image-references")
    if props & {"audio_url", "audio_urls"}:
        caps.add("audio-input")
    for w in ("video-edit", "video-extend", "motion-transfer", "object-swap", "reference-to-video", "edit"):
        if w in workflow:
            caps.add(w)
    if "motion-control" in workflow:
        caps.add("motion-transfer")
    return sorted(caps)


def parse_workflow(path: str) -> dict | None:
    md = fetch(path)
    endpoint = ENDPOINT_RE.search(md)
    schema = SCHEMA_RE.search(md)
    if not endpoint or not schema:
        return None
    output_type = "unknown"
    if out := OUTPUT_RE.search(md):
        keys = json.loads(out.group(1)).keys()
        output_type = next((k for k in ("video", "images", "audio") if k in keys), "unknown")
    summary = SUMMARY_RE.search(md)
    notes = NOTES_RE.search(md)
    endpoint_id = endpoint.group(1).strip()
    input_schema = json.loads(schema.group(1))
    output = {"images": "image", "video": "video", "audio": "audio"}.get(output_type, "unknown")
    return {
        "id": endpoint_id,
        "title": TITLE_RE.search(md).group(1).strip(),
        "summary": summary.group(1).strip() if summary else "",
        "workflow": path.rsplit("/", 1)[-1],
        "family": path.split("/")[3],
        "output": output,
        "capabilities": capabilities(path.rsplit("/", 1)[-1], output, input_schema),
        "notes": [n.lstrip("* ").strip() for n in notes.group(1).splitlines() if n.strip()] if notes else [],
        "docs_url": DOCS + path,
        "input_schema": input_schema,
    }


def main() -> int:
    families: set[str] = set()
    for cat in CATEGORIES:
        families |= {p for p in links(fetch(cat)) if p.count("/") == 3 and p not in CATEGORIES}
    with ThreadPoolExecutor(8) as pool:
        ordered = sorted(families)
        family_pages = dict(zip(ordered, pool.map(fetch, ordered)))
    workflows = sorted({p for f, md in family_pages.items() for p in links(md) if p.startswith(f + "/")})
    with ThreadPoolExecutor(8) as pool:
        parsed = [m for m in pool.map(parse_workflow, workflows) if m]
    models = sorted({m["id"]: m for m in parsed}.values(), key=lambda m: m["id"])
    OUT.write_text(
        json.dumps(
            {"synced_at": datetime.now(UTC).date().isoformat(), "source": DOCS, "models": models},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    skipped = len(workflows) - len(parsed)
    print(f"{len(models)} endpoints en {OUT} ({skipped} páginas sin endpoint/esquema)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
