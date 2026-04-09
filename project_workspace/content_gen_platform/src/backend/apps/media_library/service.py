"""Media Library service — programmatic media item creation for AI generation tasks."""
import logging
import os
import uuid

import httpx
from django.conf import settings
from django.core.files.base import ContentFile

from .models import MediaItem

logger = logging.getLogger(__name__)


def create_media_item_from_url(
    user,
    url: str,
    media_type: str,
    source: str = "ai_generated",
    title: str = "",
) -> MediaItem:
    """
    Download a file from `url` and create a MediaItem for `user`.

    Args:
        user: User instance (owner)
        url: Remote URL to download from
        media_type: 'image' | 'video' | 'audio'
        source: 'ai_generated' | 'uploaded'
        title: Human-readable title (defaults to UUID if empty)

    Returns:
        Newly created MediaItem instance.

    Raises:
        RuntimeError: if download fails.
    """
    if not title:
        title = f"ai_{media_type}_{uuid.uuid4().hex[:8]}"

    try:
        response = httpx.get(url, timeout=60, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"下载媒体文件失败: {exc}") from exc

    content = response.content
    file_size = len(content)

    # Determine file extension from Content-Type or URL
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
    }
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    ext = ext_map.get(content_type, "")
    if not ext:
        # Fall back to URL extension
        url_path = url.split("?")[0]
        ext = os.path.splitext(url_path)[1] or ".bin"

    filename = f"{uuid.uuid4().hex}{ext}"

    item = MediaItem(
        owner=user,
        media_type=media_type,
        source=source,
        title=title,
        file_size=file_size,
    )
    item.file.save(filename, ContentFile(content), save=True)

    logger.info(
        "Created MediaItem id=%d for user=%s type=%s source=%s",
        item.pk, user.pk, media_type, source,
    )
    return item


def create_media_item_from_local_file(
    user,
    file_path: str,
    media_type: str,
    source: str = "ai_generated",
    title: str = "",
) -> MediaItem:
    """
    Create a MediaItem from a local file path (already on disk).
    Used when the Celery worker has already saved the file.
    """
    if not title:
        title = os.path.splitext(os.path.basename(file_path))[0]

    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    filename = os.path.basename(file_path)

    item = MediaItem(
        owner=user,
        media_type=media_type,
        source=source,
        title=title,
        file_size=file_size,
    )

    with open(file_path, "rb") as f:
        item.file.save(filename, ContentFile(f.read()), save=True)

    logger.info(
        "Created MediaItem id=%d from local file for user=%s",
        item.pk, user.pk,
    )
    return item
