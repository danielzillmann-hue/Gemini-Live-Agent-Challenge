"""Tool result handlers — process ADK agent tool calls into game state changes and WebSocket messages.

Each handler function takes (session_id, args, game_session) and returns a list of WS messages.
"""

from __future__ import annotations

import logging
from typing import Any

from game.engine import CombatEngine, game_engine
from game.models import (
    Achievement, Faction, Item, Location, LoreEntry, NPC, Quest,
)
from services import media_service, storage_service

logger = logging.getLogger(__name__)


async def handle_narrate_scene(session_id: str, args: dict, session: Any) -> list[dict]:
    scene_desc = args.get("scene", "")
    if scene_desc:
        return [{"type": "narration", "data": {"content": scene_desc}}]
    return []


async def handle_roll_check(session_id: str, args: dict, session: Any) -> list[dict]:
    if not args.get("success", True):
        damage = args.get("damage", 0)
        if damage and session:
            char_name = args.get("character", "")
            for p in session.players:
                if p.name.lower() == char_name.lower():
                    p.hp = max(0, p.hp - damage)
                    break
    return [{"type": "dice_result", "data": args}]


async def handle_start_combat(session_id: str, args: dict, session: Any) -> list[dict]:
    messages = []
    if not session:
        return [{"type": "combat_update", "data": {"action": "start", **args}}]

    enemies_data = args.get("enemies", [])
    for enemy in enemies_data:
        npc = NPC(
            name=enemy.get("name", "Enemy"),
            description=enemy.get("description", ""),
            is_hostile=True,
            hp=int(10 + enemy.get("cr", 1) * 8),
            max_hp=int(10 + enemy.get("cr", 1) * 8),
            armor_class=int(10 + enemy.get("cr", 1) * 2),
            challenge_rating=enemy.get("cr", 1.0),
        )
        game_engine.add_npc(session_id, npc)

    enemy_ids = [nid for nid, n in session.world.npcs.items() if n.is_hostile and n.hp > 0]
    combat_state = game_engine.start_combat(session_id, enemy_ids)
    if combat_state:
        messages.append({"type": "combat_update", "data": combat_state.model_dump(mode="json")})
        try:
            map_bytes = await media_service.generate_battle_map(
                location_description=args.get("description", session.world.setting_description),
            )
            if map_bytes:
                map_url = await storage_service.upload_media(map_bytes, "image", "image/png", session_id)
                messages.append({"type": "battle_map", "data": {"url": map_url}})
        except Exception:
            logger.warning("Battle map generation failed")

    return messages


async def handle_resolve_combat(session_id: str, args: dict, session: Any) -> list[dict]:
    messages = []
    if not session or not session.combat.is_active:
        return [{"type": "combat_update", "data": {"action": "resolve", **args}}]

    attacker_name = args.get("attacker", "")
    target_name = args.get("target", "")
    action_type = args.get("type", "attack")

    attacker = next((c for c in session.combat.combatants if c.name.lower() == attacker_name.lower()), None)
    defender = next((c for c in session.combat.combatants if c.name.lower() == target_name.lower()), None)

    if attacker and defender and action_type == "attack":
        result = CombatEngine.resolve_attack(attacker, defender)
        # Sync HP
        for p in session.players:
            matching = next((c for c in session.combat.combatants if c.id == p.id), None)
            if matching:
                p.hp = matching.hp
        for npc in session.world.npcs.values():
            matching = next((c for c in session.combat.combatants if c.id == npc.id), None)
            if matching:
                npc.hp = matching.hp
        # Track kills
        if defender.hp <= 0 and attacker:
            for p in session.players:
                if p.id == attacker.id:
                    p.kills += 1
        if result.is_critical:
            for p in session.players:
                if p.id == attacker.id:
                    p.crits += 1

        messages.append({"type": "dice_result", "data": {
            "character": result.actor_name, "roll_type": "d20", "value": result.roll,
            "is_critical": result.is_critical, "is_fumble": result.is_miss and result.roll == 1,
        }})
        messages.append({"type": "combat_update", "data": session.combat.model_dump(mode="json")})

    next_combatant = CombatEngine.next_turn(session.combat)
    if not session.combat.is_active:
        messages.append({"type": "combat_update", "data": {"is_active": False, "phase": "ended"}})

    return messages


