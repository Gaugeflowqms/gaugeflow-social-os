"""Instagram Graph API connector (Business/Creator account required).

Publishing to IG via the Graph API is a two-step flow:
1. POST /{ig-user-id}/media with image_url -> returns container ID
2. POST /{ig-user-id}/media_publish with creation_id

For carousels you create child containers first, then a CAROUSEL container,
then publish.

This connector requires that any image is hosted at a publicly reachable URL.
The first version stores the URL in media_path; serving the file is the
operator's responsibility (e.g., S3 / their CDN). If no public URL is given
we fall back to caption-only behavior, which IG does not allow standalone, so
we mark the action human_required.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import httpx

from config import CONFIG

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def _result(
    success: bool,
    action_type: str,
    result_url: str = "",
    error: str = "",
    human_required: bool = False,
    extra: Optional[dict] = None,
) -> Dict:
    out = {
        "success": success,
        "platform": "instagram",
        "action_type": action_type,
        "result_url": result_url,
        "error": error,
        "screenshot_path": "",
        "human_required": human_required,
    }
    if extra:
        out.update(extra)
    return out


def is_configured() -> bool:
    return CONFIG.has_instagram()


def _create_media_container(image_url: str, caption: str, is_carousel_item: bool = False) -> Dict:
    url = f"{GRAPH_BASE}/{CONFIG.instagram_business_account_id}/media"
    payload = {
        "image_url": image_url,
        "access_token": CONFIG.instagram_access_token,
    }
    if is_carousel_item:
        payload["is_carousel_item"] = "true"
    else:
        payload["caption"] = caption
    r = httpx.post(url, data=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def _publish_container(creation_id: str) -> Dict:
    url = f"{GRAPH_BASE}/{CONFIG.instagram_business_account_id}/media_publish"
    r = httpx.post(
        url,
        data={
            "creation_id": creation_id,
            "access_token": CONFIG.instagram_access_token,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def publish_image_post(image_url: str, caption: str) -> Dict:
    if not is_configured():
        return _result(False, "post", error="instagram_not_configured")
    if not image_url:
        return _result(
            False, "post",
            error="no_image_url; IG requires a public image URL",
            human_required=True,
        )
    try:
        container = _create_media_container(image_url, caption)
        creation_id = container.get("id", "")
        if not creation_id:
            return _result(False, "post", error=f"no_creation_id: {container}")
        # IG sometimes needs a moment to process the container
        time.sleep(2)
        published = _publish_container(creation_id)
        media_id = published.get("id", "")
        result_url = f"https://www.instagram.com/p/{media_id}/" if media_id else ""
        return _result(True, "post", result_url=result_url, extra={"media_id": media_id})
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Instagram publish failed: %s %s", e, body)
        return _result(False, "post", error=f"http_{e.response.status_code}: {body[:300]}")
    except Exception as e:
        log.exception("Instagram publish error: %s", e)
        return _result(False, "post", error=str(e))


def publish_carousel(image_urls: List[str], caption: str) -> Dict:
    if not is_configured():
        return _result(False, "post", error="instagram_not_configured")
    if not image_urls or len(image_urls) < 2:
        return _result(False, "post", error="carousel_requires_min_2_images", human_required=True)
    try:
        children: List[str] = []
        for u in image_urls[:10]:
            c = _create_media_container(u, caption, is_carousel_item=True)
            children.append(c.get("id", ""))
        url = f"{GRAPH_BASE}/{CONFIG.instagram_business_account_id}/media"
        r = httpx.post(
            url,
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(c for c in children if c),
                "caption": caption,
                "access_token": CONFIG.instagram_access_token,
            },
            timeout=60,
        )
        r.raise_for_status()
        carousel = r.json()
        time.sleep(2)
        published = _publish_container(carousel.get("id", ""))
        media_id = published.get("id", "")
        result_url = f"https://www.instagram.com/p/{media_id}/" if media_id else ""
        return _result(True, "post", result_url=result_url, extra={"media_id": media_id})
    except Exception as e:
        log.exception("Instagram carousel error: %s", e)
        return _result(False, "post", error=str(e))


def publish_reel_placeholder(*args, **kwargs) -> Dict:
    """Reels require video upload to a public URL; not implemented in v1."""
    return _result(
        False, "post",
        error="reels_not_implemented_in_v1",
        human_required=True,
    )


def fetch_owned_post_comments(media_id: str, limit: int = 25) -> Dict:
    if not is_configured():
        return _result(False, "fetch_comments", error="instagram_not_configured")
    url = f"{GRAPH_BASE}/{media_id}/comments"
    try:
        r = httpx.get(
            url,
            params={
                "access_token": CONFIG.instagram_access_token,
                "limit": limit,
                "fields": "id,username,text,timestamp",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.exception("Instagram fetch comments error: %s", e)
        return _result(False, "fetch_comments", error=str(e))
    comments: List[Dict] = []
    for c in data.get("data", []):
        comments.append({
            "id": c.get("id", ""),
            "author": c.get("username", ""),
            "text": c.get("text", ""),
            "created_at": c.get("timestamp", ""),
        })
    return _result(True, "fetch_comments", extra={"comments": comments})


def reply_to_comment(comment_id: str, message: str) -> Dict:
    if not is_configured():
        return _result(False, "reply", error="instagram_not_configured")
    url = f"{GRAPH_BASE}/{comment_id}/replies"
    try:
        r = httpx.post(
            url,
            data={
                "message": message,
                "access_token": CONFIG.instagram_access_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Instagram reply failed: %s %s", e, body)
        return _result(False, "reply", error=f"http_{e.response.status_code}: {body[:300]}")
    except Exception as e:
        log.exception("Instagram reply error: %s", e)
        return _result(False, "reply", error=str(e))
    return _result(True, "reply", extra={"reply_id": data.get("id", "")})


def fetch_recent_media(limit: int = 10) -> Dict:
    if not is_configured():
        return _result(False, "fetch_posts", error="instagram_not_configured")
    url = f"{GRAPH_BASE}/{CONFIG.instagram_business_account_id}/media"
    try:
        r = httpx.get(
            url,
            params={
                "access_token": CONFIG.instagram_access_token,
                "limit": limit,
                "fields": "id,caption,media_type,permalink,timestamp",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.exception("Instagram fetch media error: %s", e)
        return _result(False, "fetch_posts", error=str(e))
    return _result(True, "fetch_posts", extra={"posts": data.get("data", [])})
