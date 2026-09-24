"""Servidor MCP (stdio) que expone HF Studio a Claude Code, Codex y otros agentes.

Es un cliente delgado de la API REST: no conoce las credenciales de Higgsfield, solo
HF_STUDIO_URL y HF_STUDIO_TOKEN (una clave `hfs_…` creada con `hf-studio create-key`).
"""

from __future__ import annotations

import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

INSTRUCTIONS = """Genera imágenes y videos con los modelos de Higgsfield a través de HF Studio.
Flujo: 1) find_models por capacidad (text-to-video, image-to-video, first-last-frame, video-input,
reference-to-video, image-references, video-edit, video-extend, motion-transfer, text-to-image);
2) get_model para leer input_schema y notes; 3) upload_media si la entrada es un archivo local;
4) opcional estimate_cost; 5) generate; 6) get_generation con wait_seconds hasta terminal=true;
7) download_outputs. La generación es asíncrona y cobra créditos: ANTES de cada generate llama a
estimate_cost y dile al usuario el costo (kind exact = créditos y USD; approx = USD aproximado;
formula/unavailable = falta subir medios o pasar hints.input_video_seconds). No repitas generate
tras un error ambiguo, consulta list_generations primero. Reutiliza idempotency_key al reintentar."""

mcp = MCPServer("hf-studio", instructions=INSTRUCTIONS)


def _client() -> httpx.Client:
    token = os.environ.get("HF_STUDIO_TOKEN")
    if not token:
        raise ToolError("Falta HF_STUDIO_TOKEN en el entorno del servidor MCP")
    base = os.environ.get("HF_STUDIO_URL", "http://127.0.0.1:8787")
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=150)


def _call(method: str, path: str, **kwargs: Any) -> Any:
    try:
        with _client() as http:
            response = http.request(method, path, **kwargs)
    except httpx.TransportError as exc:
        raise ToolError(f"HF Studio no responde ({exc}); ¿está corriendo `hf-studio serve`?") from exc
    if response.is_success:
        return response.json()
    try:
        error = response.json().get("error") or response.json()
    except ValueError:
        error = response.text
    raise ToolError(f"HTTP {response.status_code}: {error}")


@mcp.tool()
def find_models(capability: str | None = None, output: str | None = None, query: str | None = None) -> dict:
    """Busca modelos. capability: text-to-video, image-to-video, first-last-frame, video-input,
    reference-to-video, image-references, audio-input, video-edit, video-extend, motion-transfer,
    object-swap, text-to-image, edit. output: video | image. query: texto en id/título (p. ej. seedance)."""
    params = {k: v for k, v in {"capability": capability, "output": output, "q": query}.items() if v}
    return _call("GET", "/v1/models", params=params)


@mcp.tool()
def get_model(model_id: str) -> dict:
    """Esquema de entrada (JSON Schema), notas de uso y docs de un modelo, p. ej.
    bytedance/seedance-2.0/image-to-video. Léelo antes de generar."""
    return _call("GET", f"/v1/models/{model_id}")


@mcp.tool()
def upload_media(path: str) -> dict:
    """Sube una imagen (jpg/png/webp/gif), video mp4 o audio wav local y devuelve una URL pública
    para usar en campos *_url / *_urls del modelo."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise ToolError(f"No existe el archivo {file}")
    content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    with file.open("rb") as fh:
        return _call("POST", "/v1/uploads", files={"file": (file.name, fh, content_type)})


@mcp.tool()
def estimate_cost(model_id: str, input: dict, input_video_seconds: float | None = None) -> dict:
    """Costo de una generación sin ejecutarla. Funciona aunque falten los medios. Si el modelo cobra
    por segundos de video de entrada, pasa input_video_seconds (duración del video que subirás)."""
    hints = {"input_video_seconds": input_video_seconds} if input_video_seconds else {}
    return _call("POST", "/v1/estimate", json={"model": model_id, "input": input, "hints": hints})


@mcp.tool()
def generate(
    model_id: str, input: dict, idempotency_key: str | None = None, allow_duplicate: bool = False
) -> dict:
    """Encola una generación y devuelve el trabajo (id, status). No espera: usa get_generation.
    Si reintentas tras un fallo de red, pasa la misma idempotency_key para no duplicar el cobro."""
    headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
    body = {"model": model_id, "input": input, "allow_duplicate": allow_duplicate}
    return _call("POST", "/v1/generations", json=body, headers=headers)


@mcp.tool()
def get_generation(generation_id: str, wait_seconds: int = 50) -> dict:
    """Estado de una generación. Espera hasta wait_seconds (máx. 120) a que sea terminal.
    Los videos suelen tardar de 1 a 10 minutos: repite la llamada mientras terminal sea false."""
    wait = max(0, min(wait_seconds, 120))
    return _call("GET", f"/v1/generations/{generation_id}", params={"wait": wait})


@mcp.tool()
def list_generations(status: str | None = None, limit: int = 20) -> dict:
    """Lista tus generaciones recientes (status: pending, queued, in_progress, completed, failed…)."""
    params = {"limit": limit, **({"status": status} if status else {})}
    return _call("GET", "/v1/generations", params=params)


@mcp.tool()
def cancel_generation(generation_id: str) -> dict:
    """Cancela una generación que aún no empezó (pending o queued). Lo cancelado se reembolsa."""
    return _call("POST", f"/v1/generations/{generation_id}/cancel")


@mcp.tool()
def download_outputs(generation_id: str, dest_dir: str = ".") -> dict:
    """Descarga las salidas de una generación completada a dest_dir y devuelve las rutas locales."""
    job = _call("GET", f"/v1/generations/{generation_id}")
    if job["status"] != "completed":
        raise ToolError(f"La generación está en {job['status']}, no en completed")
    dest = Path(dest_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    with _client() as http:
        for i, out in enumerate(job["outputs"]):
            # Preferir la copia propia (no caduca); si no existe, la URL de Higgsfield (≥ 7 días).
            if out.get("file_url"):
                response = http.get(out["file_url"])
            else:
                response = httpx.get(out["url"], timeout=150, follow_redirects=True)
            response.raise_for_status()
            suffix = Path(out.get("file_url") or out["url"]).suffix.split("?")[0] or ".bin"
            target = dest / f"{generation_id[:8]}-{i}-{out['kind']}{suffix}"
            target.write_bytes(response.content)
            saved.append(str(target.resolve()))
    base = os.environ.get("HF_STUDIO_URL", "http://127.0.0.1:8787")
    return {
        "files": saved,
        "remote": [urljoin(base, o["file_url"]) if o.get("file_url") else o["url"] for o in job["outputs"]],
    }


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
