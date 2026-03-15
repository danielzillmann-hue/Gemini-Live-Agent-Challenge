"""Firestore service — persists game sessions, campaigns, and world state."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from google.cloud import firestore

from config import settings
from game.models import CampaignSummary, GameSession

logger = logging.getLogger(__name__)

_client: firestore.AsyncClient | None = None


def _get_client() -> firestore.AsyncClient:
    global _client
    if _client is None:
        _client = firestore.AsyncClient(
            project=settings.PROJECT_ID,
            database=settings.FIRESTORE_DATABASE,
        )
    return _client


# ── Sessions ───────────────────────────────────────────────────────────────

async def save_session(session: GameSession) -> None:
    """Save or update a game session."""
    db = _get_client()
    doc_ref = db.collection("sessions").document(session.id)
    await doc_ref.set(session.model_dump(mode="json"))
    logger.info("Saved session %s", session.id)


async def load_session(session_id: str) -> GameSession | None:
    """Load a game session by ID."""
    try:
        db = _get_client()
        doc = await db.collection("sessions").document(session_id).get()
        if doc.exists:
            return GameSession.model_validate(doc.to_dict())
    except Exception:
        logger.exception("Failed to load session %s from Firestore", session_id)
    return None


async def delete_session(session_id: str) -> None:
    """Delete a game session."""
    db = _get_client()
    await db.collection("sessions").document(session_id).delete()


async def list_sessions(campaign_id: str = "") -> list[dict[str, Any]]:
    """List all sessions, optionally filtered by campaign."""
    db = _get_client()
    query = db.collection("sessions")
    if campaign_id:
        query = query.where("campaign_id", "==", campaign_id)
    query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(50)

    docs = query.stream()
    results = []
    async for doc in docs:
        data = doc.to_dict()
        results.append({
            "id": doc.id,
            "campaign_name": data.get("world", {}).get("campaign_name", ""),
            "session_number": data.get("session_number", 1),
            "created_at": data.get("created_at", ""),
            "is_active": data.get("is_active", False),
            "player_count": len(data.get("players", [])),
        })
    return results


# ── Campaigns ──────────────────────────────────────────────────────────────

async def save_campaign(campaign: CampaignSummary) -> None:
    """Save or update a campaign summary."""
    db = _get_client()
    doc_ref = db.collection("campaigns").document(campaign.id)
    await doc_ref.set(campaign.model_dump(mode="json"))


async def load_campaign(campaign_id: str) -> CampaignSummary | None:
    """Load a campaign summary."""
    db = _get_client()
    doc = await db.collection("campaigns").document(campaign_id).get()
    if doc.exists:
        return CampaignSummary.model_validate(doc.to_dict())
    return None


async def list_campaigns() -> list[CampaignSummary]:
    """List all campaigns."""
    db = _get_client()
    query = db.collection("campaigns").order_by(
        "last_played", direction=firestore.Query.DESCENDING
    ).limit(20)

    results = []
    async for doc in query.stream():
        results.append(CampaignSummary.model_validate(doc.to_dict()))
    return results


# ── Story Events (for recap generation) ───────────────────────────────────

async def save_story_events(session_id: str, events: list[dict[str, Any]]) -> None:
    """Save story events for a session (for recap generation)."""
    db = _get_client()
    batch = db.batch()
    collection = db.collection("sessions").document(session_id).collection("events")

    for event in events:
        doc_ref = collection.document(event.get("id", ""))
        batch.set(doc_ref, event)

    await batch.commit()
    logger.info("Saved %d events for session %s", len(events), session_id)


async def get_campaign_events(campaign_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get all events across sessions for a campaign (for recap)."""
    db = _get_client()

    sessions_query = db.collection("sessions").where(
        "campaign_id", "==", campaign_id
    ).order_by("session_number")

    all_events: list[dict[str, Any]] = []
    async for session_doc in sessions_query.stream():
        events_query = (
            session_doc.reference.collection("events")
            .order_by("timestamp")
            .limit(limit)
        )
        async for event_doc in events_query.stream():
            event = event_doc.to_dict()
            event["session_number"] = session_doc.to_dict().get("session_number", 0)
            all_events.append(event)

    return all_events[-limit:]
