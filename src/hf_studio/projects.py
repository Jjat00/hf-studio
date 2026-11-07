"""Proyectos de la biblioteca: agrupan generaciones en carpetas y guardan un brief que lee Supercomputer."""

from __future__ import annotations

# El brief se manda en cada mensaje de un chat del proyecto: con este tope no pesa en el contexto.
MAX_BRIEF_IN_CHAT = 6000


def brief_template(name: str) -> str:
    """Brief vacío con las secciones de Cinema Studio (contexto, narrativa, visuales, producción, estado)."""
    return f"""# {name.strip()}

## Contexto
Por qué existe este proyecto.

## Narrativa
Historia, mensaje y público.

## Visuales
Referencias, ambiente, paleta de color y dirección creativa.

## Producción
Calendario, locaciones, personajes y formatos.

## Estado
Avance, bloqueos y próximos pasos.
"""


def brief_block(name: str, brief: str) -> str:
    """Bloque del brief para el agente (recortado si es muy largo)."""
    text = brief.strip()
    if len(text) > MAX_BRIEF_IN_CHAT:
        text = text[:MAX_BRIEF_IN_CHAT] + "\n[…brief truncated]"
    safe = name.replace('"', "'")[:120]
    return f'<studio_project name="{safe}">\n{text}\n</studio_project>'
