"""Corridas de Spaces en el servidor: un nodo y lo que depende de él, o todo el lienzo.

El navegador ya genera un nodo suelto (Run Node, fase 1). Aquí vive lo que necesita seguir aunque se cierre
la pestaña: elegir qué generadores corren y en qué orden, resolver la entrada de cada uno con lo que
produjeron sus pasos previos, y enviarlo solo si cabe en el tope aprobado. Si un paso cuesta más de lo que
queda o no tiene precio, la corrida se pausa hasta que el usuario lo apruebe.

La resolución de entradas sigue las mismas reglas que `web/src/components/spaces/space-editor.tsx`
(`resolve`): el prompt une los textos conectados y el propio del nodo; cada campo de medios recibe el medio
del nodo de origen o la salida de su generación; un campo simple toma una sola conexión.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .db import TERMINAL, ApiClient, Job, SpaceRun, utcnow
from .providers.base import ProviderError
from .service import ServiceError
from .spaces import DERIVED_OUTPUTS

log = logging.getLogger("hf_studio.space_runs")

RUN_MODES = ("downstream", "workflow")
ACTIVE_RUN = ("running", "awaiting_approval")
NODE_DONE = ("done", "failed", "skipped", "canceled")
TICK_SECONDS = 2.0
COST_TOLERANCE_USD = 1e-9


class NodeInputError(Exception):
    """La entrada de un nodo no se puede armar (falta conectar algo, un paso previo no terminó…)."""


# Fallos de un paso que quedan en el nodo (la corrida sigue con las ramas que no dependen de él).
STEP_ERRORS = (NodeInputError, ServiceError, ProviderError)


@dataclass(frozen=True)
class Port:
    key: str
    kind: str  # text, image, video o audio
    multiple: bool
    max: int
    required: bool


def _type_of(schema: dict) -> str | None:
    t = schema.get("type")
    if isinstance(t, list):
        return next((x for x in t if x != "null"), None)
    return t


def _media_kind(key: str) -> str | None:
    if not (key.endswith(("_url", "_urls")) or key == "input_images"):
        return None
    if key.startswith("video"):
        return "video"
    if key.startswith("audio"):
        return "audio"
    if "image" in key or "frame" in key:
        return "image"
    return None


def ports(schema: dict) -> list[Port]:
    """Puertos de entrada de un modelo (mismo criterio que `web/src/lib/spaces.ts`, `inPorts`)."""
    required = set(schema.get("required") or [])
    out: list[Port] = []
    for key, prop in (schema.get("properties") or {}).items():
        t = _type_of(prop)
        if key == "prompt" and t == "string":
            out.append(Port(key, "text", True, 8, key in required))
            continue
        kind = _media_kind(key)
        if kind:
            multiple = t == "array"
            out.append(
                Port(key, kind, multiple, (prop.get("maxItems") or 4) if multiple else 1, key in required)
            )
    return out


def out_kind(
    node: dict | None, output_of: Callable[[str], str | None], handle: str | None = None
) -> str | None:
    """Tipo que sale de un nodo por `handle`: la salida principal, o una derivada de un video (último
    fotograma o audio)."""
    if not node:
        return None
    if handle in DERIVED_OUTPUTS:
        base = out_kind(node, output_of) if node["type"] == "generator" else None
        return DERIVED_OUTPUTS[handle] if base == "video" else None
    if node["type"] == "text":
        return "text"
    if node["type"] in ("media", "list"):
        return node["data"].get("kind")
    if node["type"] == "generator":
        o = output_of(node["data"]["model"])
        return o if o in ("image", "video", "audio", "text") else None
    return None


def selected_run(data: dict) -> str | None:
    runs = data.get("runs") or []
    if not runs:
        return None
    i = data.get("selected", len(runs) - 1)
    return runs[min(max(i, 0), len(runs) - 1)]


def topo_order(graph: dict) -> list[str]:
    """Ids en orden topológico; entre los listos a la vez manda el orden de los nodos en el lienzo (el grafo
    ya se validó sin ciclos)."""
    ids = [n["id"] for n in graph["nodes"]]
    rank = {i: k for k, i in enumerate(ids)}
    incoming = {i: 0 for i in ids}
    out: dict[str, list[str]] = {i: [] for i in ids}
    for e in graph["edges"]:
        incoming[e["target"]] += 1
        out[e["source"]].append(e["target"])
    ready = [rank[i] for i in ids if incoming[i] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        current = ids[heapq.heappop(ready)]
        order.append(current)
        for nxt in out[current]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                heapq.heappush(ready, rank[nxt])
    return order


def run_scope(graph: dict, mode: str, start: str | None) -> list[str]:
    """Generadores que corren, en orden: todos (`workflow`) o el inicial y los que dependen de él."""
    kinds = {n["id"]: n["type"] for n in graph["nodes"]}
    order = [i for i in topo_order(graph) if kinds[i] == "generator"]
    if mode == "workflow":
        return order
    if start not in kinds or kinds[start] != "generator":
        raise NodeInputError("Start the run from a generation node")
    reach = {start}
    changed = True
    while changed:
        changed = False
        for e in graph["edges"]:
            if e["source"] in reach and e["target"] not in reach:
                reach.add(e["target"])
                changed = True
    return [i for i in order if i in reach]


def upstream(graph: dict, node_id: str) -> list[str]:
    return [e["source"] for e in graph["edges"] if e["target"] == node_id]


def list_values(node: dict) -> list[str]:
    """Elementos marcados (y no vacíos) de un nodo Lista, en su orden."""
    return [i["value"] for i in node["data"].get("items", []) if i.get("checked", True) and i.get("value")]


def split_step(step: str) -> tuple[str, int | None]:
    """`nodo#3` → (nodo, 3); un paso sin lote es el propio nodo. Los ids de nodo no pueden tener «#»."""
    if "#" in step:
        node, item = step.rsplit("#", 1)
        return node, int(item)
    return step, None


