"""Presets (recetas): un modelo + una plantilla de entrada con variables `{{nombre}}`.

Una plantilla es la entrada del modelo; cualquier cadena puede contener `{{variable}}`. Si la cadena
es exactamente `{{variable}}`, se sustituye por el valor crudo (lista de URLs, número…), no por texto.
Los presets de serie viven aquí; los de cada cliente, en la base de datos (modelo `Preset`).
"""

from __future__ import annotations

import re
from typing import Any

VAR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

# Tipos de variable: text, textarea, select, image, images, video, number.
BUILTIN: list[dict[str, Any]] = [
    {
        "slug": "hero-shot",
        "title": "Product hero shot",
        "description": "Premium studio packshot of your product, ready for a landing page or an ad.",
        "category": "Product",
        "output": "image",
        "model": "higgsfield-ai/soul/v2/standard",
        "cover": "/art/object-swap.webp",
        "variables": [
            {
                "key": "product",
                "label": "Product",
                "type": "text",
                "required": True,
                "placeholder": "matte black wireless headphones",
            },
            {
                "key": "surface",
                "label": "Surface",
                "type": "select",
                "options": ["polished concrete", "white marble", "dark wood", "reflective glass"],
                "default": "polished concrete",
            },
            {
                "key": "ratio",
                "label": "Format",
                "type": "select",
                "options": ["1:1", "4:3", "16:9", "9:16"],
                "default": "4:3",
            },
        ],
        "template": {
            "prompt": "Premium studio hero shot of {{product}} on {{surface}}, soft key light with a crisp rim light, shallow depth of field, clean negative space, commercial product photography, 85mm",
            "aspect_ratio": "{{ratio}}",
            "resolution": "1080p",
        },
    },
    {
        "slug": "reel-cover",
        "title": "Reel cover",
        "description": "Vertical 9:16 cover with space for a headline, in the style you choose.",
        "category": "Social",
        "output": "image",
        "model": "z-image/turbo",
        "cover": "/art/text-to-image.webp",
        "variables": [
            {
                "key": "subject",
                "label": "Subject",
                "type": "text",
                "required": True,
                "placeholder": "a barista pouring latte art",
            },
            {
                "key": "mood",
                "label": "Mood",
                "type": "select",
                "options": ["bold and colorful", "moody cinematic", "clean minimal", "retro film"],
                "default": "moody cinematic",
            },
        ],
        "template": {
            "prompt": "Vertical social media cover photo of {{subject}}, {{mood}}, strong focal point, generous empty space in the upper third for a headline, no text",
            "aspect_ratio": "9:16",
            "resolution": "2k",
        },
    },
    {
        "slug": "cinematic-establishing",
        "title": "Cinematic establishing shot",
        "description": "Sweeping opening shot of any place, with camera move and ambient sound.",
        "category": "Cinematic",
        "output": "video",
        "model": "bytedance/seedance-2.0/text-to-video",
        "cover": "/art/explore-hero.webp",
        "variables": [
            {
                "key": "place",
                "label": "Place",
                "type": "text",
                "required": True,
                "placeholder": "a foggy fishing village at dawn",
            },
            {
                "key": "move",
                "label": "Camera",
                "type": "select",
                "options": [
                    "slow aerial push-in",
                    "lateral tracking shot",
                    "crane up reveal",
                    "static wide with drifting clouds",
                ],
                "default": "slow aerial push-in",
            },
            {
                "key": "resolution",
                "label": "Quality",
                "type": "select",
                "options": ["480p", "720p", "1080p"],
                "default": "720p",
            },
        ],
        "template": {
            "prompt": "Cinematic establishing shot of {{place}}, {{move}}, anamorphic lens, natural film grain, atmospheric light",
            "duration": 5,
            "resolution": "{{resolution}}",
            "aspect_ratio": "21:9",
            "generate_audio": True,
        },
    },
    {
        "slug": "photo-to-life",
        "title": "Bring a photo to life",
        "description": "Subtle, natural motion for a portrait or a still: breathing, hair, light.",
        "category": "Animate",
        "output": "video",
        "model": "bytedance/seedance-2.0/image-to-video",
        "cover": "/art/text-to-video.webp",
        "variables": [
            {"key": "photo", "label": "Photo", "type": "image", "required": True},
            {
                "key": "detail",
                "label": "What should move",
                "type": "text",
                "placeholder": "hair moving in the wind, gentle smile",
            },
            {
                "key": "resolution",
                "label": "Quality",
                "type": "select",
                "options": ["480p", "720p", "1080p"],
                "default": "480p",
            },
        ],
        "template": {
            "image_url": "{{photo}}",
            "prompt": "Subtle natural motion, {{detail}}, camera almost still, realistic",
            "duration": 5,
            "resolution": "{{resolution}}",
            "generate_audio": False,
        },
    },
    {
        "slug": "morph",
        "title": "Morph between two frames",
        "description": "A seamless transition from one image to another.",
        "category": "Animate",
        "output": "video",
        "model": "bytedance/seedance-2.0/image-to-video",
        "cover": "/art/frames.webp",
        "variables": [
            {"key": "start", "label": "Start frame", "type": "image", "required": True},
            {"key": "end", "label": "End frame", "type": "image", "required": True},
            {
                "key": "style",
                "label": "Transition",
                "type": "select",
                "options": ["smooth morph", "camera push through", "light burst", "liquid transformation"],
                "default": "smooth morph",
            },
        ],
        "template": {
            "image_url": "{{start}}",
            "end_image_url": "{{end}}",
            "prompt": "{{style}} from the first frame to the last frame, continuous shot",
            "duration": 5,
            "resolution": "480p",
        },
    },
    {
        "slug": "product-orbit",
        "title": "Product 360 orbit",
        "description": "Slow orbit around your product photo, like a commercial turntable.",
        "category": "Product",
        "output": "video",
        "model": "bytedance/seedance-2.0/image-to-video",
        "cover": "/art/video-extend.webp",
        "variables": [
            {"key": "photo", "label": "Product photo", "type": "image", "required": True},
            {
                "key": "resolution",
                "label": "Quality",
                "type": "select",
                "options": ["480p", "720p", "1080p"],
                "default": "720p",
            },
        ],
        "template": {
            "image_url": "{{photo}}",
            "prompt": "Slow smooth 360 degree orbit around the product, studio lighting, reflections moving across the surface, commercial turntable shot",
            "duration": 5,
            "resolution": "{{resolution}}",
            "generate_audio": False,
        },
    },
    {
        "slug": "dance-transfer",
        "title": "Dance transfer",
        "description": "Your character performs the moves from any dance video.",
        "category": "Motion",
        "output": "video",
        "model": "kling-video/v3/motion-control/std",
        "cover": "/art/motion.webp",
        "variables": [
            {"key": "character", "label": "Character image", "type": "image", "required": True},
            {"key": "dance", "label": "Dance video (3–30 s)", "type": "video", "required": True},
        ],
        "template": {"image_url": "{{character}}", "video_url": "{{dance}}", "keep_original_sound": "yes"},
    },
    {
        "slug": "ad-multiplier",
        "title": "Ad multiplier",
        "description": "Swap the product in an existing ad and keep everything else.",
        "category": "Product",
        "output": "video",
        "model": "higgsfiled/genjutsu/object-swap/v1.0",
        "cover": "/art/object-swap.webp",
        "variables": [
            {"key": "ad", "label": "Original ad (4–30 s)", "type": "video", "required": True},
            {"key": "product", "label": "New product", "type": "images", "required": True},
            {
                "key": "note",
                "label": "What to replace",
                "type": "text",
                "placeholder": "replace the bottle in her hand",
            },
        ],
        "template": {
            "video_url": "{{ad}}",
            "image_urls": "{{product}}",
            "prompt": "{{note}}",
            "resolution": "720p",
        },
    },
    {
        "slug": "character-in-scene",
        "title": "Character in a new scene",
        "description": "Put the characters from your reference images into a new shot.",
        "category": "Cinematic",
        "output": "video",
        "model": "bytedance/seedance-2.0/reference-to-video",
        "cover": "/art/references.webp",
        "variables": [
            {"key": "refs", "label": "Character references", "type": "images", "required": True},
            {
                "key": "scene",
                "label": "Scene",
                "type": "textarea",
                "required": True,
                "placeholder": "walking through a neon market at night, handheld camera",
            },
        ],
        "template": {
            "image_urls": "{{refs}}",
            "prompt": "{{scene}}",
            "duration": 5,
            "resolution": "480p",
            "aspect_ratio": "16:9",
        },
    },
]


