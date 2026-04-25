from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TeamMember:
    id: str
    name: str
    role: str
    focus_capacity: int


@dataclass(frozen=True)
class Initiative:
    id: str
    title: str
    owner_id: str
    effort_points: int
    impact: int
    urgency: int
    confidence: int
    dependencies: List[str]


@dataclass(frozen=True)
class SignalEvent:
    id: str
    member_id: str
    category: str
    intensity: int
    notes: str


@dataclass(frozen=True)
class RitualSlot:
    id: str
    name: str
    capacity_points: int


@dataclass(frozen=True)
class PlanItem:
    ritual_slot_id: str
    initiative_id: str
    owner_id: str
    allocated_points: int


@dataclass(frozen=True)
class WeeklyPlan:
    items: List[PlanItem]
    unplanned_initiatives: List[str]