def run_steps(graph: dict, mode: str, start: str | None, output_of: Callable[[str], str | None]) -> list[str]:
    """Pasos de una corrida, en orden. Un generador conectado a una Lista corre una vez por elemento marcado
    (`nodo#0`, `nodo#1`…) y su lote se propaga en pares por la cadena: 5 prompts → 5 imágenes → 5 videos. Un
    generador con variantes (`count`) hace lo mismo con su propia entrada repetida."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    scope = run_scope(graph, mode, start)
    # Un nodo en lote lleva índice aunque su lote tenga un solo elemento: así resuelve el valor de la Lista
    # igual que con varios (revisión 69).
    fan: dict[str, int] = {}
    for node_id in scope:
        sizes = set()
        count = nodes[node_id]["data"].get("count") or 1
        for src in upstream(graph, node_id):
            if nodes[src]["type"] == "list":
                values = list_values(nodes[src])
                if not values:
                    raise NodeInputError(f"The list connected to {node_id} has no checked items")
                sizes.add(len(values))
            elif src in fan:
                sizes.add(fan[src])
        if len(sizes) > 1:
            raise NodeInputError(f"The batches connected to {node_id} have different sizes")
        if count > 1 and sizes:
            raise NodeInputError(f"{node_id} already runs once per item of a batch: set its variants to 1")
        if sizes:
            fan[node_id] = sizes.pop()
        elif count > 1:
            fan[node_id] = count
    steps: list[str] = []
    for node_id in scope:
        steps += [f"{node_id}#{i}" for i in range(fan[node_id])] if node_id in fan else [node_id]
    return steps


def step_deps(graph: dict, steps: Iterable[str], step: str) -> list[str]:
    """Pasos de la corrida de los que depende un paso: el mismo elemento si el origen va en lote."""
    known = set(steps)
    node_id, item = split_step(step)
    deps = []
    for src in upstream(graph, node_id):
        if item is not None and f"{src}#{item}" in known:
            deps.append(f"{src}#{item}")
        elif src in known:
            deps.append(src)
    return deps


async def resolve_input(
    graph: dict,
    node_id: str,
    schema: dict,
    output_of: Callable[[str], str | None],
    source_job: Callable[[str], str | None],
    output_url: Callable[[str, str | None], Awaitable[str]],
    item: int | None = None,
    output_text: Callable[[str], Awaitable[str]] | None = None,
) -> dict:
    """Entrada final de un generador: sus ajustes más lo que traen sus conexiones.

    `source_job(id)` dice qué generación usar de un generador de origen (la de esta corrida o la elegida en el
    lienzo) y `output_url(job_id, derive)` da la URL vigente de su salida, o de su último fotograma o su audio
    según el `sourceHandle` de la arista; lanza NodeInputError si aún no terminó."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    node = nodes[node_id]
    values = {k: v for k, v in (node["data"].get("values") or {}).items() if v not in (None, "", [])}
    by_port: dict[str, list[dict]] = {}
    for e in graph["edges"]:
        if e["target"] == node_id:
            by_port.setdefault(e["targetHandle"], []).append(e)
    for port in ports(schema):
        edges = [e for e in by_port.get(port.key, []) if e["source"] in nodes]
        sources = [nodes[e["source"]] for e in edges]
        if not sources:
            continue
        # Mismas reglas que el navegador: un tipo que no encaja es un error (no se ignora) y un campo simple
        # toma la primera conexión (revisión 55).
        if any(out_kind(nodes[e["source"]], output_of, e.get("sourceHandle")) != port.kind for e in edges):
            raise NodeInputError(f"A connection to {port.key} does not carry {port.kind}")

        def from_list(src: dict) -> str:
            values = list_values(src)
            if item is None or item >= len(values):
                raise NodeInputError(f"The list {src['id']} feeds a batch: run it from the node or as a run")
            return values[item]

        if port.kind == "text":
            texts = []
            for src in sources:
                if src["type"] == "generator":  # el texto que escribió un Assistant
                    job_id = source_job(src["id"])
                    if not job_id or output_text is None:
                        raise NodeInputError(f"Generate the connected step ({src['id']}) first")
                    texts.append((await output_text(job_id)).strip())
                elif src["type"] in ("text", "list"):
                    texts.append(
                        (from_list(src) if src["type"] == "list" else src["data"].get("text", "")).strip()
                    )
            own = values.get(port.key).strip() if isinstance(values.get(port.key), str) else ""
            joined = "\n\n".join(t for t in [*texts, own] if t)
            if joined:
                values[port.key] = joined
            else:
                values.pop(port.key, None)
            continue
        urls: list[str] = []
        for edge in edges if port.multiple else edges[:1]:
            src = nodes[edge["source"]]
            if src["type"] == "list":
                urls.append(from_list(src))
            elif src["type"] == "media":
                if not src["data"].get("url"):
                    raise NodeInputError(f"A connected media node ({src['id']}) has no file")
                urls.append(src["data"]["url"])
            else:
                job_id = source_job(src["id"])
                if not job_id:
                    raise NodeInputError(f"Generate the connected step ({src['id']}) first")
                handle = edge.get("sourceHandle")
                urls.append(await output_url(job_id, handle if handle in DERIVED_OUTPUTS else None))
        values[port.key] = urls[: port.max] if port.multiple else urls[0]
    missing = [p.key for p in ports(schema) if p.required and p.key not in values]
    if missing:
        raise NodeInputError(f"Missing input: {', '.join(missing)}")
    return values


