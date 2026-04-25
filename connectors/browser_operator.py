"""Browser fallback operator using Playwright with a persistent Chrome profile.

Hard rules baked in:
- Never bypass captcha, 2FA, or login challenges.
- Always take a screenshot on completion, error, or stop condition.
- If a stop-condition phrase is visible, stop immediately, screenshot, and
  return human_required=True.
- Use saved sessions; do not type passwords unless LOGIN_AUTOMATION_ALLOWED.
- Random delay between actions.
"""
from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

from config import CONFIG, SCREENSHOT_DIR
from agents.safety_checker import scan_browser_page

log = logging.getLogger(__name__)


def _result(
    success: bool,
    platform: str,
    action_type: str,
    result_url: str = "",
    error: str = "",
    human_required: bool = False,
    screenshot_path: str = "",
) -> Dict:
    return {
        "success": success,
        "platform": platform,
        "action_type": action_type,
        "result_url": result_url,
        "error": error,
        "screenshot_path": screenshot_path,
        "human_required": human_required,
    }


def is_enabled() -> bool:
    return bool(CONFIG.browser_enabled and CONFIG.browser_profile_path)


def _screenshot_name(platform: str, label: str) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    return SCREENSHOT_DIR / f"{platform}_{label}_{stamp}.png"


def _safe_pause(min_s: float = 1.5, max_s: float = 3.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


@contextmanager
def _browser_context() -> Iterator:
    """Open Playwright with a persistent Chrome profile. Caller manages pages."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "playwright not installed. pip install playwright && playwright install chromium"
        ) from e

    profile = CONFIG.browser_profile_path
    if not profile:
        raise RuntimeError("BROWSER_PROFILE_PATH not set")
    Path(profile).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=CONFIG.headless,
            viewport={"width": 1280, "height": 900},
        )
        try:
            yield ctx
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def _check_stop_conditions(page, platform: str, label: str) -> Optional[Dict]:
    """If the page shows a security challenge / stop condition, screenshot
    and return a human_required result. Otherwise return None."""
    try:
        text = page.inner_text("body", timeout=3000)
    except Exception:
        text = ""
    matched = scan_browser_page(text or "")
    if matched:
        shot = _screenshot_name(platform, f"stop_{label}")
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception as e:
            log.warning("screenshot failed: %s", e)
        log.warning("Stop condition on %s/%s: %r — human required", platform, label, matched)
        return _result(
            False, platform, label,
            error=f"stop_condition: {matched}",
            human_required=True,
            screenshot_path=str(shot),
        )
    return None


def _shot_after_action(page, platform: str, label: str) -> str:
    p = _screenshot_name(platform, label)
    try:
        page.screenshot(path=str(p), full_page=True)
        return str(p)
    except Exception as e:
        log.warning("post-action screenshot failed: %s", e)
        return ""


# ----------------------- LinkedIn ----------------------- #

def linkedin_create_post(text: str) -> Dict:
    if not is_enabled():
        return _result(False, "linkedin", "post", error="browser_disabled")
    try:
        with _browser_context() as ctx:
            page = ctx.new_page()
            page.goto("https://www.linkedin.com/feed/", timeout=45000)
            _safe_pause()

            # Stop if not logged in / challenge
            stop = _check_stop_conditions(page, "linkedin", "post_open")
            if stop:
                return stop

            # Detect login state
            if "login" in page.url.lower() or page.locator("input[name='session_password']").count() > 0:
                shot = _shot_after_action(page, "linkedin", "login_required")
                return _result(
                    False, "linkedin", "post",
                    error="login_required",
                    human_required=True,
                    screenshot_path=shot,
                )

            # Open the share box
            try:
                page.locator("button:has-text('Start a post')").first.click(timeout=15000)
            except Exception as e:
                shot = _shot_after_action(page, "linkedin", "post_no_button")
                return _result(False, "linkedin", "post", error=f"start_button_missing: {e}", screenshot_path=shot)

            _safe_pause(1.0, 2.0)
            stop = _check_stop_conditions(page, "linkedin", "post_modal")
            if stop:
                return stop

            try:
                editor = page.locator("div[role='textbox']").first
                editor.click(timeout=10000)
                editor.fill("")
                editor.type(text, delay=12)
            except Exception as e:
                shot = _shot_after_action(page, "linkedin", "post_typing")
                return _result(False, "linkedin", "post", error=f"editor_error: {e}", screenshot_path=shot)

            _safe_pause(1.0, 2.0)
            try:
                page.locator("button:has-text('Post')").last.click(timeout=15000)
            except Exception as e:
                shot = _shot_after_action(page, "linkedin", "post_submit")
                return _result(False, "linkedin", "post", error=f"submit_error: {e}", screenshot_path=shot)

            _safe_pause(2.5, 4.0)
            stop = _check_stop_conditions(page, "linkedin", "post_after")
            if stop:
                return stop

            shot = _shot_after_action(page, "linkedin", "post_done")
            return _result(True, "linkedin", "post", result_url=page.url, screenshot_path=shot)
    except Exception as e:
        log.exception("linkedin browser post error: %s", e)
        return _result(False, "linkedin", "post", error=str(e))


def linkedin_external_comment(post_url: str, text: str) -> Dict:
    if not is_enabled():
        return _result(False, "linkedin", "external_comment", error="browser_disabled")
    try:
        with _browser_context() as ctx:
            page = ctx.new_page()
            page.goto(post_url, timeout=45000)
            _safe_pause(2.0, 3.5)

            stop = _check_stop_conditions(page, "linkedin", "ext_comment_open")
            if stop:
                return stop

            if "login" in page.url.lower():
                shot = _shot_after_action(page, "linkedin", "ext_login_required")
                return _result(
                    False, "linkedin", "external_comment",
                    error="login_required",
                    human_required=True,
                    screenshot_path=shot,
                )

            try:
                page.locator("button[aria-label*='Comment']").first.click(timeout=10000)
            except Exception:
                pass

            _safe_pause(1.0, 2.0)
            try:
                editor = page.locator("div.comments-comment-box__form div[role='textbox']").first
                editor.click(timeout=10000)
                editor.type(text, delay=15)
            except Exception as e:
                shot = _shot_after_action(page, "linkedin", "ext_typing")
                return _result(False, "linkedin", "external_comment", error=f"editor_error: {e}", screenshot_path=shot)

            _safe_pause(1.5, 2.5)
            try:
                page.locator("button:has-text('Post')").first.click(timeout=10000)
            except Exception as e:
                shot = _shot_after_action(page, "linkedin", "ext_submit")
                return _result(False, "linkedin", "external_comment", error=f"submit_error: {e}", screenshot_path=shot)

            _safe_pause(2.0, 3.5)
            stop = _check_stop_conditions(page, "linkedin", "ext_comment_after")
            if stop:
                return stop

            shot = _shot_after_action(page, "linkedin", "ext_comment_done")
            return _result(True, "linkedin", "external_comment", result_url=post_url, screenshot_path=shot)
    except Exception as e:
        log.exception("linkedin browser external comment error: %s", e)
        return _result(False, "linkedin", "external_comment", error=str(e))


# ----------------------- Facebook (browser fallback) ----------------------- #

def facebook_create_post(text: str) -> Dict:
    if not is_enabled():
        return _result(False, "facebook", "post", error="browser_disabled")
    try:
        with _browser_context() as ctx:
            page = ctx.new_page()
            page.goto("https://www.facebook.com/", timeout=45000)
            _safe_pause(2.0, 3.5)

            stop = _check_stop_conditions(page, "facebook", "post_open")
            if stop:
                return stop

            if "login" in page.url.lower() or page.locator("input[name='pass']").count() > 0:
                shot = _shot_after_action(page, "facebook", "login_required")
                return _result(False, "facebook", "post", error="login_required",
                               human_required=True, screenshot_path=shot)

            try:
                page.locator("[role='button']:has-text(\"What's on your mind\")").first.click(timeout=15000)
            except Exception:
                shot = _shot_after_action(page, "facebook", "no_compose")
                return _result(False, "facebook", "post", error="compose_button_missing",
                               human_required=True, screenshot_path=shot)

            _safe_pause(1.0, 2.0)
            try:
                editor = page.locator("div[role='textbox']").first
                editor.click(timeout=10000)
                editor.type(text, delay=15)
            except Exception as e:
                shot = _shot_after_action(page, "facebook", "post_typing")
                return _result(False, "facebook", "post", error=f"editor_error: {e}", screenshot_path=shot)

            _safe_pause(1.0, 2.0)
            try:
                page.locator("[aria-label='Post'], div[role='button']:has-text('Post')").last.click(timeout=15000)
            except Exception as e:
                shot = _shot_after_action(page, "facebook", "post_submit")
                return _result(False, "facebook", "post", error=f"submit_error: {e}", screenshot_path=shot)

            _safe_pause(2.5, 4.0)
            stop = _check_stop_conditions(page, "facebook", "post_after")
            if stop:
                return stop

            shot = _shot_after_action(page, "facebook", "post_done")
            return _result(True, "facebook", "post", result_url=page.url, screenshot_path=shot)
    except Exception as e:
        log.exception("facebook browser post error: %s", e)
        return _result(False, "facebook", "post", error=str(e))


# ----------------------- Instagram (browser fallback) ----------------------- #

def instagram_create_post(image_path: str, caption: str) -> Dict:
    """IG web compose flow is fragile and varies. We attempt a basic compose,
    take screenshots, and bail out to human_required on any unexpected step."""
    if not is_enabled():
        return _result(False, "instagram", "post", error="browser_disabled")
    if not image_path or not Path(image_path).exists():
        return _result(False, "instagram", "post", error=f"image_not_found:{image_path}",
                       human_required=True)
    try:
        with _browser_context() as ctx:
            page = ctx.new_page()
            page.goto("https://www.instagram.com/", timeout=45000)
            _safe_pause(2.0, 3.5)

            stop = _check_stop_conditions(page, "instagram", "post_open")
            if stop:
                return stop

            if "login" in page.url.lower() or page.locator("input[name='password']").count() > 0:
                shot = _shot_after_action(page, "instagram", "login_required")
                return _result(False, "instagram", "post", error="login_required",
                               human_required=True, screenshot_path=shot)

            # Click "Create"
            try:
                page.locator("svg[aria-label='New post']").first.click(timeout=15000)
            except Exception:
                shot = _shot_after_action(page, "instagram", "no_create")
                return _result(False, "instagram", "post", error="create_button_missing",
                               human_required=True, screenshot_path=shot)

            _safe_pause(1.0, 2.0)
            try:
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(image_path)
            except Exception as e:
                shot = _shot_after_action(page, "instagram", "no_file_input")
                return _result(False, "instagram", "post", error=f"file_input_error: {e}",
                               human_required=True, screenshot_path=shot)

            _safe_pause(2.0, 3.0)
            # Skip crop/filter steps — UI varies; the human-required path is
            # intentionally generous here.
            for label in ("Next", "Next", "Share"):
                try:
                    page.locator(f"div[role='button']:has-text('{label}')").first.click(timeout=10000)
                except Exception as e:
                    shot = _shot_after_action(page, "instagram", f"step_{label.lower()}")
                    return _result(False, "instagram", "post",
                                   error=f"step_{label}_error: {e}",
                                   human_required=True, screenshot_path=shot)
                _safe_pause(1.0, 2.0)
                if label == "Next":
                    # Type caption when caption box appears
                    try:
                        cap = page.locator("textarea[aria-label='Write a caption...']").first
                        if cap.count() > 0:
                            cap.click()
                            cap.type(caption, delay=12)
                    except Exception:
                        pass

            _safe_pause(3.0, 5.0)
            stop = _check_stop_conditions(page, "instagram", "post_after")
            if stop:
                return stop

            shot = _shot_after_action(page, "instagram", "post_done")
            return _result(True, "instagram", "post", result_url=page.url, screenshot_path=shot)
    except Exception as e:
        log.exception("instagram browser post error: %s", e)
        return _result(False, "instagram", "post", error=str(e))


def check_session(platform: str) -> Dict:
    """Open the platform front page, verify the saved session is logged in,
    take a screenshot. Used by the platform_operator at start of day."""
    if not is_enabled():
        return _result(False, platform, "session_check", error="browser_disabled")
    urls = {
        "linkedin": "https://www.linkedin.com/feed/",
        "facebook": "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/",
    }
    url = urls.get(platform)
    if not url:
        return _result(False, platform, "session_check", error=f"unknown_platform:{platform}")
    try:
        with _browser_context() as ctx:
            page = ctx.new_page()
            page.goto(url, timeout=45000)
            _safe_pause(1.5, 2.5)
            stop = _check_stop_conditions(page, platform, "session_check")
            if stop:
                return stop
            logged_in_indicators = {
                "linkedin": ["a[href*='/feed/']", "div.feed-identity-module"],
                "facebook": ["div[aria-label='Account Controls and Settings']", "div[role='banner']"],
                "instagram": ["svg[aria-label='Home']", "a[href='/']"],
            }[platform]
            for sel in logged_in_indicators:
                if page.locator(sel).count() > 0:
                    shot = _shot_after_action(page, platform, "session_ok")
                    return _result(True, platform, "session_check",
                                   result_url=page.url, screenshot_path=shot)
            shot = _shot_after_action(page, platform, "session_unknown")
            return _result(False, platform, "session_check",
                           error="not_logged_in_or_unknown_state",
                           human_required=True, screenshot_path=shot)
    except Exception as e:
        log.exception("session_check error: %s", e)
        return _result(False, platform, "session_check", error=str(e))
