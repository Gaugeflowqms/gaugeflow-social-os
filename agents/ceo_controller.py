"""CEO controller — the orchestrator.

This is the brain that runs the daily workflow:
1. Load configuration and brand memory.
2. Generate one post per platform.
3. Run safety checks.
4. Post (or draft) according to mode and limits.
5. Check comments on owned posts and reply where safe.
6. Find external posts and draft/post comments where safe.
7. Log everything, update database, and return a structured result.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from config import CONFIG
from db import (
    session_scope,
    count_actions_today,
    recent_post_texts,
    already_engaged_today,
    update_platform_status,
    get_setting,
)
from models import (
    Action,
    EngagementHistory,
    Post,
    Comment,
    PlatformStatus,
    STATUS_DRAFT,
    STATUS_QUEUED,
    STATUS_APPROVED_AUTO,
    STATUS_POSTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_HUMAN_REQUIRED,
    STATUS_SKIPPED,
    DECISION_AUTO_POST,
    DECISION_DRAFT_ONLY,
    DECISION_BLOCKED,
    ACTION_POST,
    ACTION_REPLY,
    ACTION_EXTERNAL_COMMENT,
)

from agents.content_writer import generate_for_platform, ContentCandidate
from agents.comment_writer import generate_external_comment, CommentCandidate
from agents.reply_writer import generate_reply, is_simple_owned_comment, ReplyCandidate
from agents.engagement_finder import find_targets, EngagementTarget
from agents.media_planner import make_plan, save_plan
from agents.platform_operator import (
    post_to_linkedin,
    post_to_facebook,
    post_to_instagram,
    reply_facebook_comment,
    reply_instagram_comment,
    reply_linkedin_comment,
    external_comment_linkedin,
    external_comment_facebook,
    fetch_owned_facebook_comments,
    fetch_owned_instagram_comments,
    fetch_recent_facebook_posts,
    fetch_recent_instagram_media,
)
from connectors import telegram_bot

log = logging.getLogger(__name__)


# --------------------- Mode helpers --------------------- #

def current_mode() -> str:
    override = get_setting("mode_override", "")
    if override in ("DRY_RUN", "SEMI_AUTO", "FULL_AUTO"):
        return override
    return CONFIG.app_mode


def is_paused() -> bool:
    return get_setting("paused", "false").lower() == "true"


# --------------------- Limit helpers --------------------- #

def _limit_for(platform: str, action_type: str) -> int:
    l = CONFIG.limits
    if platform == "linkedin":
        if action_type == ACTION_POST:
            return l.linkedin_posts
        if action_type == ACTION_EXTERNAL_COMMENT:
            return l.linkedin_external_comments
        if action_type == "like":
            return l.linkedin_likes
    if platform == "instagram":
        if action_type == ACTION_POST:
            return l.instagram_posts
        if action_type == ACTION_REPLY:
            return l.instagram_replies
        if action_type == "like":
            return l.instagram_likes
    if platform == "facebook":
        if action_type == ACTION_POST:
            return l.facebook_posts
        if action_type == ACTION_REPLY:
            return l.facebook_replies
        if action_type == ACTION_EXTERNAL_COMMENT:
            return l.facebook_external_comments
    return 0


def _under_limit(session, platform: str, action_type: str) -> bool:
    cap = _limit_for(platform, action_type)
    if cap <= 0:
        return False
    return count_actions_today(session, platform, action_type) < cap


def _platform_human_required(session, platform: str) -> bool:
    row = session.query(PlatformStatus).filter_by(platform=platform).first()
    return bool(row and row.human_required)


# --------------------- Decision logic --------------------- #

def _should_auto_post(action_type: str, decision: str, mode: str, is_owned_reply: bool) -> bool:
    """Translate (mode, decision, action_type) -> auto-post yes/no."""
    if decision == DECISION_BLOCKED:
        return False
    if mode == "DRY_RUN":
        return False
    if action_type == ACTION_POST:
        # original posts: auto-post in SEMI_AUTO and FULL_AUTO if not draft_only
        return decision == DECISION_AUTO_POST
    if action_type == ACTION_REPLY:
        # owned-post replies: SEMI_AUTO allows simple safe ones; FULL_AUTO same
        return is_owned_reply and decision == DECISION_AUTO_POST
    if action_type == ACTION_EXTERNAL_COMMENT:
        # external comments only auto-post in FULL_AUTO and only at low risk
        return mode == "FULL_AUTO" and decision == DECISION_AUTO_POST
    return False


# --------------------- Persistence helpers --------------------- #

def _save_action(
    session,
    *,
    platform: str,
    action_type: str,
    text: str,
    risk_score: float,
    safety_decision: str,
    safety_reason: str,
    status: str,
    mode: str,
    target_url: str = "",
    target_name: str = "",
    topic: str = "",
    media_path: str = "",
    result_url: str = "",
    error: str = "",
    screenshot_path: str = "",
) -> Action:
    a = Action(
        platform=platform,
        action_type=action_type,
        text=text,
        risk_score=risk_score,
        safety_decision=safety_decision,
        safety_reason=safety_reason,
        status=status,
        mode=mode,
        target_url=target_url,
        target_name=target_name,
        topic=topic,
        media_path=media_path,
        result_url=result_url,
        error=error,
        screenshot_path=screenshot_path,
    )
    session.add(a)
    session.flush()
    return a


def _record_engagement(session, *, platform: str, target_name: str, target_url: str,
                       action_type: str, text: str) -> None:
    session.add(EngagementHistory(
        platform=platform,
        target_name=target_name,
        target_url=target_url,
        action_type=action_type,
        text=text,
    ))


def _mirror_comment_row(session, *, platform: str, target_url: str,
                         target_name: str, text: str, status: str,
                         risk_score: float, posted_url: str = "") -> None:
    """Keep the Comments table in sync with comment/reply/external_comment
    actions. The Action table stays the canonical record; Comments is a
    denormalized view defined in the spec."""
    session.add(Comment(
        platform=platform,
        target_url=target_url,
        target_name=target_name,
        text=text,
        posted_url=posted_url,
        status=status,
        risk_score=risk_score,
    ))


# --------------------- Workflow steps --------------------- #

def _do_posts(mode: str) -> List[Dict]:
    """Generate and (optionally) post one piece of content per configured platform."""
    out: List[Dict] = []
    platforms = ["linkedin", "facebook", "instagram"]

    with session_scope() as s:
        for platform in platforms:
            if _platform_human_required(s, platform):
                out.append({
                    "platform": platform, "topic": "",
                    "status": STATUS_HUMAN_REQUIRED,
                    "risk_score": 0,
                    "result_url": "",
                    "error": "platform_human_required",
                })
                continue
            if not _under_limit(s, platform, ACTION_POST):
                out.append({
                    "platform": platform, "topic": "",
                    "status": STATUS_SKIPPED,
                    "risk_score": 0, "result_url": "",
                    "error": "daily_limit_reached",
                })
                continue

            recent = recent_post_texts(s, platform, days=14, limit=20)
            cand = generate_for_platform(platform, recent_posts=recent, recent_topics=_recent_topics(s))

            # Generate the media plan first so its path is recorded on the
            # Action and (when posted) the Post row.
            plan_path = ""
            try:
                plan = make_plan(platform, cand.topic, cand.text)
                plan_path = str(save_plan(plan))
            except Exception as e:
                log.warning("media plan save failed: %s", e)

            entry = _persist_and_maybe_post(s, cand, mode, media_path=plan_path)
            out.append(entry)
    return out


def _persist_and_maybe_post(s, cand: ContentCandidate, mode: str,
                             media_path: str = "") -> Dict:
    decision = cand.safety.decision
    if decision == DECISION_BLOCKED:
        a = _save_action(
            s,
            platform=cand.platform, action_type=ACTION_POST,
            text=cand.text or "", topic=cand.topic,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_BLOCKED, mode=mode,
            media_path=media_path,
            error=cand.error or cand.safety.reason,
        )
        return _serialize_action(a)

    if not _should_auto_post(ACTION_POST, decision, mode, is_owned_reply=False):
        a = _save_action(
            s,
            platform=cand.platform, action_type=ACTION_POST,
            text=cand.text, topic=cand.topic,
            media_path=media_path,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_DRAFT, mode=mode,
        )
        return _serialize_action(a)

    # Attempt post
    if cand.platform == "linkedin":
        result = post_to_linkedin(cand.text)
    elif cand.platform == "facebook":
        result = post_to_facebook(cand.text)
    elif cand.platform == "instagram":
        # IG requires media. v1 falls back to draft when neither image_url nor
        # local image is configured. The dashboard/human can attach one.
        result = post_to_instagram(cand.text)
    else:
        result = {"success": False, "error": "unknown_platform", "result_url": "",
                  "screenshot_path": "", "human_required": False}

    if result.get("human_required"):
        update_platform_status(s, cand.platform, "human_required",
                               error=result.get("error", ""), human_required=True,
                               screenshot_path=result.get("screenshot_path", ""))
        a = _save_action(
            s, platform=cand.platform, action_type=ACTION_POST,
            text=cand.text, topic=cand.topic,
            media_path=media_path,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_HUMAN_REQUIRED, mode=mode,
            error=result.get("error", ""),
            screenshot_path=result.get("screenshot_path", ""),
        )
        telegram_bot.alert(
            f"{cand.platform}: human required",
            result.get("error", "see screenshot"),
        )
        if result.get("screenshot_path"):
            telegram_bot.send_photo(result["screenshot_path"], f"{cand.platform} human required")
        return _serialize_action(a)

    if result.get("success"):
        a = _save_action(
            s, platform=cand.platform, action_type=ACTION_POST,
            text=cand.text, topic=cand.topic,
            media_path=media_path,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_POSTED, mode=mode,
            result_url=result.get("result_url", ""),
            screenshot_path=result.get("screenshot_path", ""),
        )
        s.add(Post(
            platform=cand.platform, topic=cand.topic, text=cand.text,
            media_path=media_path,
            posted_url=result.get("result_url", ""),
            posted_at=datetime.utcnow(),
        ))
        return _serialize_action(a)

    # Posting failed
    a = _save_action(
        s, platform=cand.platform, action_type=ACTION_POST,
        text=cand.text, topic=cand.topic,
        media_path=media_path,
        risk_score=cand.safety.risk_score,
        safety_decision=decision, safety_reason=cand.safety.reason,
        status=STATUS_FAILED, mode=mode,
        error=result.get("error", "unknown_error"),
        screenshot_path=result.get("screenshot_path", ""),
    )
    return _serialize_action(a)


def _do_replies(mode: str) -> List[Dict]:
    """Fetch comments on owned posts and reply where safe."""
    out: List[Dict] = []
    with session_scope() as s:
        # Facebook
        if not _platform_human_required(s, "facebook"):
            try:
                fb_posts = fetch_recent_facebook_posts()
                if fb_posts.get("success"):
                    for p in fb_posts.get("posts", [])[:5]:
                        fb_comments = fetch_owned_facebook_comments(p.get("id", ""))
                        if not fb_comments.get("success"):
                            continue
                        for c in fb_comments.get("comments", [])[:10]:
                            if not _under_limit(s, "facebook", ACTION_REPLY):
                                break
                            entry = _maybe_reply(s, "facebook", c, mode)
                            if entry:
                                out.append(entry)
            except Exception as e:
                log.warning("facebook reply scan failed: %s", e)

        # Instagram
        if not _platform_human_required(s, "instagram"):
            try:
                ig_media = fetch_recent_instagram_media()
                if ig_media.get("success"):
                    for m in ig_media.get("posts", [])[:5]:
                        ig_comments = fetch_owned_instagram_comments(m.get("id", ""))
                        if not ig_comments.get("success"):
                            continue
                        for c in ig_comments.get("comments", [])[:10]:
                            if not _under_limit(s, "instagram", ACTION_REPLY):
                                break
                            entry = _maybe_reply(s, "instagram", c, mode)
                            if entry:
                                out.append(entry)
            except Exception as e:
                log.warning("instagram reply scan failed: %s", e)

        # LinkedIn API path is unavailable for most apps; skip.
    return out


def _maybe_reply(s, platform: str, raw_comment: Dict, mode: str) -> Optional[Dict]:
    author = raw_comment.get("author", "")
    text = raw_comment.get("text", "")
    cid = raw_comment.get("id", "")
    if not text:
        return None

    # Skip if we already engaged with this author today
    if already_engaged_today(s, platform, author):
        return None

    # Skip already-replied comments by checking if we have an action targeting this id
    existing = (
        s.query(Action)
        .filter(Action.platform == platform, Action.action_type == ACTION_REPLY,
                Action.target_url.like(f"%{cid}%"))
        .first()
    )
    if existing:
        return None

    # Generate
    cand: ReplyCandidate = generate_reply(
        platform=platform,
        parent_post_url="",
        parent_comment_id=cid,
        parent_comment_author=author,
        parent_comment_text=text,
        recent_replies=recent_post_texts(s, platform, days=7, limit=20),
    )

    decision = cand.safety.decision
    simple = is_simple_owned_comment(text)
    auto = (
        decision == DECISION_AUTO_POST
        and simple
        and _should_auto_post(ACTION_REPLY, decision, mode, is_owned_reply=True)
    )

    if decision == DECISION_BLOCKED:
        a = _save_action(
            s, platform=platform, action_type=ACTION_REPLY,
            text=cand.text, target_url=cid, target_name=author,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_BLOCKED, mode=mode,
            error=cand.error or cand.safety.reason,
        )
        _mirror_comment_row(s, platform=platform, target_url=cid,
                            target_name=author, text=cand.text or "",
                            status=STATUS_BLOCKED,
                            risk_score=cand.safety.risk_score)
        return _serialize_action(a)

    if not auto:
        a = _save_action(
            s, platform=platform, action_type=ACTION_REPLY,
            text=cand.text, target_url=cid, target_name=author,
            risk_score=cand.safety.risk_score,
            safety_decision=decision, safety_reason=cand.safety.reason,
            status=STATUS_DRAFT, mode=mode,
        )
        _mirror_comment_row(s, platform=platform, target_url=cid,
                            target_name=author, text=cand.text,
                            status=STATUS_DRAFT,
                            risk_score=cand.safety.risk_score)
        return _serialize_action(a)

    # Post the reply
    if platform == "facebook":
        result = reply_facebook_comment(cid, cand.text)
    elif platform == "instagram":
        result = reply_instagram_comment(cid, cand.text)
    elif platform == "linkedin":
        result = reply_linkedin_comment(cid, cand.text)
    else:
        result = {"success": False, "error": "unknown_platform"}

    status = STATUS_POSTED if result.get("success") else STATUS_FAILED
    a = _save_action(
        s, platform=platform, action_type=ACTION_REPLY,
        text=cand.text, target_url=cid, target_name=author,
        risk_score=cand.safety.risk_score,
        safety_decision=decision, safety_reason=cand.safety.reason,
        status=status, mode=mode,
        error=result.get("error", ""),
        result_url=result.get("result_url", ""),
    )
    _mirror_comment_row(s, platform=platform, target_url=cid,
                        target_name=author, text=cand.text,
                        status=status,
                        risk_score=cand.safety.risk_score,
                        posted_url=result.get("result_url", ""))
    if result.get("success"):
        _record_engagement(s, platform=platform, target_name=author,
                           target_url=cid, action_type=ACTION_REPLY, text=cand.text)
    return _serialize_action(a)


def _do_external_comments(mode: str) -> List[Dict]:
    out: List[Dict] = []
    with session_scope() as s:
        targets = find_targets(limit=20)
        if not targets:
            return out

        recent = recent_post_texts(s, "any_external_comment", days=14, limit=30)

        for target in targets:
            platform = target.platform
            if _platform_human_required(s, platform):
                continue
            if not _under_limit(s, platform, ACTION_EXTERNAL_COMMENT):
                continue
            if already_engaged_today(s, platform, target.author_name):
                continue

            cand: CommentCandidate = generate_external_comment(
                platform=platform,
                target_url=target.url,
                target_name=target.author_name,
                target_text=target.text,
                recent_comments=recent,
            )

            decision = cand.safety.decision
            auto = _should_auto_post(ACTION_EXTERNAL_COMMENT, decision, mode, is_owned_reply=False)

            if decision == DECISION_BLOCKED:
                a = _save_action(
                    s, platform=platform, action_type=ACTION_EXTERNAL_COMMENT,
                    text=cand.text, target_url=target.url, target_name=target.author_name,
                    risk_score=cand.safety.risk_score,
                    safety_decision=decision, safety_reason=cand.safety.reason,
                    status=STATUS_BLOCKED, mode=mode,
                    error=cand.error or cand.safety.reason,
                )
                _mirror_comment_row(s, platform=platform, target_url=target.url,
                                    target_name=target.author_name,
                                    text=cand.text or "",
                                    status=STATUS_BLOCKED,
                                    risk_score=cand.safety.risk_score)
                out.append(_serialize_action(a))
                continue

            if not auto:
                a = _save_action(
                    s, platform=platform, action_type=ACTION_EXTERNAL_COMMENT,
                    text=cand.text, target_url=target.url, target_name=target.author_name,
                    risk_score=cand.safety.risk_score,
                    safety_decision=decision, safety_reason=cand.safety.reason,
                    status=STATUS_DRAFT, mode=mode,
                )
                _mirror_comment_row(s, platform=platform, target_url=target.url,
                                    target_name=target.author_name, text=cand.text,
                                    status=STATUS_DRAFT,
                                    risk_score=cand.safety.risk_score)
                out.append(_serialize_action(a))
                continue

            # Post the external comment
            if platform == "linkedin":
                result = external_comment_linkedin(target.url, cand.text)
            elif platform == "facebook":
                result = external_comment_facebook(target.url, cand.text)
            else:
                result = {"success": False, "error": "external_comment_unsupported_for_platform"}

            if result.get("human_required"):
                update_platform_status(
                    s, platform, "human_required",
                    error=result.get("error", ""), human_required=True,
                    screenshot_path=result.get("screenshot_path", ""),
                )
                status = STATUS_HUMAN_REQUIRED
            elif result.get("success"):
                status = STATUS_POSTED
            else:
                status = STATUS_FAILED

            a = _save_action(
                s, platform=platform, action_type=ACTION_EXTERNAL_COMMENT,
                text=cand.text, target_url=target.url, target_name=target.author_name,
                risk_score=cand.safety.risk_score,
                safety_decision=decision, safety_reason=cand.safety.reason,
                status=status, mode=mode,
                error=result.get("error", ""),
                result_url=result.get("result_url", ""),
                screenshot_path=result.get("screenshot_path", ""),
            )
            _mirror_comment_row(s, platform=platform, target_url=target.url,
                                target_name=target.author_name, text=cand.text,
                                status=status,
                                risk_score=cand.safety.risk_score,
                                posted_url=result.get("result_url", ""))
            if status == STATUS_POSTED:
                _record_engagement(s, platform=platform, target_name=target.author_name,
                                   target_url=target.url, action_type=ACTION_EXTERNAL_COMMENT,
                                   text=cand.text)
            out.append(_serialize_action(a))
    return out


# --------------------- Public entry points --------------------- #

def run_daily_workflow() -> Dict:
    mode = current_mode()
    paused = is_paused()
    log.info("Daily workflow start. mode=%s paused=%s", mode, paused)

    if paused:
        return {
            "mode": mode, "paused": True,
            "posts": [], "replies": [], "external_comments": [],
            "issues": ["paused — no actions taken"],
        }

    issues: List[str] = []
    posts: List[Dict] = []
    replies: List[Dict] = []
    ext: List[Dict] = []

    try:
        posts = _do_posts(mode)
    except Exception as e:
        log.exception("posts step failed: %s", e)
        issues.append(f"posts step failed: {e}")

    try:
        replies = _do_replies(mode)
    except Exception as e:
        log.exception("replies step failed: %s", e)
        issues.append(f"replies step failed: {e}")

    try:
        ext = _do_external_comments(mode)
    except Exception as e:
        log.exception("external comments step failed: %s", e)
        issues.append(f"external comments step failed: {e}")

    return {
        "mode": mode,
        "paused": paused,
        "posts": posts,
        "replies": replies,
        "external_comments": ext,
        "issues": issues,
    }


def run_post_now() -> Dict:
    """Generate one safe LinkedIn post and post it (mode-aware)."""
    mode = current_mode()
    if is_paused():
        return {"mode": mode, "paused": True, "posts": [], "replies": [],
                "external_comments": [], "issues": ["paused"]}
    with session_scope() as s:
        recent = recent_post_texts(s, "linkedin", days=14, limit=20)
        cand = generate_for_platform("linkedin", recent_posts=recent, recent_topics=_recent_topics(s))
        entry = _persist_and_maybe_post(s, cand, mode)
    return {"mode": mode, "paused": False, "posts": [entry], "replies": [],
            "external_comments": [], "issues": []}


def run_draft_comments_only() -> Dict:
    """Find external posts and draft comments — never post."""
    mode = "DRY_RUN"  # force draft semantics for this command
    out: List[Dict] = []
    with session_scope() as s:
        targets = find_targets(limit=10)
        if not targets:
            return {"mode": mode, "paused": False, "posts": [], "replies": [],
                    "external_comments": [], "issues": ["no_targets_configured"]}
        recent = recent_post_texts(s, "any_external_comment", days=14, limit=30)
        for t in targets:
            cand = generate_external_comment(
                platform=t.platform,
                target_url=t.url,
                target_name=t.author_name,
                target_text=t.text,
                recent_comments=recent,
            )
            status = STATUS_DRAFT if cand.safety.decision != DECISION_BLOCKED else STATUS_BLOCKED
            a = _save_action(
                s, platform=t.platform, action_type=ACTION_EXTERNAL_COMMENT,
                text=cand.text, target_url=t.url, target_name=t.author_name,
                risk_score=cand.safety.risk_score,
                safety_decision=cand.safety.decision, safety_reason=cand.safety.reason,
                status=status, mode=mode,
                error=cand.error or "",
            )
            _mirror_comment_row(s, platform=t.platform, target_url=t.url,
                                target_name=t.author_name, text=cand.text or "",
                                status=status, risk_score=cand.safety.risk_score)
            out.append(_serialize_action(a))
    return {"mode": mode, "paused": False, "posts": [], "replies": [],
            "external_comments": out, "issues": []}


def get_status_text() -> str:
    mode = current_mode()
    paused = is_paused()
    with session_scope() as s:
        rows = s.query(PlatformStatus).all()
    lines = [f"*GaugeFlow Social OS*", f"mode: `{mode}`", f"paused: `{paused}`", ""]
    for r in rows:
        flag = " (human required)" if r.human_required else ""
        lines.append(f"{r.platform}: {r.status}{flag}")
        if r.last_error:
            lines.append(f"   last_error: {r.last_error[:200]}")
    return "\n".join(lines)


# --------------------- Helpers --------------------- #

def _recent_topics(session) -> List[str]:
    rows = (
        session.query(Action.topic)
        .filter(Action.topic != "")
        .order_by(Action.created_at.desc())
        .limit(10)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _serialize_action(a: Action) -> Dict:
    return {
        "id": a.id,
        "platform": a.platform,
        "action_type": a.action_type,
        "topic": a.topic,
        "target_name": a.target_name,
        "target_url": a.target_url,
        "text": a.text,
        "risk_score": a.risk_score,
        "safety_decision": a.safety_decision,
        "safety_reason": a.safety_reason,
        "status": a.status,
        "result_url": a.result_url,
        "error": a.error,
        "screenshot_path": a.screenshot_path,
    }
