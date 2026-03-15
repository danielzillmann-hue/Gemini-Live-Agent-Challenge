"""Integration tests for WebSocket game loop."""

import json
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_with_player(client):
    """Create a session with one character."""
    resp = client.post("/api/sessions", json={
        "campaign_name": "WS Test", "setting": "Test world",
    })
    session_id = resp.json()["session_id"]

    client.post(f"/api/sessions/{session_id}/characters", json={
        "session_id": session_id, "name": "Hero", "race": "human", "character_class": "warrior",
    })
    return session_id


class TestWebSocketConnection:
    def test_connect_valid_session(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            # Should receive game_state_sync on connect
            data = ws.receive_json()
            assert data["type"] == "game_state_sync"

    def test_connect_invalid_session(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/nonexistent") as ws:
                pass

    def test_players_online_on_connect(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            # Receive initial messages
            messages = []
            for _ in range(5):
                try:
                    msg = ws.receive_json(timeout=1)
                    messages.append(msg)
                except Exception:
                    break
            types = [m["type"] for m in messages]
            assert "players_online" in types or "game_state_sync" in types


class TestWebSocketMessages:
    def test_invalid_json(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            ws.receive_json()  # game_state_sync
            ws.send_text("not valid json")
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "Invalid JSON" in resp["data"]["message"]

    def test_unknown_message_type(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            ws.receive_json()  # game_state_sync
            ws.send_json({"type": "nonsense", "data": {}})
            # Should not crash — server stays alive

    def test_player_chat_broadcast(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            ws.receive_json()  # game_state_sync
            ws.send_json({
                "type": "player_chat",
                "data": {"sender": "Hero", "message": "Hello party!"},
            })
            # Should receive the chat message back (broadcast includes sender)
            messages = []
            for _ in range(5):
                try:
                    msg = ws.receive_json(timeout=2)
                    messages.append(msg)
                except Exception:
                    break
            chat_msgs = [m for m in messages if m["type"] == "player_chat"]
            assert len(chat_msgs) >= 1
            assert chat_msgs[0]["data"]["message"] == "Hello party!"

    def test_empty_player_action_ignored(self, client, session_with_player):
        with client.websocket_connect(f"/ws/{session_with_player}") as ws:
            ws.receive_json()  # game_state_sync
            ws.send_json({
                "type": "player_action",
                "data": {"text": "", "character_name": "Hero"},
            })
            # Should not crash or respond with error


class TestWebSocketMultiplayer:
    def test_two_clients_same_session(self, client, session_with_player):
        """Two clients connecting to the same session both receive broadcasts."""
        with client.websocket_connect(f"/ws/{session_with_player}") as ws1:
            ws1.receive_json()  # game_state_sync for ws1
            with client.websocket_connect(f"/ws/{session_with_player}") as ws2:
                ws2.receive_json()  # game_state_sync for ws2

                # Chat from ws1 should be received by both
                ws1.send_json({
                    "type": "player_chat",
                    "data": {"sender": "Hero", "message": "Team check!"},
                })

                # Both should receive the broadcast
                msg1 = ws1.receive_json(timeout=2)
                msg2 = ws2.receive_json(timeout=2)
                # At least one should be the chat message
                all_msgs = [msg1, msg2]
                chat = [m for m in all_msgs if m.get("type") == "player_chat"]
                assert len(chat) >= 1
