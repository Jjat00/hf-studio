"""Plan de una generación: qué proveedores pueden hacerla, con qué entrada y a qué precio.

El plan ordena las opciones de la más barata a la más cara (a igual precio gana la oficial y, después,
el orden del registro, con Higgsfield primero). Un proveedor con varios canales del mismo modelo (oficial y
no oficial) aporta una opción por canal; cada opción se identifica por `(provider, model)`. El worker envía la primera y, si falla sin cobrar, salta a
la siguiente: sola si cuesta lo mismo o menos que lo aprobado, y con una nueva aprobación si cuesta más.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .catalog import Catalog
from .elements import element_ids, is_element_id
from .pricing import fill_placeholders, quote
from .providers.base import Provider, ProviderError
from .providers.prices import PriceBook
from .providers.registry import DEFAULT_PROVIDER, PROVIDERS
from .providers.routes import Route, routes_for, with_defaults
from .space_assistant import assistant_quote, is_assistant
from .space_audio import audio_quote, is_audio_node
from .space_tools import ASSISTANT_PROVIDER, AUDIO_PROVIDER, TOOL_PROVIDER, is_tool

BALANCE_TTL = 60.0
OUTDATED_PRICES = 3 * 24 * 3600  # una tabla sin poder actualizarse en 3 días ya no da precios exactos
VIDEO_FIELDS = ("video_url", "video_urls")


@dataclass
class Option:
    provider: str
    title: str
    model: str  # id en el proveedor
    input: dict[str, Any]  # entrada traducida al proveedor
    usd: float | None
    kind: str  # exact | approx | formula | unavailable (como pricing.normalize)
    basis: str = ""
    official: bool = True
    notes: list[str] = field(default_factory=list)
    credits: float | None = None
    discount_pct: float | None = None
    missing: list[str] = field(default_factory=list)
    description: str | None = None
    # Débito inicial cuando es mayor que el costo final (se devuelve la diferencia al terminar).
    reserve_usd: float | None = None

    def public(self) -> dict[str, Any]:
        """Sin la entrada traducida: lo que ven la UI, el MCP y el usuario."""
        data = asdict(self)
        data.pop("input")
        return data


QUOTE_MAX_AGE = 15 * 60  # una opción cotizada hace más se vuelve a cotizar antes de enviarla


@dataclass
class Plan:
    model: str
    options: list[Option]  # utilizables, de la más barata a la más cara
    excluded: list[dict[str, Any]]  # {provider, title, reason, usd?, key_url?}
    hints: dict[str, Any] = field(default_factory=dict)
    forced: bool = False  # el usuario eligió el proveedor: no se reordena por precio

    @property
    def best(self) -> Option | None:
        return self.options[0] if self.options else None

    def public(self) -> dict[str, Any]:
        best = self.best
        higgsfield = next((o for o in self.options if o.provider == DEFAULT_PROVIDER), None)
        savings = None
        if (
            best
            and higgsfield
            and best.usd is not None
            and higgsfield.usd
            and best.provider != DEFAULT_PROVIDER
        ):
            savings = {
                "usd": round(higgsfield.usd - best.usd, 4),
                "pct": round(100 * (1 - best.usd / higgsfield.usd)),
            }
        return {
            "provider": best.provider if best else None,
            "options": [o.public() for o in self.options],
            "excluded": self.excluded,
            "savings_vs_higgsfield": savings,
        }

    def stored(self) -> list[dict[str, Any]]:
        """Lo que se guarda en el trabajo para el worker."""
        now = time.time()
        return [{"provider": o.provider, "model": o.model, "official": o.official, "input": o.input, "usd": o.usd,
                 "kind": o.kind, "reserve_usd": o.reserve_usd, "quoted_at": now, "hints": self.hints,
                 "forced": self.forced}
                for o in self.options]  # fmt: skip


class Router:
    def __init__(self, providers: dict[str, Provider], prices: PriceBook, catalog_getter, elements=None):
        self.providers = providers
        self.prices = prices
        self.catalog_getter = catalog_getter
        # `async (ids) -> {id: {name, description, image_urls}}`: elementos de HF Studio con URLs vigentes.
        self.elements = elements
        self._balances: dict[str, tuple[float, float | None, bool | None]] = {}

    @property
    def catalog(self) -> Catalog:
        return self.catalog_getter()

    async def balance(self, name: str) -> tuple[float | None, bool | None]:
        """(saldo en USD o None si no se sabe, clave válida o None). En caché un minuto."""
        cached = self._balances.get(name)
        if cached and time.monotonic() - cached[0] < BALANCE_TTL:
            return cached[1], cached[2]
        check = await self.providers[name].check_key()
        self._balances[name] = (time.monotonic(), check.balance_usd, check.valid)
        return check.balance_usd, check.valid

    def forget_balance(self, name: str) -> None:
        self._balances.pop(name, None)

    async def plan(
        self,
        model: dict,
        arguments: dict,
        hints: dict | None = None,
        only: str | None = None,
        check_balance: bool = True,
        route: str | None = None,
    ) -> Plan:
        """`only` limita el plan a un proveedor; `route`, además, a uno de sus canales (id del modelo en el
        proveedor): así una opción guardada se recotiza en el mismo canal y no salta a otro en silencio."""
        hints = dict(hints or {})
        hints.pop("elements", None)  # planes guardados antes de la revisión 43: nunca se usa ese snapshot
        logical = with_defaults(model["input_schema"], arguments)
        if is_tool(model["id"]):
            # Herramienta local (ffmpeg): una sola opción, gratis, en el proveedor interno del worker.
            option = Option(TOOL_PROVIDER, "HF Studio (local)", model["id"], logical, 0.0, "exact",
                            basis="Local tool (ffmpeg): free")  # fmt: skip
            return Plan(model["id"], [option], [], hints, forced=only is not None)
        if is_assistant(model["id"]):
            # Nodo Assistant de Spaces: la API de Claude, cotizada con su cota superior (aproximada).
            est = assistant_quote(logical)
            option = Option(ASSISTANT_PROVIDER, "Claude", model["id"], logical, est["usd"], est["kind"],
                            basis=est["basis"])  # fmt: skip
            return Plan(model["id"], [option], [], hints, forced=only is not None)
        if is_audio_node(model["id"]):
            # Nodo de audio de Spaces: ElevenLabs, a su tarifa de API (aproximada, como en /v1/audio).
            est = audio_quote(model["id"], logical)
            if est is None:
                excluded = [
                    {
                        "provider": AUDIO_PROVIDER,
                        "title": "ElevenLabs",
                        "reason": "The input is not valid yet",
                    }
                ]
                return Plan(model["id"], [], excluded, hints, forced=only is not None)
            option = Option(AUDIO_PROVIDER, "ElevenLabs", model["id"], logical, est["usd"], est["kind"],
                            basis=est["basis"])  # fmt: skip
            return Plan(model["id"], [option], [], hints, forced=only is not None)
        ids = element_ids(arguments.get("elements"))
        elements = await self.elements(ids) if ids and self.elements else {}
        options: list[Option] = []
        excluded: list[dict[str, Any]] = []
        names = [only] if only else list(PROVIDERS)
        for name in names:
            provider = self.providers.get(name)
            if provider is None:
                raise ProviderError("unsupported", f"Unknown provider {name!r}", provider=name)
            for option in await self._options(
                provider, model, arguments, logical, hints, excluded, route, elements
            ):
                await self._admit(provider, option, check_balance, options, excluded)
        order = {name: i for i, name in enumerate(PROVIDERS)}
        options.sort(key=lambda o: (o.usd is None, o.usd or 0, not o.official, order.get(o.provider, 99)))
        return Plan(model["id"], options, excluded, hints, forced=only is not None)

    async def _admit(
        self, provider: Provider, option: Option, check_balance: bool, options: list, excluded: list
    ) -> None:
        """Añade la opción al plan si el proveedor tiene clave válida y saldo; si no, la deja en `excluded`."""
        info = {"provider": provider.name, "title": provider.title, "model": option.model}
        if not provider.configured:
            excluded.append({**info, "reason": f"no key ({provider.env_var})", "usd": option.usd,
                             "key_url": provider.key_url, "signup_url": provider.signup_url})  # fmt: skip
            return
        needed = max(option.usd or 0, option.reserve_usd or 0) or None
        if check_balance and needed is not None and provider.has_price_table:
            balance, valid = await self.balance(provider.name)
            if valid is False:
                excluded.append(
                    {**info, "reason": "invalid key", "usd": option.usd, "key_url": provider.key_url}
                )
                return
            if balance is not None and balance < needed:
                excluded.append({**info, "reason": f"insufficient balance ({balance:.2f} USD)", "usd": option.usd,
                                 "billing_url": provider.billing_url})  # fmt: skip
                return
        options.append(option)

    async def _options(
        self,
        provider: Provider,
        model: dict,
        arguments: dict,
        logical: dict,
        hints: dict,
        excluded: list,
        route: str | None = None,
        elements: dict | None = None,
    ) -> list[Option]:
        """Una opción por canal del proveedor que puede hacer el pedido (los que no, van a `excluded`)."""
        info = {"provider": provider.name, "title": provider.title}
        if provider.name == DEFAULT_PROVIDER:
            if route is not None and route != model["id"]:
                return []
            if any(is_element_id(v) for v in arguments.get("elements") or []):
                excluded.append({**info, "model": model["id"],
                                 "reason": "HF Studio elements only run on APIMart and KIE"})  # fmt: skip
                return []
            priced = await quote(provider, self.catalog, model, arguments, hints)
            if priced["kind"] == "unavailable" and priced.get("errors"):
                excluded.append({**info, "model": model["id"], "reason": priced["basis"]})
                return []
            return [Option(
                provider.name, provider.title, model["id"], arguments, priced["usd"], priced["kind"],
                priced["basis"], credits=priced.get("credits"), discount_pct=priced.get("discount_pct"),
                missing=priced.get("missing") or [], description=priced.get("description"),
            )]  # fmt: skip
        options = []
        for candidate in routes_for(provider.routes(), model["id"]):
            if route is not None and candidate.model != route:
                continue
            option = self._route_option(
                provider, candidate, model, arguments, logical, hints, info, excluded, elements or {}
            )
            if option is not None:
                options.append(option)
        return options

    def _route_option(
        self,
        provider: Provider,
        route: Route,
        model: dict,
        arguments: dict,
        logical: dict,
        hints: dict,
        info: dict,
        excluded: list,
        elements: dict,
    ) -> Option | None:
        filled, placeholders = fill_placeholders(model["input_schema"], arguments)
        if filled.get("elements"):
            # Elementos de HF Studio resueltos desde la base (nombre, descripción e imágenes), que el traductor
            # envía en línea. Un id de Higgsfield queda como texto.
            filled = {**filled, "elements": [elements.get(v, v) for v in filled["elements"]]}
        try:
            translated = route.translate(with_defaults(model["input_schema"], filled), frozenset(arguments))
        except ProviderError as exc:
            excluded.append({**info, "model": route.model, "reason": exc.message})
            return None
        prices = self.prices.prices(provider.name)
        usd = route.price(logical, hints, prices) if route.price else None
        reserve = route.reserve(logical, hints, prices) if route.reserve else None
        missing = [] if usd is not None or not _has_video(logical) else ["input_video_seconds"]
        synced = self.prices.synced_at(provider.name)
        basis = f"{provider.title} price list" + (
            f" ({time.strftime('%Y-%m-%d', time.gmtime(synced))})" if synced else ""
        )
        if usd is None and not missing:
            basis = f"{provider.title} has no price for this request in its list"
        outdated = synced is not None and time.time() - synced > OUTDATED_PRICES
        if usd is None:
            kind = "formula" if missing else "unavailable"
        elif route.settles_later or outdated:
            kind = "approx"  # liquidado después o tabla sin actualizar: no es un precio exacto
            basis += " · settled after generating" if route.settles_later else " · outdated price list"
        else:
            kind = "exact"
        return Option(
            provider.name, provider.title, route.model, translated if not placeholders else {}, usd, kind, basis,
            official=route.official, notes=list(route.notes), missing=missing,
            reserve_usd=reserve if reserve is not None and usd is not None and reserve > usd else None,
        )  # fmt: skip


def _has_video(arguments: dict) -> bool:
    return any(arguments.get(k) for k in VIDEO_FIELDS)


def video_urls(arguments: dict) -> list[str]:
    urls = []
    for key in VIDEO_FIELDS:
        value = arguments.get(key)
        urls.extend(value if isinstance(value, list) else [value] if value else [])
    return [u for u in urls if isinstance(u, str)]


def stale(option: dict) -> bool:
    return time.time() - float(option.get("quoted_at") or 0) > QUOTE_MAX_AGE


async def requote(router: Router, model: dict, arguments: dict, option: dict) -> dict | None:
    """Vuelve a cotizar una opción guardada en su proveedor (con los mismos datos de cotización). None si
    ese proveedor ya no puede hacer el pedido."""
    hints = option.get("hints") or {}
    # Mismo canal (`model`): si un proveedor tiene uno oficial y otro no, no se cambia de uno a otro aquí.
    plan = await router.plan(model, arguments, hints, only=option["provider"], route=option["model"])
    fresh = plan.best
    if fresh is None:
        return None
    priced = fresh.usd is not None and not fresh.missing
    return {**option, "model": fresh.model, "official": fresh.official, "input": fresh.input or option["input"],
            "usd": fresh.usd if priced else None, "kind": fresh.kind, "reserve_usd": fresh.reserve_usd,
            "quoted_at": time.time()}  # fmt: skip