@dataclass
class Hooks:
    """Lo que el motor necesita de la API (definido en `api.py`, con las mismas reglas que generar a mano).

    plan(session, owner, model_id, arguments) -> Plan; create(session, owner, model_id, arguments, key, plan,
    usd, reserve, accept_unknown) -> Job, sin commit (lo confirma el motor junto con la corrida);
    output_url(session, owner, job_id, derive=None) -> str; trusted(session, owner, url) -> bool; schema(model_id) ->
    input_schema o None; output_of(model_id) -> tipo de salida; wake() despierta al worker."""

    plan: Callable[..., Awaitable[Any]]
    create: Callable[..., Awaitable[Job]]
    output_url: Callable[..., Awaitable[str]]
    trusted: Callable[..., Awaitable[bool]]
    schema: Callable[[str], dict | None]
    output_of: Callable[[str], str | None]
    wake: Callable[[], None]
    output_text: Callable[..., Awaitable[str]] | None = (
        None  # (session, owner, job_id) -> texto de un Assistant
    )


def spend_of(usd: float | None, reserve: float | None) -> float:
    """Lo que un paso compromete del tope: su precio o su retención inicial, lo que sea mayor."""
    return max(usd or 0.0, reserve or 0.0)


def run_key(run_id: str, node_id: str) -> str:
    """Clave de idempotencia de un paso: la identidad estable para recuperar su trabajo tras un reinicio."""
    return f"space-run:{run_id}:{node_id}"


