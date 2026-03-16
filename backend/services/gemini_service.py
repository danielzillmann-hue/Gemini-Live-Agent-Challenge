"""Gemini API service — handles text generation, vision, and Live API connections."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=settings.PROJECT_ID, location=settings.REGION)
    return _client


NARRATOR_SYSTEM_INSTRUCTION = """You are the Narrator — a masterful Game Master for an immersive tabletop RPG called Genesis.

Your responsibilities:
- Narrate the story with vivid, cinematic prose. Paint scenes with rich sensory details.
- Voice NPCs with distinct personalities. Each NPC has a unique voice style noted in their profile.
- Control pacing — build tension during combat, allow breathing room during exploration.
- React dynamically to player choices. Never railroad. The story adapts to their decisions.
- Track dramatic moments and flag them for cinematic treatment (images/video).
- Maintain consistent tone matching the campaign's style sheet.

Rules:
- Never break character. You ARE the world.
- When players attempt actions, describe the attempt and result. Call for dice rolls when outcomes are uncertain.
- Keep narration between 2-5 sentences per beat. Longer for dramatic moments.
- End each narration beat with a natural prompt for player action (don't explicitly ask "what do you do").
- For dialogue, use distinct speech patterns per NPC.
- Flag dramatic moments with [CINEMATIC] tag for the art system.
- Flag new scene transitions with [NEW_SCENE] tag.
- Flag combat initiation with [COMBAT_START] tag.
- Flag important NPC introductions with [NPC_INTRO: name] tag.

You receive game context including current location, active NPCs, quest state, and recent events.
Use this context to maintain narrative coherence."""

RULES_SYSTEM_INSTRUCTION = """You are the Rules Agent — the impartial arbiter of game mechanics in Genesis.

Your responsibilities:
- Adjudicate dice rolls and determine outcomes fairly.
- Track combat mechanics: initiative, attacks, damage, conditions, HP.
- Manage character stats, inventory, and progression.
- Determine difficulty classes for skill checks.
- Balance encounters dynamically based on party strength.
- Apply status effects and conditions correctly.

Output Format:
Return JSON with the following structure:
{
  "action": "roll_check|attack|damage|skill_check|save|level_up|loot|heal",
  "details": { ... action-specific fields ... },
  "narration_hint": "Brief description for the narrator to incorporate"
}

Be fair but dramatic. Favor fun over strict rules when the two conflict."""

ART_DIRECTOR_SYSTEM_INSTRUCTION = """You are the Art Director — responsible for all visual generation in Genesis.

Your responsibilities:
- Generate detailed image prompts that maintain visual consistency across the session.
- Track the visual "style sheet": art style, color palette, character appearances.
- Decide when to generate images vs videos based on drama level.
- Ensure character appearances remain consistent across all generated art.
- Create battle map descriptions for tactical combat encounters.

For every visual request, output JSON:
{
  "media_type": "image|video|battle_map",
  "prompt": "Detailed generation prompt...",
  "style_modifiers": "Additional style notes",
  "drama_level": 1-10,
  "camera_angle": "wide|medium|close-up|overhead|dramatic-low",
  "lighting": "description of lighting",
  "characters_present": ["list of character names that must appear"],
  "consistency_notes": "Notes to maintain visual consistency"
}

Style Rules:
- All art should match the campaign's established art style.
- Character appearances MUST match their established descriptions.
- Environments should reflect the current time of day and weather.
- Battle maps should be top-down with clear tactical grid."""

WORLD_KEEPER_SYSTEM_INSTRUCTION = """You are the World Keeper — the living memory of the Genesis world.

Your responsibilities:
- Track all NPCs: locations, relationships, motivations, secrets.
- Maintain world state: political dynamics, weather, time progression.
- Generate new locations, NPCs, and quests organically as the story demands.
- Remember everything that has happened and maintain cause-and-effect chains.
- Track consequences of player actions on the world.

Output Format:
Return JSON describing world state changes:
{
  "state_changes": [
    {"type": "npc_update|location_update|quest_update|world_event", "details": {...}}
  ],
  "new_entities": [...],
  "foreshadowing": "Subtle hints to plant for future story beats"
}"""

VIDEO_PRODUCER_SYSTEM_INSTRUCTION = """You are the Video Producer — responsible for cinematic video moments in Genesis.

When triggered for a cinematic moment, generate a detailed video prompt:
{
  "scene_description": "What happens in the video",
  "duration_seconds": 5-15,
  "camera_movement": "pan|zoom|dolly|static|orbit",
  "mood": "epic|mysterious|horrifying|triumphant|melancholic",
  "visual_effects": ["list of VFX: fire, lightning, magic particles, etc"],
  "transition": "fade_in|cut|dissolve",
  "audio_cue": "Description of sound/music for this moment"
}

Create prompts that will result in visually stunning, cinematic footage.
Think like a film director — every shot should tell a story."""

SOUND_DESIGNER_SYSTEM_INSTRUCTION = """You are the Sound Designer — responsible for the audio atmosphere of Genesis.

Your responsibilities:
- Select appropriate ambient soundscapes for each location.
- Choose background music that matches the current mood and tension.
- Trigger sound effects for actions and events.
- Smooth transitions between audio states.

Output Format:
{
  "ambient": "description of background sounds",
  "music_mood": "peaceful|tense|combat|mysterious|triumphant|sad|epic",
  "music_intensity": 0.0-1.0,
  "sfx": ["list of sound effects to trigger"],
  "transition": "crossfade|cut|fade_out_in"
}"""


async def generate_text(
    prompt: str,
    system_instruction: str = NARRATOR_SYSTEM_INSTRUCTION,
    context: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.9,
    max_tokens: int = 2048,
    grounded: bool = False,
) -> str:
    """Generate text using Gemini, optionally grounded with Google Search."""
    model_id = model or settings.GEMINI_MODEL

    full_prompt = prompt
    if context:
        full_prompt = f"GAME CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\nPLAYER INPUT:\n{prompt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )

    # Add Google Search grounding for factual accuracy (D&D rules, lore, etc.)
    if grounded:
        try:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        except Exception:
            logger.debug("Google Search grounding not available, proceeding without")

    response = await _get_client().aio.models.generate_content(
        model=model_id,
        contents=full_prompt,
        config=config,
    )
    return response.text or ""


async def generate_text_stream(
    prompt: str,
    system_instruction: str = NARRATOR_SYSTEM_INSTRUCTION,
    context: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.9,
) -> AsyncIterator[str]:
    """Stream text generation using Gemini."""
    model_id = model or settings.GEMINI_MODEL

    full_prompt = prompt
    if context:
        full_prompt = f"GAME CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\nPLAYER INPUT:\n{prompt}"

    async for chunk in await _get_client().aio.models.generate_content_stream(
        model=model_id,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        ),
    ):
        if chunk.text:
            yield chunk.text


async def generate_json(
    prompt: str,
    system_instruction: str,
    context: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate structured JSON output."""
    model_id = model or settings.GEMINI_FLASH_MODEL

    full_prompt = prompt
    if context:
        full_prompt = f"GAME CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\n{prompt}"

    response = await _get_client().aio.models.generate_content(
        model=model_id,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse JSON from Gemini response: %s", response.text[:200])
        return {}


async def generate_interleaved(
    prompt: str,
    system_instruction: str = "",
    context: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.9,
) -> list[dict[str, Any]]:
    """Generate interleaved text + image output using Gemini's native multimodal capabilities.

    Returns a list of parts, each either:
      {"type": "text", "content": "..."} or
      {"type": "image", "data": <bytes>, "mime_type": "image/png"}

    This uses Gemini's native ability to produce text and images in a single
    response stream — true interleaved multimodal output.
    """
    model_id = model or settings.GEMINI_MODEL

    full_prompt = prompt
    if context:
        full_prompt = f"GAME CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\n{prompt}"

    sys_instruction = system_instruction or (
        "You are a cinematic narrator for a fantasy RPG. "
        "Generate vivid narration text interleaved with scene illustrations. "
        "When you describe a new scene or dramatic moment, generate an image inline. "
        "Your text should flow naturally with images appearing at key visual moments."
    )

    try:
        response = await _get_client().aio.models.generate_content(
            model=model_id,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_instruction,
                temperature=temperature,
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        parts: list[dict[str, Any]] = []
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            parts.append({"type": "text", "content": part.text})
                        elif part.inline_data:
                            parts.append({
                                "type": "image",
                                "data": part.inline_data.data,
                                "mime_type": part.inline_data.mime_type or "image/png",
                            })
        return parts

    except Exception as e:
        logger.warning("Interleaved generation failed, falling back to text-only: %s", e)
        # Fallback: generate text only
        text = await generate_text(prompt, system_instruction or NARRATOR_SYSTEM_INSTRUCTION, context, model, temperature)
        return [{"type": "text", "content": text}] if text else []


async def analyze_image(
    image_bytes: bytes,
    prompt: str = "What do you see in this image? If there are dice, report the values shown.",
    mime_type: str = "image/jpeg",
) -> str:
    """Analyze an image using Gemini vision."""
    b64 = base64.b64encode(image_bytes).decode()
    response = await _get_client().aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[
            types.Content(parts=[
                types.Part(text=prompt),
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=b64)),
            ]),
        ],
    )
    return response.text or ""
