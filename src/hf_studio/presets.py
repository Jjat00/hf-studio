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
    # Apps: herramientas de un solo paso al estilo de las de Higgsfield, sobre modelos de edición del catálogo.
    {
        "slug": "relight",
        "title": "Relight",
        "description": "Change the light of a photo: direction, color and mood, keeping the subject intact.",
        "category": "Apps",
        "output": "image",
        "model": "xai/grok-imagine-image-2.0",
        "cover": "/art/image-edit.webp",
        "variables": [
            {"key": "photo", "label": "Photo", "type": "image", "required": True},
            {
                "key": "light",
                "label": "Light",
                "type": "select",
                "options": [
                    "warm golden hour sunlight from the side",
                    "soft studio key light with a gentle rim light",
                    "neon pink and blue rim lights",
                    "dramatic low-key spotlight from above",
                    "soft overcast daylight",
                    "warm candlelight",
                ],
                "default": "warm golden hour sunlight from the side",
            },
        ],
        "template": {
            "image_urls": ["{{photo}}"],
            "prompt": "Relight this photo with {{light}}. Keep the subject, identity, pose, framing and background exactly the same; only change the lighting, shadows, highlights and reflections so they look physically real.",
            "aspect_ratio": "auto",
        },
    },
    {
        "slug": "color-palette",
        "title": "Change color palette",
        "description": "Regrade a photo with a new palette and mood without touching what is in it.",
        "category": "Apps",
        "output": "image",
        "model": "xai/grok-imagine-image-2.0",
        "cover": "/art/text-to-image.webp",
        "variables": [
            {"key": "photo", "label": "Photo", "type": "image", "required": True},
            {
                "key": "palette",
                "label": "Palette",
                "type": "select",
                "options": [
                    "teal and orange blockbuster grade",
                    "warm vintage film with faded blacks",
                    "cool desaturated nordic tones",
                    "soft pastel tones",
                    "high contrast black and white",
                    "neon cyberpunk magenta and cyan",
                ],
                "default": "teal and orange blockbuster grade",
            },
        ],
        "template": {
            "image_urls": ["{{photo}}"],
            "prompt": "Color grade this photo with a {{palette}}. Keep every element, the composition and the people exactly the same; only change colors, tones and overall mood.",
            "aspect_ratio": "auto",
        },
    },
    {
        "slug": "face-swap",
        "title": "Face swap",
        "description": "Put a face from one photo into another, matching light, angle and skin tone.",
        "category": "Apps",
        "output": "image",
        "model": "marketing-studio/image/sunburst",
        "cover": "/art/references.webp",
        "variables": [
            {"key": "photo", "label": "Target photo", "type": "image", "required": True},
            {"key": "face", "label": "Face to use", "type": "image", "required": True},
            {
                "key": "ratio",
                "label": "Format",
                "type": "select",
                "options": ["3:4", "1:1", "4:3", "9:16", "16:9"],
                "default": "3:4",
            },
        ],
        "template": {
            "image_urls": ["{{photo}}", "{{face}}"],
            "prompt": "Replace the face of the person in the first image with the face of the person in the second image. Keep the body, hair, outfit, pose, background and lighting of the first image; match the head angle, skin tone and light so the result looks like an untouched photograph.",
            "aspect_ratio": "{{ratio}}",
            "resolution": "2k",
        },
    },
    {
        "slug": "character-swap",
        "title": "Character swap",
        "description": "Replace the person in a scene with your character, keeping pose, place and light.",
        "category": "Apps",
        "output": "image",
        "model": "marketing-studio/image/sunburst",
        "cover": "/art/object-swap.webp",
        "variables": [
            {"key": "scene", "label": "Scene", "type": "image", "required": True},
            {"key": "character", "label": "Your character", "type": "image", "required": True},
            {
                "key": "ratio",
                "label": "Format",
                "type": "select",
                "options": ["3:4", "1:1", "4:3", "9:16", "16:9"],
                "default": "3:4",
            },
        ],
        "template": {
            "image_urls": ["{{scene}}", "{{character}}"],
            "prompt": "Replace the person in the first image with the character from the second image: same face, body, hair and outfit as the second image. Keep the pose, framing, background and lighting of the first image so it looks like one real photograph.",
            "aspect_ratio": "{{ratio}}",
            "resolution": "2k",
        },
    },
    {
        "slug": "reframe-image",
        "title": "Reframe image",
        "description": "Change the aspect ratio of a photo by extending it naturally beyond its edges.",
        "category": "Apps",
        "output": "image",
        "model": "xai/grok-imagine-image-2.0",
        "cover": "/art/frames.webp",
        "variables": [
            {"key": "photo", "label": "Photo", "type": "image", "required": True},
            {
                "key": "ratio",
                "label": "New format",
                "type": "select",
                "options": ["9:16", "16:9", "1:1", "4:3", "3:4", "2:1"],
                "default": "9:16",
            },
        ],
        "template": {
            "image_urls": ["{{photo}}"],
            "prompt": "Outpaint this photo to the new frame: keep the original content unchanged and centered, and extend the scene naturally beyond its edges with matching perspective, light and texture.",
            "aspect_ratio": "{{ratio}}",
        },
    },
    {
        "slug": "video-relight",
        "title": "Video relight",
        "description": "Relight a video clip with a new light setup while keeping its motion.",
        "category": "Apps",
        "output": "video",
        "model": "bytedance/seedance-2.5/video-edit",
        "cover": "/art/video-edit.webp",
        "variables": [
            {"key": "video", "label": "Video", "type": "video", "required": True},
            {
                "key": "light",
                "label": "Light",
                "type": "select",
                "options": [
                    "warm golden hour sunlight from the side",
                    "neon pink and blue rim lights",
                    "dramatic low-key spotlight from above",
                    "soft overcast daylight",
                    "moonlight at night",
                ],
                "default": "warm golden hour sunlight from the side",
            },
        ],
        "template": {
            "video_url": "{{video}}",
            "prompt": "Relight the whole video with {{light}}. Keep the people, motion, camera, framing and timing exactly the same; only change lighting, shadows and reflections.",
            "resolution": "720p",
            "generate_audio": False,
        },
    },
    {
        "slug": "video-color-grade",
        "title": "Video color grade",
        "description": "Give a clip a new color palette and mood, shot by shot.",
        "category": "Apps",
        "output": "video",
        "model": "bytedance/seedance-2.5/video-edit",
        "cover": "/art/video-extend.webp",
        "variables": [
            {"key": "video", "label": "Video", "type": "video", "required": True},
            {
                "key": "palette",
                "label": "Palette",
                "type": "select",
                "options": [
                    "teal and orange blockbuster grade",
                    "warm vintage film with faded blacks",
                    "cool desaturated nordic tones",
                    "high contrast black and white",
                    "neon cyberpunk magenta and cyan",
                ],
                "default": "teal and orange blockbuster grade",
            },
        ],
        "template": {
            "video_url": "{{video}}",
            "prompt": "Color grade the whole video with a {{palette}}. Keep the content, motion, camera and timing exactly the same; only change colors, tones and mood.",
            "resolution": "720p",
            "generate_audio": False,
        },
    },
    # AI Influencer: personaje por rasgos (Soul 2.0) y luego su video de movimiento.
    {
        "slug": "ai-influencer",
        "title": "AI Influencer",
        "description": "Build your own character from its traits: type, build, hair, style, age and more.",
        "category": "Influencer",
        "output": "image",
        "model": "higgsfield-ai/soul/v2/standard",
        "cover": "/art/text-to-image.webp",
        "variables": [
            {
                "key": "type",
                "label": "Character type",
                "type": "select",
                "options": [
                    "human",
                    "bold-looking human",
                    "extreme stylized human",
                    "insect-headed humanoid",
                    "frog-headed humanoid",
                    "cat-headed humanoid",
                    "dog-headed humanoid",
                    "rodent-headed humanoid",
                    "bird-headed humanoid",
                ],
                "default": "human",
            },
            {
                "key": "gender",
                "label": "Gender",
                "type": "select",
                "options": ["woman", "man", "non-binary person"],
                "default": "woman",
            },
            {
                "key": "build",
                "label": "Build",
                "type": "select",
                "options": [
                    "slim",
                    "athletic",
                    "average",
                    "curvy",
                    "plus-size",
                    "muscular",
                    "ultra muscular",
                ],
                "default": "athletic",
            },
            {
                "key": "hair",
                "label": "Hairstyle",
                "type": "select",
                "options": [
                    "long straight hair",
                    "curly afro",
                    "blunt bob with bangs",
                    "buzz cut",
                    "slicked-back hair",
                    "messy wolf cut",
                    "long braids",
                    "bald head",
                ],
                "default": "long straight hair",
            },
            {
                "key": "hair_color",
                "label": "Hair color",
                "type": "select",
                "options": [
                    "black",
                    "brown",
                    "platinum blonde",
                    "copper red",
                    "silver grey",
                    "pastel pink",
                    "electric blue",
                ],
                "default": "brown",
            },
            {
                "key": "style",
                "label": "Style",
                "type": "select",
                "options": [
                    "streetwear",
                    "quiet luxury",
                    "y2k",
                    "tailored suit",
                    "gorpcore",
                    "vintage 70s",
                    "avant-garde fashion",
                    "sporty athleisure",
                ],
                "default": "streetwear",
            },
            {
                "key": "ethnicity",
                "label": "Ethnicity",
                "type": "select",
                "options": [
                    "Latin American",
                    "East Asian",
                    "South Asian",
                    "Black",
                    "Middle Eastern",
                    "white European",
                ],
                "default": "Latin American",
            },
            {
                "key": "age",
                "label": "Age",
                "type": "select",
                "options": ["early 20s", "30s", "50s", "70s"],
                "default": "early 20s",
            },
            {
                "key": "details",
                "label": "Extra details",
                "type": "text",
                "placeholder": "freckles, gold septum ring, mustache",
            },
            {
                "key": "ratio",
                "label": "Format",
                "type": "select",
                "options": ["3:4", "9:16", "1:1"],
                "default": "3:4",
            },
        ],
        "template": {
            "prompt": "Full-body fashion portrait of a {{age}} {{ethnicity}} {{gender}}, {{type}}, {{build}} build, {{hair_color}} {{hair}}, wearing {{style}} outfit, {{details}}, standing in a clean white photo studio, confident pose, sharp focus, editorial lookbook photography",
            "aspect_ratio": "{{ratio}}",
            "resolution": "1080p",
        },
    },
    {
        "slug": "influencer-motion",
        "title": "Influencer motion",
        "description": "Turn your character into a ready-to-post video with a viral motion.",
        "category": "Influencer",
        "output": "video",
        "model": "bytedance/seedance-2.0/image-to-video",
        "cover": "/art/motion.webp",
        "variables": [
            {"key": "character", "label": "Character image", "type": "image", "required": True},
            {
                "key": "motion",
                "label": "Motion",
                "type": "select",
                "options": [
                    "walks confidently toward the camera",
                    "does a runway catwalk turn",
                    "dances to an upbeat trending beat",
                    "talks to the camera like a vlog",
                    "slow-motion hair flip and smile",
                    "jumps and lands in a power pose",
                ],
                "default": "walks confidently toward the camera",
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
            "image_url": "{{character}}",
            "prompt": "The character {{motion}}, same face and outfit, smooth realistic motion, social media video",
            "duration": 5,
            "resolution": "{{resolution}}",
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
