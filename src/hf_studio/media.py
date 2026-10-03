"""Comprobaciones de medios contra SSRF (revisión 28 de Codex).

Un archivo «propio» no hace confiable su contenido: un manifiesto DASH/HLS subido como `video/mp4` hace que
ffprobe abra las URLs que trae dentro. Por eso las subidas se validan por su firma real y la duración se
mide sobre una copia local, sin red y solo con demuxers de contenedores de video.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import httpx

from .audio import PROBE_GUARD, _run

# Firma (magic bytes) de cada tipo de subida admitido.
_SIGNATURES = {
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/gif": lambda b: b.startswith((b"GIF87a", b"GIF89a")),
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
    "audio/wav": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WAVE",
    "audio/x-wav": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WAVE",
    "video/mp4": lambda b: b[4:8] == b"ftyp",
}
# Demuxers de contenedor: nada de dash, hls, concat, image2… que abren otros archivos o URLs.
VIDEO_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm"


def is_media_container(head: bytes) -> bool:
    """Firma de un contenedor de audio o video que ffmpeg puede leer sin abrir nada más."""
    return (
        head[4:8] == b"ftyp"  # MP4, MOV, M4A
        or head[:4] == b"\x1a\x45\xdf\xa3"  # Matroska, WebM
        or (head[:4] == b"RIFF" and head[8:12] == b"WAVE")
        or head[:3] == b"ID3"
        or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)  # MP3 / AAC ADTS
        or head[:4] in (b"OggS", b"fLaC")
    )


async def _download(url: str, client: httpx.AsyncClient, max_bytes: int, dest: Path) -> bool:
    """Descarga controlada: solo HTTPS, sin seguir redirecciones, con tope de tamaño."""
    if not url.startswith("https://"):
        return False
    size = 0
    try:
        async with client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                return False
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        return False
                    fh.write(chunk)
    except httpx.HTTPError:
        return False
    return size > 0


async def cached_source(url: str, storage: Path, client: httpx.AsyncClient, max_bytes: int) -> str | None:
    """Copia local de un medio remoto propio (una sola descarga por URL) para dárselo a ffmpeg. None si no se
    pudo descargar o no es un contenedor de audio o video. Las rutas locales se devuelven tal cual."""
    if "://" not in url:
        return url
    folder = Path(storage) / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / hashlib.sha256(url.encode()).hexdigest()
    if path.is_file():
        return str(path)
    tmp = path.with_suffix(".part")
    try:
        if not await _download(url, client, max_bytes, tmp):
            return None
        with tmp.open("rb") as fh:
            if not is_media_container(fh.read(16)):
                return None
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return str(path)


def matches_type(data: bytes, content_type: str) -> bool:
    check = _SIGNATURES.get(content_type)
    return bool(check and check(data[:16]))


async def local_duration(
    url: str, client: httpx.AsyncClient, max_bytes: int, ffprobe: str = "ffprobe"
) -> float | None:
    """Descarga `url` (HTTPS, sin seguir redirecciones, con tope de tamaño) y mide su duración en local."""
    with tempfile.TemporaryDirectory(prefix="hfs-probe-") as tmp:
        path = Path(tmp) / "media"
        if not await _download(url, client, max_bytes, path):
            return None
        with path.open("rb") as fh:
            head = fh.read(16)
        if not matches_type(head, "video/mp4") and head[:4] != b"\x1a\x45\xdf\xa3":
            return None  # ni MP4/MOV ni Matroska/WebM
        code, out = await _run(
            ffprobe, "-v", "error", *PROBE_GUARD, "-show_entries", "format=duration", "-of", "csv=p=0", str(path),
        )  # fmt: skip
    try:
        return float(out) if code == 0 else None
    except ValueError:
        return None
