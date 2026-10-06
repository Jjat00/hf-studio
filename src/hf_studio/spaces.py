"""Spaces: lienzo de nodos para generar por pasos.

Un Space guarda un grafo `{nodes, edges, viewport}`. Los nodos son pasos (texto, medio, generador, nota); las
aristas llevan la salida de un nodo a un campo de entrada de otro (`targetHandle` = clave del `input_schema`).
Generar sigue pasando por `/v1/estimate` y `/v1/generations`: cada nodo generador guarda los ids de sus
trabajos en `data.runs`. Aquí solo se valida y normaliza el grafo para que lo que se guarda sea coherente
(ids únicos, aristas entre nodos existentes, sin ciclos) y no crezca sin límite.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

NODE_TYPES = ("text", "media", "generator", "note")
MEDIA_KINDS = ("image", "video", "audio")
MAX_NODES = 300
MAX_EDGES = 1000
MAX_RUNS = 200
MAX_GRAPH_BYTES = 512 * 1024
ID = r"^[A-Za-z0-9_.:-]{1,64}$"


class GraphError(ValueError):
    """Grafo inválido: el mensaje dice qué falla (se devuelve como 422)."""


class Position(BaseModel):
    x: float
    y: float


class Node(BaseModel):
    model_config = ConfigDict(extra="ignore")  # React Flow añade estado de vista (selected, measured…)

    id: str = Field(pattern=ID)
    type: Literal["text", "media", "generator", "note"]
    position: Position
    data: dict[str, Any] = Field(default_factory=dict)
    width: float | None = None
    height: float | None = None


class Edge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=ID)
    source: str = Field(pattern=ID)
    target: str = Field(pattern=ID)
    sourceHandle: str | None = Field(None, max_length=64)
    targetHandle: str = Field(pattern=r"^[a-z0-9_]{1,64}$")


class Viewport(BaseModel):
    x: float = 0
    y: float = 0
    zoom: float = Field(1, gt=0, le=10)


class Graph(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: list[Node] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[Edge] = Field(default_factory=list, max_length=MAX_EDGES)
    viewport: Viewport = Field(default_factory=Viewport)


def input_kinds(schema: dict) -> list[str]:
    """Tipos que acepta un modelo por sus puertos (mismo criterio que `web/src/lib/schema.ts`): el prompt es
    texto y los campos `*_url(s)` son imagen, video o audio según su nombre."""
    kinds: set[str] = set()
    for key, prop in (schema.get("properties") or {}).items():
        if key == "prompt" and prop.get("type") in ("string", ["string", "null"]):
            kinds.add("text")
        elif key.endswith(("_url", "_urls")) or key == "input_images":
            if key.startswith("video"):
                kinds.add("video")
            elif key.startswith("audio"):
                kinds.add("audio")
            elif "image" in key or "frame" in key:
                kinds.add("image")
    return sorted(kinds)


def check_values(graph: dict, schemas: dict[str, dict]) -> dict:
    """Ajustes de cada generador contra el esquema de su modelo (`schemas`: id → input_schema). Cada valor
    debe cumplir el esquema de su campo, porque el inspector lo pinta con un control de ese tipo (revisión
    52); las claves que el modelo no tiene se descartan. No exige los obligatorios: un nodo a medio
    configurar es válido. Un modelo que ya no está en el catálogo conserva sus valores tal cual."""
    for node in graph["nodes"]:
        if node["type"] != "generator" or node["data"]["model"] not in schemas:
            continue
        root = schemas[node["data"]["model"]]
        props = root.get("properties") or {}
        # El campo se valida con las definiciones del esquema completo: sus `$ref` apuntan a `#/$defs/…`
        # de la raíz (revisión 53).
        shared = {k: root[k] for k in ("$defs", "definitions") if k in root}
        kept = {}
        for key, value in node["data"]["values"].items():
            if key not in props or value is None:
                continue
            if not Draft202012Validator({**props[key], **shared}).is_valid(value):
                raise GraphError(f"Node {node['id']}: invalid value for {key}")
            kept[key] = value
        node["data"]["values"] = kept
    return graph


def empty_graph() -> dict:
    return Graph().model_dump()


def _optional_str(node: Node, data: dict, key: str, limit: int) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise GraphError(f"Node {node.id}: {key} must be a string of at most {limit} characters")
    return value


def _normalize_data(node: Node) -> dict:
    """`data` con solo los campos que usa la UI, por tipo de nodo y con sus valores por defecto escritos:
    lo que la API acepta siempre se puede abrir en el lienzo (revisión 51)."""
    data = node.data
    if node.type in ("text", "note"):
        return {"text": _optional_str(node, data, "text", 20000) or ""}
    if node.type == "media":
        kind = data.get("kind")
        if kind is not None and kind not in MEDIA_KINDS:
            raise GraphError(f"Node {node.id}: kind must be one of {', '.join(MEDIA_KINDS)}")
        out = {
            "url": _optional_str(node, data, "url", 2048),
            "kind": kind,
            "name": _optional_str(node, data, "name", 200),
        }
        return {k: v for k, v in out.items() if v is not None}
    model = data.get("model")
    if not isinstance(model, str) or not model or len(model) > 200:
        raise GraphError(f"Node {node.id}: a generator needs a model")
    values = data.get("values", {})
    if not isinstance(values, dict):
        raise GraphError(f"Node {node.id}: values must be an object")
    runs = data.get("runs", [])
    if not isinstance(runs, list) or not all(isinstance(r, str) and 0 < len(r) <= 64 for r in runs):
        raise GraphError(f"Node {node.id}: runs must be a list of generation ids")
    if len(runs) > MAX_RUNS:
        raise GraphError(f"Node {node.id}: at most {MAX_RUNS} runs per node")
    out = {"model": model, "values": values, "runs": runs}
    selected = data.get("selected")
    if selected is not None:
        if (
            isinstance(selected, bool)
            or not isinstance(selected, int)
            or not 0 <= selected < max(len(runs), 1)
        ):
            raise GraphError(f"Node {node.id}: selected must be the index of one of its runs")
        out["selected"] = selected
    return out


def _check_acyclic(nodes: list[Node], edges: list[Edge]) -> None:
    """Kahn: si quedan nodos sin procesar, hay un ciclo (un paso dependería de sí mismo)."""
    incoming = {n.id: 0 for n in nodes}
    out: dict[str, list[str]] = {n.id: [] for n in nodes}
    for e in edges:
        incoming[e.target] += 1
        out[e.source].append(e.target)
    ready = [n for n, c in incoming.items() if c == 0]
    seen = 0
    while ready:
        current = ready.pop()
        seen += 1
        for nxt in out[current]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                ready.append(nxt)
    if seen != len(nodes):
        raise GraphError("Connections cannot form a loop")


def check_graph(raw: Any) -> dict:
    """Valida y normaliza un grafo. Devuelve solo los campos conocidos; lanza GraphError si no vale."""
    try:
        graph = Graph.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = "/".join(str(p) for p in first["loc"])
        raise GraphError(f"Invalid graph at {where}: {first['msg']}") from None
    ids = [n.id for n in graph.nodes]
    if len(set(ids)) != len(ids):
        raise GraphError("Node ids must be unique")
    known = set(ids)
    edge_ids: set[str] = set()
    for e in graph.edges:
        if e.id in edge_ids:
            raise GraphError("Connection ids must be unique")
        edge_ids.add(e.id)
        if e.source not in known or e.target not in known:
            raise GraphError(f"Connection {e.id} points to a node that does not exist")
        if e.source == e.target:
            raise GraphError("A node cannot be connected to itself")
    for node in graph.nodes:
        node.data = _normalize_data(node)
    _check_acyclic(graph.nodes, graph.edges)
    clean = graph.model_dump(exclude_none=True)
    if len(json.dumps(clean, separators=(",", ":"))) > MAX_GRAPH_BYTES:
        raise GraphError(f"The space is too large (max {MAX_GRAPH_BYTES // 1024} KB)")
    return clean