async def handle_create_npc(session_id: str, args: dict, session: Any) -> list[dict]:
    npc = NPC(
        name=args.get("name", ""),
        description=args.get("description", ""),
        personality=args.get("personality", ""),
        voice_style=args.get("voice_style", "neutral"),
        is_hostile=args.get("is_hostile", False),
        location=session.world.current_location_id if session else "",
    )
    game_engine.add_npc(session_id, npc)

    portrait_url = ""
    try:
        portrait_bytes = await media_service.generate_character_portrait(
            name=npc.name, race="human", character_class="commoner", appearance=npc.description,
        )
        if portrait_bytes:
            portrait_url = await storage_service.upload_media(portrait_bytes, "image", "image/png", session_id)
            npc.portrait_url = portrait_url
    except Exception:
        logger.warning("NPC portrait generation failed for %s", npc.name)

    return [{"type": "npc_portrait", "data": {
        "id": npc.id, "name": npc.name, "portrait_url": portrait_url,
        "description": npc.description, "personality": npc.personality,
    }}]


async def handle_change_location(session_id: str, args: dict, session: Any) -> list[dict]:
    loc = Location(
        name=args.get("name", ""), description=args.get("description", ""),
        location_type=args.get("type", "generic"), visited=True,
    )
    game_engine.add_location(session_id, loc)
    game_engine.move_to_location(session_id, loc.id)

    scene_url = ""
    try:
        scene_bytes = await media_service.generate_scene_image(
            scene_description=args.get("description", ""),
            time_of_day=session.world.time_of_day if session else "day",
            weather=session.world.weather if session else "clear",
        )
        if scene_bytes:
            scene_url = await storage_service.upload_media(scene_bytes, "image", "image/png", session_id)
            loc.image_url = scene_url
    except Exception:
        logger.warning("Location scene generation failed")

    return [{"type": "location_change", "data": {
        "name": loc.name, "description": loc.description,
        "image_url": scene_url, "location_id": loc.id,
    }}]


async def handle_update_quest(session_id: str, args: dict, session: Any) -> list[dict]:
    if not session:
        return [{"type": "quest_update", "data": args}]

    quest_title = args.get("quest", "")
    update_type = args.get("update", "progress")
    details = args.get("details", "")

    existing = next((q for q in session.world.quests if q.title.lower() == quest_title.lower()), None)
    if existing:
        if update_type == "complete":
            existing.is_complete = True
            existing.is_active = False
            for p in session.players:
                p.xp += existing.reward_xp
                p.gold += existing.reward_gold
                p.quests_completed += 1
        elif update_type == "progress" and details:
            for i in range(len(existing.objectives)):
                if i not in existing.completed_objectives:
                    existing.completed_objectives.append(i)
                    break
    elif update_type == "new" or not existing:
        new_quest = Quest(title=quest_title, description=details, objectives=[details] if details else [])
        game_engine.add_quest(session_id, new_quest)

    return [{"type": "quest_update", "data": {
        **args, "quests": [q.model_dump(mode="json") for q in session.world.quests] if session else [],
    }}]


async def handle_update_world(session_id: str, args: dict, session: Any) -> list[dict]:
    if session:
        if args.get("time_of_day"):
            session.world.time_of_day = args["time_of_day"]
        if args.get("weather"):
            session.world.weather = args["weather"]
        if args.get("advance_day"):
            session.world.day_count += 1
        if args.get("event"):
            session.world.global_events.append(args["event"])

    return [{"type": "world_update", "data": {
        "time_of_day": session.world.time_of_day if session else "",
        "weather": session.world.weather if session else "",
        "day_count": session.world.day_count if session else 1,
    }}]


async def handle_award_xp(session_id: str, args: dict, session: Any) -> list[dict]:
    messages = []
    xp_amount = args.get("xp", 0)
    reason = args.get("reason", "")
    level_ups = game_engine.award_xp(session_id, xp_amount)
    messages.append({"type": "xp_awarded", "data": {"xp": xp_amount, "reason": reason, "level_ups": level_ups}})

    if session:
        new_achievements = game_engine.check_achievements(session)
        for a in new_achievements:
            messages.append({"type": "achievement", "data": a.model_dump(mode="json")})

    return messages


async def handle_generate_loot(session_id: str, args: dict, session: Any) -> list[dict]:
    item = Item(
        name=args.get("name", "Mystery Item"), item_type=args.get("type", "misc"),
        rarity=args.get("rarity", "common"), description=args.get("description", ""),
        lore=args.get("lore", ""), properties={"damage": args.get("damage", "")} if args.get("damage") else {},
    )
    if session:
        target = session.get_alive_players()[0] if session.get_alive_players() else None
        if target:
            target.inventory.append(item)
    return [{"type": "loot_found", "data": {"item": item.model_dump(mode="json")}}]


