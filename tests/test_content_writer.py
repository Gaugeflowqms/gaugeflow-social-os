"""Content writer tests use a stub provider so no AI keys are required."""
from agents import content_writer
from agents.content_writer import generate_for_platform
from connectors.ai_provider import AIProvider


class StubProvider(AIProvider):
    name = "stub"

    def __init__(self, payload: str = ""):
        self.payload = payload or (
            "Most shops are not struggling because the people are bad at quality. "
            "They are struggling because the records are spread across too many "
            "places. Tie inspection records, FAI packages, and CMM reports to "
            "the job — not someone's desktop folder. AS9100 audits get a lot less "
            "stressful when the cert packet is already organized."
        )

    def complete(self, system, user, max_tokens=800, temperature=0.7):
        return self.payload


def test_generate_returns_safe_post():
    cand = generate_for_platform(
        platform="linkedin",
        recent_posts=[],
        recent_topics=[],
        provider=StubProvider(),
        forced_topic="AS9100 readiness",
    )
    assert cand.text
    assert cand.safety.decision in ("auto_post", "draft_only")
    assert cand.is_duplicate is False


def test_generate_blocks_duplicate():
    text = (
        "Most shops are not struggling because the people are bad at quality. "
        "They are struggling because the records are spread across too many places. "
        "Tie inspection records, FAI packages, and CMM reports to the job."
    )
    cand = generate_for_platform(
        platform="linkedin",
        recent_posts=[text],
        recent_topics=[],
        provider=StubProvider(payload=text),
        forced_topic="AS9100",
    )
    assert cand.is_duplicate is True
    assert cand.safety.decision == "blocked"


def test_generate_blocks_buzzword_post():
    bad = "Our 10x revolutionary game-changing platform will transform your business."
    cand = generate_for_platform(
        platform="linkedin",
        recent_posts=[],
        recent_topics=[],
        provider=StubProvider(payload=bad),
        forced_topic="AS9100",
    )
    assert cand.safety.decision == "blocked"


def test_generate_handles_skip():
    cand = generate_for_platform(
        platform="linkedin",
        recent_posts=[],
        recent_topics=[],
        provider=StubProvider(payload="SKIP"),
        forced_topic="AS9100",
    )
    assert cand.text == ""
    assert cand.safety.decision == "blocked"
    assert cand.error == "model_skipped"


def test_topic_rotation_picks_unused():
    # provide many "recent_topics" to verify pick_topic prefers fresh ones
    topics = content_writer.load_topics()
    used = topics[:8]
    pick = content_writer.pick_topic(used)
    # should not be in the first 8 used (unless we ran out)
    if len(topics) > 8:
        assert pick not in used
