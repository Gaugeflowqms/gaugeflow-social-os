"""LinkedIn API connector.

LinkedIn's Marketing/Community APIs require an organization-scoped access
token with w_organization_social. Comment-on-third-party-posts is not part of
the standard partner program for most accounts. We:
- post original organization content via /rest/posts when API token is present
- mark fetch/reply/external-comment as unavailable for browser fallback

This connector is conservative on purpose. Anything LinkedIn returns as 401,
403, or 429 is logged and returned as a structured failure so the orchestrator
can fall through to browser_operator if BROWSER_ENABLED=true.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

import httpx

from config import CONFIG

log = logging.getLogger(__name__)

REST_BASE = "https://api.linkedin.com/rest"


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
        "platform": "linkedin",
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
    return CONFIG.has_linkedin_api()


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {CONFIG.linkedin_access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202404",
        "Content-Type": "application/json",
    }


def create_organization_post(text: str) -> Dict:
    if not is_configured():
        return _result(False, "post", error="linkedin_not_configured")
    org_urn = f"urn:li:organization:{CONFIG.linkedin_organization_id}"
    body = {
        "author": org_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    try:
        r = httpx.post(
            f"{REST_BASE}/posts",
            headers=_headers(),
            content=json.dumps(body),
            timeout=30,
        )
        if r.status_code in (401, 403):
            return _result(
                False, "post",
                error=f"linkedin_auth_{r.status_code}: {r.text[:200]}",
                human_required=True,
            )
        r.raise_for_status()
        post_urn = r.headers.get("x-restli-id") or ""
        result_url = (
            f"https://www.linkedin.com/feed/update/{post_urn}/"
            if post_urn else ""
        )
        return _result(True, "post", result_url=result_url, extra={"urn": post_urn})
    except httpx.HTTPStatusError as e:
        body_text = e.response.text if e.response is not None else ""
        log.error("LinkedIn post failed: %s %s", e, body_text)
        return _result(False, "post", error=f"http_{e.response.status_code}: {body_text[:300]}")
    except Exception as e:
        log.exception("LinkedIn post error: %s", e)
        return _result(False, "post", error=str(e))


def fetch_owned_post_comments(post_urn: str, limit: int = 25) -> Dict:
    """Most token tiers cannot read comments via API. Return unavailable
    so the orchestrator can decide to use the browser fallback or skip."""
    if not is_configured():
        return _result(False, "fetch_comments", error="linkedin_not_configured")
    return _result(
        False,
        "fetch_comments",
        error="linkedin_api_fetch_comments_unavailable_in_v1",
        human_required=True,
    )


def reply_to_comment(comment_urn: str, message: str) -> Dict:
    """Same as above — typically not available via API. Mark unavailable."""
    if not is_configured():
        return _result(False, "reply", error="linkedin_not_configured")
    return _result(
        False,
        "reply",
        error="linkedin_api_reply_unavailable_in_v1",
        human_required=True,
    )


def post_external_comment(*args, **kwargs) -> Dict:
    """LinkedIn does not expose third-party-post commenting via API for most
    apps. The orchestrator should route this through the browser fallback."""
    return _result(
        False,
        "external_comment",
        error="linkedin_api_external_comment_unavailable",
        human_required=True,
    )
