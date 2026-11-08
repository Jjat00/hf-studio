"""Katana, paso 1: leer un video de referencia (un «edit») cuadro a cuadro sin gastar nada.

Katana rehace un edit ajeno con el sujeto del usuario: no copia sus tomas, toma su lenguaje (ritmo de cortes,
destellos, sacudidas, movimientos de cámara, golpes de la música, tipografía). Para eso primero hay que medir la
referencia. Todo aquí es local y determinista (ffmpeg + numpy):

- `probe`: tamaño, fps racional, cuadros, duración y si trae audio.
- Señales por cuadro (a 96 px de ancho, en gris): luminancia media, diferencia con el cuadro anterior,
  histograma (cortes) y desplazamiento global por correlación de fase (cámara y sacudida).
- `energy`: cortes, destellos (picos breves de luz), ráfagas de sacudida, movimientos de cámara y golpes de
  audio (flujo espectral), con sus tasas por segundo y un tempo estimado.
- Hojas de contacto: páginas JPG con cuadros numerados y su tiempo, para que el planificador las vea.

El resultado (`analysis.json`) lo consumen `katana_plan` (Claude con visión) y el compositor (`katana_edit`), que
reproduce la energía de la referencia sobre las tomas nuevas.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from .audio import PROBE_GUARD, guarded

SIG_W = 96  # ancho de las señales por cuadro (alto proporcional, par)
AUDIO_SR = 22050
HOP = 512  # ~23 ms por ventana de audio
MAX_SECONDS = 180.0  # un edit dura segundos, no minutos
SHEET_COLS, SHEET_ROWS = 4, 4
SHEET_TILE_W = 320
SHEET_FPS_DEFAULT = 4.0  # cuadros por segundo en las hojas (los edits rápidos piden más)
MAX_SHEETS = 24

# Umbrales (medidos sobre señales a 96 px; ajustables con pruebas).
CUT_HIST = 0.42  # distancia chi² normalizada del histograma entre cuadros vecinos
CUT_DIFF = 0.14  # diferencia media absoluta (0..1) que también exige el corte
FLASH_JUMP = 0.16  # subida de luminancia sobre la mediana local (0..1)
FLASH_MAX_FRAMES = 4  # un destello dura pocos cuadros; más es un cambio de plano
SHAKE_JITTER_PX = 1.6  # jitter (px a 96 de ancho) tras quitar el movimiento suave
CAMERA_SPEED = 0.35  # px/cuadro sostenido (a 96 de ancho) para contar un movimiento de cámara
CAMERA_MIN_S = 0.4
HIT_Z = 2.2  # golpe de audio: flujo espectral sobre media + z·desviación


class AnalysisError(Exception):
    pass


@dataclass
class Probe:
    width: int
    height: int
    fps: str  # racional, p. ej. "30000/1001"
    fps_float: float
    frames: int
    duration: float
    has_audio: bool
    rotation: int = 0


@dataclass
class Event:
    t: float
    kind: str
    strength: float
    end: float | None = None
    data: dict[str, Any] = field(default_factory=dict)


async def _exec(*args: str, timeout: float = 300.0, stdin: bytes | None = None) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out, err


async def probe(path: str, ffprobe: str = "ffprobe") -> Probe:
    code, out, err = await _exec(
        ffprobe, "-v", "error", *PROBE_GUARD, "-show_streams", "-show_format", "-of", "json", path, timeout=60
    )
    if code != 0:
        raise AnalysisError(f"ffprobe could not read the reference: {err.decode(errors='replace')[-300:]}")
    data = json.loads(out or b"{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise AnalysisError("The reference has no video stream")
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    try:
        fps = Fraction(rate)
        if fps <= 0:
            raise ZeroDivisionError
    except (ValueError, ZeroDivisionError):
        fps = Fraction(30)
    dur = float(video.get("duration") or (data.get("format") or {}).get("duration") or 0)
    if dur <= 0:
        raise AnalysisError("Could not measure the reference duration")
    if dur > MAX_SECONDS:
        raise AnalysisError(f"The reference lasts {dur:.0f} s; Katana reads edits up to {MAX_SECONDS:.0f} s")
    rotation = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"]) % 360
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if rotation in (90, 270):
        w, h = h, w
    frames = int(video.get("nb_frames") or 0) or round(dur * float(fps))
    return Probe(
        width=w,
        height=h,
        fps=f"{fps.numerator}/{fps.denominator}",
        fps_float=float(fps),
        frames=frames,
        duration=round(dur, 3),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        rotation=rotation,
    )


def _sig_size(p: Probe) -> tuple[int, int]:
    h = max(2, round(SIG_W * p.height / max(1, p.width) / 2) * 2)
    return SIG_W, h


async def decode_gray(path: str, p: Probe, ffmpeg: str = "ffmpeg") -> np.ndarray:
    """Todos los cuadros (a su fps nativo, sin saltarse ninguno) en gris a 96 px: array (n, h, w) en 0..1."""
    w, h = _sig_size(p)
    code, out, err = await _exec(
        ffmpeg, "-v", "error", *guarded(path), "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area,format=gray",
        "-vsync", "passthrough", "-f", "rawvideo", "-",
        timeout=600,
    )  # fmt: skip
    if code != 0:
        raise AnalysisError(f"ffmpeg could not decode the reference: {err.decode(errors='replace')[-300:]}")
    n = len(out) // (w * h)
    if n < 2:
        raise AnalysisError("The reference has too few frames")
    return np.frombuffer(out[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32) / 255.0


async def decode_audio(path: str, ffmpeg: str = "ffmpeg") -> np.ndarray | None:
    code, out, _ = await _exec(
        ffmpeg, "-v", "error", *guarded(path), "-map", "0:a:0", "-ac", "1", "-ar", str(AUDIO_SR),
        "-f", "f32le", "-",
        timeout=300,
    )  # fmt: skip
    if code != 0 or len(out) < AUDIO_SR * 4 // 2:
        return None
    return np.frombuffer(out, dtype=np.float32).copy()


# ---------------------------------------------------------------- señales de video


def _phase_shift(a: np.ndarray, b: np.ndarray, win: np.ndarray) -> tuple[float, float, float]:
    """Desplazamiento (dx, dy) de b respecto de a por correlación de fase, y la nitidez del pico (confianza)."""
    fa = np.fft.fft2((a - a.mean()) * win)
    fb = np.fft.fft2((b - b.mean()) * win)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    c = np.fft.ifft2(r).real
    iy, ix = np.unravel_index(int(np.argmax(c)), c.shape)
    peak = float(c[iy, ix])
    h, w = c.shape

    def sub(cm: float, c0: float, cp: float) -> float:  # refinamiento parabólico
        d = cm - 2 * c0 + cp
        return 0.0 if abs(d) < 1e-12 else 0.5 * (cm - cp) / d

    dx = ix + sub(c[iy, (ix - 1) % w], c[iy, ix], c[iy, (ix + 1) % w])
    dy = iy + sub(c[(iy - 1) % h, ix], c[iy, ix], c[(iy + 1) % h, ix])
    if dx > w / 2:
        dx -= w
    if dy > h / 2:
        dy -= h
    return -float(dx), -float(dy), peak


def frame_signals(frames: np.ndarray) -> dict[str, np.ndarray]:
    n, h, w = frames.shape
    luma = frames.mean(axis=(1, 2))
    diff = np.zeros(n, np.float32)
    diff[1:] = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2))
    bins = 32
    hists = np.stack([np.histogram(f, bins=bins, range=(0, 1))[0] for f in frames]).astype(np.float32)
    hists /= hists.sum(axis=1, keepdims=True) + 1e-9
    hdist = np.zeros(n, np.float32)
    num = (hists[1:] - hists[:-1]) ** 2
    den = hists[1:] + hists[:-1] + 1e-9
    hdist[1:] = 0.5 * (num / den).sum(axis=1)
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    dx = np.zeros(n, np.float32)
    dy = np.zeros(n, np.float32)
    conf = np.zeros(n, np.float32)
    for i in range(1, n):
        dx[i], dy[i], conf[i] = _phase_shift(frames[i - 1], frames[i], win)
    sharp = np.zeros(n, np.float32)  # nitidez (laplaciano): baja en desenfoques de movimiento y fundidos
    lap = np.abs(
        frames[:, 1:-1, 1:-1] * 4
        - frames[:, :-2, 1:-1]
        - frames[:, 2:, 1:-1]
        - frames[:, 1:-1, :-2]
        - frames[:, 1:-1, 2:]
    )
    sharp[:] = lap.mean(axis=(1, 2))
    return {
        "luma": luma,
        "diff": diff,
        "hist": hdist,
        "hists": hists,
        "dx": dx,
        "dy": dy,
        "conf": conf,
        "sharp": sharp,
    }


def _median_filter(x: np.ndarray, k: int) -> np.ndarray:
    k = max(1, k | 1)
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.array([np.median(xp[i : i + k]) for i in range(len(x))], dtype=np.float32)


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    k = max(1, k)
    if k == 1:
        return x.astype(np.float32)
    ker = np.ones(k, np.float32) / k
    return np.convolve(np.pad(x, (k // 2, k - 1 - k // 2), mode="edge"), ker, mode="valid")


def _chi2(h: np.ndarray, a: int, b: int) -> float:
    return float(0.5 * (((h[a] - h[b]) ** 2) / (h[a] + h[b] + 1e-9)).sum())


def detect_cuts(sig: dict[str, np.ndarray], fps: float) -> list[int]:
    """Índices de cuadro donde empieza un plano nuevo (sin contar el 0). Exige histograma y diferencia; un
    destello (la imagen vuelve a la de antes en pocos cuadros) no es corte, ni a la ida ni a la vuelta."""
    hist, diff, hists = sig["hist"], sig["diff"], sig["hists"]
    n = len(hist)
    cand = {i for i in range(1, n) if hist[i] > CUT_HIST and diff[i] > CUT_DIFF}
    # Umbral adaptativo para edits de cortes suaves: picos muy por encima de su entorno.
    local = _median_filter(diff, max(5, int(fps)))
    cand |= {i for i in range(1, n) if diff[i] > max(0.07, local[i] * 4) and hist[i] > CUT_HIST * 0.6}
    flash: set[int] = set()
    for i in sorted(cand):
        if i in flash:
            continue
        for k in range(1, FLASH_MAX_FRAMES + 1):
            j = i + k
            if j >= n:
                break
            # vuelve a la imagen previa: los cuadros i..j-1 son un inserto breve (destello) del mismo plano
            if (
                _chi2(hists, i - 1, j) < CUT_HIST * 0.35
                and float(np.abs(sig["luma"][j] - sig["luma"][i - 1])) < 0.08
            ):
                flash.update(range(i, j + 1))
                break
    return sorted(cand - flash)


def detect_flashes(sig: dict[str, np.ndarray], fps: float, cuts: list[int]) -> list[Event]:
    luma = sig["luma"]
    base = _median_filter(luma, max(7, int(fps * 0.5)))
    over = luma - base
    events: list[Event] = []
    i, n = 0, len(luma)
    while i < n:
        if over[i] > FLASH_JUMP:
            j = i
            while j + 1 < n and over[j + 1] > FLASH_JUMP * 0.5:
                j += 1
            if j - i + 1 <= FLASH_MAX_FRAMES:
                peak = int(i + np.argmax(over[i : j + 1]))
                events.append(
                    Event(t=i / fps, end=(j + 1) / fps, kind="flash", strength=round(float(over[peak]), 3),
                          data={"frames": j - i + 1, "white": bool(luma[peak] > 0.8), "on_cut": any(abs(c - i) <= 1 for c in cuts)})
                )  # fmt: skip
            i = j + 1
        else:
            i += 1
    return events


def _segments(cuts: list[int], n: int) -> list[tuple[int, int]]:
    bounds = [0, *[c for c in cuts if 0 < c < n], n]
    return [(a, b) for a, b in itertools.pairwise(bounds) if b > a]


def detect_motion(sig: dict[str, np.ndarray], fps: float, cuts: list[int]) -> tuple[list[Event], list[Event]]:
    """Ráfagas de sacudida (jitter alto) y movimientos de cámara (deriva sostenida), dentro de cada plano."""
    dx, dy, conf = sig["dx"].copy(), sig["dy"].copy(), sig["conf"]
    n = len(dx)
    for c in cuts:  # el salto de un corte no es movimiento
        dx[c] = dy[c] = 0.0
    shakes: list[Event] = []
    moves: list[Event] = []
    k = max(3, round(fps / 4))
    for a, b in _segments(cuts, n):
        if b - a < 4:
            continue
        sx, sy = _smooth(dx[a:b], k), _smooth(dy[a:b], k)
        jit = np.hypot(dx[a:b] - sx, dy[a:b] - sy)
        jit[conf[a:b] < 0.02] = 0
        # sacudida: ventanas de ~1/4 s con jitter medio alto
        i = 0
        L = b - a
        while i < L:
            if jit[i] > SHAKE_JITTER_PX:
                j = i
                quiet = 0
                while j + 1 < L and quiet < k:
                    j += 1
                    quiet = quiet + 1 if jit[j] <= SHAKE_JITTER_PX else 0
                j -= quiet
                if j - i + 1 >= max(2, k // 2):
                    seg = jit[i : j + 1]
                    shakes.append(
                        Event(t=(a + i) / fps, end=(a + j + 1) / fps, kind="shake",
                              strength=round(float(seg.mean()) / SIG_W, 4),
                              data={"amplitude_frac": round(float(seg.max()) / SIG_W, 4)})
                    )  # fmt: skip
                i = j + 1
            else:
                i += 1
        # movimiento de cámara: velocidad suavizada sostenida
        speed = np.hypot(sx, sy)
        i = 0
        while i < L:
            if speed[i] > CAMERA_SPEED:
                j = i
                while j + 1 < L and speed[j + 1] > CAMERA_SPEED * 0.6:
                    j += 1
                if (j - i + 1) / fps >= CAMERA_MIN_S:
                    mx, my = float(sx[i : j + 1].sum()), float(sy[i : j + 1].sum())
                    direction = (
                        ("right" if mx > 0 else "left")
                        if abs(mx) >= abs(my)
                        else ("down" if my > 0 else "up")
                    )
                    moves.append(
                        Event(t=(a + i) / fps, end=(a + j + 1) / fps, kind="camera_move",
                              strength=round(float(speed[i : j + 1].mean()) / SIG_W * fps, 4),
                              data={"direction": f"pan_{direction}", "travel_frac": round(math.hypot(mx, my) / SIG_W, 3)})
                    )  # fmt: skip
                i = j + 1
            else:
                i += 1
    return shakes, moves


# ---------------------------------------------------------------- audio


def onset_envelope(y: np.ndarray) -> np.ndarray:
    nfft = 2048
    if len(y) < nfft:
        return np.zeros(1, np.float32)
    frames = 1 + (len(y) - nfft) // HOP
    idx = np.arange(nfft)[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(y[idx] * np.hanning(nfft)[None, :], axis=1))
    logs = np.log1p(spec * 10)
    flux = np.zeros(frames, np.float32)
    flux[1:] = np.maximum(0, logs[1:] - logs[:-1]).sum(axis=1)
    return flux


def estimate_tempo(env: np.ndarray) -> tuple[float | None, float]:
    """BPM por autocorrelación del flujo (60–200) y la fase del primer pulso (s)."""
    if len(env) < 64:
        return None, 0.0
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1 :]
    fr = AUDIO_SR / HOP
    lo, hi = int(fr * 60 / 200), int(fr * 60 / 60)
    if hi >= len(ac) or lo < 1:
        return None, 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    if ac[lag] <= 0:
        return None, 0.0
    bpm = 60 * fr / lag
    while bpm < 80:
        bpm *= 2
    while bpm > 170:
        bpm /= 2
    period = fr * 60 / bpm
    step = max(1, round(period))
    phases = [env[p::step].sum() for p in range(step)]
    phase = float(np.argmax(phases)) / fr
    return round(float(bpm), 1), round(phase, 3)


def detect_hits(env: np.ndarray) -> list[Event]:
    if len(env) < 8:
        return []
    fr = AUDIO_SR / HOP
    local = _smooth(env, int(fr))  # media en ~1 s
    sd = float(env.std()) + 1e-9
    out: list[Event] = []
    last = -1.0
    for i in range(1, len(env) - 1):
        if env[i] >= env[i - 1] and env[i] >= env[i + 1] and env[i] > local[i] + HIT_Z * sd:
            t = i / fr
            if t - last >= 0.12:
                out.append(
                    Event(t=round(t, 3), kind="hit", strength=round(float((env[i] - local[i]) / sd), 2))
                )
                last = t
    return out


# ---------------------------------------------------------------- energía y resumen


def _rate(events: list[Any], dur: float) -> float:
    return round(len(events) / dur, 3) if dur > 0 else 0.0


def energy(p: Probe, sig: dict[str, np.ndarray], audio: np.ndarray | None) -> dict[str, Any]:
    fps = p.fps_float
    n = len(sig["luma"])
    dur = n / fps
    cuts = detect_cuts(sig, fps)
    flashes = detect_flashes(sig, fps, cuts)
    shakes, moves = detect_motion(sig, fps, cuts)
    hits: list[Event] = []
    bpm, phase = None, 0.0
    if audio is not None:
        env = onset_envelope(audio)
        hits = detect_hits(env)
        bpm, phase = estimate_tempo(env)
    segs = _segments(cuts, n)
    shot_lengths = [(b - a) / fps for a, b in segs]
    cut_times = [round(c / fps, 3) for c in cuts]
    # cortes sobre golpes: qué tan pegado a la música está el montaje
    on_beat = 0
    if hits and cut_times:
        ht = np.array([h.t for h in hits])
        on_beat = sum(1 for c in cut_times if np.min(np.abs(ht - c)) <= 0.07)
    # curva de energía por segundo (0..1): cortes, destellos, sacudida y movimiento
    secs = max(1, math.ceil(dur))
    curve = []
    for s in range(secs):
        a, b = int(s * fps), min(n, int((s + 1) * fps))
        motion = float(np.hypot(sig["dx"][a:b], sig["dy"][a:b]).mean()) if b > a else 0.0
        c = sum(1 for t in cut_times if s <= t < s + 1)
        f = sum(1 for e in flashes if s <= e.t < s + 1)
        k = sum(1 for e in shakes if e.t < s + 1 and (e.end or e.t) > s)
        curve.append(round(min(1.0, 0.18 * c + 0.25 * f + 0.25 * k + motion / 6), 3))
    return {
        "duration": round(dur, 3),
        "frames": n,
        "cuts": cut_times,
        "shots": [
            {"index": i, "start": round(a / fps, 3), "end": round(b / fps, 3), "frames": b - a}
            for i, (a, b) in enumerate(segs)
        ],
        "flashes": [asdict(e) for e in flashes],
        "shakes": [asdict(e) for e in shakes],
        "camera_moves": [asdict(e) for e in moves],
        "hits": [asdict(e) for e in hits],
        "tempo_bpm": bpm,
        "beat_phase": phase,
        "rates": {
            "cuts_per_s": _rate(cut_times, dur),
            "flashes_per_s": _rate(flashes, dur),
            "shakes_per_s": _rate(shakes, dur),
            "camera_moves_per_s": _rate(moves, dur),
            "hits_per_s": _rate(hits, dur),
            "mean_shot_s": round(float(np.mean(shot_lengths)), 3) if shot_lengths else dur,
            "median_shot_s": round(float(np.median(shot_lengths)), 3) if shot_lengths else dur,
            "cuts_on_hits": round(on_beat / len(cut_times), 3) if cut_times else 0.0,
        },
        "curve": curve,
        "luma_mean": round(float(sig["luma"].mean()), 3),
    }


def sheet_fps(rates: dict[str, Any]) -> float:
    """Más cuadros por segundo en las hojas cuanto más rápido corta la referencia (máx. 8)."""
    cps = rates.get("cuts_per_s") or 0
    return float(min(8.0, max(SHEET_FPS_DEFAULT, round(cps * 2))))


async def contact_sheets(
    path: str, p: Probe, out_dir: Path, fps: float, ffmpeg: str = "ffmpeg"
) -> list[dict]:
    """Páginas 4×4 de cuadros tomados a `fps`, cada uno con su tiempo impreso. Si salen más de MAX_SHEETS
    páginas, baja el fps para cubrir toda la referencia igual (la cobertura no se recorta)."""
    per = SHEET_COLS * SHEET_ROWS
    while fps > 1 and math.ceil(p.duration * fps / per) > MAX_SHEETS:
        fps /= 2
    out_dir.mkdir(parents=True, exist_ok=True)
    tile_h = max(2, round(SHEET_TILE_W * p.height / max(1, p.width) / 2) * 2)
    vf = (
        f"fps={fps},scale={SHEET_TILE_W}:{tile_h}:flags=bicubic,"
        "drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4,"
        f"tile={SHEET_COLS}x{SHEET_ROWS}:padding=4:margin=4:color=0x111111"
    )
    code, _, err = await _exec(
        ffmpeg, "-v", "error", "-y", *guarded(path), "-map", "0:v:0", "-vf", vf, "-q:v", "4",
        str(out_dir / "sheet-%03d.jpg"),
        timeout=600,
    )  # fmt: skip
    if code != 0:
        raise AnalysisError(
            f"ffmpeg could not draw the contact sheets: {err.decode(errors='replace')[-300:]}"
        )
    pages = sorted(out_dir.glob("sheet-*.jpg"))
    span = per / fps
    return [
        {
            "file": f.name,
            "start": round(i * span, 3),
            "end": round(min(p.duration, (i + 1) * span), 3),
            "fps": fps,
        }
        for i, f in enumerate(pages)
    ]


async def keyframes(
    path: str, times: list[float], out_dir: Path, ffmpeg: str = "ffmpeg", side: int = 768
) -> list[str]:
    """Un JPG por tiempo pedido (lado mayor `side`), para usar como fotograma de estilo o de lugar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for i, t in enumerate(times):
        name = f"key-{i:03d}.jpg"
        code, _, _ = await _exec(
            ffmpeg, "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", *guarded(path), "-frames:v", "1",
            "-vf", f"scale='if(gt(iw,ih),{side},-2)':'if(gt(iw,ih),-2,{side})'", "-q:v", "3", str(out_dir / name),
            timeout=60,
        )  # fmt: skip
        if code == 0 and (out_dir / name).exists():
            names.append(name)
    return names