def variables_in(template: Any) -> set[str]:
    if isinstance(template, str):
        return set(VAR.findall(template))
    if isinstance(template, dict):
        return set().union(*(variables_in(v) for v in template.values())) if template else set()
    if isinstance(template, list):
        return set().union(*(variables_in(v) for v in template)) if template else set()
    return set()


def render(template: Any, values: dict[str, Any]) -> Any:
    """Sustituye variables; las vacías desaparecen (claves con valor vacío se omiten)."""
    if isinstance(template, str):
        whole = VAR.fullmatch(template.strip())
        if whole:
            return values.get(whole.group(1))
        text = VAR.sub(lambda m: str(values.get(m.group(1)) or ""), template)
        return re.sub(r"\s*,\s*,", ",", re.sub(r"\s{2,}", " ", text)).strip(" ,")
    if isinstance(template, dict):
        out = {}
        for k, v in template.items():
            r = render(v, values)
            if r not in (None, "", []):
                out[k] = r
        return out
    if isinstance(template, list):
        return [render(v, values) for v in template]
    return template


def resolve_values(preset: dict, given: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Aplica defaults y devuelve (valores, variables obligatorias que faltan)."""
    values, missing = {}, []
    for var in preset["variables"]:
        value = given.get(var["key"], var.get("default"))
        if var.get("type") == "images" and isinstance(value, str):
            value = [value]
        if value in (None, "", []):
            if var.get("required"):
                missing.append(var["key"])
            continue
        values[var["key"]] = value
    return values, missing
