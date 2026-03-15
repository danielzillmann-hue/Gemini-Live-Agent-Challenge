"""ADK tool functions — exposed to the Genesis agent for game interactions."""

from __future__ import annotations

from typing import Any

from game.engine import roll_d20


# ── Narration & Media ─────────────────────────────────────────────────────

def narrate_scene(
    session_id: str, scene_description: str, mood: str = "neutral"
) -> dict[str, Any]:
    """Generate narration for a scene transition or story beat."""
    return {"action": "narrate", "session_id": session_id, "scene": scene_description, "mood": mood}


def generate_scene_art(
    session_id: str, scene_description: str,
    characters_present: list[str] | None = None, camera_angle: str = "wide",
) -> dict[str, Any]:
    """Request scene illustration generation."""
    return {"action": "generate_image", "session_id": session_id,
            "description": scene_description, "characters": characters_present or [], "camera": camera_angle}


def generate_cinematic_video(
    session_id: str, scene_description: str, mood: str = "epic", duration_seconds: int = 5,
) -> dict[str, Any]:
    """Request cinematic video generation for dramatic moments."""
    return {"action": "generate_video", "session_id": session_id,
            "description": scene_description, "mood": mood, "duration": duration_seconds}


def set_music_mood(mood: str, intensity: float = 0.5) -> dict[str, Any]:
    """Change the background music mood and intensity."""
    return {"action": "music_change", "mood": mood, "intensity": min(1.0, max(0.0, intensity))}


# ── Rules & Combat ────────────────────────────────────────────────────────

def roll_check(
    character_name: str, ability: str, difficulty_class: int = 10,
    advantage: bool = False, disadvantage: bool = False,
) -> dict[str, Any]:
    """Roll an ability check for a character."""
    total, raw = roll_d20()
    if advantage:
        t2, r2 = roll_d20()
        if t2 > total:
            total, raw = t2, r2
    elif disadvantage:
        t2, r2 = roll_d20()
        if t2 < total:
            total, raw = t2, r2

    return {
        "character": character_name, "ability": ability, "roll": raw, "total": total,
        "dc": difficulty_class, "success": total >= difficulty_class,
        "critical_success": raw == 20, "critical_failure": raw == 1,
    }


def start_combat_encounter(
    session_id: str, enemy_names: list[str], enemy_descriptions: list[str],
    challenge_rating: float = 1.0,
) -> dict[str, Any]:
    """Initiate a combat encounter."""
    return {"action": "start_combat", "session_id": session_id,
            "enemies": [{"name": n, "description": d, "cr": challenge_rating}
                        for n, d in zip(enemy_names, enemy_descriptions)]}


def resolve_combat_action(
    session_id: str, attacker_name: str, action_type: str,
    target_name: str = "", weapon_or_spell: str = "",
) -> dict[str, Any]:
    """Resolve a combat action (attack, spell, ability, etc.)."""
    return {"action": "combat_action", "session_id": session_id,
            "attacker": attacker_name, "type": action_type,
            "target": target_name, "weapon_or_spell": weapon_or_spell}


# ── World Management ──────────────────────────────────────────────────────

def create_npc(
    session_id: str, name: str, description: str, personality: str,
    voice_style: str = "neutral", is_hostile: bool = False,
) -> dict[str, Any]:
    """Create a new NPC in the world."""
    return {"action": "create_npc", "session_id": session_id, "name": name,
            "description": description, "personality": personality,
            "voice_style": voice_style, "is_hostile": is_hostile}


def update_quest(
    session_id: str, quest_title: str, update_type: str = "progress", details: str = "",
) -> dict[str, Any]:
    """Update quest state — progress, complete, or add new quest."""
    return {"action": "quest_update", "session_id": session_id,
            "quest": quest_title, "update": update_type, "details": details}


def change_location(
    session_id: str, location_name: str, location_description: str,
    location_type: str = "generic",
) -> dict[str, Any]:
    """Move the party to a new location."""
    return {"action": "change_location", "session_id": session_id,
            "name": location_name, "description": location_description, "type": location_type}


def update_world_state(
    session_id: str, time_of_day: str = "", weather: str = "",
    advance_day: bool = False, world_event: str = "",
) -> dict[str, Any]:
    """Update world state — time, weather, global events."""
    return {"action": "world_update", "session_id": session_id,
            "time_of_day": time_of_day, "weather": weather,
            "advance_day": advance_day, "event": world_event}


# ── Progression & Economy ─────────────────────────────────────────────────

def award_experience(
    session_id: str, xp_amount: int, reason: str = "",
) -> dict[str, Any]:
    """Award XP to all alive players for combat victory, quest completion, or clever actions."""
    return {"action": "award_xp", "session_id": session_id, "xp": xp_amount, "reason": reason}


def generate_loot(
    session_id: str, item_name: str, item_type: str = "weapon",
    rarity: str = "common", description: str = "", lore: str = "",
    damage: str = "", properties: str = "",
) -> dict[str, Any]:
    """Generate a unique loot item with AI-created name, description, and lore."""
    return {"action": "generate_loot", "session_id": session_id, "name": item_name,
            "type": item_type, "rarity": rarity, "description": description,
            "lore": lore, "damage": damage, "properties": properties}


# ── NPC & Faction ─────────────────────────────────────────────────────────

def record_npc_memory(
    session_id: str, npc_name: str, event: str,
    sentiment: int = 0, character_involved: str = "",
) -> dict[str, Any]:
    """Record a memory for an NPC about an interaction with a player."""
    return {"action": "npc_memory", "session_id": session_id, "npc_name": npc_name,
            "event": event, "sentiment": sentiment, "character": character_involved}


def update_faction_reputation(
    session_id: str, faction_name: str, character_name: str,
    change: int = 0, reason: str = "",
) -> dict[str, Any]:
    """Change a character's reputation with a faction."""
    return {"action": "faction_reputation", "session_id": session_id,
            "faction": faction_name, "character": character_name,
            "change": change, "reason": reason}


# ── Lore & Consequences ──────────────────────────────────────────────────

def add_world_consequence(
    session_id: str, trigger: str, effect: str, severity: int = 3,
) -> dict[str, Any]:
    """Record a consequence of player actions that will ripple through the world."""
    return {"action": "add_consequence", "session_id": session_id,
            "trigger": trigger, "effect": effect, "severity": severity}


def add_lore_entry(
    session_id: str, title: str, content: str,
    keywords: list[str] | None = None, category: str = "world",
) -> dict[str, Any]:
    """Add a new lorebook entry that will be injected into context when keywords match."""
    return {"action": "add_lore", "session_id": session_id, "title": title,
            "content": content, "keywords": keywords or [title.lower()], "category": category}
