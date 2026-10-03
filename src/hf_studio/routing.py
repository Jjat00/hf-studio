"""Plan de una generación: qué proveedores pueden hacerla, con qué entrada y a qué precio.

El plan ordena las opciones de la más barata a la más cara (a igual precio gana la oficial y, después,
el orden del registro, con Higgsfield primero). El worker envía la primera y, si falla sin cobrar, salta a
la siguiente: sola si cuesta lo mismo o menos que lo aprobado, y con una nueva aprobación si cuesta más.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .catalog import Catalog
from .pricing import fill_placeholders, quote
from .providers.base import Provider, ProviderError
from .providers.prices import PriceBook
from .providers.registry import DEFAULT_PROVIDER, PROVIDERS
from .providers.routes import with_defaults

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
        return [{"provider": o.provider, "model": o.model, "input": o.input, "usd": o.usd, "kind": o.kind,
                 "reserve_usd": o.reserve_usd, "quoted_at": now, "hints": self.hints, "forced": self.forced}
                for o in self.options]  # fmt: skip


class Router:
    def __init__(self, providers: dict[str, Provider], prices: PriceBook, catalog_getter):
        self.providers = providers
        self.prices = prices
        self.catalog_getter = catalog_getter
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
    ) -> Plan:
        hints = dict(hints or {})
        logical = with_defaults(model["input_schema"], arguments)
        options: list[Option] = []
        excluded: list[dict[str, Any]] = []
        names = [only] if only else list(PROVIDERS)
        for name in names:
            provider = self.providers.get(name)
            if provider is None:
                raise ProviderError("unsupported", f"Unknown provider {name!r}", provider=name)
            info = {"provider": name, "title": provider.title}
            option = await self._option(provider, model, arguments, logical, hints, info, excluded)
            if option is None:
                continue
            if not provider.configured:
                excluded.append({**info, "reason": f"no key ({provider.env_var})", "usd": option.usd,
                                 "key_url": provider.key_url, "signup_url": provider.signup_url})  # fmt: skip
                continue
            needed = max(option.usd or 0, option.reserve_usd or 0) or None
            if check_balance and needed is not None and provider.has_price_table:
                balance, valid = await self.balance(name)
                if valid is False:
                    excluded.append(
                        {**info, "reason": "invalid key", "usd": option.usd, "key_url": provider.key_url}
                    )
                    continue
                if balance is not None and balance < needed:
                    excluded.append({**info, "reason": f"insufficient balance ({balance:.2f} USD)", "usd": option.usd,
                                     "billing_url": provider.billing_url})  # fmt: skip
                    continue
            options.append(option)
        order = {name: i for i, name in enumerate(PROVIDERS)}
        options.sort(key=lambda o: (o.usd is None, o.usd or 0, not o.official, order.get(o.provider, 99)))
        return Plan(model["id"], options, excluded, hints, forced=only is not None)

    async def _option(
        self,
        provider: Provider,
        model: dict,
        arguments: dict,
        logical: dict,
        hints: dict,
        info: dict,
        excluded: list,
    ) -> Option | None:
        if provider.name == DEFAULT_PROVIDER:
            priced = await quote(provider, self.catalog, model, arguments, hints)
            if priced["kind"] == "unavailable" and priced.get("errors"):
                excluded.append({**info, "reason": priced["basis"]})
                return None
            return Option(
                provider.name, provider.title, model["id"], arguments, priced["usd"], priced["kind"],
                priced["basis"], credits=priced.get("credits"), discount_pct=priced.get("discount_pct"),
                missing=priced.get("missing") or [], description=priced.get("description"),
            )  # fmt: skip
        route = provider.routes().get(model["id"])
        if route is None:
            return None
        filled, placeholders = fill_placeholders(model["input_schema"], arguments)
        try:
            translated = route.translate(with_defaults(model["input_schema"], filled), frozenset(arguments))
        except ProviderError as exc:
            excluded.append({**info, "reason": exc.message})
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
    fresh = (await router.plan(model, arguments, hints, only=option["provider"])).best
    if fresh is None:
        return None
    priced = fresh.usd is not None and not fresh.missing
    return {**option, "model": fresh.model, "input": fresh.input or option["input"],
            "usd": fresh.usd if priced else None, "kind": fresh.kind, "reserve_usd": fresh.reserve_usd,
            "quoted_at": time.time()}  # fmt: skip
