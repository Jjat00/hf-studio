"""Servicios de audio de ElevenLabs como trabajos locales de HF Studio: texto a voz, efectos de sonido,
música y aislamiento de voz. Igual que el cambio de voz (voice.py): se cotizan con precio de la API de
pago por uso, se lanzan con esa cotización y el resultado (un MP3) queda en la biblioteca.

Precios de la API a 2026-09-24 (https://elevenlabs.io/pricing/api): texto a voz 0,05 USD por 1.000
caracteres en Flash/Turbo y 0,10 en v3 y Multilingual v2; efectos 0,12 USD/min; música 0,15 USD/min;
aislamiento 0,12 USD/min.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .audio import PROTOCOLS, duration, has_audio
from .voice import ElevenLabsClient, VoiceError, _run

TTS_MODEL = "elevenlabs/text-to-speech"
SFX_MODEL = "elevenlabs/sound-effects"
MUSIC_MODEL = "elevenlabs/music"
ISOLATE_MODEL = "elevenlabs/voice-isolator"
AUDIO_MODELS = (TTS_MODEL, SFX_MODEL, MUSIC_MODEL, ISOLATE_MODEL)

TTS_USD_PER_1K = {
    "eleven_flash_v2_5": 0.05,
    "eleven_turbo_v2_5": 0.05,
    "eleven_v3": 0.10,
    "eleven_multilingual_v2": 0.10,
}
TTS_MAX_CHARS = {
    "eleven_flash_v2_5": 40000,
    "eleven_turbo_v2_5": 40000,
    "eleven_v3": 5000,
    "eleven_multilingual_v2": 10000,
}
SFX_USD_PER_MIN = 0.12
MUSIC_USD_PER_MIN = 0.15
ISOLATE_USD_PER_MIN = 0.12
MAX_ISOLATE_SECONDS = 3600.0


class TextToSpeechIn(BaseModel):
    text: str = Field(
        min_length=1, description="Texto a leer; con eleven_v3 admite etiquetas como [whispers] o [laughs]"
    )
    voice_id: str = Field(description="Voz (voice_id de list_voices)")
    voice_name: str | None = Field(None, description="Nombre de la voz, solo para mostrarlo")
    public_owner_id: str | None = Field(
        None, description="Solo voces de la biblioteca pública (ocupan un hueco)"
    )
    model_id: Literal["eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5"] = (
        Field("eleven_multilingual_v2", description="eleven_v3 = más expresivo; flash = más barato y rápido")
    )
    language_code: str | None = Field(
        None, max_length=5, description="ISO 639-1, p. ej. es (no en multilingual_v2)"
    )
    stability: float | None = Field(None, ge=0, le=1)
    style: float | None = Field(None, ge=0, le=1)
    speed: float | None = Field(None, ge=0.7, le=1.2)
    audio_quote: str | None = Field(None, description="audio_quote de la cotización; obligatorio al lanzar")

    @model_validator(mode="after")
    def _limits(self) -> TextToSpeechIn:
        if len(self.text) > TTS_MAX_CHARS[self.model_id]:
            raise ValueError(f"{self.model_id} accepts at most {TTS_MAX_CHARS[self.model_id]} characters")
        return self


class SoundEffectIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000, description="Descripción del sonido (mejor en inglés)")
    duration_seconds: float = Field(5, ge=0.5, le=30, description="Duración del efecto")
    prompt_influence: float = Field(0.3, ge=0, le=1, description="Más alto = sigue más el texto")
    loop: bool = Field(False, description="Que se pueda repetir en bucle sin cortes")
    audio_quote: str | None = None


class MusicIn(BaseModel):
    prompt: str = Field(
        min_length=1, max_length=4000, description="Descripción de la música (género, tempo, ánimo…)"
    )
    seconds: float = Field(30, ge=3, le=600, description="Duración de la pista")
    force_instrumental: bool = Field(False, description="Garantiza que no haya voz cantada")
    audio_quote: str | None = None


class IsolateIn(BaseModel):
    source_generation_id: str | None = Field(None, description="Video o audio de tu biblioteca")
    source_url: str | None = Field(None, description="URL de upload_media")
    audio_quote: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> IsolateIn:
        if bool(self.source_generation_id) == bool(self.source_url):
            raise ValueError("Pass exactly one of source_generation_id or source_url")
        return self


SERVICES: dict[str, tuple[str, type[BaseModel]]] = {
    "text-to-speech": (TTS_MODEL, TextToSpeechIn),
    "sound-effects": (SFX_MODEL, SoundEffectIn),
    "music": (MUSIC_MODEL, MusicIn),
    "voice-isolator": (ISOLATE_MODEL, IsolateIn),
}


def _estimate(usd: float, basis: str, units: float) -> dict:
    return {
        "kind": "approx",
        "usd": round(usd, 6),  # sin redondear a 0 un costo positivo (1 carácter en Flash = 0,00005 USD)
        "credits": None,
        "discount_pct": None,
        "units": units,
        "complete": True,
        "missing": [],
        "description": None,
        "basis": basis,
    }


def estimate(body: BaseModel, source_seconds: float | None = None) -> dict:
    """Costo según la tarifa de la API. `units` (caracteres o segundos) se vuelve a comprobar al lanzar."""
    if isinstance(body, TextToSpeechIn):
        rate, chars = TTS_USD_PER_1K[body.model_id], len(body.text)
        return _estimate(
            chars / 1000 * rate, f"{chars} chars × ${rate}/1K · ElevenLabs {body.model_id}", chars
        )
    if isinstance(body, SoundEffectIn):
        s = body.duration_seconds
        return _estimate(
            s / 60 * SFX_USD_PER_MIN, f"{s:.1f}s × ${SFX_USD_PER_MIN}/min · ElevenLabs sound effects", s
        )
    if isinstance(body, MusicIn):
        s = body.seconds
        return _estimate(
            s / 60 * MUSIC_USD_PER_MIN, f"{s:.0f}s × ${MUSIC_USD_PER_MIN}/min · ElevenLabs music", s
        )
    s = source_seconds or 0.0
    return _estimate(
        s / 60 * ISOLATE_USD_PER_MIN, f"{s:.1f}s × ${ISOLATE_USD_PER_MIN}/min · ElevenLabs voice isolator", s
    )


async def run(client: ElevenLabsClient, body: BaseModel, out: Path, source: str | None = None) -> None:
    """Genera el MP3 del servicio en `out`. Lanza VoiceError si ElevenLabs o ffmpeg fallan."""
    if isinstance(body, TextToSpeechIn):
        voice_id = await client.ensure_voice(body.voice_id, body.public_owner_id)
        payload: dict = {"text": body.text, "model_id": body.model_id}
        if body.language_code:
            payload["language_code"] = body.language_code
        settings = {
            k: getattr(body, k) for k in ("stability", "style", "speed") if getattr(body, k) is not None
        }
        if settings:
            payload["voice_settings"] = settings
        data = await client.text_to_speech(voice_id, payload)
    elif isinstance(body, SoundEffectIn):
        data = await client.sound_effect(
            {"text": body.text, "duration_seconds": body.duration_seconds,
             "prompt_influence": body.prompt_influence, "loop": body.loop, "model_id": "eleven_text_to_sound_v2"}
        )  # fmt: skip
    elif isinstance(body, MusicIn):
        data = await client.music(
            {"prompt": body.prompt, "music_length_ms": int(body.seconds * 1000),
             "force_instrumental": body.force_instrumental, "model_id": "music_v2"}
        )  # fmt: skip
    else:
        if not source or not await has_audio(source):
            raise VoiceError(422, "source_has_no_audio", "The source has no audio to isolate")
        with tempfile.TemporaryDirectory(prefix="hfs-isolate-") as tmp:
            wav = Path(tmp) / "input.wav"
            code, err = await _run(
                "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", PROTOCOLS, "-i", source,
                "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(wav),
            )  # fmt: skip
            if code != 0:
                raise VoiceError(
                    422, "audio_extract_failed", f"Could not read the source audio: {err[-200:]}"
                )
            data = await client.isolate(wav.read_bytes())
    if not data:
        raise VoiceError(502, "elevenlabs_empty", "ElevenLabs returned an empty file")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_name(f"{out.stem}.tmp{out.suffix}")
    tmp_out.write_bytes(data)
    if await duration(str(tmp_out)) is None:
        tmp_out.unlink(missing_ok=True)
        raise VoiceError(502, "elevenlabs_bad_audio", "ElevenLabs returned audio that could not be read")
    tmp_out.replace(out)
