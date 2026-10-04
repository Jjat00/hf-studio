"""Elementos de HF Studio para Kling 3.0: personajes, productos o lugares reutilizables.

La API pública de Higgsfield no permite crear ni leer sus elementos (solo acepta ids decimales de la cuenta),
así que HF Studio guarda los suyos: nombre, descripción y de 2 a 4 imágenes JPG o PNG. En una generación se
pasan por su id (`el_…`) en el campo `elements` del modelo y se citan en el prompt con `@nombre`. Solo APIMart
(`element_list`) y KIE (`kling_elements`) los aceptan, con las imágenes en línea; Higgsfield queda fuera.
"""

from __future__ import annotations

import re
import secrets
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import ACTIVE, Element, Job, utcnow
from .media import matches_type

PREFIX = "el_"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MIN_IMAGES, MAX_IMAGES = 2, 4
MAX_PER_REQUEST = 3  # APIMart y KIE admiten hasta 3 elementos por tarea
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # límite de KIE por imagen
CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}  # KIE solo acepta JPG y PNG
# Las URLs de CloudFront de Higgsfield duran unos 7 días: se vuelven a subir pasados 5.
REFRESH_AFTER = timedelta(days=5)
# Un borrado se purga (fila e imágenes) solo pasado este margen: una creación de trabajo que comprobó el
# elemento vivo justo antes de insertarse siempre termina antes (revisión 44).
PURGE_GRACE = timedelta(minutes=10)


class ElementError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def is_element_id(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def new_element_id() -> str:
    return PREFIX + secrets.token_hex(6)


def check_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ElementError(
            422, "invalid_name",
            "The name must be 2 to 32 characters: lowercase letters, digits or _, starting with a letter "
            "(it is cited in the prompt as @name)",
        )  # fmt: skip
    return name


def check_image(data: bytes, content_type: str) -> str:
    """Tipo real de una imagen de elemento (por su firma, no por lo que diga el cliente)."""
    for kind in CONTENT_TYPES:
        if matches_type(data[:16], kind):
            if len(data) > MAX_IMAGE_BYTES:
                raise ElementError(413, "too_large", "Each element image must be at most 10 MB")
            return kind
    raise ElementError(415, "unsupported_media", "Element images must be JPG or PNG")


def folder(storage: Path, element_id: str) -> Path:
    return Path(storage) / "elements" / element_id


def element_out(element: Element) -> dict:
    return {
        "id": element.id,
        "name": element.name,
        "description": element.description,
        "mention": f"@{element.name}",
        "images": [f"/v1/elements/{element.id}/images/{i}" for i in range(len(element.images))],
        "created_at": element.created_at.isoformat() + "Z",
    }


async def fresh_urls(element: Element, storage: Path, upload) -> list[str]:
    """URLs públicas de las imágenes; si las de Higgsfield tienen más de 5 días, las vuelve a subir desde la
    copia local (subir no cobra). `upload(data, content_type) -> url`."""
    if utcnow() - element.uploaded_at < REFRESH_AFTER and all(i.get("url") for i in element.images):
        return [i["url"] for i in element.images]
    images = []
    for image in element.images:
        data = (folder(storage, element.id) / image["file"]).read_bytes()
        images.append({**image, "url": await upload(data, image["content_type"])})
    element.images, element.uploaded_at = images, utcnow()
    return [i["url"] for i in images]


def element_ids(values: Any) -> list[str]:
    return [v for v in values if is_element_id(v)] if isinstance(values, list) else []


async def check_available(session: AsyncSession, values: Any) -> None:
    """Una petición nueva solo puede citar elementos que existen y no están borrados (404 si no)."""
    ids = element_ids(values)
    if not ids:
        return
    live = set(
        await session.scalars(select(Element.id).where(Element.id.in_(ids), Element.deleted_at.is_(None)))
    )
    missing = [i for i in ids if i not in live]
    if missing:
        raise ElementError(404, "element_not_found", f"Unknown element(s): {', '.join(missing)}")


async def purge_deleted(session: AsyncSession, storage: Path) -> None:
    """Borra del todo los elementos borrados hace más de `PURGE_GRACE` que ya no cita ningún trabajo activo
    (fila e imágenes). Junto con `check_available` justo antes de insertar un trabajo, un trabajo nunca queda
    apuntando a un elemento purgado."""
    cutoff = utcnow() - PURGE_GRACE
    deleted = list(await session.scalars(select(Element).where(Element.deleted_at < cutoff)))
    if not deleted:
        return
    in_use = {v for values in await session.scalars(select(Job.input).where(Job.status.in_(ACTIVE)))
              for v in element_ids((values or {}).get("elements"))}  # fmt: skip
    gone = [e for e in deleted if e.id not in in_use]
    for element in gone:
        await session.delete(element)
    await session.commit()
    for element in gone:
        shutil.rmtree(folder(storage, element.id), ignore_errors=True)


async def resolve(session: AsyncSession, values: list, storage: Path, upload) -> dict[str, dict]:
    """`{id: {name, description, image_urls}}` de los elementos de HF Studio citados en `values` (los ids
    decimales de Higgsfield se ignoran), con URLs vigentes. Incluye los borrados que siguen guardados: un
    trabajo ya creado los necesita; las peticiones nuevas pasan antes por `check_available`. Un id que ya no
    existe es un error: nunca se envía un elemento vacío."""
    ids = element_ids(values)
    if not ids:
        return {}
    found = {e.id: e for e in await session.scalars(select(Element).where(Element.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ElementError(404, "element_not_found", f"Unknown element(s): {', '.join(missing)}")
    resolved = {}
    for element_id in ids:
        element = found[element_id]
        resolved[element_id] = {
            "name": element.name,
            "description": element.description,
            "image_urls": await fresh_urls(element, storage, upload),
        }
    await session.commit()  # guarda las URLs renovadas
    return resolved
