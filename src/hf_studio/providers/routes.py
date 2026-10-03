"""Mapa de modelos: qué proveedores ofrecen cada modelo lógico y cómo se le traduce la entrada.

El modelo lógico es el id del catálogo (el de Higgsfield): no cambia presets, UI ni historial. Cada
proveedor declara en `Provider.routes()` una `Route` por modelo lógico que ofrece. Higgsfield ofrece todo
el catálogo con la entrada tal cual.

Regla de fidelidad: un traductor nunca cambia lo que se pide. Si un valor no tiene equivalente exacto
(una duración o una relación de aspecto que el proveedor no admite, un campo sin traducción), lanza
`unsupported` y ese proveedor queda fuera para ese pedido; el fallback es el mismo modelo, no otro.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .base import ProviderError

Translator = Callable[[dict[str, Any]], dict[str, Any]]
# Precio en USD de una entrada lógica (ya con los valores por defecto del esquema), con la tabla del
# proveedor (`prices.PriceBook`). `hints` lleva lo que la entrada no dice: `input_video_seconds` (suma de
# los videos de entrada). Devuelve None si falta un dato o la tabla no tiene esa fila.
Pricer = Callable[[dict[str, Any], dict[str, Any], dict[str, float]], float | None]


@dataclass(frozen=True)
class Route:
    provider: str
    model: str  # id del modelo en el proveedor
    translate: Translator
    price: Pricer | None = None
    official: bool = True  # False: canal no oficial del proveedor (más barato, menos estable)
    notes: tuple[str, ...] = field(default_factory=tuple)


def unsupported(provider: str, message: str) -> ProviderError:
    return ProviderError("unsupported", message, provider=provider)


# --- Piezas para escribir traductores ---------------------------------------------------------


class Spec:
    """Traductor declarativo: cada campo lógico se renombra, se transforma o se descarta.

    - `rename={"end_image_url": "last_frame_url"}`
    - `convert={"sound": lambda v: v == "on"}` (se aplica antes de renombrar; si devuelve None, el
      campo se acepta pero no se envía)
    - `allowed={"duration": {5, 10}}` valores admitidos por el proveedor; otro valor es `unsupported`
    - `drop={"cfg_scale"}` campos que se pueden omitir sin cambiar el resultado
    - `fixed={"generation_type": "TEXT_2_VIDEO"}` campos que el proveedor exige
    - `keep` campos que pasan con el mismo nombre (por defecto prompt, duration, resolution, aspect_ratio,
      seed y negative_prompt)
    - `build` función final opcional `(logical_input, translated) -> translated`
    Un campo lógico que no aparece en ninguna regla y llega con valor es `unsupported`: así un campo nuevo
    del catálogo nunca se pierde en silencio.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        *,
        rename: dict[str, str] | None = None,
        convert: dict[str, Callable[[Any], Any]] | None = None,
        allowed: dict[str, Iterable[Any]] | None = None,
        drop: Iterable[str] = (),
        fixed: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
        build: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        keep: Iterable[str] = ("prompt", "duration", "resolution", "aspect_ratio", "seed", "negative_prompt"),
    ):
        self.provider = provider
        self.model = model
        self.rename = rename or {}
        self.convert = convert or {}
        self.allowed = {k: set(v) for k, v in (allowed or {}).items()}
        self.drop = set(drop)
        self.fixed = fixed or {}
        self.defaults = defaults or {}
        self.build = build
        self.keep = set(keep)

    def __call__(self, logical: dict[str, Any]) -> dict[str, Any]:
        source = {**self.defaults, **logical}
        out: dict[str, Any] = {}
        for key, value in source.items():
            if value is None:
                continue
            if key in self.drop:
                continue
            if key in self.allowed and value not in self.allowed[key]:
                raise unsupported(
                    self.provider, f"{self.model}: {key}={value!r} is not available on {self.provider}"
                )
            if key in self.convert:
                value = self.convert[key](value)
                if value is None:  # aceptado sin enviarlo (p. ej. `only_default`)
                    continue
            if key in self.rename:
                out[self.rename[key]] = value
            elif key in self.keep or key in self.convert or key in self.allowed:
                out[key] = value
            else:
                raise unsupported(
                    self.provider, f"{self.model}: field {key!r} has no equivalent on {self.provider}"
                )
        out.update(self.fixed)
        return self.build(source, out) if self.build else out


def first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def per_second(prices: dict[str, float], key: str, seconds: float | None) -> float | None:
    rate = prices.get(key)
    return None if rate is None or seconds is None else round(rate * seconds, 4)


def per_unit(prices: dict[str, float], key: str, units: float = 1) -> float | None:
    rate = prices.get(key)
    return None if rate is None else round(rate * units, 4)


def video_seconds(hints: dict[str, Any]) -> float | None:
    value = hints.get("input_video_seconds")
    return float(value) if isinstance(value, int | float) and value > 0 else None


def only_default(field_name: str, default: Any) -> Callable[[Any], Any]:
    """Para un campo que el proveedor no tiene: se acepta solo con el valor por defecto lógico (el
    resultado es el mismo) y se descarta; con otro valor el pedido no se puede reproducir."""

    def check(value: Any) -> Any:
        if value != default:
            raise ProviderError("unsupported", f"{field_name}={value!r} cannot be reproduced here")
        return None

    return check


def with_defaults(schema: dict[str, Any], logical: dict[str, Any]) -> dict[str, Any]:
    """Completa la entrada con los `default` del esquema lógico antes de traducir: los proveedores tienen
    otros valores por defecto (KIE y APIMart apagan el audio de Kling, por ejemplo) y omitir un campo
    cambiaría el resultado."""
    props = schema.get("properties") or {}
    filled = {
        k: v["default"]
        for k, v in props.items()
        if isinstance(v, dict) and "default" in v and v["default"] != ""
    }
    return {**filled, **logical}
