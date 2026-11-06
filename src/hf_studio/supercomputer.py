"""Supercomputer: un agente de chat (Claude) que ayuda a aclarar una idea y la convierte en un prompt de
escena elaborado (mundo, personajes, cámara, luz, sonido, tomas con tiempos) para un modelo del catálogo.

Como el SuperComputer de Higgsfield, el LLM conversa y planea, y las herramientas de generación producen el
resultado. Aquí el agente **nunca gasta créditos**: sus herramientas son gratuitas (buscar modelos, leer un
esquema, cotizar) y lo más que hace es dejar una *propuesta* en el chat. Generar es un clic del usuario en esa
propuesta, que pasa por el mismo flujo de cotización y aprobación que el resto del estudio.

El chat sí consume la API de Claude (`ANTHROPIC_API_KEY`): cada vuelta suma su costo real (tokens de
`usage` por la tarifa del modelo) al chat, y el usuario lo ve.

La conversación se guarda en el formato de la API (bloques de pensamiento incluidos) y solo crece por el
final: nada se reescribe, así el prefijo cacheado y los bloques de pensamiento siguen siendo válidos.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .space_assistant import CLAUDE_PRICES, DEFAULT_CLAUDE

MAX_TOKENS = 32000
MAX_ROUNDS = 10  # llamadas a Claude por mensaje del usuario (herramientas incluidas)
MAX_ATTACHMENTS = 6
MODES = ("ask", "auto")
EFFORTS = ("low", "medium", "high")

SYSTEM = """\
You are Supercomputer, the creative director inside HF Studio, a studio that generates video and images with \
many AI models (Seedance, Kling, Veo, Sora-like, Nano Banana, GPT Image, Seedream and more). The person you talk \
to has an idea, often a vague one. Your job is to help them clarify it and turn it into a production-grade \
prompt that gets a great result on the right model.

# How a conversation goes
1. Understand the idea. Each user turn starts with a <studio_mode> tag:
   - `ask`: collaborate before writing. If the request leaves decisions open that change the result (subject, \
setting, mood, action, format, duration, references), ask about them ONE AT A TIME with the `ask_user` tool: \
one short question with 2-4 short options the user can click (put your recommendation first and say so in its \
detail); they can also type their own answer. Never list several questions or numbered options in your text. \
A sentence of context before the question is fine. After `ask_user`, stop: the answer arrives as the next \
message, and then you ask the next question or move on. Ask only what matters (usually 1-3 questions in total); \
if the user says to decide, decide. Do not propose a generation until the open decisions are settled or they \
ask you to go ahead.
     For a video, unless they already attached references or said they don't want any, one of your questions \
is whether to include a character (or product): call `list_elements` first and offer their saved elements by \
name as options, plus "use an image of mine" (attach it or pick it from history) and "a new character you \
describe" or "no character".
   - `auto`: make the creative decisions yourself, tell them in one or two sentences what you chose, and propose \
right away.
2. Pick the model. If the user names a model, put its name in the `find_models` task (for example "gemini \
omni 1.2"): named models come first. Use `find_models` (it returns real prices), then `get_model` to read the exact input schema, \
limits (prompt maxLength, durations, aspect ratios, resolutions, audio support) and notes before writing for it. \
Prefer what the user asked for; otherwise balance quality and price and say why in one line.
3. Propose. Call `propose_generation` with the full prompt and settings. It validates the input against the \
model and quotes the cost. If it returns errors, fix them and call it again. The proposal appears to the user as \
a card with the prompt, the settings and the price, and a Generate button. Do not paste the whole prompt again \
in your text; summarise what it contains in a few lines.
4. Iterate. When the user asks for changes, propose a revised version. Updates about their generations (status, \
output URLs) arrive inside <studio_update> tags; an output URL can be reused as an input (for example the image \
of a character as `image_url` / start frame of a video).

# References
The user can attach images or videos (from their device or their history); each arrives as a line \
"Attached image (name): URL", numbered in the order they come, and you see the images themselves. They are \
references: decide what each one is for (a character or product to keep, the first or last frame, a location, \
a style or palette, a motion or camera to imitate, a clip to edit) and, in `ask` mode, ask when it is not clear. \
Then pick a model that takes that kind of input (capabilities such as image-to-video, first-last-frame, \
reference-to-video, image-references, edit, video-edit, motion-transfer), pass the exact URLs in the matching \
fields of its schema, and refer to them in the prompt by role and order ("the woman from image 1 wears the \
jacket from image 2"). Never invent or alter a URL. The user's saved elements (recurring characters, products \
or places) come from `list_elements`: on Kling 3.0 models put their ids in the `elements` field and cite each \
as @name in the prompt; on other models, describe them instead.

