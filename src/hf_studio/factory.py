"""Content Factory: cortos verticales «¿Qué pasaría si…?» con gráficos dibujados por código y una sola voz.

Es un modelo más del catálogo (`hf-studio/content-factory`, salida video) que corre un proveedor interno del
worker (`ContentFactoryJobs`), como las herramientas locales de Spaces: aparece en el historial, se cotiza,
se aprueba y se cancela igual que cualquier generación. Un episodio por trabajo; una serie son varios trabajos.

Tubería, todo en `storage/factory-work/<id>/` (se borra al entregar, al fallar o al cancelar):
1. Voz por escena: edge-tts (gratis, con marcas de palabra) o ElevenLabs (de pago, con `with-timestamps`).
2. Duración de cada escena = su voz + un respiro; las palabras quedan con su tiempo absoluto.
3. Composición HyperFrames (`factory_compose`), render a MP4 1080×1920 a 30 fps con `npx hyperframes@<versión
   fija>` y mezcla de la voz normalizada a -14 LUFS con ffmpeg.

Precio: 0 con edge-tts; con ElevenLabs, la tarifa de texto a voz por los caracteres de la narración
(`elevenlabs_audio.estimate`, aproximada). Si falta Node.js 22+, npx o ffmpeg, el plan sale sin opciones y la
cotización dice por qué (en la imagen de Docker, por ejemplo).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import math
import os
import re
import shutil
import signal
import subprocess
import time
import unicodedata
from pathlib import Path

import edge_tts
from pydantic import ValidationError

from .audio import duration
from .config import Settings
from .elevenlabs_audio import TTS_USD_PER_1K
from .factory_compose import SceneTime, Word, build_composition
from .factory_formats import ASPECTS
from .factory_rich import assets_needed
from .factory_script import Script, narration_chars, script_schema
from .factory_styles import DEFAULT_STYLE, STYLES
from .space_tools import FACTORY_PROVIDER, BackgroundProvider

log = logging.getLogger("hf_studio.factory")

FACTORY_MODEL = "hf-studio/content-factory"
HYPERFRAMES_VERSION = "0.9.19"  # fijada: cada versión de HyperFrames puede cambiar el render
MIN_NODE = 22
FPS = 30
LEAD_IN = 0.25  # silencio antes de la voz de cada escena
TAIL = 0.35  # respiro tras la voz de cada escena
END_HOLD = 1.0  # la última escena se queda un poco más en pantalla
LOUDNESS = "loudnorm=I=-14:TP=-1.5:LRA=11"  # objetivo de las redes verticales
TTS_TIMEOUT = 90.0
RENDER_TIMEOUT_MIN = 600.0
ASSETS = Path(__file__).with_name("factory_assets")


def _input_schema() -> dict:
    script = script_schema()
    defs = script.pop("$defs", {})
    return {
        "type": "object",
        "required": ["script", "voice"],
        "$defs": defs,
        "properties": {
            "script": {**script, "title": "Script (one episode)"},
            "style": {"type": "string", "enum": list(STYLES), "default": DEFAULT_STYLE, "title": "Style"},
            "voice": {
                "type": "object",
                "title": "Narrator",
                "required": ["engine", "voice_id"],
                "additionalProperties": False,
                "properties": {
                    "engine": {"type": "string", "enum": ["edge", "elevenlabs"]},
                    "voice_id": {"type": "string", "minLength": 1, "maxLength": 100},
                    "rate": {"type": "string", "pattern": "^[+-][0-9]{1,2}%$"},
                    "model_id": {"type": "string", "enum": list(TTS_USD_PER_1K)},
                },
            },
            "aspect": {"type": "string", "enum": list(ASPECTS), "default": "9:16", "title": "Aspect ratio"},
            "format": {"type": "string", "maxLength": 40, "title": "Format (for reference)"},
            "language": {"type": "string", "maxLength": 5, "default": "es"},
        },
    }


FACTORY_NODE = {
    "id": FACTORY_MODEL,
    "title": "Content Factory — Faceless shorts API",
    "summary": (
        "A narrated video in any format (9:16, 16:9 or 1:1): code-drawn data graphics, equations, plots, 3D, "
        "word-synced captions and one narrator voice."
    ),
    "workflow": "Faceless shorts",
    "family": "HF Studio",
    "output": "video",
    "capabilities": ["content-factory"],
    "notes": [
        (
            "Rendered locally with HyperFrames (needs Node.js 22+ and ffmpeg). Free with an edge-tts voice; with "
            "ElevenLabs it costs the text to speech of the narration."
        ),
        "Write the script with POST /v1/factory/scripts (Claude) or by hand; one episode per generation.",
    ],
    "docs_url": "",
    "input_schema": _input_schema(),
}


def is_factory(model_id: str | None) -> bool:
    return model_id == FACTORY_MODEL


# --- Disponibilidad ----------------------------------------------------------------------------------------------

_status: tuple[float, str | None] | None = None


def _node_major() -> int | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        import subprocess

        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"v(\d+)", out.strip())
    return int(match.group(1)) if match else None


def renderer_problem() -> str | None:
    """Por qué no se puede renderizar aquí (None si se puede). En caché un minuto."""
    global _status
    if _status and time.monotonic() - _status[0] < 60:
        return _status[1]
    problem = None
    if os.environ.get("HF_STUDIO_FACTORY_DISABLED"):
        problem = "Content Factory is disabled on this server"
    elif not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        problem = "Install ffmpeg to render shorts"
    elif not shutil.which("npx"):
        problem = f"Install Node.js {MIN_NODE}+ (with npx) to render shorts with HyperFrames"
    else:
        major = _node_major()
        if major is None or major < MIN_NODE:
            problem = f"HyperFrames needs Node.js {MIN_NODE}+ (found {major or 'none'})"
    _status = (time.monotonic(), problem)
    return problem


def script_problem(arguments: dict) -> str | None:
    """Por qué el guion no se puede producir (None si se puede): la validación estricta (LaTeX, expresiones,
    nodos del diagrama…) que el JSON Schema del catálogo no expresa."""
    try:
        Script.model_validate(arguments.get("script") or {})
    except ValidationError as exc:
        first = exc.errors()[0]
        where = "/".join(str(p) for p in first["loc"])
        return f"Invalid script ({where}: {first['msg']})"
    return None


def quote(arguments: dict) -> dict:
    """Precio del episodio: 0 con edge-tts; con ElevenLabs, sus caracteres a la tarifa del modelo elegido."""
    voice = arguments.get("voice") or {}
    try:
        chars = narration_chars(arguments.get("script") or {})
    except ValueError:
        chars = 0
    if voice.get("engine") != "elevenlabs":
        return {"usd": 0.0, "kind": "exact", "basis": f"Free voice (edge-tts) · {chars} chars · local render"}
    model = voice.get("model_id") or "eleven_v4"
    rate = TTS_USD_PER_1K[model]
    usd = chars / 1000 * rate
    # Tarifa de lista de la API (como elevenlabs_audio.estimate): aproximada, ElevenLabs cobra por su cuenta.
    return {
        "usd": round(usd, 6),
        "kind": "approx",
        "basis": f"{chars} chars × ${rate}/1K · ElevenLabs {model} · local render",
    }


# --- Voz ---------------------------------------------------------------------------------------------------------


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum())


def attach_punctuation(words: list[Word], text: str) -> list[Word]:
    """edge-tts devuelve las palabras sin signos: se recuperan del texto original, en orden."""
    tokens = text.split()
    out: list[Word] = []
    j = 0
    for w in words:
        target = _norm(w.text)
        k = j
        while k < len(tokens) and k < j + 4 and _norm(tokens[k]) != target:
            k += 1
        if k < len(tokens) and _norm(tokens[k]) == target:
            out.append(Word(tokens[k], w.start, w.end))
            j = k + 1
        else:
            out.append(w)
    return out


def words_from_alignment(alignment: dict) -> list[Word]:
    """Palabras con tiempo a partir del alineamiento por carácter de ElevenLabs."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[Word] = []
    cur, t0, t1 = "", 0.0, 0.0
    for c, s, e in zip(chars, starts, ends, strict=False):
        if c.isspace():
            if cur:
                words.append(Word(cur, t0, t1))
            cur = ""
            continue
        if not cur:
            t0 = float(s)
        cur += c
        t1 = float(e)
    if cur:
        words.append(Word(cur, t0, t1))
    return words


