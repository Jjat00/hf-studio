"""Voces gratis con edge-tts (voces neuronales de Microsoft Edge): catálogo y muestras con caché.

No gasta créditos ni necesita clave. Sirve para escuchar voces y para narraciones sin costo; las voces de
ElevenLabs (de pago) viven en voice.py.
"""

import asyncio
import hashlib
from pathlib import Path

import edge_tts

# País de cada locale, para agrupar y filtrar en la UI.
COUNTRIES = {
    "es-AR": "Argentina", "es-BO": "Bolivia", "es-CL": "Chile", "es-CO": "Colombia", "es-CR": "Costa Rica",
    "es-CU": "Cuba", "es-DO": "República Dominicana", "es-EC": "Ecuador", "es-ES": "España",
    "es-GQ": "Guinea Ecuatorial", "es-GT": "Guatemala", "es-HN": "Honduras", "es-MX": "México",
    "es-NI": "Nicaragua", "es-PA": "Panamá", "es-PE": "Perú", "es-PR": "Puerto Rico", "es-PY": "Paraguay",
    "es-SV": "El Salvador", "es-US": "Estados Unidos", "es-UY": "Uruguay", "es-VE": "Venezuela",
}  # fmt: skip

MAX_SAMPLE_CHARS = 300
RATE_LIMITS = ("-20%", "+30%")

_cache: list[dict] | None = None
_lock = asyncio.Lock()


class FreeVoiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _shape(v: dict) -> dict:
    locale = v["Locale"]
    # "Microsoft Gonzalo Online (Natural) - Spanish (Colombia)" -> "Gonzalo"
    friendly = v.get("FriendlyName", "")
    name = friendly.removeprefix("Microsoft ").split(" Online")[0] or v["ShortName"]
    tags = v.get("VoiceTag") or {}
    return {
        "voice_id": v["ShortName"],
        "name": name,
        "locale": locale,
        "country": COUNTRIES.get(locale, locale),
        "gender": (v.get("Gender") or "").lower(),
        "personalities": tags.get("VoicePersonalities") or [],
        "multilingual": "Multilingual" in v["ShortName"],
    }


async def free_voices(lang: str = "es") -> list[dict]:
    """Voces de edge-tts de un idioma (por defecto español), Colombia primero y luego por país y nombre."""
    global _cache
    async with _lock:
        if _cache is None:
            _cache = await edge_tts.list_voices()
    prefix = f"{lang}-"
    voices = [_shape(v) for v in _cache if v["Locale"].startswith(prefix)]
    return sorted(voices, key=lambda v: (v["locale"] != "es-CO", v["country"], v["name"]))


async def free_sample(voice_id: str, text: str, rate: str, storage_dir: Path) -> Path:
    """MP3 de la voz diciendo el texto. Se guarda por (voz, texto, velocidad): repetir no vuelve a sintetizar."""
    text = " ".join(text.split())
    if not text:
        raise FreeVoiceError(400, "empty_text", "Write a text to hear the voice")
    if len(text) > MAX_SAMPLE_CHARS:
        raise FreeVoiceError(400, "text_too_long", f"Samples are limited to {MAX_SAMPLE_CHARS} characters")
    if not _valid_rate(rate):
        raise FreeVoiceError(
            400, "invalid_rate", f"Rate must be between {RATE_LIMITS[0]} and {RATE_LIMITS[1]}, e.g. +10%"
        )
    known = {v["voice_id"] for v in await free_voices(voice_id.split("-")[0])}
    if voice_id not in known:
        raise FreeVoiceError(404, "unknown_voice", f"Unknown free voice: {voice_id}")
    root = Path(storage_dir).resolve() / "voice_samples"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{voice_id}|{rate}|{text}".encode()).hexdigest()[:24]
    path = root / f"{voice_id}-{key}.mp3"
    if not path.exists():
        tmp = path.with_suffix(".part")
        try:
            await edge_tts.Communicate(text, voice_id, rate=rate).save(str(tmp))
        except Exception as exc:  # red o servicio de Microsoft caído
            tmp.unlink(missing_ok=True)
            raise FreeVoiceError(502, "tts_failed", f"Could not synthesize the sample: {exc}") from exc
        tmp.replace(path)
    return path


def _valid_rate(rate: str) -> bool:
    if not rate or rate[0] not in "+-" or not rate.endswith("%"):
        return False
    try:
        n = int(rate[:-1])
    except ValueError:
        return False
    lo, hi = (int(x[:-1]) for x in RATE_LIMITS)
    return lo <= n <= hi
