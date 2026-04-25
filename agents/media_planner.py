"""Media planner.

For each post, generates an optional media plan: image idea, carousel outline,
short reel idea, text overlay suggestion. The first version does not generate
actual images; it stores the plan in the database and on disk so the human can
produce or approve media later.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import EXPORT_DIR

log = logging.getLogger(__name__)


@dataclass
class MediaPlan:
    platform: str
    topic: str
    image_idea: str
    carousel_slides: List[str]
    reel_idea: str
    text_overlay: str

    def to_dict(self) -> dict:
        return asdict(self)


CAROUSEL_TEMPLATES = {
    "Cert packets": [
        "Your cert packet should not be a scavenger hunt.",
        "Material cert here. CMM report there. Rev note in an email.",
        "That works until shipment is waiting.",
        "Keep the record trail tied to the job.",
    ],
    "Audit stress": [
        "The auditor is rarely the problem.",
        "The problem is the records.",
        "Three folders, four spreadsheets, and a binder.",
        "Tie quality records to the job, not to a person's memory.",
    ],
    "Traceability from PO to shipment": [
        "Traceability is a chain.",
        "PO. Material cert. Inspection. CMM. Rev. Shipment.",
        "Break one link and the chain disappears.",
        "Keep them connected to the job.",
    ],
    "FAI packages": [
        "FAI should not depend on someone's memory.",
        "Drawing. Balloon. Inspection. AS9102 form.",
        "If any one of those is missing, FAI is late.",
        "Tie the package to the part and the rev.",
    ],
    "Calibration logs": [
        "Calibration records matter most when nobody has time to look.",
        "The audit asks for the gauge ID.",
        "The spreadsheet has a different ID.",
        "Pull calibration into the same system as the inspection record.",
    ],
}


def _matching_template(topic: str) -> Optional[List[str]]:
    if not topic:
        return None
    t = topic.lower()
    for k, v in CAROUSEL_TEMPLATES.items():
        if k.lower() in t or t in k.lower():
            return v
    return None


def make_plan(platform: str, topic: str, post_text: str) -> MediaPlan:
    template = _matching_template(topic)
    if template:
        slides = template[:]
    else:
        # Generic carousel: split the post text into 3-4 short slides
        sentences = [s.strip() for s in post_text.replace("\n", " ").split(".") if s.strip()]
        slides = sentences[:4] if len(sentences) >= 3 else [
            f"On {topic.lower()}.",
            "Most shops have the right people.",
            "What's missing is the connected record.",
            "Tie it to the job.",
        ]

    overlay = slides[0] if slides else topic
    image_idea = f"Plain shop-floor photo: workbench, calipers, drawing, inspection sheet — overlay: \"{overlay}\""
    reel_idea = (
        "5-8 second clip: pan across messy spreadsheets / binders / desktop folders, "
        "end on a clean GaugeFlow record view. No music, no voiceover."
    )

    return MediaPlan(
        platform=platform,
        topic=topic,
        image_idea=image_idea,
        carousel_slides=slides,
        reel_idea=reel_idea,
        text_overlay=overlay,
    )


def save_plan(plan: MediaPlan) -> Path:
    """Persist the plan as JSON under storage/exports for the human to review."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"media_plan_{plan.platform}_{stamp}.json"
    path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    log.info("Saved media plan to %s", path)
    return path
