"""Integration tests for REST API endpoints using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_id(client):
    resp = client.post("/api/sessions", json={
        "campaign_name": "Test Campaign",
        "setting": "A test world",
    })
    assert resp.status_code == 200
    return resp.json()["session_id"]


class TestHealthEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Genesis RPG"
        assert data["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestSessionAPI:
    def test_create_session(self, client):
        resp = client.post("/api/sessions", json={
            "campaign_name": "The Shattered Crown",
            "setting": "A dark medieval kingdom",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_name"] == "The Shattered Crown"
        assert "session_id" in data

    def test_create_session_validation(self, client):
        # Empty campaign name
        resp = client.post("/api/sessions", json={
            "campaign_name": "",
            "setting": "A world",
        })
        assert resp.status_code == 422  # Validation error

    def test_get_session(self, client, session_id):
        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world"]["campaign_name"] == "Test Campaign"

    def test_get_session_not_found(self, client):
        resp = client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404

    def test_list_sessions(self, client, session_id):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(s["id"] == session_id for s in data)


class TestCharacterAPI:
    def test_create_character(self, client, session_id):
        resp = client.post(f"/api/sessions/{session_id}/characters", json={
            "session_id": session_id,
            "name": "Kira Shadowmend",
            "race": "elf",
            "character_class": "ranger",
            "backstory": "A wandering exile",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Kira Shadowmend"
        assert data["race"] == "elf"
        assert data["character_class"] == "ranger"
        assert data["level"] == 1
        assert data["hp"] > 0
        assert len(data["inventory"]) > 0

    def test_create_character_invalid_session(self, client):
        resp = client.post("/api/sessions/fake/characters", json={
            "session_id": "fake",
            "name": "Test",
        })
        assert resp.status_code == 404

    def test_create_character_name_too_long(self, client, session_id):
        resp = client.post(f"/api/sessions/{session_id}/characters", json={
            "session_id": session_id,
            "name": "A" * 101,  # Exceeds max_length=100
        })
        assert resp.status_code == 422

    def test_multiple_characters(self, client, session_id):
        for name in ["Kira", "Thane", "Zeph"]:
            resp = client.post(f"/api/sessions/{session_id}/characters", json={
                "session_id": session_id,
                "name": name,
            })
            assert resp.status_code == 200

        resp = client.get(f"/api/sessions/{session_id}")
        assert len(resp.json()["players"]) == 3


class TestSessionRecap:
    def test_recap_empty_session(self, client, session_id):
        resp = client.get(f"/api/sessions/{session_id}/recap")
        assert resp.status_code == 200
        data = resp.json()
        assert "recap" in data
        assert "raw" in data

    def test_recap_not_found(self, client):
        resp = client.get("/api/sessions/fake/recap")
        assert resp.status_code == 404
