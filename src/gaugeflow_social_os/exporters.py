import csv
import json
from pathlib import Path
from typing import Dict, Sequence

from gaugeflow_social_os.engine import build_weekly_plan, critical_chain_points, member_health_scores, owner_load
from gaugeflow_social_os.models import Initiative, RitualSlot, SignalEvent, TeamMember


def export_initiatives_csv(initiatives: Sequence[Initiative], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "id",
                "title",
                "owner_id",
                "effort_points",
                "impact",
                "urgency",
                "confidence",
                "dependencies",
            ]
        )
        for initiative in initiatives:
            writer.writerow(
                [
                    initiative.id,
                    initiative.title,
                    initiative.owner_id,
                    initiative.effort_points,
                    initiative.impact,
                    initiative.urgency,
                    initiative.confidence,
                    ",".join(initiative.dependencies),
                ]
            )


def export_summary_markdown(
    members: Sequence[TeamMember],
    initiatives: Sequence[Initiative],
    signals: Sequence[SignalEvent],
    ritual_slots: Sequence[RitualSlot],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    health = member_health_scores(members, signals)
    loads = owner_load(initiatives)
    plan = build_weekly_plan(members, initiatives, ritual_slots)
    chain, chain_points = critical_chain_points(initiatives)

    lines = [
        "# GAUA-17 GaugeFlow Social OS Summary",
        "",
        "## Team Health",
    ]

    id_to_name: Dict[str, str] = {member.id: member.name for member in members}
    for member_id, score in health.items():
        lines.append(f"- {id_to_name.get(member_id, member_id)} ({member_id}): {score}/100")

    lines.extend(
        [
            "",
            "## Initiative Load",
        ]
    )
    for owner_id, points in loads.items():
        lines.append(f"- {id_to_name.get(owner_id, owner_id)} ({owner_id}): {points} pts")

    lines.extend(
        [
            "",
            "## Critical Chain",
            f"- Chain: {' -> '.join(chain)}",
            f"- Total effort points: {chain_points}",
            "",
            "## Weekly Plan",
        ]
    )

    for item in plan.items:
        lines.append(
            f"- {item.ritual_slot_id}: {item.initiative_id} owned by {id_to_name.get(item.owner_id, item.owner_id)} ({item.allocated_points} pts)"
        )

    if plan.unplanned_initiatives:
        lines.extend(
            [
                "",
                "## Unplanned Initiatives",
            ]
        )
        for initiative_id in plan.unplanned_initiatives:
            lines.append(f"- {initiative_id}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_plan_json(
    members: Sequence[TeamMember],
    initiatives: Sequence[Initiative],
    ritual_slots: Sequence[RitualSlot],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plan = build_weekly_plan(members, initiatives, ritual_slots)
    payload = {
        "planned": [
            {
                "ritual_slot_id": item.ritual_slot_id,
                "initiative_id": item.initiative_id,
                "owner_id": item.owner_id,
                "allocated_points": item.allocated_points,
            }
            for item in plan.items
        ],
        "unplanned_initiatives": plan.unplanned_initiatives,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
