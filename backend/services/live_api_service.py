"""Gemini Live API service — real-time voice conversation with NPCs.

Enables players to have spoken conversations with NPCs using Gemini's
native audio capabilities. The AI hears the player's voice and responds
with a character-appropriate voice in real-time.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

LIVE_MODEL = "gemini-live-2.5-flash-native-audio"


async def create_live_session(
    npc_name: str = "Narrator",
    npc_personality: str = "",
    npc_voice_style: str = "neutral",
    game_context: str = "",
) -> Any:
    """Create a Gemini Live API session for real-time voice conversation.

    Returns an async context manager for the live session.
    """
    client = genai.Client(
        vertexai=True,
        project=settings.PROJECT_ID,
        location=settings.REGION,
        http_options=types.HttpOptions(api_version="v1beta1"),
    )

    # Build system instruction for this NPC
    voice_descriptions = {
        "gruff": "Speak in a deep, rough, gravelly voice. Short sentences. Blunt.",
        "noble": "Speak eloquently with refined vocabulary. Measured pace. Authoritative.",
        "mysterious": "Speak slowly and cryptically. Use metaphors. Whisper at times.",
        "cheerful": "Speak energetically with warmth. Laugh occasionally. Enthusiastic.",
        "neutral": "Speak naturally and conversationally.",
        "old": "Speak slowly and wisely. Raspy voice. Reference the past often.",
        "young": "Speak quickly with excitement. Energetic. Use informal language.",
    }

    voice_desc = voice_descriptions.get(npc_voice_style, voice_descriptions["neutral"])

    system_instruction = (
        f"You are {npc_name}, a character in a fantasy RPG called Genesis. "
        f"You are having a real-time voice conversation with a player. "
        f"Stay in character at all times. {voice_desc} "
        f"Personality: {npc_personality or 'A helpful character in the game world.'}\n\n"
        f"GAME CONTEXT:\n{game_context}\n\n"
        f"Respond naturally as this character would. Keep responses concise (2-3 sentences) "
        f"since this is a real-time conversation. React to what the player says. "
        f"If they ask about the world, share what your character would know. "
        f"If they ask for help, respond in character."
    )

    try:
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=system_instruction)]
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
    except (AttributeError, TypeError):
        # Fallback if AudioTranscriptionConfig not available in SDK version
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=system_instruction)]
            ),
        )

    return client.aio.live.connect(model=LIVE_MODEL, config=config)


async def process_live_audio(
    session: Any,
    audio_chunk: bytes,
) -> bytes | None:
    """Send an audio chunk to the live session and get audio response.

    Args:
        session: Active Gemini Live API session
        audio_chunk: Raw PCM audio (16-bit, 16kHz, little-endian)

    Returns:
        Response audio bytes or None
    """
    try:
        await session.send_realtime_input(
            audio=types.Blob(
                data=audio_chunk,
                mime_type="audio/pcm;rate=16000",
            )
        )

        # Collect response audio
        response_audio = bytearray()
        async for response in session.receive():
            if response.server_content and response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        response_audio.extend(part.inline_data.data)
            # Check if the turn is complete
            if response.server_content and response.server_content.turn_complete:
                break

        return bytes(response_audio) if response_audio else None

    except Exception as e:
        logger.warning("Live API audio processing failed: %s", e)
        return None
