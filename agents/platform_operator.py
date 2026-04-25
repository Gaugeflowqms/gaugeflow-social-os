"""Platform operator.

Responsible for actually executing an action: try the official API first, fall
back to browser automation only when API is unavailable AND BROWSER_ENABLED
is true. Returns the structured result dict.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from config import CONFIG
from connectors import (
    facebook_page_api,
    instagram_graph_api,
    linkedin_api,
    browser_operator,
)

log = logging.getLogger(__name__)


def _empty(success: bool, platform: str, action_type: str, error: str = "") -> Dict:
    return {
        "success": success,
        "platform": platform,
        "action_type": action_type,
        "result_url": "",
        "error": error,
        "screenshot_path": "",
        "human_required": False,
    }


# ---------- Posting ---------- #

def post_to_linkedin(text: str) -> Dict:
    if linkedin_api.is_configured():
        result = linkedin_api.create_organization_post(text)
        if result.get("success"):
            return result
        log.info("LinkedIn API post failed (%s); checking browser fallback", result.get("error"))
    if browser_operator.is_enabled():
        return browser_operator.linkedin_create_post(text)
    return _empty(False, "linkedin", "post", error="no_api_and_browser_disabled")


def post_to_facebook(text: str, photo_path: Optional[str] = None) -> Dict:
    if facebook_page_api.is_configured():
        if photo_path:
            return facebook_page_api.create_photo_post(text, photo_path)
        return facebook_page_api.create_text_post(text)
    if browser_operator.is_enabled():
        return browser_operator.facebook_create_post(text)
    return _empty(False, "facebook", "post", error="no_api_and_browser_disabled")


def post_to_instagram(caption: str, image_url: Optional[str] = None,
                      image_path: Optional[str] = None) -> Dict:
    if instagram_graph_api.is_configured() and image_url:
        return instagram_graph_api.publish_image_post(image_url, caption)
    if browser_operator.is_enabled() and image_path:
        return browser_operator.instagram_create_post(image_path, caption)
    return _empty(
        False, "instagram", "post",
        error="instagram_requires_public_image_url_for_api_or_local_image_for_browser",
    )


# ---------- Replies on owned posts ---------- #

def reply_facebook_comment(comment_id: str, text: str) -> Dict:
    return facebook_page_api.reply_to_comment(comment_id, text)


def reply_instagram_comment(comment_id: str, text: str) -> Dict:
    return instagram_graph_api.reply_to_comment(comment_id, text)


def reply_linkedin_comment(comment_urn: str, text: str) -> Dict:
    # API path is generally not available; browser fallback would need a URL
    # to the specific post. Mark unavailable for now.
    if linkedin_api.is_configured():
        return linkedin_api.reply_to_comment(comment_urn, text)
    return _empty(False, "linkedin", "reply", error="reply_unavailable")


# ---------- External comments ---------- #

def external_comment_linkedin(post_url: str, text: str) -> Dict:
    if browser_operator.is_enabled():
        return browser_operator.linkedin_external_comment(post_url, text)
    return _empty(False, "linkedin", "external_comment", error="browser_disabled")


def external_comment_facebook(post_id_or_url: str, text: str) -> Dict:
    """For FB, posting on someone else's public post requires that the
    page have permission. If the target is a comment ID we can reply to,
    we use the same reply endpoint; otherwise fall back to browser."""
    if facebook_page_api.is_configured() and post_id_or_url and "/" not in post_id_or_url:
        return facebook_page_api.reply_to_comment(post_id_or_url, text)
    return _empty(False, "facebook", "external_comment",
                  error="external_comment_unsupported_in_v1")


def external_comment_instagram(media_id: str, text: str) -> Dict:
    """IG Graph API does not allow commenting on other users' media. Skip."""
    return _empty(False, "instagram", "external_comment",
                  error="instagram_external_comments_not_supported_by_api")


# ---------- Discovery ---------- #

def fetch_owned_facebook_comments(post_id: str) -> Dict:
    return facebook_page_api.fetch_owned_post_comments(post_id)


def fetch_owned_instagram_comments(media_id: str) -> Dict:
    return instagram_graph_api.fetch_owned_post_comments(media_id)


def fetch_recent_facebook_posts() -> Dict:
    return facebook_page_api.fetch_recent_page_posts()


def fetch_recent_instagram_media() -> Dict:
    return instagram_graph_api.fetch_recent_media()
