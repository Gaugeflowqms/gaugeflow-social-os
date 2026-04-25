"""Facebook Page Graph API connector.

Wraps the small subset of the Graph API we actually use:
- create a text or photo post on the Page
- fetch comments on owned posts
- reply to comments as the Page

All public functions return the structured result dict described in the spec.
"""
from __future__ import annotations

import logging
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
    extra: Optional[dict] = None,
) -> Dict:
    out = {
        "success": success,
        "platform": "facebook",
        "action_type": action_type,
        "result_url": result_url,
        "error": error,
        "screenshot_path": "",
        "human_required": False,
    }
    if extra:
        out.update(extra)
    return out


def is_configured() -> bool:
    return CONFIG.has_facebook()


def create_text_post(message: str) -> Dict:
    if not is_configured():
        return _result(False, "post", error="facebook_not_configured")
    url = f"{GRAPH_BASE}/{CONFIG.facebook_page_id}/feed"
    try:
        r = httpx.post(
            url,
            data={
                "message": message,
                "access_token": CONFIG.facebook_page_access_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Facebook post failed: %s %s", e, body)
        return _result(False, "post", error=f"http_{e.response.status_code if e.response else 0}: {body[:300]}")
    except Exception as e:
        log.exception("Facebook post error: %s", e)
        return _result(False, "post", error=str(e))

    post_id = data.get("id", "")
    page_part = post_id.split("_", 1)
    if len(page_part) == 2:
        result_url = f"https://www.facebook.com/{page_part[0]}/posts/{page_part[1]}"
    else:
        result_url = f"https://www.facebook.com/{post_id}"
    return _result(True, "post", result_url=result_url, extra={"post_id": post_id})


def create_photo_post(message: str, photo_path: str) -> Dict:
    if not is_configured():
        return _result(False, "post", error="facebook_not_configured")
    url = f"{GRAPH_BASE}/{CONFIG.facebook_page_id}/photos"
    try:
        with open(photo_path, "rb") as f:
            files = {"source": f}
            r = httpx.post(
                url,
                data={
                    "caption": message,
                    "access_token": CONFIG.facebook_page_access_token,
                },
                files=files,
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
    except FileNotFoundError:
        return _result(False, "post", error=f"photo_not_found:{photo_path}")
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Facebook photo post failed: %s %s", e, body)
        return _result(False, "post", error=f"http_{e.response.status_code}: {body[:300]}")
    except Exception as e:
        log.exception("Facebook photo error: %s", e)
        return _result(False, "post", error=str(e))

    post_id = data.get("post_id") or data.get("id", "")
    return _result(True, "post", result_url=f"https://www.facebook.com/{post_id}", extra={"post_id": post_id})


def fetch_owned_post_comments(post_id: str, limit: int = 25) -> Dict:
    if not is_configured():
        return _result(False, "fetch_comments", error="facebook_not_configured")
    url = f"{GRAPH_BASE}/{post_id}/comments"
    try:
        r = httpx.get(
            url,
            params={
                "access_token": CONFIG.facebook_page_access_token,
                "limit": limit,
                "order": "reverse_chronological",
                "fields": "id,from,message,created_time",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.exception("Facebook fetch comments error: %s", e)
        return _result(False, "fetch_comments", error=str(e))

    comments: List[Dict] = []
    for c in data.get("data", []):
        comments.append({
            "id": c.get("id", ""),
            "author": (c.get("from") or {}).get("name", ""),
            "text": c.get("message", ""),
            "created_at": c.get("created_time", ""),
        })
    return _result(True, "fetch_comments", extra={"comments": comments})


def reply_to_comment(comment_id: str, message: str) -> Dict:
    if not is_configured():
        return _result(False, "reply", error="facebook_not_configured")
    url = f"{GRAPH_BASE}/{comment_id}/comments"
    try:
        r = httpx.post(
            url,
            data={
                "message": message,
                "access_token": CONFIG.facebook_page_access_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Facebook reply failed: %s %s", e, body)
        return _result(False, "reply", error=f"http_{e.response.status_code}: {body[:300]}")
    except Exception as e:
        log.exception("Facebook reply error: %s", e)
        return _result(False, "reply", error=str(e))

    new_id = data.get("id", "")
    return _result(True, "reply", result_url=f"https://www.facebook.com/{new_id}", extra={"comment_id": new_id})


def fetch_recent_page_posts(limit: int = 10) -> Dict:
    if not is_configured():
        return _result(False, "fetch_posts", error="facebook_not_configured")
    url = f"{GRAPH_BASE}/{CONFIG.facebook_page_id}/posts"
    try:
        r = httpx.get(
            url,
            params={
                "access_token": CONFIG.facebook_page_access_token,
                "limit": limit,
                "fields": "id,message,created_time,permalink_url",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.exception("Facebook fetch posts error: %s", e)
        return _result(False, "fetch_posts", error=str(e))

    posts = data.get("data", [])
    return _result(True, "fetch_posts", extra={"posts": posts})