You never generate anything yourself and you never say a generation has started: only the user's click on a \
proposal does that, after they see the price. Never invent model ids, fields or prices: use the tools.

# Writing the prompt
Write model prompts in English (models follow it best) unless the user wants another language; spoken \
dialogue and on-screen text stay in the language the user wants, quoted exactly. Talk to the user in their \
language. Stay within the model's prompt maxLength.

For a video, write it like a director's treatment. A strong scene prompt has:
- Setup / world: where and when, the look of the world (palette with named colours, atmosphere, materials, \
weather, scale), what moves in it. Keep it physically concrete.
- Distinct roles: few characters or objects, each with a recognisable silhouette, wardrobe, materials and a \
clear function in the action. Describe faces when they must read.
- Geography and continuity: screen direction (who moves left-to-right), positions, distances, what stays \
consistent between shots (palette, light sources, hull or costume details).
- Cause and consequence: every beat triggers the next; the action reads as a chain (attack, evade, decide, \
strike), ending on an identifiable outcome.
- Camera: shot size, lens or field of view (for example "wide at 84°", "handheld at 63°"), height, movement and \
what it is relative to, where subjects sit in frame (thirds), the first frame, and how each shot ends (hard \
cut, match cut, whip).
- Light: key sources and their colour, direction and quality, practicals, catchlights, how light changes with \
events.
- Sound: ambience, foley and score tied to on-screen events (engines, breath, impacts), plus dialogue if any. \
Only when the model generates audio.
- Motion cadence: shutter and motion blur, speed cues (what passes the lens, what grows or shrinks).
- Focused constraints: limit the cast and the action so the model can deliver it; say what must not appear if \
it matters.
For clips of 8 s or more with several beats, add a shot list with timings that add up to the duration: \
"Shot 1 · 0.0-3.0s · <shot size and lens>, <camera>. First frame: … Hard cut." Short clips (5 s or less) get a \
single continuous shot. Match the duration the user wants with a duration the model accepts.

For an image: subject and pose, composition and framing, lens and depth of field, light (sources, colour, \
quality), palette, materials and textures, setting, mood, and any text exactly as it must be rendered.

