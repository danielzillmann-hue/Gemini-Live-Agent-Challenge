"""Media generation service — images (Imagen), videos (Veo), and audio."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from google.genai import types

from config import settings
from services.gemini_service import _get_client

logger = logging.getLogger(__name__)


# ── Image Generation (Imagen) ─────────────────────────────────────────────

async def generate_image(
    prompt: str,
    style_modifier: str = "",
    aspect_ratio: str = "16:9",
    negative_prompt: str = "blurry, low quality, text, watermark, signature, deformed",
) -> bytes | None:
    """Generate an image using Imagen.

    Returns raw image bytes or None on failure.
    """
    full_prompt = f"{prompt}. {style_modifier}. {settings.ART_STYLE}".strip(". ")

    try:
        response = await _get_client().aio.models.generate_images(
            model=settings.IMAGEN_MODEL,
            prompt=full_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
                negative_prompt=negative_prompt,
            ),
        )
        if response.generated_images:
            return response.generated_images[0].image.image_bytes
    except Exception:
        logger.exception("Image generation failed for prompt: %s", prompt[:100])
    return None


async def generate_scene_image(
    scene_description: str,
    characters: list[str] | None = None,
    time_of_day: str = "day",
    weather: str = "clear",
    camera_angle: str = "wide",
) -> bytes | None:
    """Generate a scene illustration with context-aware prompting."""
    char_desc = ""
    if characters:
        char_desc = f"Characters present: {', '.join(characters)}. "

    atmosphere = {
        "morning": "warm golden morning light, long shadows",
        "afternoon": "bright daylight, clear visibility",
        "evening": "warm sunset colors, orange and purple sky",
        "night": "moonlit, dark atmosphere, dramatic shadows, torch/firelight",
    }
    weather_desc = {
        "clear": "",
        "rain": "heavy rain, wet surfaces, dramatic storm clouds",
        "fog": "thick fog, limited visibility, mysterious atmosphere",
        "snow": "falling snow, cold blue lighting, frost-covered surfaces",
        "storm": "lightning, dark storm clouds, violent wind",
    }

    prompt = (
        f"{scene_description}. {char_desc}"
        f"{atmosphere.get(time_of_day, '')}. "
        f"{weather_desc.get(weather, '')}. "
        f"Camera angle: {camera_angle}."
    )

    return await generate_image(prompt)


async def generate_character_portrait(
    name: str,
    race: str,
    character_class: str,
    appearance: str,
    mood: str = "determined",
) -> bytes | None:
    """Generate a character portrait."""
    prompt = (
        f"Fantasy character portrait of {name}, a {race} {character_class}. "
        f"Appearance: {appearance}. Expression: {mood}. "
        f"Detailed face, upper body, dramatic lighting, painterly style. "
        f"Portrait orientation, dark background with subtle magical elements."
    )
    return await generate_image(prompt, aspect_ratio="9:16")


async def generate_battle_map(
    location_description: str,
    terrain_features: list[str] | None = None,
) -> bytes | None:
    """Generate a top-down tactical battle map."""
    features = ""
    if terrain_features:
        features = f"Terrain features: {', '.join(terrain_features)}. "

    prompt = (
        f"Top-down tactical battle map, grid overlay, tabletop RPG style. "
        f"Location: {location_description}. {features}"
        f"Clear terrain markings, high contrast, clean design. "
        f"Overhead view, square grid, fantasy cartography style."
    )
    return await generate_image(prompt, aspect_ratio="1:1")


async def generate_world_map(
    setting_description: str,
    locations: list[str] | None = None,
) -> bytes | None:
    """Generate a fantasy world map."""
    loc_text = ""
    if locations:
        loc_text = f"Key locations to include: {', '.join(locations)}. "

    prompt = (
        f"Fantasy world map, parchment style, hand-drawn cartography. "
        f"{setting_description}. {loc_text}"
        f"Detailed coastlines, mountains, forests, rivers, labeled cities. "
        f"Aged paper texture, compass rose, decorative border. "
        f"Top-down view, full continent visible."
    )
    return await generate_image(prompt, aspect_ratio="16:9")


# ── Video Generation (Veo) ────────────────────────────────────────────────

async def generate_video(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
    style_modifier: str = "",
) -> bytes | None:
    """Generate a video using Veo.

    Returns raw video bytes or None on failure.
    Note: Video generation can take 30-120 seconds.
    """
    full_prompt = f"{prompt}. {style_modifier}. {settings.ART_STYLE}, cinematic quality".strip(". ")

    try:
        operation = await _get_client().aio.models.generate_videos(
            model=settings.VEO_MODEL,
            prompt=full_prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
            ),
        )

        # Poll for completion
        max_wait = 180
        start = time.time()
        while time.time() - start < max_wait:
            result = await operation.result()
            if result and result.generated_videos:
                video = result.generated_videos[0]
                if video.video and video.video.video_bytes:
                    return video.video.video_bytes
                break
            await asyncio.sleep(5)

    except Exception:
        logger.exception("Video generation failed for prompt: %s", prompt[:100])
    return None


async def generate_cinematic(
    scene_description: str,
    mood: str = "epic",
    camera_movement: str = "slow dolly in",
    visual_effects: list[str] | None = None,
) -> bytes | None:
    """Generate a cinematic video cutscene."""
    vfx = ""
    if visual_effects:
        vfx = f"Visual effects: {', '.join(visual_effects)}. "

    prompt = (
        f"Cinematic fantasy scene: {scene_description}. "
        f"Mood: {mood}. Camera: {camera_movement}. {vfx}"
        f"Film grain, dramatic lighting, depth of field. "
        f"High production value, movie quality."
    )
    return await generate_video(prompt, duration_seconds=8)


async def generate_session_recap_video(
    events_summary: str,
    campaign_name: str,
) -> bytes | None:
    """Generate a 'previously on...' recap video."""
    prompt = (
        f"Epic fantasy montage recap for '{campaign_name}'. "
        f"Key events: {events_summary}. "
        f"Dramatic transitions between scenes, cinematic quality, "
        f"dark fantasy atmosphere, sweeping camera movements. "
        f"Title card style with dramatic lighting."
    )
    return await generate_video(prompt, duration_seconds=15)


# ── Media Decision Engine ─────────────────────────────────────────────────

def should_generate_media(drama_level: int, event_type: str) -> dict[str, Any]:
    """Decide what media to generate based on drama level and event type.

    Returns a dict with media generation instructions.
    """
    if drama_level <= 2:
        if event_type == "new_scene":
            return {"generate": True, "type": "image", "priority": "low"}
        return {"generate": False}

    if drama_level <= 5:
        return {
            "generate": True,
            "type": "image",
            "priority": "medium",
            "aspect_ratio": "16:9",
        }

    if drama_level <= 7:
        return {
            "generate": True,
            "type": "image",
            "priority": "high",
            "aspect_ratio": "16:9",
            "also_video": event_type in ("boss_reveal", "plot_twist", "combat_start"),
        }

    # Drama level 8-10: Full cinematic treatment
    return {
        "generate": True,
        "type": "video",
        "priority": "critical",
        "duration": min(5 + (drama_level - 7) * 3, 15),
        "fallback_image": True,  # Generate image while video renders
    }