EDGE_ATTEMPTS = 3


def spoken_ratio(words: list[Word], text: str) -> float:
    """Qué parte de las palabras del texto llegó con su marca de tiempo (edge-tts a veces corta el audio)."""
    expected = [t for t in (_norm(x) for x in text.split()) if t]
    return min(1.0, len(words) / len(expected)) if expected else 1.0


async def edge_scene(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    """Voz de una escena con edge-tts. Si el servicio corta la respuesta (llegan bastantes menos palabras que las
    del texto), se pide otra vez: un corte deja la escena muda a mitad de frase."""
    words: list[Word] = []
    for _ in range(EDGE_ATTEMPTS):
        words = await _edge_once(text, voice, rate, out)
        if spoken_ratio(words, text) >= 0.85:
            break
        log.warning("edge-tts devolvió %d palabras de %d; se repite", len(words), len(text.split()))
    return words


async def _edge_once(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    comm = edge_tts.Communicate(text, voice, rate=rate or "+0%", boundary="WordBoundary")
    words: list[Word] = []
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
    return attach_punctuation(words, text)


async def eleven_scene(eleven, text: str, voice: dict, language: str, out: Path) -> list[Word]:
    voice_id = await eleven.ensure_voice(voice["voice_id"], None)
    body: dict = {"text": text, "model_id": voice.get("model_id") or "eleven_v4"}
    if language and body["model_id"] != "eleven_multilingual_v2":
        body["language_code"] = language[:2]
    data = await eleven.text_to_speech_timestamps(voice_id, body)
    out.write_bytes(base64.b64decode(data.get("audio_base64") or ""))
    return words_from_alignment(data.get("alignment") or data.get("normalized_alignment") or {})


def plan_timeline(durations: list[float]) -> tuple[list[SceneTime], list[float], float]:
    """(tiempos de escena, inicio de la voz de cada una, duración total) a partir de lo que dura cada voz."""
    times, voice_at = [], []
    t = 0.0
    for i, d in enumerate(durations):
        length = LEAD_IN + d + TAIL + (END_HOLD if i == len(durations) - 1 else 0.0)
        times.append(SceneTime(round(t, 3), round(length, 3)))
        voice_at.append(round(t + LEAD_IN, 3))
        t += length
    return times, voice_at, round(t, 3)


# --- Procesos ----------------------------------------------------------------------------------------------------


async def run_proc(
    *args: str, timeout: float, cwd: Path | None = None, env: dict | None = None
) -> tuple[int, str]:
    """Subproceso en su propio grupo: al vencer el plazo o cancelarse se mata entero (npx lanza Chrome)."""
    windows = os.name == "nt"
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if windows else {"start_new_session": True}
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **group,
    )

    def kill() -> None:
        """Mata el árbol entero: en POSIX su grupo de procesos; en Windows con taskkill /T (hijos y nietos)."""
        if windows:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)

    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        kill()
        await proc.wait()
        return 124, "timeout"
    except asyncio.CancelledError:
        kill()
        await proc.wait()
        raise
    return proc.returncode or 0, (out or b"").decode(errors="replace").strip()


