"""Estilos de Content Factory: cada uno es código (paleta, tipografía, fondo dibujado y cómo se ven los datos).

Nada de imágenes ni de generación con IA: el fondo y los gráficos se dibujan con CSS y SVG en
`factory_compose.py`. Las fuentes van incluidas en `factory_assets/fonts` (todas con licencia OFL), así el
render no depende de lo que tenga instalado el sistema ni de la red.
"""

from __future__ import annotations

# Familias incluidas: nombre CSS -> [(archivo, peso, estilo)].
FONTS: dict[str, list[tuple[str, int, str]]] = {
    "Anton": [("Anton-Regular.woff2", 400, "normal")],
    "Geist": [("Geist-400.woff2", 400, "normal"), ("Geist-700.woff2", 700, "normal")],
    "JetBrains Mono": [
        ("JetBrainsMono-Regular.woff2", 400, "normal"),
        ("JetBrainsMono-Bold.woff2", 700, "normal"),
    ],
    "Poppins": [("Poppins-Bold.woff2", 700, "normal")],
    "Liberation Serif": [
        ("LiberationSerif-Bold.woff2", 700, "normal"),
        ("LiberationSerif-Italic.woff2", 400, "italic"),
    ],
}


def _style(
    sid: str,
    name: tuple[str, str],
    description: tuple[str, str],
    motif: str,
    palette: dict[str, str],
    display: str,
    body: str,
    mono: str = "JetBrains Mono",
    display_weight: int = 700,
    uppercase: bool = True,
    display_scale: float = 1.0,
) -> dict:
    return {
        "id": sid,
        "name": {"es": name[0], "en": name[1]},
        "description": {"es": description[0], "en": description[1]},
        "motif": motif,
        "palette": palette,
        "fonts": {"display": display, "body": body, "mono": mono},
        "display_weight": display_weight,
        "uppercase": uppercase,
        "display_scale": display_scale,
        "preview": f"/factory/{sid}.jpg",
    }


