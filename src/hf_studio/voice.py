"""Cambio de voz en un tramo de video con ElevenLabs Voice Changer (speech-to-speech).

Flujo: se recorta el audio del tramo [start, end] con ffmpeg, ElevenLabs lo convierte a la voz
elegida (con `remove_background_noise`, que aísla la voz en la misma llamada), se aplica un efecto
opcional y se mezcla de vuelta en el tramo con fundidos cortos, sin volver a codificar la imagen.

Es un trabajo local más (modelo `elevenlabs/voice-changer`): vive en la tabla de trabajos, así que
aparece en la biblioteca, el detalle y el MCP como cualquier generación. El worker de Higgsfield no
lo toca: no queda en `pending` y no tiene `next_check_at`.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from .audio import PROTOCOLS, duration, has_audio
from .config import Settings

log = logging.getLogger(__name__)

VOICE_MODEL = "elevenlabs/voice-changer"
MIN_SECONDS = 0.5
MAX_SECONDS = 300.0  # límite de ElevenLabs por petición
FADE = 0.05
LIBRARY_PREFIX = "hfs-"  # nombre con el que se guarda en la cuenta una voz añadida desde la biblioteca

Effect = Literal["none", "deep", "monster", "ghost"]


def effect_graph(effect: str, src: str, out: str) -> str:
    """Subgrafo de ffmpeg que aplica el efecto a la voz convertida (de la etiqueta src a out)."""
    if effect == "deep":
        return f"[{src}]rubberband=pitch=0.78:formant=shifted,equalizer=f=110:t=q:w=1:g=4[{out}]"
    if effect == "monster":
        return (
            f"[{src}]asplit=2[{out}_a][{out}_b];"
            f"[{out}_a]rubberband=pitch=0.7:formant=shifted[{out}_1];"
            f"[{out}_b]rubberband=pitch=0.5:formant=shifted,volume=0.6[{out}_2];"
            f"[{out}_1][{out}_2]amix=inputs=2:normalize=0,equalizer=f=120:t=q:w=1:g=5,"
            f"asoftclip=type=tanh:threshold=0.7,aecho=0.8:0.8:60|120:0.35|0.2[{out}]"
        )
    if effect == "ghost":
        return f"[{src}]rubberband=pitch=1.06,highpass=f=180,aecho=0.8:0.9:280|560:0.45|0.3[{out}]"
    return f"[{src}]anull[{out}]"


class VoiceChangeIn(BaseModel):
    source_generation_id: str | None = Field(None, description="Generación de video de tu biblioteca")
    source_url: str | None = Field(None, description="URL pública de un video (p. ej. de upload_media)")
    start: float = Field(0, ge=0, description="Inicio del tramo, en segundos")
    end: float | None = Field(None, gt=0, description="Fin del tramo, en segundos (vacío = hasta el final)")
    voice_id: str = Field(description="Voz destino (voice_id de list_voices)")
    voice_name: str | None = Field(None, description="Nombre de la voz, solo para mostrarlo")
    public_owner_id: str | None = Field(
        None, description="Solo para voces de la biblioteca pública: se añaden a la cuenta antes de usarlas"
    )
    effect: Effect = Field(
        "none", description="Capa extra: deep (grave), monster (monstruo) o ghost (fantasma)"
    )
    original_volume: float = Field(
        0, ge=0, le=1, description="Volumen del audio original dentro del tramo (0 = solo la voz nueva)"
    )
    remove_background_noise: bool = Field(True, description="Aísla la voz antes de convertirla")
    voice_quote: str | None = Field(
        None,
        description="voice_quote devuelto por /v1/voice/estimate para esta misma petición. Obligatorio al lanzar "
        "(un solo uso, 15 min); si el tramo real ya no dura lo cotizado, no se cobra y hay que volver a cotizar",
    )

    @model_validator(mode="after")
    def _one_source(self) -> VoiceChangeIn:
        if bool(self.source_generation_id) == bool(self.source_url):
            raise ValueError("Pass exactly one of source_generation_id or source_url")
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class VoiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class ElevenLabsClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        key = settings.elevenlabs_api_key.get_secret_value().strip()
        self.configured = bool(key)
        self._http = httpx.AsyncClient(
            base_url=settings.elevenlabs_base_url.rstrip("/"),
            headers={"xi-api-key": key},
            timeout=httpx.Timeout(180.0, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        if not self.configured:
            raise VoiceError(
                503, "elevenlabs_not_configured", "Set ELEVENLABS_API_KEY in .env to change voices"
            )
        try:
            response = await self._http.request(method, path, **kw)
        except httpx.TransportError as exc:
            raise VoiceError(502, "elevenlabs_network", f"ElevenLabs is not reachable: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            try:
                body = response.json().get("detail")
                detail = body.get("message", detail) if isinstance(body, dict) else (body or detail)
            except ValueError:
                pass
            code = {401: "elevenlabs_auth", 402: "elevenlabs_credits", 429: "elevenlabs_rate_limit"}.get(
                response.status_code, "elevenlabs_error"
            )
            raise VoiceError(response.status_code if response.status_code < 500 else 502, code, str(detail))
        return response

    async def voices(self, search: str | None = None, library: bool = False, limit: int = 30) -> list[dict]:
        """Voces de la cuenta (incluidas las predefinidas) o de la biblioteca pública."""
        if library:
            params = {"page_size": limit, **({"search": search} if search else {})}
            data = (await self._request("GET", "/v1/shared-voices", params=params)).json()
            return [
                {
                    "voice_id": v["voice_id"],
                    "name": v.get("name") or v["voice_id"],
                    "public_owner_id": v.get("public_owner_id"),
                    "preview_url": v.get("preview_url"),
                    "description": v.get("description") or v.get("descriptive"),
                    "labels": {k: v.get(k) for k in ("gender", "accent", "language", "age") if v.get(k)},
                    "library": True,
                }
                for v in data.get("voices", [])
            ]
        params = {"page_size": min(limit, 100), **({"search": search} if search else {})}
        data = (await self._request("GET", "/v2/voices", params=params)).json()
        return [
            {
                "voice_id": v["voice_id"],
                "name": v.get("name") or v["voice_id"],
                "public_owner_id": None,
                "preview_url": v.get("preview_url"),
                "description": v.get("description"),
                "labels": v.get("labels") or {},
                "library": False,
            }
            for v in data.get("voices", [])
        ]

    async def subscription(self) -> dict:
        data = (await self._request("GET", "/v1/user/subscription")).json()
        used, limit = data.get("character_count"), data.get("character_limit")
        return {
            "tier": data.get("tier"),
            "credits_used": used,
            "credits_limit": limit,
            "credits_left": limit - used if isinstance(used, int) and isinstance(limit, int) else None,
        }

    async def ensure_voice(self, voice_id: str, public_owner_id: str | None) -> str:
        """Una voz de la biblioteca pública se añade a la cuenta (una sola vez) y se usa su nuevo id."""
        if not public_owner_id:
            return voice_id
        name = f"{LIBRARY_PREFIX}{voice_id}"
        mine = await self._request("GET", "/v2/voices", params={"search": name, "page_size": 10})
        for v in mine.json().get("voices", []):
            if v.get("name") == name:
                return v["voice_id"]
        added = await self._request(
            "POST", f"/v1/voices/add/{public_owner_id}/{voice_id}", json={"new_name": name}
        )
        return added.json()["voice_id"]

    async def speech_to_speech(self, voice_id: str, audio: bytes, remove_background_noise: bool) -> bytes:
        response = await self._request(
            "POST",
            f"/v1/speech-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            data={
                "model_id": self.settings.elevenlabs_sts_model,
                "remove_background_noise": "true" if remove_background_noise else "false",
            },
            files={"audio": ("segment.wav", audio, "audio/wav")},
        )
        return response.content


# --- ffmpeg --------------------------------------------------------------------------------------


async def _run(*args: str, timeout: float = 300) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 1, "timeout"
    except asyncio.CancelledError:  # plazo global vencido: que ffmpeg no siga vivo
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, (out or err).decode(errors="replace").strip()


async def probe_duration(source: str) -> float | None:
    return await duration(source)


async def image_duration(source: str) -> float | None:
    """Lo que dura la imagen (la pista de video), que puede diferir de la del audio."""
    code, out = await _run(
        "ffprobe", "-v", "error", "-protocol_whitelist", PROTOCOLS, "-select_streams", "v:0",
        "-show_entries", "stream=duration", "-of", "csv=p=0", source, timeout=60,
    )  # fmt: skip
    try:
        return float(out.splitlines()[0]) if code == 0 and out else await duration(source)
    except ValueError:
        return await duration(source)


VOICE_QUOTE_TTL = 15 * 60


def voice_digest(body: VoiceChangeIn) -> str:
    """Huella de la petición (sin la cotización): liga el voice_quote y la idempotencia a lo pedido."""
    from .service import input_hash

    return input_hash(VOICE_MODEL, body.model_dump(exclude_none=True, exclude={"voice_quote"}))


def segment_bounds(body: VoiceChangeIn, duration: float) -> tuple[float, float]:
    start = min(body.start, duration)
    end = min(body.end if body.end is not None else duration, duration)
    seconds = end - start
    if seconds < MIN_SECONDS:
        raise VoiceError(422, "segment_too_short", f"The segment must last at least {MIN_SECONDS}s")
    if seconds > MAX_SECONDS:
        raise VoiceError(
            422, "segment_too_long", f"ElevenLabs accepts at most {MAX_SECONDS:.0f}s per segment"
        )
    return round(start, 3), round(end, 3)


def estimate(seconds: float, settings: Settings) -> dict:
    rate = settings.elevenlabs_usd_per_minute
    usd = round(seconds / 60 * rate, 4)
    return {
        "kind": "approx",
        "usd": usd,
        "credits": None,
        "discount_pct": None,
        "seconds": round(seconds, 2),
        "complete": True,
        "missing": [],
        "description": None,
        # Con un plan de ElevenLabs se descuenta de sus minutos incluidos en vez de cobrarse aparte.
        "basis": f"{seconds:.1f}s × ${rate}/min · ElevenLabs Voice Changer",
    }


def mix_command(
    source: str,
    voice: Path,
    out: Path,
    start: float,
    end: float,
    body: VoiceChangeIn,
    voiced: float | None = None,
    total: float | None = None,
) -> list[str]:
    """Mezcla la voz convertida en [start, end]. `voiced` es lo que dura de verdad la voz devuelta: si es más
    corta que el tramo, el original solo se atenúa mientras suena la voz nueva."""
    seconds = min(end - start, voiced) if voiced else end - start
    stop = start + seconds
    fade_out = max(0.0, seconds - FADE)
    wet = (
        effect_graph(body.effect, "1:a", "fx") + ";"
        f"[fx]aresample=48000,atrim=0:{seconds},afade=t=in:d={FADE},afade=t=out:st={fade_out}:d={FADE},"
        f"adelay=delays={int(start * 1000)}:all=1"
    )
    # El original baja a original_volume solo mientras suena la voz nueva (con fundidos) y encima entra ella.
    cut = 1 - body.original_volume
    graph = (
        f"[0:a]aresample=48000,apad,volume=eval=frame:"
        f"volume='1-{cut}*clip((t-{start})/{FADE},0,1)*clip(({stop}-t)/{FADE},0,1)'[dry];"
        f"{wet}[wet];[dry][wet]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]"
    )
    return [
        "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", PROTOCOLS, "-i", source, "-i", str(voice),
        "-filter_complex", graph, "-map", "0:v:0", "-map", "[a]",
        # La duración la fija la imagen: el audio original se completa con silencio (apad) si es más corto.
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", *(["-t", f"{total:.3f}"] if total else ["-shortest"]),
        "-movflags", "+faststart", str(out),
    ]  # fmt: skip


async def change_voice(
    client: ElevenLabsClient, body: VoiceChangeIn, source: str, start: float, end: float, out: Path
) -> None:
    """Ejecuta el flujo completo y deja el video final en `out`. Lanza VoiceError si algo falla."""
    if not await has_audio(source):
        raise VoiceError(422, "source_has_no_audio", "The source video has no audio to convert")
    voice_id = await client.ensure_voice(body.voice_id, body.public_owner_id)
    with tempfile.TemporaryDirectory(prefix="hfs-voice-") as tmp:
        segment, converted = Path(tmp) / "segment.wav", Path(tmp) / "voice.mp3"
        code, err = await _run(
            "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", PROTOCOLS,
            "-ss", str(start), "-t", str(end - start), "-i", source,
            "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(segment),
        )  # fmt: skip
        if code != 0:
            raise VoiceError(
                422, "segment_extract_failed", f"Could not extract the segment audio: {err[-200:]}"
            )
        converted.write_bytes(
            await client.speech_to_speech(voice_id, segment.read_bytes(), body.remove_background_noise)
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = out.with_name(f"{out.stem}.tmp{out.suffix}")
        voiced = await duration(str(converted))
        total = await image_duration(source)
        code, err = await _run(*mix_command(source, converted, tmp_out, start, end, body, voiced, total))
        result = await image_duration(str(tmp_out)) if code == 0 else None
        # Nunca se publica un video recortado: la imagen debe durar lo mismo que la del original.
        if code != 0 or result is None or (total is not None and abs(result - total) > 0.1):
            tmp_out.unlink(missing_ok=True)
            raise VoiceError(
                500, "mix_failed", f"Could not mix the new voice ({total} → {result}s): {err[-300:]}"
            )
        tmp_out.replace(out)