class FactoryError(Exception):
    pass


class ContentFactoryJobs(BackgroundProvider):
    """Proveedor interno del worker: voz, composición, render con HyperFrames y mezcla final."""

    name = FACTORY_PROVIDER
    title = "Content Factory (local)"
    blurb = "Faceless shorts rendered locally"
    work_name = "factory-work"

    def __init__(
        self, settings: Settings, eleven=None, transport=None, slots: asyncio.Semaphore | None = None
    ):
        super().__init__(settings, transport)
        self.eleven = eleven
        self.slots = slots or asyncio.Semaphore(1)  # un render a la vez: cada uno ya usa varios Chrome

    def accepts(self, model: str) -> bool:
        return model == FACTORY_MODEL

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        # Absoluta: el render corre con otro `cwd` y `storage_dir` puede ser relativo (data/files por defecto).
        folder = folder.resolve()
        script = Script.model_validate(arguments["script"]).model_dump(exclude_none=True, by_alias=True)
        style = STYLES.get(arguments.get("style") or DEFAULT_STYLE, STYLES[DEFAULT_STYLE])
        voice = arguments["voice"]
        lang = arguments.get("language") or "es"
        aspect = arguments.get("aspect") if arguments.get("aspect") in ASPECTS else "9:16"
        audio = folder / "voice"
        audio.mkdir()
        durations: list[float] = []
        scene_words: list[list[Word]] = []
        for i, scene in enumerate(script["scenes"]):
            mp3 = audio / f"{i:02d}.mp3"
            try:
                if voice.get("engine") == "elevenlabs":
                    if self.eleven is None or not self.eleven.configured:
                        raise FactoryError("Set ELEVENLABS_API_KEY in .env to narrate with ElevenLabs")
                    words = await asyncio.wait_for(
                        eleven_scene(self.eleven, scene["narration"], voice, lang, mp3), TTS_TIMEOUT
                    )
                else:
                    words = await asyncio.wait_for(
                        edge_scene(scene["narration"], voice["voice_id"], voice.get("rate") or "+0%", mp3),
                        TTS_TIMEOUT,
                    )
            except TimeoutError:
                raise FactoryError(f"The voice took too long on scene {i + 1}") from None
            except FactoryError:
                raise
            except Exception as exc:  # noqa: BLE001 (red, voz desconocida o servicio caído: se informa)
                raise FactoryError(
                    f"Could not synthesize scene {i + 1}: {getattr(exc, 'message', None) or exc}"
                ) from None
            secs = await duration(str(mp3))
            if not secs:
                raise FactoryError(f"The voice of scene {i + 1} came back empty")
            durations.append(secs)
            scene_words.append(words)
        times, voice_at, total = plan_timeline(durations)
        words = [
            Word(w.text, w.start + at, w.end + at)
            for ws, at in zip(scene_words, voice_at, strict=True)
            for w in ws
        ]
        voice_track = folder / "voice.wav"
        await self._voice_track(audio, durations, times, voice_track)
        project = folder / "project"
        (project / "fonts").mkdir(parents=True)
        for font in (ASSETS / "fonts").glob("*.woff2"):
            shutil.copyfile(font, project / "fonts" / font.name)
        html = build_composition(script, style, times, words, lang, total, aspect)
        for name in assets_needed(html):  # KaTeX y three.js, solo si alguna escena los usa
            shutil.copytree(ASSETS / "vendor" / name, project / "vendor" / name)
        (project / "index.html").write_text(html, "utf-8")
        silent = folder / "render.mp4"
        async with self.slots:
            await self._render(project, silent, total)
        out = folder / "0-video.mp4"
        code, msg = await run_proc(
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(silent),
            "-i",
            str(voice_track),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-af",
            await self._loudness(voice_track),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{total:.3f}",
            "-movflags",
            "+faststart",
            str(out),
            timeout=300,
        )
        if code != 0 or not out.is_file():
            raise FactoryError(f"Could not mix the voice: {msg[-300:]}")
        for leftover in (audio, project, silent, voice_track):  # solo queda la salida
            if leftover.is_dir():
                shutil.rmtree(leftover, ignore_errors=True)
            else:
                leftover.unlink(missing_ok=True)
        return "video", out.name, "video/mp4"

    async def _loudness(self, track: Path) -> str:
        """loudnorm en dos pasadas: mide la voz y aplica una ganancia lineal exacta (una sola pasada se queda corta
        con tantas pausas). Si la medición falla, se usa la pasada dinámica."""
        _, msg = await run_proc(
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(track),
            "-af",
            f"{LOUDNESS}:print_format=json",
            "-f",
            "null",
            "-",
            timeout=120,
        )
        try:
            data = json.loads(msg[msg.rindex("{") : msg.rindex("}") + 1])
            keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
            if not all(math.isfinite(float(data[k])) for k in keys):
                return "anull"  # silencio: nada que normalizar
            return (
                f"{LOUDNESS}:measured_I={data['input_i']}:measured_TP={data['input_tp']}:"
                f"measured_LRA={data['input_lra']}:measured_thresh={data['input_thresh']}:"
                f"offset={data['target_offset']}:linear=true"
            )
        except (ValueError, KeyError):
            return LOUDNESS

    async def _voice_track(
        self, audio: Path, durations: list[float], times: list[SceneTime], out: Path
    ) -> None:
        """Cada voz con su silencio de entrada y relleno hasta el final de su escena, todas seguidas."""
        inputs: list[str] = []
        parts: list[str] = []
        for i, tm in enumerate(times):
            inputs += ["-i", str(audio / f"{i:02d}.mp3")]
            parts.append(
                f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,adelay={int(LEAD_IN * 1000)}:all=1,"
                f"apad=whole_dur={tm.duration:.3f},atrim=0:{tm.duration:.3f}[a{i}]"
            )
        parts.append(f"{''.join(f'[a{i}]' for i in range(len(times)))}concat=n={len(times)}:v=0:a=1[out]")
        code, msg = await run_proc(
            "ffmpeg",
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(out),
            timeout=300,
        )
        if code != 0 or not out.is_file():
            raise FactoryError(f"Could not join the voice: {msg[-300:]}")

    async def _render(self, project: Path, out: Path, total: float) -> None:
        problem = renderer_problem()
        if problem:
            raise FactoryError(problem)
        env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "CI": "1"}
        timeout = max(RENDER_TIMEOUT_MIN, total * 20)
        code, msg = await run_proc(
            "npx",
            "--yes",
            f"hyperframes@{HYPERFRAMES_VERSION}",
            "render",
            str(project),
            "-o",
            str(out),
            "--fps",
            str(FPS),
            "--quality",
            "looks",
            "--quiet",
            timeout=timeout,
            cwd=project,
            env=env,
        )
        if code != 0 or not out.is_file() or out.stat().st_size == 0:
            tail = "timed out" if msg == "timeout" else msg[-400:]
            raise FactoryError(f"HyperFrames could not render the short: {tail}")
        log.info("Content Factory: render de %.1f s listo", total)


def factory_summary(arguments: dict) -> dict:
    """Datos útiles del pedido para la UI (escenas, caracteres, duración estimada)."""
    script = arguments.get("script") or {}
    scenes = script.get("scenes") or []
    words = sum(len(str(s.get("narration") or "").split()) for s in scenes)
    return {
        "scenes": len(scenes),
        "chars": sum(len(str(s.get("narration") or "")) for s in scenes),
        "approx_seconds": round(words / 2.5 + len(scenes) * (LEAD_IN + TAIL) + END_HOLD),
    }