Keep your chat messages short and warm. Use Markdown sparingly (short lists are fine). No emojis.
"""

TOOLS: list[dict] = [
    {
        "name": "find_models",
        "description": (
            "Search the studio catalog for models that fit a task, with the cheapest current price for a standard "
            "setting (5 s, 720p for video). Free. Use the user's goal in plain words, e.g. 'cinematic 15 second "
            "sci-fi video with sound' or 'product photo with text on it'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What to create, in natural language"},
                "output": {"type": "string", "enum": ["video", "image"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_model",
        "description": (
            "Read a model's input schema (fields, enums, defaults, limits such as the prompt maxLength), its notes "
            "and the studio notes. Free. Always call it before proposing a generation on a model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"model_id": {"type": "string"}},
            "required": ["model_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "propose_generation",
        "description": (
            "Show the user a generation proposal card: the model, the exact input (prompt and settings) and the "
            "quoted price, with a Generate button only the user can press. Free: it validates and quotes, it does "
            "not generate. Returns the proposal id and price, or validation errors to fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string"},
                "input": {
                    "type": "object",
                    "description": "Arguments for the model, matching its input_schema (prompt, duration, …)",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the card, in the user's language",
                },
            },
            "required": ["model_id", "input", "title"],
            "additionalProperties": False,
        },
    },
]

TOOLS.append(
    {
        "name": "list_elements",
        "description": (
            "List the user's saved elements: recurring characters, products or places with a name, a description "
            "and reference images. Free. Kling 3.0 models take their ids in the `elements` field and the prompt "
            "cites each as @name."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
)

TOOLS.append(
    {
        "name": "ask_user",
        "description": (
            "Ask the user ONE question with 2-4 clickable options (they can also type something else). The "
            "question appears in the chat and your turn ends; their answer is their next message. Use it for each "
            "open creative decision, one at a time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Short question in the user's language"},
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "What the user clicks (a few words)"},
                            "detail": {"type": "string", "description": "Optional one-line explanation"},
                        },
                        "required": ["label"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["question", "options"],
            "additionalProperties": False,
        },
    }
)

TOOL_LABELS = {
    "ask_user": "asking",
    "find_models": "searching",
    "get_model": "reading",
    "propose_generation": "proposing",
    "list_elements": "reading",
}


@dataclass
class Toolbox:
    """Lo que el agente puede hacer en el estudio; lo implementa la API (catálogo, router, base)."""

    find_models: Callable[[str, str | None, int], Awaitable[dict]]
    get_model: Callable[[str], Awaitable[dict]]
    # Devuelve (resultado para Claude, propuesta para guardar o None si no pasó la validación).
    propose: Callable[[str, dict, str], Awaitable[tuple[dict, dict | None]]]
    list_elements: Callable[[], Awaitable[dict]] | None = None


@dataclass
class Turn:
    """Estado de una vuelta: lo que se añade a la conversación y lo que cuesta."""

    messages: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None


def usage_usd(model: str, usage: Any) -> float:
    """Costo real de una respuesta: entrada, escritura y lectura de caché, y salida (pensamiento incluido)."""
    price_in, price_out = CLAUDE_PRICES.get(model, CLAUDE_PRICES[DEFAULT_CLAUDE])
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return (tokens_in * price_in + written * price_in * 1.25 + read * price_in * 0.1 + out * price_out) / 1e6


def user_content(text: str, mode: str, attachments: list[dict], updates: list[str]) -> list[dict]:
    """Bloques del mensaje del usuario: modo, novedades de sus generaciones, adjuntos (las imágenes también
    como imagen, para que Claude las vea) y el texto."""
    head = f"<studio_mode>{mode}</studio_mode>"
    if updates:
        head += "\n<studio_update>\n" + "\n".join(updates) + "\n</studio_update>"
    blocks: list[dict] = [{"type": "text", "text": head}]
    for a in attachments[:MAX_ATTACHMENTS]:
        kind = (a.get("content_type") or "").split("/")[0] or "file"
        if kind == "image":
            blocks.append({"type": "image", "source": {"type": "url", "url": a["url"]}})
        blocks.append(
            {"type": "text", "text": f"Attached {kind} ({a.get('filename') or 'file'}): {a['url']}"}
        )
    blocks.append({"type": "text", "text": text})
    return blocks


async def run_turn(
    client: anthropic.AsyncAnthropic,
    model: str,
    effort: str,
    history: list[dict],
    tools: Toolbox,
    turn: Turn,
) -> AsyncIterator[dict]:
    """Corre una vuelta del agente sobre `history` (que ya termina en el mensaje del usuario) y emite eventos
    para la UI. Cada respuesta completa de Claude (y los resultados de sus herramientas) se añade a
    `turn.messages`; si algo falla a medias, lo ya añadido forma pares completos y se puede guardar."""
    params: dict = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "tools": TOOLS,
        # Caché automática del último bloque: cada vuelta reutiliza el prefijo de la conversación.
        "cache_control": {"type": "ephemeral"},
    }
    if model != "claude-haiku-4-5":  # Haiku 4.5 no acepta effort ni pensamiento adaptativo
        params["thinking"] = {"type": "adaptive"}
        params["output_config"] = {"effort": effort}
    for _ in range(MAX_ROUNDS):
        async with client.messages.stream(messages=history + turn.messages, **params) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    name = event.content_block.name
                    yield {"type": "tool", "name": name, "label": TOOL_LABELS.get(name, name)}
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield {"type": "text", "text": event.delta.text}
            response = await stream.get_final_message()
        cost = usage_usd(model, response.usage)
        turn.cost_usd += cost
        yield {"type": "usage", "cost_usd": round(turn.cost_usd, 6)}
        content = [block.to_dict() for block in response.content]
        if response.stop_reason == "refusal":
            turn.error = "Claude declined this request"
            return
        uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason == "max_tokens" and uses:
            turn.error = "The answer was cut off; ask again with a shorter request"
            return
        if response.stop_reason == "pause_turn" or not uses:
            turn.messages.append({"role": "assistant", "content": content})
            if response.stop_reason == "pause_turn":
                continue
            return
        results = []
        asked = False
        for use in uses:
            if use.name == "ask_user":
                question, error = parse_question(use.input)
                result = {"error": error} if error else {"shown": True, "note": QUESTION_NOTE}
                proposal = None
                if question:
                    asked = True
                    yield {"type": "question", "question": {**question, "id": use.id}}
            else:
                result, proposal = await call_tool(tools, use.name, use.input)
            if proposal:
                proposal = {**proposal, "tool_use_id": use.id}
                turn.proposals.append(proposal)
                yield {"type": "proposal", "proposal": proposal}
            results.append({
                "type": "tool_result", "tool_use_id": use.id, "content": json.dumps(result, ensure_ascii=False),
                **({"is_error": True} if "error" in result or "errors" in result else {}),
            })  # fmt: skip
        # La llamada y sus resultados entran juntos: una conversación guardada nunca deja un tool_use sin
        # respuesta (la API rechazaría la siguiente vuelta).
        turn.messages.append({"role": "assistant", "content": content})
        turn.messages.append({"role": "user", "content": results})
        if asked:  # la pregunta queda en pantalla: la vuelta termina hasta que el usuario responda
            return
    turn.error = "Stopped after too many steps; send another message to continue"


QUESTION_NOTE = "Shown to the user with clickable options. Stop now; their answer is their next message."


def parse_question(args: Any) -> tuple[dict | None, str | None]:
    """Pregunta de `ask_user` validada: texto y de 2 a 4 opciones con etiqueta (y detalle opcional)."""
    if (
        not isinstance(args, dict)
        or not isinstance(args.get("question"), str)
        or not args["question"].strip()
    ):
        return None, "`question` is required"
    options = []
    for o in args.get("options") or []:
        label = o.get("label") if isinstance(o, dict) else o
        if isinstance(label, str) and label.strip():
            detail = o.get("detail") if isinstance(o, dict) and isinstance(o.get("detail"), str) else None
            options.append(
                {"label": label.strip()[:80], **({"detail": detail.strip()[:200]} if detail else {})}
            )
    if not 2 <= len(options) <= 4:
        return None, "Give 2 to 4 options, each with a `label`"
    return {"question": args["question"].strip()[:300], "options": options}, None


def with_user_turn(messages: list[dict], user_msg: dict) -> list[dict]:
    """Añade el mensaje del usuario. Si el chat termina en los resultados de una vuelta que paró en una
    pregunta (`ask_user`), van en el mismo mensaje: la API no admite dos mensajes de usuario seguidos."""
    if messages and messages[-1]["role"] == "user":
        return [*messages[:-1], {"role": "user", "content": [*messages[-1]["content"], *user_msg["content"]]}]
    return [*messages, user_msg]


async def call_tool(tools: Toolbox, name: str, args: Any) -> tuple[dict, dict | None]:
    """Ejecuta una herramienta con entrada validada a mano: un error vuelve a Claude como resultado."""
    if not isinstance(args, dict):
        return {"error": "Invalid tool input"}, None
    try:
        if name == "find_models":
            task = args.get("task")
            if not isinstance(task, str) or not task.strip():
                return {"error": "`task` is required"}, None
            output = args.get("output") if args.get("output") in ("video", "image") else None
            limit = args.get("limit") if isinstance(args.get("limit"), int) else 5
            return await tools.find_models(task[:500], output, max(1, min(limit, 8))), None
        if name == "get_model":
            if not isinstance(args.get("model_id"), str):
                return {"error": "`model_id` is required"}, None
            return await tools.get_model(args["model_id"]), None
        if name == "propose_generation":
            model_id, arguments, title = args.get("model_id"), args.get("input"), args.get("title")
            if not isinstance(model_id, str) or not isinstance(arguments, dict):
                return {"error": "`model_id` and `input` are required"}, None
            return await tools.propose(model_id, arguments, str(title or "")[:120])
        if name == "list_elements":
            if tools.list_elements is None:
                return {"elements": []}, None
            return await tools.list_elements(), None
    except Exception as exc:  # noqa: BLE001 - el agente ve el error y decide
        return {"error": str(exc)[:500]}, None
    return {"error": f"Unknown tool {name}"}, None


def sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


def chat_title(text: str) -> str:
    words = " ".join(text.split())
    return (words[:60] + "…") if len(words) > 60 else (words or "New chat")


def visible_messages(messages: list[dict], proposals: dict[str, dict]) -> list[dict]:
    """La conversación como la ve la UI: mensajes del usuario (texto y adjuntos) y del agente (texto y
    propuestas), sin pensamiento, llamadas internas ni resultados de herramientas."""
    out: list[dict] = []
    for msg in messages:
        content = msg["content"]
        if msg["role"] == "user":
            if all(b.get("type") == "tool_result" for b in content):
                continue
            texts = [b["text"] for b in content if b.get("type") == "text"]
            attachments = [
                t.split(": ", 1)[1] for t in texts[1:-1] if t.startswith("Attached ") and ": " in t
            ]  # fmt: skip
            out.append({"role": "user", "text": texts[-1] if texts else "", "attachments": attachments})
            continue
        parts = []
        for b in content:
            if b.get("type") == "text" and b.get("text", "").strip():
                parts.append({"type": "text", "text": b["text"]})
            elif (
                b.get("type") == "tool_use" and b.get("name") == "propose_generation" and b["id"] in proposals
            ):
                parts.append({"type": "proposal", "proposal": proposals[b["id"]]})
            elif b.get("type") == "tool_use" and b.get("name") == "ask_user":
                question, _ = parse_question(b.get("input"))
                if question:
                    parts.append({"type": "question", "question": {**question, "id": b["id"]}})
        if not parts:
            continue
        if out and out[-1]["role"] == "assistant":  # varias rondas de una vuelta: un solo mensaje
            out[-1]["parts"].extend(parts)
        else:
            out.append({"role": "assistant", "parts": parts})
    return out
