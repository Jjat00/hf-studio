"""Voces gratis (edge-tts) y filtros de la biblioteca de ElevenLabs. edge-tts está simulado: no sale a la red."""

import asyncio
from pathlib import Path
from typing import ClassVar

import pytest

from hf_studio import free_voices as fv

from .test_voice import voice_env  # noqa: F401  (fixture)

VOICES = [
    {"ShortName": "es-MX-JorgeNeural", "Locale": "es-MX", "Gender": "Male",
     "FriendlyName": "Microsoft Jorge Online (Natural) - Spanish (Mexico)", "VoiceTag": {"VoicePersonalities": ["Friendly"]}},
    {"ShortName": "es-CO-SalomeNeural", "Locale": "es-CO", "Gender": "Female",
     "FriendlyName": "Microsoft Salome Online (Natural) - Spanish (Colombia)"},
    {"ShortName": "en-US-AriaNeural", "Locale": "en-US", "Gender": "Female",
     "FriendlyName": "Microsoft Aria Online (Natural) - English (United States)"},
]  # fmt: skip


class FakeCommunicate:
    made: ClassVar[list[tuple[str, str, str]]] = []

    def __init__(self, text: str, voice: str, rate: str = "+0%"):
        self.args = (text, voice, rate)

    async def save(self, path: str) -> None:
        FakeCommunicate.made.append(self.args)
        await asyncio.to_thread(Path(path).write_bytes, b"ID3fake-mp3")


@pytest.fixture(autouse=True)
def fake_edge(monkeypatch):
    async def list_voices():
        return VOICES

    monkeypatch.setattr(fv.edge_tts, "list_voices", list_voices)
    monkeypatch.setattr(fv.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(fv, "_cache", None)
    FakeCommunicate.made = []


async def test_free_voices_spanish_colombia_first(voice_env):  # noqa: F811
    _, http, _, _ = voice_env
    voices = (await http.get("/v1/voice/free-voices")).json()["voices"]
    assert [v["voice_id"] for v in voices] == ["es-CO-SalomeNeural", "es-MX-JorgeNeural"]
    assert voices[0] | {"personalities": []} == {
        "voice_id": "es-CO-SalomeNeural", "name": "Salome", "locale": "es-CO", "country": "Colombia",
        "gender": "female", "personalities": [], "multilingual": False,
    }  # fmt: skip


async def test_free_sample_is_cached(voice_env):  # noqa: F811
    _, http, _, _ = voice_env
    params = {"voice": "es-CO-SalomeNeural", "text": "Hola  Colombia", "rate": "+10%"}
    first = await http.get("/v1/voice/free-sample", params=params)
    again = await http.get("/v1/voice/free-sample", params=params)
    assert first.status_code == again.status_code == 200
    assert first.headers["content-type"] == "audio/mpeg" and first.content == b"ID3fake-mp3"
    assert FakeCommunicate.made == [("Hola Colombia", "es-CO-SalomeNeural", "+10%")]


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"voice": "es-CO-SalomeNeural", "text": "   "}, "empty_text"),
        ({"voice": "es-CO-SalomeNeural", "text": "a" * 301}, "text_too_long"),
        ({"voice": "es-CO-SalomeNeural", "text": "hola", "rate": "fast"}, "invalid_rate"),
        ({"voice": "es-CO-SalomeNeural", "text": "hola", "rate": "+90%"}, "invalid_rate"),
        ({"voice": "es-CO-NadieNeural", "text": "hola"}, "unknown_voice"),
    ],
)
async def test_free_sample_rejects_bad_input(voice_env, params, code):  # noqa: F811
    _, http, _, _ = voice_env
    body = (await http.get("/v1/voice/free-sample", params=params)).json()
    assert body["error"]["code"] == code
    assert FakeCommunicate.made == []


async def test_library_filters_reach_elevenlabs(voice_env):  # noqa: F811
    _, http, fake, _ = voice_env
    params = {"library": True, "language": "es", "accent": "colombian", "gender": "female"}
    await http.get("/v1/voice/voices", params=params)
    sent = fake.calls[-1].url.params
    assert (sent["language"], sent["accent"], sent["gender"]) == ("es", "colombian", "female")