def is_run_key(key: str | None) -> bool:
    return bool(key) and key.startswith("space-run:")


def media_urls(arguments: dict, schema: dict) -> list[str]:
    """URLs de medios de una entrada (campos de puertos de imagen, video o audio)."""
    urls: list[str] = []
    for port in ports(schema):
        if port.kind == "text" or port.key not in arguments:
            continue
        value = arguments[port.key]
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str):
                urls.append(item)
    return urls


class SpaceRunner:
    """Una tarea asyncio por corrida activa. Se retoman al arrancar el servidor (`resume_all`).

    Cada paso se envía en su propia transacción: el trabajo nuevo y el estado de la corrida (nodo y gasto
    comprometido) se confirman juntos, con el bloqueo optimista de `SpaceRun`. Si mientras tanto alguien
    detuvo o aprobó la corrida, el commit pierde y el trabajo no llega a existir (revisión 55)."""

    def __init__(self, sessions: async_sessionmaker, hooks: Hooks):
        self.sessions = sessions
        self.hooks = hooks
        self.tasks: dict[str, asyncio.Task] = {}

    def start(self, run_id: str) -> None:
        task = self.tasks.get(run_id)
        if task and not task.done():
            return
        self.tasks[run_id] = asyncio.create_task(self.drive(run_id), name=f"space-run-{run_id}")

    async def resume_all(self) -> None:
        async with self.sessions() as session:
            ids = (await session.scalars(select(SpaceRun.id).where(SpaceRun.status.in_(ACTIVE_RUN)))).all()
        for run_id in ids:
            self.start(run_id)

    async def stop(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def drive(self, run_id: str) -> None:
        while True:
            try:
                active = await self.tick(run_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Fallo en la corrida %s", run_id)
                active = True
            if not active:
                return
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self, run_id: str) -> bool:
        """Un paso del motor: actualiza el estado y envía los pasos listos. Devuelve si sigue activa."""
        if not await self._reconcile(run_id):
            return False
        while await self._start_next(run_id):
            pass
        async with self.sessions() as session:
            run = await session.get(SpaceRun, run_id)
            return run is not None and run.status in ACTIVE_RUN

    async def _reconcile(self, run_id: str) -> bool:
        """Estado de los pasos enviados, saltos, pausas del worker y fin de la corrida."""
        async with self.sessions() as session:
            run = await session.get(SpaceRun, run_id)
            if run is None or run.status not in ACTIVE_RUN:
                return False
            nodes = {k: dict(v) for k, v in run.nodes.items()}
            await self._refresh(session, nodes)
            self._skip_blocked(run, nodes)
            run.nodes = nodes
            self._job_pause(run, nodes, await self._waiting_jobs(session, nodes))
            if all(st["status"] in NODE_DONE for st in nodes.values()):
                done = [st for st in nodes.values() if st["status"] == "done"]
                run.status = "completed" if len(done) == len(nodes) else ("failed" if not done else "partial")
                run.pause = None
                run.finished_at = utcnow()
            try:
                await session.commit()
            except StaleDataError:
                await session.rollback()  # una ruta escribió a la vez: se relee en el siguiente paso
            return True

    async def _refresh(self, session: AsyncSession, nodes: dict) -> None:
        for state in nodes.values():
            if state["status"] != "running":
                continue
            job = await session.get(Job, state["job_id"])
            if job is None:
                state.update(status="failed", error="The generation no longer exists")
            elif job.status == "completed":
                state["status"] = "done"
                state.pop("waiting", None)
            elif job.status in TERMINAL:
                state.update(status="failed", error=job.error or job.status)
                state.pop("waiting", None)
            else:
                state["waiting"] = job.status == "awaiting_approval"

    @staticmethod
    async def _waiting_jobs(session: AsyncSession, nodes: dict) -> dict[str, Job]:
        out = {}
        for node_id, state in nodes.items():
            if state.get("waiting"):
                job = await session.get(Job, state["job_id"])
                if job is not None and job.status == "awaiting_approval" and job.plan:
                    out[node_id] = job
        return out

    @staticmethod
    def _job_pause(run: SpaceRun, nodes: dict, waiting: dict[str, Job]) -> None:
        """Un paso cuyo proveedor de respaldo cuesta más espera aprobación: la corrida se pausa y la aprobación
        pasa por ella, con el nuevo total contra el tope (revisión 55)."""
        pause = run.pause or {}
        if pause.get("reason") == "job_approval" and pause.get("node") not in waiting:
            run.status, run.pause = "running", None  # se resolvió por otra vía (p. ej. se canceló el trabajo)
            pause = {}
        same = pause.get("reason") == "job_approval" and pause.get("node") in waiting
        if not waiting or (run.status != "running" and not same):
            return
        # Una pausa de respaldo ya abierta se mantiene al día con la última cotización del trabajo.
        node_id, job = (pause["node"], waiting[pause["node"]]) if same else next(iter(waiting.items()))
        option = job.plan[job.plan_index]
        state = nodes[node_id]
        new = spend_of(option.get("usd"), option.get("reserve_usd"))
        needed = run.committed_usd - state.get("spend", 0.0) + new
        run.status = "awaiting_approval"
        run.pause = {"node": node_id, "reason": "job_approval", "job_id": job.id, "usd": option.get("usd"),
                     "reserve_usd": option.get("reserve_usd"), "needed_total_usd": round(needed, 6),
                     "unknown": option.get("usd") is None}  # fmt: skip

    @staticmethod
    def _skip_blocked(run: SpaceRun, nodes: dict) -> None:
        """Un paso cuyo origen falló no puede correr: queda saltado (y lo que depende de él también)."""
        changed = True
        while changed:
            changed = False
            for node_id in run.order:
                if nodes[node_id]["status"] != "pending":
                    continue
                deps = step_deps(run.graph, nodes, node_id)
                if any(nodes[d]["status"] in ("failed", "skipped", "canceled") for d in deps):
                    nodes[node_id].update(status="skipped", error="A previous step did not finish")
                    changed = True

    async def _start_next(self, run_id: str) -> bool:
        """Envía el siguiente paso listo en una transacción propia. Devuelve si conviene seguir con otro."""
        async with self.sessions() as session:
            run = await session.get(SpaceRun, run_id)
            if run is None or run.status != "running":
                return False
            nodes = {k: dict(v) for k, v in run.nodes.items()}
            node_id = next(
                (
                    i
                    for i in run.order
                    if nodes[i]["status"] == "pending"
                    and all(nodes[d]["status"] == "done" for d in step_deps(run.graph, nodes, i))
                ),
                None,
            )
            if node_id is None:
                return False
            owner = await session.get(ApiClient, run.owner_id)
            state = nodes[node_id]
            committed = run.committed_usd
            pause = None
            job: Job | None = None
            # Primero se recupera el trabajo que este paso ya creó (reinicio entre crearlo y guardar la corrida):
            # se adopta con su entrada y su compromiso originales, sin volver a cotizar (revisión 55).
            existing = await session.scalar(
                select(Job).where(
                    Job.owner_id == run.owner_id, Job.idempotency_key == run_key(run.id, node_id)
                )
            )
            if existing is not None:
                spend = spend_of(existing.max_usd, existing.max_reserve_usd)
                state.update(status="running", job_id=existing.id, usd=existing.max_usd,
                             reserve_usd=existing.max_reserve_usd, spend=spend)  # fmt: skip
                committed += spend
            else:
                outcome = await self._prepare(session, run, owner, node_id, state, committed)
                if "wait" in outcome:
                    # Cola llena (cupos de generaciones activas): el paso sigue pendiente y se reintenta, ya
                    # recotizado, en la próxima vuelta, cuando termine algún trabajo (revisión 70).
                    await session.rollback()
                    return False
                if "pause" in outcome:
                    pause = outcome["pause"]
                elif "job" in outcome:
                    job = outcome["job"]
                    committed += outcome["spend"]
            run.nodes = nodes
            run.committed_usd = round(committed, 6)
            if pause:
                run.status, run.pause = "awaiting_approval", pause
            try:
                await session.commit()
            except StaleDataError:
                # Alguien detuvo o aprobó la corrida mientras tanto: el rollback deshace también el trabajo.
                await session.rollback()
                return False
            if job is not None:
                self.hooks.wake()
            return pause is None

    async def _prepare(
        self,
        session: AsyncSession,
        run: SpaceRun,
        owner: ApiClient,
        node_id: str,
        state: dict,
        committed: float,
    ) -> dict:
        """Resuelve, cotiza y crea (sin commit) un paso. Devuelve {job, spend}, {pause}, {wait} si la cola de
        generaciones activas está llena, o {} si falló."""
        nodes = run.nodes
        graph_nodes = {n["id"]: n for n in run.graph["nodes"]}
        step = node_id
        node_id, item = split_step(step)
        model_id = graph_nodes[node_id]["data"]["model"]
        schema = self.hooks.schema(model_id)
        if schema is None:
            state.update(status="failed", error=f"Unknown model: {model_id}")
            return {}

        def source_job(src: str) -> str | None:
            mine = f"{src}#{item}" if item is not None and f"{src}#{item}" in nodes else src
            if mine in nodes:  # generado en esta corrida (el mismo elemento del lote)
                return nodes[mine].get("job_id") if nodes[mine]["status"] == "done" else None
            return selected_run(graph_nodes[src]["data"])

        try:
            arguments = await resolve_input(
                run.graph,
                node_id,
                schema,
                self.hooks.output_of,
                source_job,
                lambda job_id, derive=None: self.hooks.output_url(session, owner, job_id, derive),
                item,
                (lambda job_id: self.hooks.output_text(session, owner, job_id))
                if self.hooks.output_text
                else None,
            )
            for url in media_urls(arguments, schema):
                if not await self.hooks.trusted(session, owner, url):
                    raise NodeInputError("A connected file is not one of your uploads or generations")
            plan = await self.hooks.plan(session, owner, model_id, arguments)
        except STEP_ERRORS as exc:  # entrada incompleta, 422 del catálogo, medios ajenos, proveedor
            state.update(status="failed", error=str(getattr(exc, "message", None) or exc))
            return {}
        best = plan.best
        if best is None:
            state.update(status="failed", error="No provider can run this step")
            return {}
        unknown = best.usd is None or bool(best.missing)
        if unknown and not state.get("accept_unknown"):
            return {"pause": {"node": step, "reason": "unknown_cost", "reserve_usd": best.reserve_usd}}
        need = spend_of(None if unknown else best.usd, best.reserve_usd)
        if committed + need > run.max_total_usd + COST_TOLERANCE_USD:
            return {"pause": {"node": step, "reason": "over_budget", "usd": best.usd,
                              "reserve_usd": best.reserve_usd, "needed_total_usd": round(committed + need, 6)}}  # fmt: skip
        try:
            job = await self.hooks.create(
                session, owner, model_id, arguments, run_key(run.id, step), plan,
                None if unknown else best.usd, best.reserve_usd, unknown,
            )  # fmt: skip
        except ServiceError as exc:
            if exc.code == "too_many_active":
                return {"wait": True}
            state.update(status="failed", error=str(exc.message or exc))
            return {}
        except STEP_ERRORS as exc:
            state.update(status="failed", error=str(getattr(exc, "message", None) or exc))
            return {}
        state.update(status="running", job_id=job.id, usd=None if unknown else best.usd,
                     reserve_usd=best.reserve_usd, spend=need)  # fmt: skip
        return {"job": job, "spend": need}
