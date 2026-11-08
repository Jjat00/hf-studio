"""Katana en HF Studio: remixes de un edit de referencia con el sujeto del usuario (réplica de Higgsfield Katana).

Flujo (las rutas viven en `api.py`):
1. `POST /v1/katana/projects`: la referencia (una subida o generación propia, o un preset público de Katana) se
   copia a `storage/katana/<id>/ref.mp4` y se analiza gratis (`katana_analysis`).
2. `POST /v1/katana/projects/{id}/plan`: Claude escribe el plan (`katana_plan`), con el tope aprobado de
   `/plan/estimate`; se suben los fotogramas de la referencia que el plan cita y su música, y se crea el Space.
3. El Space se cotiza (`/v1/spaces/{id}/runs/estimate`) y corre con el presupuesto que apruebe el usuario; su
   último nodo es `hf-studio/katana-edit`, que monta el video.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

PRESET_HOST = "static-public-media.higgsfield.ai"
PRESET_PREFIX = "/katana-presets/"
FILE_GROUPS = {"sheets": "sheets", "shots": "shots"}
FILE_NAME = re.compile(r"^(sheet|key)-[0-9]{3}\.jpg$")

# Presets públicos de la galería de Katana de Higgsfield (a 2026-11-07): solo enlaces a sus videos de muestra,
# que sirven de referencia como cualquier otro video. No se copian ni se publican aquí.
PRESETS: list[dict[str, str]] = [
    {"id": "kinetic-tech-edit", "name": "Kinetic Tech Edit", "video": "d501cb9e-17b0-4d99-8c17-0be403afd3f8",
     "thumb": "ca2f300e-740a-4ea0-b8d4-8c5795bd0bc1"},
    {"id": "candy-pop", "name": "Candy Pop", "video": "18188271-4cc2-48c4-9529-33842cb5fd26",
     "thumb": "645f3f9c-7655-4b7e-8a99-43ef130009b5"},
    {"id": "daytona-drift", "name": "Daytona Drift", "video": "3a28f2ce-8d74-4050-9eb1-4bdc6e9aeaa9",
     "thumb": "3ed7e61a-e9cf-4fb2-9ac2-bddce519a8aa"},
    {"id": "pop-cutout-fashion-edit", "name": "Pop Cutout Fashion Edit",
     "video": "6ee557af-3506-4dac-82e1-1c7862cc9653", "thumb": "928df55f-d725-418a-9295-0178a966f7ce"},
    {"id": "monolith", "name": "Monolith", "video": "af9c9242-9c72-4908-8959-afd98e0476a2",
     "thumb": "ba97e077-3938-42f6-a16b-bad586227f96"},
    {"id": "chrome-noir-style-edit", "name": "Chrome Noir Style Edit",
     "video": "744f0bcb-a098-471a-bc1a-d139be1ad5c6", "thumb": "577732f5-6a55-44d0-93d2-e5a39824e65a"},
    {"id": "fw26-style-lookbook", "name": "FW26 Style Lookbook", "video": "73188a33-b46b-4cf3-838c-6bb8af24dcc9",
     "thumb": "be194f27-f4b2-42b0-bcde-c9f17b6ee95c"},
    {"id": "neon-laser-motion-graphics-edit", "name": "Neon Laser Motion Graphics Edit",
     "video": "7674caaa-e1f8-4051-8b15-a4a9831694a2", "thumb": "10ad60cc-4191-4076-8ca9-ba13445ce564"},
    {"id": "aura-fast", "name": "Aura Fast", "video": "8ec26d06-e5bf-4d72-987d-ab200570cc87", "thumb": ""},
    {"id": "track-day-showcase", "name": "Track Day Showcase", "video": "249a2cb6-40ee-48dc-9b12-4be307d98fb8",
     "thumb": "fc410882-ca7d-4154-8aa8-c5cfe57512de"},
    {"id": "pop-art-comic-edit", "name": "Pop Art Comic Edit", "video": "679b5af9-ff1d-4cd2-a4e8-610afa217c7b",
     "thumb": "4e0b3564-aa45-437e-aae2-ccc4e84253bc"},
    {"id": "kinetic-typography-edit", "name": "Kinetic Typography Edit",
     "video": "e8ecfb44-776a-4286-9fe7-d757d73371bb", "thumb": "ae61691d-da56-4f6d-81fc-900ee8bb7473"},
    {"id": "kinetic-graphic-photo-edit", "name": "Kinetic Graphic Photo Edit",
     "video": "8e91b0ae-f30a-4bf5-be0d-dff7e72447a6", "thumb": "b7355b40-b829-4c7b-b993-9422f1cafb26"},
    {"id": "swole-cinema-aesthetic", "name": "Swole Cinema Aesthetic",
     "video": "213eba9e-3934-469d-963c-a64c1887f83f", "thumb": "a20000dd-4989-47c2-afb0-fdcd15ec6003"},
    {"id": "high-octane-turbo-sprint", "name": "High Octane Turbo Sprint",
     "video": "85717c9a-1b1b-4eb3-886f-5fe491ca8f83", "thumb": "743ea835-6137-4c3a-a372-d031a9ba54f4"},
    {"id": "noir-crowned-fashion-montage", "name": "Noir Crowned Fashion Montage",
     "video": "fc019f51-dd02-4d19-8b17-f284cece2199", "thumb": "e8c59c66-7695-4c88-a866-3bb91bdee7b9"},
    {"id": "surreal-collage-vibe", "name": "Surreal Collage Vibe", "video": "62229f50-0679-414c-a186-9a16dfcd25da",
     "thumb": "773986d4-3bff-431b-a93e-6faa2b36bb04"},
    {"id": "comic", "name": "Comic", "video": "e14ea8ec-99be-4de5-a966-d4fb76d55c85",
     "thumb": "ab0ebde3-796f-468d-a620-bb25d71d6576"},
    {"id": "monochrome-glitch-montage", "name": "Monochrome Glitch Montage",
     "video": "66c09734-44da-4f57-94b0-84e38f59c272", "thumb": "33b8910f-6443-494b-80f7-aa754c089615"},
    {"id": "perfume-commercial-style-edit", "name": "Perfume Commercial Style Edit",
     "video": "8d22fd89-4fc8-4009-a01b-695102f38967", "thumb": "65d6d864-eb05-43d1-b852-b5fe27582548"},
]  # fmt: skip


def _media(asset: str, ext: str) -> str:
    return f"https://{PRESET_HOST}{PRESET_PREFIX}{asset}.{ext}" if asset else ""


def presets() -> list[dict[str, str]]:
    return [
        {"id": p["id"], "name": p["name"], "video_url": _media(p["video"], "mp4"),
         "thumbnail_url": _media(p["thumb"], "webp")}
        for p in PRESETS
    ]  # fmt: skip


def is_preset_video(url: str) -> bool:
    """Un video de la galería pública de Katana (solo esas rutas exactas, nada más de ese dominio)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == PRESET_HOST
        and parsed.port is None
        and not parsed.query
        and any(parsed.path == f"{PRESET_PREFIX}{p['video']}.mp4" for p in PRESETS)
    )


def preset_for(url: str) -> str | None:
    return next((p["id"] for p in PRESETS if url.endswith(f"{p['video']}.mp4")), None)


def folder(storage_dir: str | Path, project_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{36}", project_id):
        raise ValueError("invalid project id")
    return Path(storage_dir) / "katana" / project_id


def remove(storage_dir: str | Path, project_id: str) -> None:
    shutil.rmtree(folder(storage_dir, project_id), ignore_errors=True)


def file_path(storage_dir: str | Path, project_id: str, group: str, name: str) -> Path | None:
    if group not in FILE_GROUPS or not FILE_NAME.match(name):
        return None
    path = folder(storage_dir, project_id) / FILE_GROUPS[group] / name
    return path if path.is_file() else None
