"""Skills de Supercomputer: instrucciones reutilizables en Markdown, en el formato SKILL.md de Claude.

Un SKILL.md empieza con un frontmatter YAML (`name`, `description`) y sigue con las instrucciones. En
Supercomputer se llaman escribiendo `/nombre` en el mensaje (el agente recibe su contenido junto al mensaje) o
el agente las carga solo con la herramienta `use_skill` cuando su descripción encaja con lo que se pide.
"""

from __future__ import annotations

import re

import yaml

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MAX_BODY = 60_000  # caracteres: una skill larga llena el contexto en cada vuelta que la usa
MAX_DESCRIPTION = 1_000
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


def skill_block(slug: str, body: str) -> str:
    return f'<skill name="{slug}">\n{body}\n</skill>'
