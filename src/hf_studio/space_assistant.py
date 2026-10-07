"""Nodo Assistant de Spaces (fase 3d): un LLM (Claude) que escribe o mejora prompts, describe imágenes o
redacta guiones, y entrega texto que alimenta el puerto de prompt de otros nodos.

Como las herramientas y el audio, es un modelo del catálogo (`claude/assistant`) que corre un proveedor interno
del worker (`AnthropicJobs`, con el SDK oficial `anthropic`). Es opcional: necesita `ANTHROPIC_API_KEY`.
El precio se cotiza con una cota superior: un token nunca ocupa menos de un byte, así que la entrada no pasa de
los bytes UTF-8 del texto más un margen fijo por la estructura del mensaje y uno generoso por imagen; la salida
no pasa de `MAX_TOKENS` (incluye el razonamiento). Todo a la tarifa de API del modelo elegido, sin respaldo a
otro modelo ni reintentos automáticos: lo que se aprueba es lo único que se envía (revisión 69).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic

from .config import Settings
from .space_tools import ASSISTANT_PROVIDER, BackgroundProvider

ASSISTANT_MODEL = "claude/assistant"
MAX_TOKENS = 6000
MAX_IMAGES = 4
# USD por millón de tokens (entrada, salida), tarifa de API a 2026-09.
CLAUDE_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DEFAULT_CLAUDE = "claude-opus-5-5"
IMAGE_TOKENS = 5000  # cota por imagen de entrada (las imágenes grandes se reducen antes de contarse)
MESSAGE_OVERHEAD_TOKENS = 200  # roles, separadores y bloque de sistema

ASSISTANT_NODE = {
    "id": ASSISTANT_MODEL,
    "title": "Assistant — Text with Claude API",
    "summary": "Writes or improves prompts, describes images and drafts scripts; its text feeds other nodes.",
    "workflow": "Text with Claude",
    "family": "Claude",
    "output": "text",
    "capabilities": ["studio-assistant"],
    "notes": ["Runs on the Claude API with your ANTHROPIC_API_KEY (optional)."],
    "docs_url": "https://platform.claude.com/docs",
    "input_schema": {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 20000, "title": "Instructions"},
            "image_urls": {
                "type": "array",
                "items": {"type": "string", "format": "uri"},
                "maxItems": MAX_IMAGES,
            },
            "system": {"type": "string", "maxLength": 4000, "title": "System prompt"},
            "model_id": {"type": "string", "enum": list(CLAUDE_PRICES), "default": DEFAULT_CLAUDE},
            "effort": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
        },
    },
}


def is_assistant(model_id: str | None) -> bool:
    return model_id == ASSISTANT_MODEL


def assistant_quote(arguments: dict) -> dict:
    """Cota superior del costo: entrada estimada + el tope de salida, a la tarifa del modelo elegido."""
    model = arguments.get("model_id") or DEFAULT_CLAUDE
    price_in, price_out = CLAUDE_PRICES[model]
    text = (arguments.get("prompt") or "") + (arguments.get("system") or "")
    images = len((arguments.get("image_urls") or [])[:MAX_IMAGES])
    tokens_in = len(text.encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS + IMAGE_TOKENS * images
    usd = (tokens_in * price_in + MAX_TOKENS * price_out) / 1_000_000
    return {
        "usd": round(usd, 6),
        "kind": "approx",
        "basis": f"Up to ~{tokens_in} input + {MAX_TOKENS} output tokens · Claude API {model} (upper bound)",
    }


class AnthropicJobs(BackgroundProvider):
    """Proveedor interno del worker para el nodo Assistant: una llamada a la API de Claude, salida en texto."""

    name = ASSISTANT_PROVIDER
    title = "Claude (Assistant)"
    blurb = "Prompts, descriptions and scripts"
    work_name = "assistant-work"

    def __init__(self, settings: Settings, transport=None, slots: asyncio.Semaphore | None = None):
        super().__init__(settings, transport)
        self.slots = slots or asyncio.Semaphore(2)
        # Cliente HTTP del SDK (httpx2): None en producción; los tests ponen uno con transporte simulado.
        self.http_client_factory: Callable[[], Any] | None = None

    @property
    def api_key(self) -> str:
        return self.settings.secret("ANTHROPIC_API_KEY").strip()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def accepts(self, model: str) -> bool:
        return model == ASSISTANT_MODEL

    async def produce(self, folder: Path, model: str, arguments: dict) -> tuple[str, str, str]:
        claude = arguments.get("model_id") or DEFAULT_CLAUDE
        content: list[dict] = [
            {"type": "image", "source": {"type": "url", "url": url}}
            for url in (arguments.get("image_urls") or [])[:MAX_IMAGES]
        ]
        content.append({"type": "text", "text": arguments["prompt"]})
        params: dict = {
            "model": claude,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": content}],
        }
        if arguments.get("system"):
            params["system"] = arguments["system"]
        if claude != "claude-haiku-4-5":  # Haiku 4.5 no acepta effort
            params["output_config"] = {"effort": arguments.get("effort") or "medium"}
        # Sin reintentos del SDK: un error ambiguo (respuesta perdida) no reenvía una petición pagada fuera del
        # presupuesto aprobado; el paso falla visible y el usuario decide (revisión 69).
        client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            max_retries=0,
            base_url=self.settings.secret("ANTHROPIC_BASE_URL") or None,
            http_client=self.http_client_factory() if self.http_client_factory else None,
        )
        try:
            async with self.slots:
                response = await client.messages.create(**params)
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"Claude API error {exc.status_code}: {exc.message}") from None
        except anthropic.APIConnectionError:
            raise RuntimeError("Could not reach the Claude API") from None
        finally:
            await client.close()
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise RuntimeError(f"Claude declined this request ({category or 'policy'})")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise RuntimeError("Claude returned no text")
        out = folder / "0-text.txt"
        out.write_text(text, encoding="utf-8")
        return "text", out.name, "text/plain"
