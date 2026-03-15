"""End-to-end campaign test — plays through a full game session against the live backend.

This test creates a session, adds characters, starts the game, performs actions,
and verifies all major features work. Requires the backend to be running.

Usage:
    GENESIS_URL=https://genesis-backend-241457909657.us-central1.run.app pytest tests/test_e2e_campaign.py -v -s

    Or against local:
    GENESIS_URL=http://localhost:8080 pytest tests/test_e2e_campaign.py -v -s
"""

import asyncio
import json
import os
import time

import httpx
import pytest
import websockets

BASE_URL = os.getenv("GENESIS_URL", "https://genesis-backend-241457909657.us-central1.run.app")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=60)


@pytest.fixture
def session_id(client):
    """Create a fresh game session."""
    resp = client.post("/api/sessions", json={
        "campaign_name": "E2E Test Campaign",
        "setting": "A small village threatened by goblins in a dark forest. A mysterious tower looms in the distance.",
    })
    assert resp.status_code == 200, f"Failed to create session: {resp.text}"
    data = resp.json()
    print(f"\n  Session created: {data['session_id']}")
    return data["session_id"]


class TestE2ECampaign:
    """Play through a full campaign testing all major features."""

    def test_01_health(self, client):
        """Backend is running."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        print("  Backend healthy")

    def test_02_create_session(self, session_id):
        """Session creation works."""
        assert len(session_id) > 0
        print(f"  Session: {session_id}")

    def test_03_get_session(self, client, session_id):
        """Session is retrievable."""
        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world"]["campaign_name"] == "E2E Test Campaign"
        print(f"  Campaign: {data['world']['campaign_name']}")

    def test_04_create_characters(self, client, session_id):
        """Character creation works with different classes."""
        characters = [
            {"name": "Kira", "race": "elf", "character_class": "ranger",
             "backstory": "A wandering exile seeking redemption",
             "appearance": "Silver hair, green eyes, leather armor"},
            {"name": "Thane", "race": "dwarf", "character_class": "warrior",
             "backstory": "Former blacksmith turned adventurer",
             "appearance": "Red beard, heavy plate armor, battle axe"},
        ]

        for char in characters:
            resp = client.post(f"/api/sessions/{session_id}/characters", json={
                "session_id": session_id, **char,
            })
            assert resp.status_code == 200, f"Failed to create {char['name']}: {resp.text}"
            data = resp.json()
            assert data["name"] == char["name"]
            assert data["level"] == 1
            assert data["hp"] > 0
            assert len(data["inventory"]) > 0
            print(f"  Created {data['name']}: Lvl {data['level']} {data['race']} {data['character_class']} "
                  f"HP:{data['hp']}/{data['max_hp']} AC:{data['armor_class']}")

    def test_05_verify_party(self, client, session_id):
        """Create two characters and verify both are in the session."""
        # Create characters in THIS session
        for char in [
            {"name": "Kira", "race": "elf", "character_class": "ranger"},
            {"name": "Thane", "race": "dwarf", "character_class": "warrior"},
        ]:
            client.post(f"/api/sessions/{session_id}/characters", json={
                "session_id": session_id, **char,
            })

        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        players = resp.json()["players"]
        assert len(players) == 2
        names = [p["name"] for p in players]
        assert "Kira" in names
        assert "Thane" in names
        print(f"  Party: {', '.join(names)}")

    def test_06_websocket_connect_and_start(self, client, session_id):
        """WebSocket connects and game starts with AI narration."""
        # First create characters
        for char in [
            {"name": "TestHero", "race": "human", "character_class": "warrior"},
        ]:
            client.post(f"/api/sessions/{session_id}/characters", json={
                "session_id": session_id, **char,
            })

        async def _run():
            uri = f"{WS_URL}/ws/{session_id}"
            messages = []

            async with websockets.connect(uri, close_timeout=120, ping_interval=20, ping_timeout=60) as ws:
                # Receive initial messages (players_online + game_state_sync)
                got_sync = False
                for _ in range(5):
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                        messages.append(msg)
                        if msg["type"] == "game_state_sync":
                            got_sync = True
                            break
                    except asyncio.TimeoutError:
                        break
                assert got_sync, f"Never received game_state_sync. Got: {[m['type'] for m in messages]}"
                print(f"  Connected — received game_state_sync")

                # Start the game
                await ws.send(json.dumps({"type": "start_game", "data": {}}))
                print("  Sent start_game")

                # Collect responses for up to 90 seconds (AI generation can be slow)
                start = time.time()
                while time.time() - start < 90:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        msg = json.loads(raw)
                        messages.append(msg)
                        print(f"  Received: {msg['type']}", end="")
                        if msg["type"] == "narration":
                            content = msg["data"].get("content", "")[:80]
                            print(f" — {content}...")
                        elif msg["type"] == "scene_image":
                            print(f" — {msg['data'].get('url', '')[:60]}...")
                        else:
                            print()
                    except asyncio.TimeoutError:
                        break

                # Verify we got narration
                narration_msgs = [m for m in messages if m["type"] == "narration"]
                assert len(narration_msgs) > 0, "No narration received from AI"
                print(f"\n  Got {len(narration_msgs)} narration message(s)")

                # Send a player action
                await ws.send(json.dumps({
                    "type": "player_action",
                    "data": {"text": "I look around the room carefully", "character_name": "TestHero"},
                }))
                print("  Sent player action: 'I look around the room carefully'")

                # Collect AI response
                action_responses = []
                start = time.time()
                while time.time() - start < 30:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        msg = json.loads(raw)
                        action_responses.append(msg)
                        if msg["type"] == "narration":
                            content = msg["data"].get("content", "")[:80]
                            print(f"  AI response: {content}...")
                            break
                    except asyncio.TimeoutError:
                        break

                assert len(action_responses) > 0, "No response to player action"
                print(f"  Got {len(action_responses)} response message(s)")

                # Test chat
                await ws.send(json.dumps({
                    "type": "player_chat",
                    "data": {"sender": "TestHero", "message": "Testing chat!"},
                }))
                chat_received = False
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg["type"] == "player_chat":
                        chat_received = True
                        print(f"  Chat works: {msg['data']['message']}")
                except asyncio.TimeoutError:
                    pass

            return messages, action_responses, chat_received

        messages, responses, chat_ok = asyncio.run(_run())
        assert len(messages) > 1, "Too few messages received"
        print(f"\n  Total messages: {len(messages)} + {len(responses)} responses")
        print(f"  Chat: {'OK' if chat_ok else 'Not received'}")

    def test_07_save_session(self, client, session_id):
        """Session saves to Firestore."""
        # Create a character first
        client.post(f"/api/sessions/{session_id}/characters", json={
            "session_id": session_id, "name": "SaveTest", "race": "human", "character_class": "mage",
        })
        resp = client.post(f"/api/sessions/{session_id}/save")
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        print("  Session saved to Firestore")

    def test_08_save_characters(self, client, session_id):
        """Characters save to persistent roster."""
        # Create a character
        client.post(f"/api/sessions/{session_id}/characters", json={
            "session_id": session_id, "name": "RosterTest", "race": "elf", "character_class": "ranger",
        })
        resp = client.post(f"/api/sessions/{session_id}/characters/save-all")
        assert resp.status_code == 200
        saved = resp.json()["characters"]
        assert len(saved) > 0
        print(f"  Saved {len(saved)} character(s) to roster")

    def test_09_list_saved_characters(self, client):
        """Saved characters are listable."""
        resp = client.get("/api/characters?owner_id=default")
        assert resp.status_code == 200
        chars = resp.json()
        print(f"  Roster has {len(chars)} character(s)")

    def test_10_session_recap(self, client, session_id):
        """Session recap generates."""
        resp = client.get(f"/api/sessions/{session_id}/recap")
        assert resp.status_code == 200
        data = resp.json()
        assert "recap" in data
        assert len(data["recap"]) > 0
        print(f"  Recap: {data['recap'][:80]}...")

    def test_11_tts_endpoint(self, client):
        """Text-to-speech works."""
        resp = client.post("/api/tts", json={
            "text": "The adventure begins.",
            "voice_type": "narrator",
        })
        assert resp.status_code == 200
        data = resp.json()
        if data.get("audio"):
            print(f"  TTS generated: {len(data['audio'])} bytes of audio")
        else:
            print(f"  TTS fallback (Cloud TTS not available)")

    def test_12_input_validation(self, client, session_id):
        """Input validation rejects bad data."""
        # Name too long
        resp = client.post(f"/api/sessions/{session_id}/characters", json={
            "session_id": session_id, "name": "A" * 101,
        })
        assert resp.status_code == 422
        print("  Validation: name too long correctly rejected")

        # Empty campaign name
        resp = client.post("/api/sessions", json={
            "campaign_name": "", "setting": "test",
        })
        assert resp.status_code == 422
        print("  Validation: empty campaign name correctly rejected")

    def test_13_nonexistent_session(self, client):
        """404 for nonexistent sessions."""
        resp = client.get("/api/sessions/nonexistent_session_id")
        assert resp.status_code == 404
        print("  404 for nonexistent session: correct")
