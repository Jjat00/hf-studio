"""Sonoteca: todos los sonidos de ElevenLabs en un sitio, clasificados para reutilizarlos.

Cada sonido tiene una categoría (de qué se trata), etiquetas y un título. Se clasifica solo a partir del
texto o la descripción que lo generó (palabras clave en español e inglés); un agente puede darlos al
generar (lo hace mejor que unas reglas) y la UI permite corregirlos.

Fuentes: los trabajos de audio de HF Studio (su copia local) y el historial de ElevenLabs, que por API
solo expone voz (texto a voz, cambio de voz, doblaje): los efectos y la música generados en su web no se
pueden recuperar.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audio import duration
from .db import ApiClient, Job, Sound

# Orden de presentación. Cada categoría: palabras clave (sin tildes, en minúscula) que la delatan.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "scream": (
        "grito",
        "gritar",
        "alarido",
        "chillido",
        "lamento",
        "llanto",
        "sollozo",
        "scream",
        "shriek",
        "yell",
        "wail",
        "cry",
        "sob",
        "moan",
        "gasp",
        "horror scream",
    ),
    "laugh": ("risa", "carcajada", "reir", "laugh", "giggle", "cackle", "chuckle"),
    "creature": (
        "monstruo",
        "criatura",
        "demonio",
        "bestia",
        "zombi",
        "zombie",
        "gruñido",
        "rugido",
        "fantasma",
        "espectro",
        "bruja",
        "monster",
        "creature",
        "demon",
        "beast",
        "growl",
        "roar",
        "snarl",
        "ghost",
        "witch",
        "wolf",
        "lobo",
        "howl",
        "aullido",
        "hiss",
        "sise",
        "spider",
        "arana",
        "insect",
        "insecto",
        "rat",
        "rata",
        "raton",
        "bat",
        "bats",
        "murcielago",
        "raven",
        "cuervo",
        "crow",
        "snake",
        "serpiente",
        "cat",
        "gato",
        "dog",
        "perro",
        "bird",
        "pajaro",
        "owl",
        "buho",
    ),
    "ambience": (
        "ambiente",
        "atmosfera",
        "lluvia",
        "viento",
        "tormenta",
        "trueno",
        "bosque",
        "noche",
        "grillos",
        "mar",
        "olas",
        "ciudad",
        "ambience",
        "ambient",
        "atmosphere",
        "rain",
        "wind",
        "storm",
        "thunder",
        "forest",
        "night",
        "crickets",
        "ocean",
        "waves",
        "city",
        "room tone",
        "drone",
        "drones",
    ),
    "impact": (
        "golpe",
        "impacto",
        "explosion",
        "disparo",
        "choque",
        "estruendo",
        "hit",
        "impact",
        "punch",
        "explosion",
        "gunshot",
        "crash",
        "slam",
        "thud",
        "boom",
        "braam",
    ),
    "foley": (
        "puerta",
        "paso",
        "pasos",
        "cadena",
        "cadenas",
        "cristal",
        "vidrio",
        "reloj",
        "campana",
        "llave",
        "rechinar",
        "crujido",
        "door",
        "footstep",
        "footsteps",
        "steps",
        "chain",
        "chains",
        "glass",
        "clock",
        "bell",
        "key",
        "creak",
        "creaking",
        "knock",
        "scratch",
        "arañazo",
        "click",
        "clic",
        "switch",
        "interruptor",
        "shutter",
        "obturador",
        "button",
        "boton",
        "typing",
        "teclado",
        "paper",
        "papel",
        "phone",
        "telefono",
        "camera",
        "camara",
    ),
    "transition": (
        "transicion",
        "whoosh",
        "swoosh",
        "riser",
        "rise",
        "sweep",
        "stinger",
        "swell",
        "reverse",
        "glitch",
        "transition",
    ),
}
LABELS = (
    "voice",
    "scream",
    "laugh",
    "creature",
    "ambience",
    "impact",
    "foley",
    "transition",
    "music",
    "other",
)
# Etiquetas de ánimo que se añaden si aparecen en el texto.
MOODS: dict[str, tuple[str, ...]] = {
    "terror": ("terror", "horror", "miedo", "escalofriante", "siniestro", "oscuro", "oscuridad", "malvad", "evil", "creepy", "scary", "spooky",
               "sinister", "dark", "eerie", "haunted", "embrujad", "halloween"),
    "suspenso": ("suspenso", "tension", "suspense", "tense", "ominous"),
    "epico": ("epico", "epic", "cinematic", "cinematografic", "trailer"),
    "alegre": ("alegre", "feliz", "happy", "cheerful", "upbeat", "fun"),
    "triste": ("triste", "melancol", "sad", "melanchol"),
}  # fmt: skip
KINDS = {
    "elevenlabs/text-to-speech": "speech",
    "elevenlabs/sound-effects": "sound_effect",
    "elevenlabs/music": "music",
    "elevenlabs/voice-isolator": "isolated",
    # Nodos de audio de Spaces (space_audio).
    "elevenlabs/tts": "speech",
    "elevenlabs/sfx": "sound_effect",
    "elevenlabs/music-gen": "music",
}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _has(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(_plain(word))}", text) is not None


def classify(text: str, kind: str) -> tuple[str, list[str]]:
    """(categoría, etiquetas) a partir del texto que generó el sonido y de su tipo."""
    plain = _plain(text)
    tags = [mood for mood, words in MOODS.items() if any(_has(plain, w) for w in words)]
    if kind == "music":
        return "music", tags
    if kind in ("speech", "voice_change", "isolated"):
        # Una voz que grita o ríe sigue siendo voz, pero lo dicen sus etiquetas ([screams], [laughs]…).
        for category in ("scream", "laugh"):
            if any(_has(plain, w) for w in CATEGORIES[category]):
                tags.append(category)
        return "voice", tags
    scores = {c: sum(_has(plain, w) for w in words) for c, words in CATEGORIES.items()}
    best = max(scores, key=lambda c: scores[c])
    return (best if scores[best] else "other"), tags


def title_from(text: str, limit: int = 60) -> str:
    """Título corto a partir del texto: primera frase, sin etiquetas [así] y cortado en una palabra."""
    clean = re.sub(r"\[[^\]]*\]", "", text).strip()
    first = re.split(r"(?<=[.!?¿¡])\s", clean, maxsplit=1)[0].strip() or clean
    if len(first) <= limit:
        return first or "Sin título"
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def clean_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = t.strip().lower()[:30]
        if t and t not in out:
            out.append(t)
    return out[:12]


async def register_job(session: AsyncSession, job: Job, storage: Path) -> Sound | None:
    """Crea (una vez) el sonido de un trabajo de audio completado, con la clasificación que pidió el
    agente o la automática."""
    kind = KINDS.get(job.model)
    if not kind or job.status != "completed" or not job.files:
        return None
    if await session.scalar(select(Sound.id).where(Sound.job_id == job.id)):
        return None
    args = job.input or {}
    text = str(args.get("text") or args.get("prompt") or "")
    auto_category, auto_tags = classify(text, kind)
    category = args.get("category") if args.get("category") in LABELS else auto_category
    file_name = f"outputs/{job.id}/{job.files[0]['name']}"
    sound = Sound(
        owner_id=job.owner_id,
        job_id=job.id,
        origin="studio",
        kind=kind,
        title=(args.get("title") or (title_from(text) if text else "Voz aislada"))[:200],
        category=category,
        tags=clean_tags([*(args.get("tags") or []), *auto_tags]),
        text=text,
        file_name=file_name,
        duration=await duration(str(storage / file_name)),
        created_at=job.finished_at or job.created_at,
    )
    session.add(sound)
    return sound


async def backfill(session: AsyncSession, storage: Path, owner: ApiClient) -> int:
    """Registra los trabajos de audio completados que aún no están en la sonoteca."""
    query = select(Job).where(Job.model.in_(KINDS), Job.status == "completed")
    if not owner.sees_all:
        query = query.where(Job.owner_id == owner.id)
    known = set(await session.scalars(select(Sound.job_id).where(Sound.job_id.is_not(None))))
    added = 0
    for job in await session.scalars(query):
        if job.id not in known and await register_job(session, job, storage):
            added += 1
    if added:
        await session.commit()
    return added


def history_kind(source: str | None) -> str:
    return {"TTS": "speech", "STS": "voice_change"}.get(source or "", "speech")


def as_dict(s: Sound, source_name: str | None = None) -> dict:
    return {
        "id": s.id,
        "job_id": s.job_id,
        "origin": s.origin,
        "kind": s.kind,
        "title": s.title,
        "category": s.category,
        "tags": s.tags or [],
        "text": s.text,
        "duration": s.duration,
        "file_url": f"/v1/sounds/{s.id}/file",
        "created_at": s.created_at.isoformat() + "Z",
        **({"source": source_name} if source_name else {}),
    }
