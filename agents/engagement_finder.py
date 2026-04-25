"""Engagement finder.

Finds candidate posts to comment on. The first version reads from a
configured list (memory/engagement_targets.json) and from the Facebook /
Instagram graph APIs where possible. It does not scrape private content
and never engages with sensitive or off-topic material.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from config import MEMORY_DIR

log = logging.getLogger(__name__)


KEYWORDS = (
    "AS9100", "ISO 9001", "ISO 13485", "FAI", "AS9102", "CMM",
    "inspection", "quality manager", "CNC machining",
    "aerospace manufacturing", "medical device manufacturing",
    "traceability", "calibration", "quality audit",
    "manufacturing quality", "supplier quality",
)

# Topics we never engage on
EXCLUDE_KEYWORDS = (
    "politics", "election", "religion", "abortion",
    "tragedy", "layoff", "lawsuit", "medical advice",
)


@dataclass
class EngagementTarget:
    platform: str
    url: str
    author_name: str
    text: str
    source: str  # "configured" | "search" | "feed"


def _targets_file() -> Path:
    return MEMORY_DIR / "engagement_targets.json"


def load_configured_targets() -> List[EngagementTarget]:
    f = _targets_file()
    if not f.exists():
        # seed with empty file so the human can edit it
        f.write_text(json.dumps({"targets": []}, indent=2), encoding="utf-8")
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("engagement_targets.json invalid: %s", e)
        return []
    out: List[EngagementTarget] = []
    for t in raw.get("targets", []):
        try:
            out.append(EngagementTarget(
                platform=t.get("platform", "").lower(),
                url=t.get("url", ""),
                author_name=t.get("author_name", ""),
                text=t.get("text", ""),
                source="configured",
            ))
        except Exception:
            continue
    return out


def looks_relevant(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if any(ex in t for ex in EXCLUDE_KEYWORDS):
        return False
    return any(kw.lower() in t for kw in KEYWORDS)


def find_targets(platform: Optional[str] = None, limit: int = 5) -> List[EngagementTarget]:
    """Return a filtered list of engagement targets.

    For now this only reads configured targets. The platform connectors can
    extend this by appending discovered posts via their fetch_search() helpers.
    """
    targets = load_configured_targets()
    if platform:
        targets = [t for t in targets if t.platform == platform.lower()]
    targets = [t for t in targets if looks_relevant(t.text)]
    return targets[:limit]
