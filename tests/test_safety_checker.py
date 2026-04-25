"""Tests for the safety checker. No network or DB needed."""
from agents.safety_checker import (
    check_action,
    is_duplicate,
    scan_browser_page,
)


def test_blocks_political_content():
    r = check_action(
        action_type="post",
        text="The democrats and republicans both need to fix this.",
        platform="linkedin",
    )
    assert r.decision == "blocked"
    assert r.risk_score >= 81


def test_blocks_medical_advice():
    r = check_action(
        action_type="post",
        text="If you have headaches you should diagnose them as migraines and take...",
        platform="linkedin",
    )
    assert r.decision == "blocked"


def test_blocks_buzzwords():
    r = check_action(
        action_type="post",
        text="Our 10x revolutionary platform will transform your business and unlock seamless growth.",
        platform="linkedin",
    )
    assert r.decision == "blocked"


def test_blocks_aggressive_cta():
    r = check_action(
        action_type="post",
        text="Book a demo today! Limited time only. DM me now.",
        platform="linkedin",
    )
    assert r.decision == "blocked"


def test_blocks_action_type():
    r = check_action(
        action_type="cold_dm",
        text="Hey, I noticed you run a CNC shop, want to chat?",
        platform="linkedin",
    )
    assert r.decision == "blocked"
    assert "cold_dm" in r.matched_rules[0]


def test_blocks_security_challenge_in_context():
    r = check_action(
        action_type="post",
        text="Quality records are part of the product.",
        platform="linkedin",
        extra_context="Please complete the captcha to verify it's you",
    )
    assert r.decision == "blocked"


def test_approves_safe_manufacturing_post():
    r = check_action(
        action_type="post",
        text=(
            "Most shops are not struggling because the people are bad at quality. "
            "They are struggling because the records are spread across too many "
            "places. AS9100 audits, FAI packages, and CMM reports get harder when "
            "the cert packet is a scavenger hunt. Tie quality records to the job."
        ),
        platform="linkedin",
    )
    assert r.decision == "auto_post"
    assert r.risk_score <= 50


def test_short_post_penalized():
    r = check_action(
        action_type="post",
        text="Short.",
        platform="linkedin",
    )
    assert r.risk_score >= 21


def test_external_comment_baseline_higher():
    safe_text = "Inspection records tied to the job make audits a lot less painful."
    post_r = check_action(action_type="post", text=safe_text, platform="linkedin")
    ext_r = check_action(action_type="external_comment", text=safe_text, platform="linkedin")
    assert ext_r.risk_score >= post_r.risk_score


def test_owned_reply_discount():
    # Use a domain-light line so the heavy domain discount doesn't make
    # both scores clamp to 0.
    text = "Solid point. The records around it are usually the harder part."
    reply_r = check_action(action_type="reply", text=text, platform="facebook", is_owned_post=True)
    ext_r = check_action(action_type="external_comment", text=text, platform="facebook")
    assert reply_r.risk_score < ext_r.risk_score


def test_duplicate_detection_exact():
    a = "Quality records are part of the product. Tie them to the job."
    assert is_duplicate(a, [a]) is True


def test_duplicate_detection_near():
    a = "Quality records are part of the product. Tie them to the job."
    b = "Quality records are part of the product. Tie them to the job today."
    assert is_duplicate(a, [b]) is True


def test_duplicate_detection_clearly_different():
    a = "Quality records are part of the product."
    b = "Calibration logs make audits less painful."
    assert is_duplicate(a, [b]) is False


def test_scan_browser_page_detects_captcha():
    assert scan_browser_page("Please complete the CAPTCHA below") == "captcha"
    assert scan_browser_page("verify it's you") == "verify it's you"
    assert scan_browser_page("Hello world") is None