# Paleta: bg (fondo), bg2 (segundo tono del fondo), ink (texto), muted (texto secundario), accent y accent2
# (datos y realces), line (trazos finos), cap_bg / cap_ink (caja de subtítulos), hi (palabra que se dice).
STYLES: dict[str, dict] = {
    s["id"]: s
    for s in (
        _style(
            "neon-grid",
            ("Rejilla de neón", "Neon Grid"),
            (
                "Horizonte retro con suelo de rejilla en perspectiva, sol a franjas y cifras en cian.",
                "Retro horizon with a perspective grid floor, a striped sun and cyan figures.",
            ),
            "neon",
            {
                "bg": "#0d0221",
                "bg2": "#2a0b4a",
                "ink": "#fdf6ff",
                "muted": "#b9a3d9",
                "accent": "#21e6ff",
                "accent2": "#ff3ea5",
                "line": "#ff3ea5",
                "cap_bg": "rgba(13,2,33,0.82)",
                "cap_ink": "#fdf6ff",
                "hi": "#21e6ff",
            },
            "Anton",
            "Geist",
            display_weight=400,
            display_scale=1.12,
        ),
        _style(
            "paper-atlas",
            ("Atlas de papel", "Paper Atlas"),
            (
                "Papel envejecido, tinta sepia, meridianos y rutas punteadas como en un atlas antiguo.",
                "Aged paper, sepia ink, meridians and dotted routes like an old atlas.",
            ),
            "atlas",
            {
                "bg": "#efe3c8",
                "bg2": "#e2d1ac",
                "ink": "#3b2614",
                "muted": "#7a5c3c",
                "accent": "#a8321f",
                "accent2": "#2f5d62",
                "line": "#8a6a45",
                "cap_bg": "rgba(59,38,20,0.9)",
                "cap_ink": "#f6ecd6",
                "hi": "#ffcf6e",
            },
            "Liberation Serif",
            "Liberation Serif",
            uppercase=False,
        ),
        _style(
            "blueprint",
            ("Plano técnico", "Blueprint"),
            (
                "Azul de plano con retícula blanca, cotas, marcas de esquina y rótulos técnicos.",
                "Blueprint blue with a white grid, dimension lines, corner marks and technical labels.",
            ),
            "blueprint",
            {
                "bg": "#0b3d91",
                "bg2": "#0a347c",
                "ink": "#f2f7ff",
                "muted": "#a9c4ef",
                "accent": "#ffffff",
                "accent2": "#ffd34d",
                "line": "#8fb3f0",
                "cap_bg": "rgba(5,30,75,0.88)",
                "cap_ink": "#f2f7ff",
                "hi": "#ffd34d",
            },
            "JetBrains Mono",
            "JetBrains Mono",
            display_scale=0.82,
        ),
        _style(
            "phosphor",
            ("Fósforo verde", "Green Phosphor"),
            (
                "Terminal de fósforo verde: brillo, líneas de barrido y barras hechas de caracteres.",
                "Green phosphor terminal: glow, scanlines and bars made of characters.",
            ),
            "phosphor",
            {
                "bg": "#020a04",
                "bg2": "#06200d",
                "ink": "#7dff9a",
                "muted": "#3fa65a",
                "accent": "#c8ffd2",
                "accent2": "#ffb547",
                "line": "#1f7a37",
                "cap_bg": "rgba(0,0,0,0.85)",
                "cap_ink": "#7dff9a",
                "hi": "#ffffff",
            },
            "JetBrains Mono",
            "JetBrains Mono",
            display_scale=0.82,
        ),
        _style(
            "swiss",
            ("Retícula suiza", "Swiss Grid"),
            (
                "Blanco, negro y un rojo: columnas visibles, tipografía enorme y datos sin adornos.",
                "White, black and one red: visible columns, huge type and unadorned data.",
            ),
            "swiss",
            {
                "bg": "#f4f1ea",
                "bg2": "#e6e1d6",
                "ink": "#111111",
                "muted": "#5b5b5b",
                "accent": "#e3261b",
                "accent2": "#111111",
                "line": "#111111",
                "cap_bg": "#111111",
                "cap_ink": "#f4f1ea",
                "hi": "#ff5a4f",
            },
            "Geist",
            "Geist",
        ),
        _style(
            "chalkboard",
            ("Pizarra", "Chalkboard"),
            (
                "Pizarra verde con trazos de tiza, flechas a mano alzada y cifras subrayadas.",
                "Green chalkboard with chalk strokes, freehand arrows and underlined figures.",
            ),
            "chalk",
            {
                "bg": "#1f3b2d",
                "bg2": "#2a4a39",
                "ink": "#f3f1e7",
                "muted": "#b9c7b5",
                "accent": "#ffe27a",
                "accent2": "#ff9fb2",
                "line": "#e9efe0",
                "cap_bg": "rgba(16,32,24,0.86)",
                "cap_ink": "#f3f1e7",
                "hi": "#ffe27a",
            },
            "Poppins",
            "Geist",
        ),
        _style(
            "riso",
            ("Risografía", "Riso Print"),
            (
                "Impresión a dos tintas (rosa flúor y verde azulado) con semitono y registro desplazado.",
                "Two-ink print (fluoro pink and teal) with halftone dots and offset registration.",
            ),
            "riso",
            {
                "bg": "#f6f0e4",
                "bg2": "#efe6d4",
                "ink": "#1d4e5f",
                "muted": "#4f7c8a",
                "accent": "#ff4f9a",
                "accent2": "#1d8a99",
                "line": "#1d4e5f",
                "cap_bg": "#1d4e5f",
                "cap_ink": "#f6f0e4",
                "hi": "#ff8cc0",
            },
            "Anton",
            "Geist",
            display_weight=400,
            display_scale=1.12,
        ),
        _style(
            "orbital",
            ("Órbita", "Orbital"),
            (
                "Espacio profundo: estrellas, órbitas elípticas, el borde de un planeta y lecturas de telemetría.",
                "Deep space: stars, elliptical orbits, a planet's limb and telemetry readouts.",
            ),
            "orbital",
            {
                "bg": "#03050c",
                "bg2": "#0b1430",
                "ink": "#eef3ff",
                "muted": "#8b9cc7",
                "accent": "#7fd8ff",
                "accent2": "#ffb36b",
                "line": "#3b4e85",
                "cap_bg": "rgba(3,5,12,0.8)",
                "cap_ink": "#eef3ff",
                "hi": "#7fd8ff",
            },
            "Geist",
            "Geist",
        ),
        _style(
            "brutalist",
            ("Hormigón", "Concrete"),
            (
                "Gris hormigón, bloques negros, franjas de obra amarillas y cifras gigantes.",
                "Concrete grey, black blocks, yellow hazard stripes and giant figures.",
            ),
            "concrete",
            {
                "bg": "#b9b5ad",
                "bg2": "#a5a097",
                "ink": "#121212",
                "muted": "#3d3b37",
                "accent": "#ffd200",
                "accent2": "#121212",
                "line": "#121212",
                "cap_bg": "#121212",
                "cap_ink": "#ffd200",
                "hi": "#ffffff",
            },
            "Anton",
            "Geist",
            display_weight=400,
            display_scale=1.12,
        ),
    )
}

DEFAULT_STYLE = "neon-grid"


def public_styles(lang: str = "es") -> list[dict]:
    """Lo que ve la UI: id, nombre, descripción, paleta corta y vista previa."""
    lang = "es" if lang.startswith("es") else "en"
    return [
        {
            "id": s["id"],
            "name": s["name"][lang],
            "names": s["name"],
            "description": s["description"][lang],
            "descriptions": s["description"],
            "colors": [s["palette"][k] for k in ("bg", "ink", "accent", "accent2")],
            "preview": s["preview"],
        }
        for s in STYLES.values()
    ]
