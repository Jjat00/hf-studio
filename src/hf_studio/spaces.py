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

NODE_TYPES = ("text", "media", "generator", "note", "list")
LIST_KINDS = ("text", "image", "video", "audio")
MAX_LIST_ITEMS = 20  # el lote del nodo usa /v1/generations/batch (máx. 20 ítems)
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
    type: Literal["text", "media", "generator", "note", "list"]
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


MAX_FLOW_INPUTS = 10
FLOW_INPUT_TYPES = ("text", "media", "list")


def check_flow(raw: Any, graph: dict) -> dict:
    """Space publicado como flujo: título, descripción y qué nodos (texto, medio o lista) son sus entradas,
    con la etiqueta que ve quien lo corre. Lanza GraphError si no vale."""
    if not isinstance(raw, dict):
        raise GraphError("A flow is an object with title, description and inputs")
    title = raw.get("title")
    if not isinstance(title, str) or not 0 < len(title.strip()) <= 120:
        raise GraphError("A flow needs a title (up to 120 characters)")
    description = raw.get("description") or ""
    if not isinstance(description, str) or len(description) > 1000:
        raise GraphError("The flow description has at most 1000 characters")
    nodes = {n["id"]: n for n in graph["nodes"]}
    inputs, seen = [], set()
    for item in raw.get("inputs") or []:
        node_id = item.get("node_id") if isinstance(item, dict) else None
        label = item.get("label") if isinstance(item, dict) else None
        if node_id not in nodes or nodes[node_id]["type"] not in FLOW_INPUT_TYPES or node_id in seen:
            raise GraphError("Flow inputs are distinct text, media or list nodes of the space")
        if not isinstance(label, str) or not 0 < len(label.strip()) <= 80:
            raise GraphError("Every flow input needs a label (up to 80 characters)")
        seen.add(node_id)
        inputs.append({"node_id": node_id, "label": label.strip()})
    if not inputs or len(inputs) > MAX_FLOW_INPUTS:
        raise GraphError(f"A flow has between 1 and {MAX_FLOW_INPUTS} inputs")
    return {"title": title.strip(), "description": description.strip(), "inputs": inputs}


def flow_for_graph(flow: dict | None, graph: dict) -> dict | None:
    """El flujo tras cambiar el grafo: se quitan las entradas cuyos nodos ya no existen (o cambiaron de tipo);
    sin entradas deja de estar publicado."""
    if not flow:
        return None
    nodes = {n["id"]: n for n in graph["nodes"]}
    inputs = [
        i for i in flow["inputs"] if i["node_id"] in nodes and nodes[i["node_id"]]["type"] in FLOW_INPUT_TYPES
    ]
    return {**flow, "inputs": inputs} if inputs else None


def apply_inputs(graph: dict, flow: dict, values: dict) -> dict:
    """Copia del grafo con los valores de las entradas del flujo: el texto de un nodo Texto, la URL de un Medio
    o los elementos de una Lista. Solo se tocan las entradas publicadas."""
    allowed = {i["node_id"] for i in flow["inputs"]}
    unknown = set(values) - allowed
    if unknown:
        raise GraphError(f"Not inputs of this flow: {', '.join(sorted(unknown))}")
    out = json.loads(json.dumps(graph))
    for node in out["nodes"]:
        if node["id"] not in values:
            continue
        value = values[node["id"]]
        if node["type"] == "text":
            if not isinstance(value, str):
                raise GraphError(f"Input {node['id']} is a text")
            node["data"] = {**node["data"], "text": value}
        elif node["type"] == "media":
            if not isinstance(value, str) or not value:
                raise GraphError(f"Input {node['id']} is a file URL (from upload_media or use_output)")
            node["data"] = {**node["data"], "url": value}
        else:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise GraphError(f"Input {node['id']} is a list of strings")
            items = [{"id": f"in{k}", "value": v, "checked": True} for k, v in enumerate(value)]
            node["data"] = {**node["data"], "items": items}
    return out


def empty_graph() -> dict:
    return Graph().model_dump()


def _optional_str(node: Node, data: dict, key: str, limit: int) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise GraphError(f"Node {node.id}: {key} must be a string of at most {limit} characters")
    return value


def _normalize_list(node: Node, data: dict) -> dict:
    """Lista de un tipo (texto o medios) para lotes: cada elemento marcado es una corrida del generador."""
    kind = data.get("kind", "text")
    if kind not in LIST_KINDS:
        raise GraphError(f"Node {node.id}: kind must be one of {', '.join(LIST_KINDS)}")
    items = data.get("items", [])
    if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
        raise GraphError(f"Node {node.id}: a list holds at most {MAX_LIST_ITEMS} items")
    out = []
    limit = 20000 if kind == "text" else 2048
    for item in items:
        if not isinstance(item, dict):
            raise GraphError(f"Node {node.id}: invalid list item")
        item_id, value = item.get("id"), item.get("value", "")
        if not isinstance(item_id, str) or not 0 < len(item_id) <= 64:
            raise GraphError(f"Node {node.id}: every list item needs an id")
        if not isinstance(value, str) or len(value) > limit:
            raise GraphError(f"Node {node.id}: list values are strings of at most {limit} characters")
        out.append({"id": item_id, "value": value, "checked": item.get("checked", True) is not False})
    return {"kind": kind, "items": out}


def _normalize_data(node: Node) -> dict:
    """`data` con solo los campos que usa la UI, por tipo de nodo y con sus valores por defecto escritos:
    lo que la API acepta siempre se puede abrir en el lienzo (revisión 51)."""
    data = node.data
    if node.type in ("text", "note"):
        return {"text": _optional_str(node, data, "text", 20000) or ""}
    if node.type == "list":
        return _normalize_list(node, data)
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
