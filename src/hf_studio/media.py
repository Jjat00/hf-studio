"""Comprobaciones de medios contra SSRF (revisión 28 de Codex).

Un archivo «propio» no hace confiable su contenido: un manifiesto DASH/HLS subido como `video/mp4` hace que
ffprobe abra las URLs que trae dentro. Por eso las subidas se validan por su firma real y la duración se
mide sobre una copia local, sin red y solo con demuxers de contenedores de video.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx

from .audio import _run

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


def matches_type(data: bytes, content_type: str) -> bool:
    check = _SIGNATURES.get(content_type)
    return bool(check and check(data[:16]))


async def local_duration(
    url: str, client: httpx.AsyncClient, max_bytes: int, ffprobe: str = "ffprobe"
) -> float | None:
    """Descarga `url` (HTTPS, sin seguir redirecciones, con tope de tamaño) y mide su duración en local."""
    if not url.startswith("https://"):
        return None
    with tempfile.TemporaryDirectory(prefix="hfs-probe-") as tmp:
        path = Path(tmp) / "media"
        size = 0
        try:
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.status_code != 200:
                    return None
                with path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            return None
                        fh.write(chunk)
        except httpx.HTTPError:
            return None
        with path.open("rb") as fh:
            head = fh.read(16)
        if not matches_type(head, "video/mp4") and head[:4] != b"\x1a\x45\xdf\xa3":
            return None  # ni MP4/MOV ni Matroska/WebM
        code, out = await _run(
            ffprobe, "-v", "error", "-protocol_whitelist", "file", "-format_whitelist", VIDEO_FORMATS,
            "-show_entries", "format=duration", "-of", "csv=p=0", str(path),
        )  # fmt: skip
    try:
        return float(out) if code == 0 else None
    except ValueError:
        return None
