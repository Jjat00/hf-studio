"""Uso y gasto: lo que costaron las generaciones terminadas, por día, proveedor y modelo (página /usage).

El costo es el cotizado al lanzar la opción que corrió (`plan[plan_index].usd`), no el cobro conciliado con el
proveedor: en los modelos por tokens (`kind` approx) puede diferir un poco del real (Parkboard #121). Los
trabajos sin precio guardado (anteriores al plan multiproveedor o sin cotización) se cuentan aparte.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MAX_FILLED_DAYS = 400  # «todo» con un historial muy largo no rellena días vacíos más allá de esto


@dataclass(frozen=True)
class UsageRow:
    model: str
    provider: str
    usd: float | None
    kind: str | None
    at: datetime  # UTC ingenuo, como en la base


def _round(usd: float) -> float:
    return round(usd, 4)


def summarize(
    rows: list[UsageRow], since: datetime | None, now: datetime, utc_offset_minutes: int = 0
) -> dict:
    """Totales, reparto por proveedor y modelo, y una serie diaria (en la hora local de quien consulta) con
    los días sin gasto incluidos, para que la gráfica no salte huecos."""
    shift = timedelta(minutes=utc_offset_minutes)
    providers: dict[str, dict] = defaultdict(lambda: {"usd": 0.0, "generations": 0, "unpriced": 0})
    models: dict[tuple[str, str], dict] = defaultdict(lambda: {"usd": 0.0, "generations": 0, "unpriced": 0})
    days: dict[date, float] = defaultdict(float)
    total = approx = 0.0
    unpriced = 0
    for row in rows:
        p, m = providers[row.provider], models[(row.model, row.provider)]
        p["generations"] += 1
        m["generations"] += 1
        day = (row.at + shift).date()
        days.setdefault(day, 0.0)
        if row.usd is None:
            p["unpriced"] += 1
            m["unpriced"] += 1
            unpriced += 1
            continue
        total += row.usd
        p["usd"] += row.usd
        m["usd"] += row.usd
        days[day] += row.usd
        if row.kind not in (None, "exact"):
            approx += row.usd

    today = (now + shift).date()
    first = (since + shift).date() if since else min(days, default=today)
    first = max(first, today - timedelta(days=MAX_FILLED_DAYS - 1))
    series = [
        {
            "date": (first + timedelta(days=i)).isoformat(),
            "usd": _round(days.get(first + timedelta(days=i), 0.0)),
        }
        for i in range((today - first).days + 1)
    ]

    def ranked(items: dict, label) -> list[dict]:
        out = [{**label(k), **d, "usd": _round(d["usd"])} for k, d in items.items()]
        return sorted(out, key=lambda x: (-x["usd"], -x["generations"]))

    return {
        "since": since.isoformat() + "Z" if since else None,
        "total_usd": _round(total),
        "approx_usd": _round(approx),
        "generations": len(rows),
        "unpriced": unpriced,
        "providers": ranked(providers, lambda k: {"provider": k}),
        "models": ranked(models, lambda k: {"model": k[0], "provider": k[1]}),
        "days": series,
    }