async def handle_npc_memory(session_id: str, args: dict, session: Any) -> list[dict]:
    if session:
        npc_name = args.get("npc_name", "")
        for npc in session.world.npcs.values():
            if npc.name.lower() == npc_name.lower():
                npc.add_memory(
                    event=args.get("event", ""),
                    sentiment=args.get("sentiment", 0),
                    character=args.get("character", ""),
                )
                break
    return []


async def handle_consequence(session_id: str, args: dict, session: Any) -> list[dict]:
    if session:
        consequence = session.world.add_consequence(
            trigger=args.get("trigger", ""), effect=args.get("effect", ""),
            severity=args.get("severity", 3),
        )
        return [{"type": "consequence", "data": {
            "trigger": consequence.trigger_event, "effect": consequence.effect, "severity": consequence.severity,
        }}]
    return []


async def handle_faction_reputation(session_id: str, args: dict, session: Any) -> list[dict]:
    if session:
        faction_name = args.get("faction", "")
        for faction in session.world.factions.values():
            if faction.name.lower() == faction_name.lower():
                new_rep = faction.adjust_reputation(args.get("character", ""), args.get("change", 0))
                return [{"type": "faction_update", "data": {
                    "faction": faction.name, "character": args.get("character", ""),
                    "new_reputation": new_rep, "reason": args.get("reason", ""),
                }}]
    return []


async def handle_add_lore(session_id: str, args: dict, session: Any) -> list[dict]:
    if session:
        entry = LoreEntry(
            title=args.get("title", ""), content=args.get("content", ""),
            keywords=args.get("keywords", []), category=args.get("category", "world"),
        )
        game_engine.add_lore_entry(session_id, entry)
    return []


async def handle_scene_art(session_id: str, args: dict, session: Any) -> list[dict]:
    if not session:
        return []
    try:
        image_bytes = await media_service.generate_scene_image(
            scene_description=args.get("description", ""),
            characters=args.get("characters"),
            time_of_day=session.world.time_of_day,
            weather=session.world.weather,
            camera_angle=args.get("camera", "wide"),
        )
        if image_bytes:
            url = await storage_service.upload_media(image_bytes, "image", "image/png", session_id)
            return [{"type": "scene_image", "data": {"url": url, "description": args.get("description", "")}}]
    except Exception:
        logger.warning("Scene art generation failed")
    return []


async def handle_cinematic_video(session_id: str, args: dict, session: Any) -> list[dict]:
    try:
        video_bytes = await media_service.generate_cinematic(
            scene_description=args.get("description", ""), mood=args.get("mood", "epic"),
        )
        if video_bytes:
            url = await storage_service.upload_media(video_bytes, "video", "video/mp4", session_id)
            return [{"type": "scene_video", "data": {"url": url, "description": args.get("description", "")}}]
    except Exception:
        logger.warning("Cinematic video generation failed")
    return []


# ── Handler Registry ──────────────────────────────────────────────────────

TOOL_HANDLERS: dict[str, Any] = {
    "narrate_scene": handle_narrate_scene,
    "narrate": handle_narrate_scene,
    "generate_scene_art": handle_scene_art,
    "generate_image": handle_scene_art,
    "generate_cinematic_video": handle_cinematic_video,
    "generate_video": handle_cinematic_video,
    "roll_check": handle_roll_check,
    "skill_check": handle_roll_check,
    "start_combat_encounter": handle_start_combat,
    "start_combat": handle_start_combat,
    "resolve_combat_action": handle_resolve_combat,
    "combat_action": handle_resolve_combat,
    "create_npc": handle_create_npc,
    "change_location": handle_change_location,
    "update_quest": handle_update_quest,
    "quest_update": handle_update_quest,
    "update_world_state": handle_update_world,
    "world_update": handle_update_world,
    "set_music_mood": lambda sid, args, s: [{"type": "music_change", "data": args}],
    "music_change": lambda sid, args, s: [{"type": "music_change", "data": args}],
    "award_xp": handle_award_xp,
    "award_experience": handle_award_xp,
    "generate_loot": handle_generate_loot,
    "record_npc_memory": handle_npc_memory,
    "npc_memory": handle_npc_memory,
    "add_world_consequence": handle_consequence,
    "add_consequence": handle_consequence,
    "update_faction_reputation": handle_faction_reputation,
    "faction_reputation": handle_faction_reputation,
    "add_lore_entry": handle_add_lore,
    "add_lore": handle_add_lore,
}
