"""Nodos de audio de Spaces (fase 2c): voz, efecto de sonido y música con ElevenLabs.

Como las herramientas de la fase 2b, son modelos del catálogo (`elevenlabs/tts`, `elevenlabs/sfx`,
`elevenlabs/music-gen`) con su `input_schema`. El texto va en `prompt`, para que en Spaces entre por el mismo
puerto de texto que el resto de modelos. Su precio es el de la API de ElevenLabs (`elevenlabs_audio.estimate`)
y los ejecuta `ElevenLabsJobs`, un proveedor interno del worker que reutiliza `elevenlabs_audio.run`. El
resultado queda también en la sonoteca.

Son distintos de los servicios `/v1/audio/*` (con su propio `audio_quote`), que siguen igual para la página
de Audio y el MCP.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .config import Settings
from .elevenlabs_audio import TTS_MAX_CHARS, TTS_USD_PER_1K, MusicIn, SoundEffectIn, TextToSpeechIn, estimate
from .elevenlabs_audio import run as run_service
from .space_tools import AUDIO_PROVIDER, BackgroundProvider

TTS_NODE = "elevenlabs/tts"
SFX_NODE = "elevenlabs/sfx"
MUSIC_NODE = "elevenlabs/music-gen"


def _node(model_id: str, title: str, workflow: str, summary: str, schema: dict) -> dict:
    return {
        "id": model_id,
        "title": f"{title} — {workflow} API",
        "summary": summary,
        "workflow": workflow,
        "family": "ElevenLabs",
        "output": "audio",
        "capabilities": ["studio-audio"],
        "notes": [
            "Runs on ElevenLabs with your ELEVENLABS_API_KEY; the result also lands in your sound library."
        ],
        "docs_url": "https://elevenlabs.io/docs",
        "input_schema": {"type": "object", **schema},
    }


AUDIO_NODES: dict[str, dict] = {
    n["id"]: n
    for n in (
        _node(
            TTS_NODE, "Voiceover", "Text to speech", "Reads a text aloud with one of your ElevenLabs voices.",
            {"required": ["prompt", "voice_id"], "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": max(TTS_MAX_CHARS.values())},
                "voice_id": {"type": "string", "minLength": 1, "maxLength": 100, "title": "Voice"},
                "model_id": {"type": "string", "enum": list(TTS_USD_PER_1K), "default": "eleven_v4"},
                "language_code": {"type": "string", "maxLength": 5},
                "stability": {"type": "number", "minimum": 0, "maximum": 1},
                "style": {"type": "number", "minimum": 0, "maximum": 1},
                "speed": {"type": "number", "minimum": 0.7, "maximum": 1.2},
            }},
        ),
        _node(
            SFX_NODE, "Sound effect", "Sound effect", "A sound effect from a description (better in English).",
            {"required": ["prompt"], "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 2000},
                "duration_seconds": {"type": "number", "minimum": 0.5, "maximum": 30, "default": 5},
                "prompt_influence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3},
                "loop": {"type": "boolean", "default": False},
            }},
        ),
        _node(
            MUSIC_NODE, "Music", "Music", "An original music track from a description (genre, tempo, mood).",
            {"required": ["prompt"], "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
                "seconds": {"type": "number", "minimum": 3, "maximum": 600, "default": 30},
                "force_instrumental": {"type": "boolean", "default": False},
            }},
        ),
    )
}  # fmt: skip


def is_audio_node(model_id: str | None) -> bool:
    return model_id in AUDIO_NODES


def to_body(model_id: str, arguments: dict) -> BaseModel:
    """Cuerpo del servicio de ElevenLabs para una entrada del nodo. Lanza ValueError si no vale."""
    # Solo los campos que declara el nodo: un extra como `text` no puede duplicar ni colarse (revisión 62).
    allowed = AUDIO_NODES[model_id]["input_schema"]["properties"]
    args = {k: v for k, v in arguments.items() if v is not None and k in allowed}
    prompt = args.pop("prompt", "")
    try:
        if model_id == TTS_NODE:
            return TextToSpeechIn(text=prompt, **args)
        if model_id == SFX_NODE:
            return SoundEffectIn(text=prompt, **args)
        return MusicIn(prompt=prompt, **args)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ValueError(f"{'/'.join(str(p) for p in first['loc'])}: {first['msg']}") from None


def audio_quote(model_id: str, arguments: dict) -> dict | None:
    """Costo del nodo (aproximado, tarifa de la API) o None si la entrada no vale todavía."""
    try:
        return estimate(to_body(model_id, arguments))
    except ValueError:
        return None


class ElevenLabsJobs(BackgroundProvider):
    """Proveedor interno del worker para los nodos de audio: llama a ElevenLabs y entrega el MP3."""

    name = AUDIO_PROVIDER
    title = "ElevenLabs"
    blurb = "Voice, sound effects and music"
    work_name = "audio-work"

    def __init__(self, settings: Settings, eleven, transport=None, slots: asyncio.Semaphore | None = None):
        super().__init__(settings, transport)
        self.eleven = eleven
        self.slots = slots or asyncio.Semaphore(2)

    def accepts(self, model: str) -> bool:
        return model in AUDIO_NODES

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        body = to_body(model, arguments)
        out = folder / "0-audio.mp3"
        async with self.slots:
            await run_service(self.eleven, body, out)
        return "audio", out.name, "audio/mpeg"
