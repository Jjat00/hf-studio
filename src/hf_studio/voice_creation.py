"""Crear voces nuevas en la cuenta de ElevenLabs, todo por la API: clonación instantánea a partir de
muestras de audio (la voz propia o cualquier otra con permiso) y diseño a partir de una descripción.

La voz creada queda en la cuenta, así que aparece en list_voices y sirve en texto a voz, cambio de voz y
Spaces sin nada más. Clonar no gasta créditos, pero ocupa un espacio de voces del plan. Diseñar cobra los
caracteres del texto de muestra una sola vez, aunque ElevenLabs devuelva tres muestras; guardar la elegida
no cobra.

Precio del diseño a 2026-10-30: ElevenLabs no publica una tarifa propia para la API; se cotiza como texto a
voz Multilingual/v3 (0,10 USD por 1.000 caracteres a precio de lista) para no quedarse corto.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .audio import duration, guarded
from .media import _head, is_media_container
from .voice import ElevenLabsClient, VoiceError, _run

DESIGN_MODEL = "elevenlabs/voice-design"
DESIGN_USD_PER_1K = 0.10
CLONE_MIN_SECONDS = 10.0  # menos no da una voz reconocible; ElevenLabs recomienda 1 a 2 minutos
CLONE_MAX_SAMPLES = 25
SAMPLE_MAX_SECONDS = 300.0  # cada muestra se recorta a 5 minutos: más no mejora el clon instantáneo
PREVIEW_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Texto de muestra por idioma (100 a 1000 caracteres). Sin texto propio, el diseño habla en este idioma.
PREVIEW_TEXT = {
    "es": "Hola, ¿cómo estás? Hoy te quiero contar algo que me pasó esta mañana camino al trabajo. "
    "Fue tan inesperado que todavía me río cuando lo recuerdo, así que ponte cómodo y escucha.",
    "en": "Hi there, how are you doing? Today I want to tell you about something that happened to me this "
    "morning on my way to work. It was so unexpected that I still laugh when I think about it.",
}


class DesignVoiceIn(BaseModel):
    description: str = Field(
        min_length=20,
        max_length=1000,
        description="Cómo suena la voz: edad, género, acento, tono, ritmo, emoción (p. ej. «hombre de 50 años, "
        "acento colombiano paisa, voz grave y cálida, habla despacio»)",
    )
    language: str = Field(
        "es", pattern=r"^[a-z]{2}$", description="Idioma ISO 639-1 de la voz; con es o en no hace falta text"
    )
    text: str | None = Field(
        None, min_length=100, max_length=1000, description="Lo que dicen las muestras (cobra sus caracteres)"
    )
    model_id: Literal["eleven_ttv_v3", "eleven_multilingual_ttv_v2"] = Field(
        "eleven_ttv_v3",
        description="eleven_ttv_v3 = más expresivo y multilingüe; multilingual_ttv_v2 = el anterior",
    )
    guidance_scale: float | None = Field(
        None, ge=0, le=100, description="Más alto = sigue más la descripción (muy alto suena artificial)"
    )
    seed: int | None = Field(None, ge=0, description="Misma semilla y mismos datos = misma voz")
    should_enhance: bool = Field(False, description="ElevenLabs amplía una descripción corta")
    voice_quote: str | None = Field(None, description="voice_quote de la cotización; obligatorio al lanzar")

    @model_validator(mode="after")
    def _has_text(self) -> DesignVoiceIn:
        if not self.text and self.language not in PREVIEW_TEXT:
            raise ValueError(f"Pass text (100 to 1000 characters) for language {self.language}")
        return self

    @property
    def preview_text(self) -> str:
        return self.text or PREVIEW_TEXT[self.language]


class SaveVoiceIn(BaseModel):
    generated_voice_id: str = Field(pattern=PREVIEW_ID.pattern, description="Id de la muestra elegida")
    name: str = Field(min_length=1, max_length=100, description="Nombre de la voz en la cuenta")
    description: str = Field(min_length=20, max_length=1000, description="Descripción con la que se diseñó")
    language: str = Field("es", pattern=r"^[a-z]{2}$")


def design_estimate(body: DesignVoiceIn) -> dict:
    chars = len(body.preview_text)
    return {
        "kind": "approx",
        "usd": round(chars / 1000 * DESIGN_USD_PER_1K, 6),
        "credits": None,
        "discount_pct": None,
        "units": chars,
        "complete": True,
        "missing": [],
        "description": None,
        "basis": f"{chars} chars × ${DESIGN_USD_PER_1K}/1K · ElevenLabs voice design {body.model_id} "
        "(3 samples, charged once)",
    }


def design_payload(body: DesignVoiceIn) -> dict:
    payload: dict = {
        "voice_description": body.description,
        "model_id": body.model_id,
        "text": body.preview_text,
        "should_enhance": body.should_enhance,
    }
    if body.guidance_scale is not None:
        payload["guidance_scale"] = body.guidance_scale
    if body.seed is not None:
        payload["seed"] = body.seed
    return payload


def previews_dir(storage: Path, owner_id: str) -> Path:
    return storage / "voice-previews" / owner_id


def preview_path(storage: Path, owner_id: str, generated_voice_id: str) -> Path | None:
    """Archivo de una muestra de este dueño, o None si el id no es válido o no existe."""
    if not PREVIEW_ID.match(generated_voice_id):
        return None
    path = previews_dir(storage, owner_id) / f"{generated_voice_id}.mp3"
    return path if path.is_file() else None


async def design(client: ElevenLabsClient, body: DesignVoiceIn, storage: Path, owner_id: str) -> dict:
    """Genera las muestras, las guarda como MP3 del dueño y devuelve sus ids (sin el audio en base64)."""
    data = await client.design_voice(design_payload(body))
    folder = previews_dir(storage, owner_id)
    folder.mkdir(parents=True, exist_ok=True)
    previews = []
    for p in data.get("previews") or []:
        gid = p.get("generated_voice_id") or ""
        if not PREVIEW_ID.match(gid) or not p.get("audio_base_64"):
            continue
        (folder / f"{gid}.mp3").write_bytes(base64.b64decode(p["audio_base_64"]))
        previews.append(
            {
                "generated_voice_id": gid,
                "duration_secs": p.get("duration_secs"),
                "language": p.get("language"),
            }
        )
    if not previews:
        raise VoiceError(502, "elevenlabs_empty", "ElevenLabs returned no voice samples")
    return {"previews": previews, "text": data.get("text") or body.preview_text}


async def save(client: ElevenLabsClient, body: SaveVoiceIn) -> dict:
    data = await client.save_designed_voice(
        {"voice_name": body.name, "voice_description": body.description,
         "generated_voice_id": body.generated_voice_id, "labels": {"language": body.language}}
    )  # fmt: skip
    return {"voice_id": data["voice_id"], "name": data.get("name") or body.name}


async def sample_to_mp3(source: str, out: Path) -> float:
    """MP3 mono de la voz de una muestra (audio o video), recortado a SAMPLE_MAX_SECONDS. Devuelve su duración."""
    if not is_media_container(_head(Path(source))):
        raise VoiceError(415, "unsupported_media", "Each sample must be an audio or video file")
    code, err = await _run(
        "ffmpeg", "-y", "-v", "error", *guarded(source), "-vn", "-t", str(SAMPLE_MAX_SECONDS),
        "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "192k", str(out),
    )  # fmt: skip
    seconds = await duration(str(out)) if code == 0 and out.is_file() else None
    if not seconds:
        raise VoiceError(422, "audio_extract_failed", f"Could not read the voice in a sample: {err[-200:]}")
    return seconds


async def clone(
    client: ElevenLabsClient,
    sources: list[str],
    name: str,
    description: str | None,
    language: str,
    remove_background_noise: bool,
) -> dict:
    """Clonación instantánea con las muestras locales (rutas ya validadas). Lanza VoiceError si no alcanza."""
    if not sources:
        raise VoiceError(422, "no_samples", "Pass at least one audio or video sample of the voice")
    if len(sources) > CLONE_MAX_SAMPLES:
        raise VoiceError(422, "too_many_samples", f"Pass at most {CLONE_MAX_SAMPLES} samples")
    with tempfile.TemporaryDirectory(prefix="hfs-clone-") as tmp:
        samples, total = [], 0.0
        for i, source in enumerate(sources):
            out = Path(tmp) / f"sample-{i + 1}.mp3"
            total += await sample_to_mp3(source, out)
            samples.append((out.name, out.read_bytes()))
        if total < CLONE_MIN_SECONDS:
            raise VoiceError(
                422, "samples_too_short",
                f"The samples last {total:.1f}s; pass at least {CLONE_MIN_SECONDS:.0f}s of voice (1 to 2 minutes is best)",
            )  # fmt: skip
        data = await client.clone_voice(
            name, samples, description, {"language": language}, remove_background_noise
        )
    return {
        "voice_id": data["voice_id"],
        "name": name,
        "requires_verification": bool(data.get("requires_verification")),
        "sample_seconds": round(total, 1),
    }
