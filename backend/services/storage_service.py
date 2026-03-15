"""Cloud Storage service — persists generated media assets."""

from __future__ import annotations

import logging
import uuid

from google.cloud import storage

from config import settings

logger = logging.getLogger(__name__)

_client: storage.Client | None = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client(project=settings.PROJECT_ID)
    return _client


def _get_bucket() -> storage.Bucket:
    client = _get_client()
    return client.bucket(settings.STORAGE_BUCKET)


async def upload_media(
    data: bytes,
    media_type: str = "image",
    content_type: str = "image/png",
    session_id: str = "",
    filename: str | None = None,
) -> str:
    """Upload media to Cloud Storage and return the public URL.

    Args:
        data: Raw bytes of the media file.
        media_type: One of 'image', 'video', 'audio', 'map'.
        content_type: MIME type.
        session_id: Game session ID for organizing assets.
        filename: Optional filename override.

    Returns:
        Public URL of the uploaded file.
    """
    if filename is None:
        ext = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "video/mp4": "mp4",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
        }.get(content_type, "bin")
        filename = f"{uuid.uuid4().hex}.{ext}"

    blob_path = f"sessions/{session_id}/{media_type}/{filename}" if session_id else f"global/{media_type}/{filename}"

    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type=content_type)

    public_url = f"https://storage.googleapis.com/{settings.STORAGE_BUCKET}/{blob_path}"
    logger.info("Uploaded %s to gs://%s/%s", media_type, settings.STORAGE_BUCKET, blob_path)
    return public_url


async def get_session_media(session_id: str, media_type: str = "") -> list[dict[str, str]]:
    """List all media files for a session."""
    bucket = _get_bucket()
    prefix = f"sessions/{session_id}/"
    if media_type:
        prefix += f"{media_type}/"

    blobs = bucket.list_blobs(prefix=prefix)
    return [
        {"name": blob.name, "url": blob.public_url, "content_type": blob.content_type or ""}
        for blob in blobs
    ]


async def delete_session_media(session_id: str) -> int:
    """Delete all media for a session. Returns count of deleted files."""
    bucket = _get_bucket()
    blobs = list(bucket.list_blobs(prefix=f"sessions/{session_id}/"))
    for blob in blobs:
        blob.delete()
    logger.info("Deleted %d media files for session %s", len(blobs), session_id)
    return len(blobs)
