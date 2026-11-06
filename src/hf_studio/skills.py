"""Skills de Supercomputer: instrucciones reutilizables en Markdown, en el formato SKILL.md de Claude.

Un SKILL.md empieza con un frontmatter YAML (`name`, `description`) y sigue con las instrucciones. En
Supercomputer se llaman escribiendo `/nombre` en el mensaje (el agente recibe su contenido junto al mensaje) o
el agente las carga solo con la herramienta `use_skill` cuando su descripción encaja con lo que se pide.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MAX_BODY = 60_000  # caracteres: una skill larga llena el contexto en cada vuelta que la usa
MAX_DESCRIPTION = 1_000
FILE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*){0,4}$")
FILE_TYPES = (".md", ".txt", ".json", ".csv", ".yaml", ".yml")
MAX_FILE = 100_000
MAX_FILES = 100
MAX_FILES_TOTAL = 600_000
MENTION = re.compile(r"(?:^|(?<=\s))/([a-z0-9][a-z0-9-]{0,62})(?=$|[\s.,;:!?)])")
MAX_INVOKED = 3


class SkillError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:63].strip("-")
    return slug


def check(slug: str, description: str, body: str) -> tuple[str, str, str]:
    """Valida y limpia una skill; devuelve (slug, descripción, cuerpo)."""
    slug, description, body = slug.strip(), " ".join(description.split()), body.strip()
    if not SLUG.match(slug):
        raise SkillError(
            422, "invalid_slug", "The name must be lowercase letters, digits and dashes (e.g. ads-ugc)"
        )
    if not description:
        raise SkillError(422, "missing_description", "Describe when to use the skill")
    if len(description) > MAX_DESCRIPTION:
        raise SkillError(
            422, "description_too_long", f"The description is limited to {MAX_DESCRIPTION} characters"
        )
    if not body:
        raise SkillError(422, "missing_body", "The skill has no instructions")
    if len(body) > MAX_BODY:
        raise SkillError(422, "body_too_long", f"A skill is limited to {MAX_BODY:,} characters")
    return slug, description, body


def check_files(files: dict[str, str] | None) -> dict[str, str]:
    """Archivos de referencia: rutas relativas de texto (sin `..`), con límites de tamaño y cantidad."""
    clean: dict[str, str] = {}
    for path, content in (files or {}).items():
        path = path.strip().lstrip("./")
        if path == "SKILL.md":
            continue  # es el cuerpo de la skill
        if not FILE_PATH.match(path) or ".." in path.split("/") or not path.endswith(FILE_TYPES):
            raise SkillError(
                422, "invalid_file", f"Skill files are text files with a relative path: {path!r}"
            )
        if not isinstance(content, str) or len(content) > MAX_FILE:
            raise SkillError(422, "file_too_long", f"{path} is limited to {MAX_FILE:,} characters")
        clean[path] = content
    if len(clean) > MAX_FILES or sum(len(v) for v in clean.values()) > MAX_FILES_TOTAL:
        raise SkillError(
            422, "too_many_files", f"A skill takes up to {MAX_FILES} files and {MAX_FILES_TOTAL:,} characters"
        )
    return clean


def parse_skill_md(text: str) -> tuple[str, str, str]:
    """(slug, descripción, cuerpo) de un SKILL.md: frontmatter con `name` y `description` y el resto como cuerpo."""
    text = text.lstrip("﻿")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)$", text, re.DOTALL)
    if not match:
        raise SkillError(422, "no_frontmatter", "A SKILL.md starts with --- name: … description: … ---")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillError(422, "bad_frontmatter", f"The frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillError(422, "bad_frontmatter", "The frontmatter must have name and description")
    name, description = str(meta.get("name") or ""), str(meta.get("description") or "")
    return check(slugify(name), description, match.group(2))


def invoked(text: str, known: set[str]) -> list[str]:
    """Skills que el mensaje llama con /nombre (solo las que existen, en orden y sin repetir, hasta 3)."""
    found: list[str] = []
    for slug in MENTION.findall(text):
        if slug in known and slug not in found:
            found.append(slug)
    return found[:MAX_INVOKED]


def skill_block(slug: str, body: str, files: list[str] | None = None) -> str:
    listing = ""
    if files:
        listing = (
            "\n\nFiles of this skill (read one with read_skill_file when the instructions point to it):\n"
        )
        listing += "\n".join(f"- {f}" for f in files)
    return f'<skill name="{slug}">\n{body}{listing}\n</skill>'


BUILTIN_DIR = Path(__file__).with_name("builtin_skills")


def builtin() -> dict[str, tuple[str, str, dict[str, str]]]:
    """Skills que trae HF Studio: `{slug: (descripción, cuerpo, archivos)}` desde builtin_skills/<carpeta>/."""
    found: dict[str, tuple[str, str, dict[str, str]]] = {}
    for main in sorted(BUILTIN_DIR.glob("*/SKILL.md")):
        slug, description, body = parse_skill_md(main.read_text())
        files = {
            str(f.relative_to(main.parent)): f.read_text()
            for f in sorted(main.parent.rglob("*"))
            if f.is_file() and f != main and f.suffix in FILE_TYPES
        }
        found[slug] = (description, body, check_files(files))
    return found


def unseeded(storage_dir: Path) -> tuple[list[str], Path]:
    """Skills incluidas que esta instalación aún no recibió. Se instalan una sola vez: si el usuario borra una, no
    vuelve al reiniciar (la lista de las ya instaladas vive en `storage_dir/skills_seeded.json`)."""
    marker = Path(storage_dir) / "skills_seeded.json"
    try:
        done = set(json.loads(marker.read_text()))
    except (OSError, ValueError):
        done = set()
    return [slug for slug in builtin() if slug not in done], marker


def mark_seeded(marker: Path, slugs: list[str]) -> None:
    try:
        done = set(json.loads(marker.read_text()))
    except (OSError, ValueError):
        done = set()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(sorted(done | set(slugs))))