async def extract_audio(path: str, dest: Path, ffmpeg: str = "ffmpeg") -> bool:
    code, _, _ = await _exec(
        ffmpeg, "-v", "error", "-y", *guarded(path), "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        str(dest),
        timeout=120,
    )  # fmt: skip
    return code == 0 and dest.exists()


async def analyze(
    path: str, out_dir: Path, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"
) -> dict[str, Any]:
    """Lee la referencia completa y escribe `analysis.json`, las hojas de contacto, un fotograma por plano y
    el audio (si lo trae) en `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = await probe(path, ffprobe)
    frames = await decode_gray(path, p, ffmpeg)
    sig = await asyncio.to_thread(frame_signals, frames)
    del frames
    audio = await decode_audio(path, ffmpeg) if p.has_audio else None
    en = await asyncio.to_thread(energy, p, sig, audio)
    sheets = await contact_sheets(path, p, out_dir / "sheets", sheet_fps(en["rates"]), ffmpeg)
    mids = [round((s["start"] + s["end"]) / 2, 3) for s in en["shots"]][:60]
    keys = await keyframes(path, mids, out_dir / "shots", ffmpeg)
    has_track = await extract_audio(path, out_dir / "music.wav", ffmpeg) if p.has_audio else False
    result = {
        "version": 1,
        "probe": asdict(p),
        "aspect": aspect_of(p.width, p.height),
        "energy": en,
        "sheets": sheets,
        "shot_frames": [{"shot": i, "t": mids[i], "file": k} for i, k in enumerate(keys)],
        "music": "music.wav" if has_track else None,
    }
    (out_dir / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return result


ASPECTS = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "21:9": 21 / 9}


def aspect_of(w: int, h: int) -> str:
    r = w / max(1, h)
    return min(ASPECTS, key=lambda k: abs(math.log(ASPECTS[k] / r)))
