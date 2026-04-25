from collections import defaultdict, deque
from typing import Dict, Iterable, List, Sequence, Tuple

from gaugeflow_social_os.models import Initiative, PlanItem, RitualSlot, SignalEvent, TeamMember, WeeklyPlan


class ValidationError(Exception):
    """Raised for invalid GaugeFlow planning graph or ownership."""


def _index_members(members: Sequence[TeamMember]) -> Dict[str, TeamMember]:
    idx: Dict[str, TeamMember] = {}
    for member in members:
        if member.id in idx:
            raise ValidationError(f"Duplicate team member id: {member.id}")
        idx[member.id] = member
    return idx


def _index_initiatives(initiatives: Sequence[Initiative]) -> Dict[str, Initiative]:
    idx: Dict[str, Initiative] = {}
    for initiative in initiatives:
        if initiative.id in idx:
            raise ValidationError(f"Duplicate initiative id: {initiative.id}")
        idx[initiative.id] = initiative
    return idx


def validate_inputs(members: Sequence[TeamMember], initiatives: Sequence[Initiative]) -> None:
    members_idx = _index_members(members)
    initiatives_idx = _index_initiatives(initiatives)

    for initiative in initiatives:
        if initiative.owner_id not in members_idx:
            raise ValidationError(f"Unknown owner '{initiative.owner_id}' on {initiative.id}")
        for dep in initiative.dependencies:
            if dep not in initiatives_idx:
                raise ValidationError(f"Unknown dependency '{dep}' on {initiative.id}")

    topological_order(initiatives)


def topological_order(initiatives: Sequence[Initiative]) -> List[str]:
    idx = _index_initiatives(initiatives)
    indegree = {initiative.id: 0 for initiative in initiatives}
    graph: Dict[str, List[str]] = defaultdict(list)

    for initiative in initiatives:
        for dep in initiative.dependencies:
            if dep not in idx:
                raise ValidationError(f"Unknown dependency '{dep}' on {initiative.id}")
            graph[dep].append(initiative.id)
            indegree[initiative.id] += 1

    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    order: List[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in sorted(graph[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(initiatives):
        raise ValidationError("Cycle detected in initiative dependencies")
    return order


def member_health_scores(members: Sequence[TeamMember], signals: Sequence[SignalEvent]) -> Dict[str, int]:
    _index_members(members)
    base = {member.id: 70 for member in members}

    category_weights = {
        "burnout_risk": -4,
        "collaboration_friction": -3,
        "delivery_confidence": 3,
        "momentum": 2,
    }

    for signal in signals:
        if signal.member_id not in base:
            raise ValidationError(f"Unknown member '{signal.member_id}' in signal {signal.id}")
        weight = category_weights.get(signal.category, 0)
        base[signal.member_id] += weight * signal.intensity

    for member_id in list(base):
        base[member_id] = max(0, min(100, base[member_id]))

    return dict(sorted(base.items()))


def _priority_score(initiative: Initiative) -> float:
    # Bias toward impact and urgency while discounting low-confidence bets.
    return (initiative.impact * 2.0 + initiative.urgency * 1.7 + initiative.confidence) / max(initiative.effort_points, 1)


def prioritize_initiatives(initiatives: Sequence[Initiative]) -> List[Initiative]:
    ordered_ids = topological_order(initiatives)
    idx = _index_initiatives(initiatives)
    by_score = sorted(ordered_ids, key=lambda iid: (-_priority_score(idx[iid]), iid))
    return [idx[iid] for iid in by_score]


def owner_load(initiatives: Iterable[Initiative]) -> Dict[str, int]:
    loads: Dict[str, int] = defaultdict(int)
    for initiative in initiatives:
        loads[initiative.owner_id] += initiative.effort_points
    return dict(sorted(loads.items()))


def build_weekly_plan(
    members: Sequence[TeamMember],
    initiatives: Sequence[Initiative],
    ritual_slots: Sequence[RitualSlot],
) -> WeeklyPlan:
    validate_inputs(members, initiatives)
    members_idx = _index_members(members)
    priorities = prioritize_initiatives(initiatives)

    slot_remaining = {slot.id: slot.capacity_points for slot in ritual_slots}
    member_remaining = {member.id: member.focus_capacity for member in members}
    planned_ids = set()
    items: List[PlanItem] = []

    for initiative in priorities:
        if any(dep not in planned_ids for dep in initiative.dependencies):
            continue

        if member_remaining[initiative.owner_id] < initiative.effort_points:
            continue

        assigned_slot_id = None
        for slot in ritual_slots:
            if slot_remaining[slot.id] >= initiative.effort_points:
                assigned_slot_id = slot.id
                break

        if assigned_slot_id is None:
            continue

        slot_remaining[assigned_slot_id] -= initiative.effort_points
        member_remaining[initiative.owner_id] -= initiative.effort_points
        planned_ids.add(initiative.id)

        # Allocation tracks where execution and accountability happen this week.
        items.append(
            PlanItem(
                ritual_slot_id=assigned_slot_id,
                initiative_id=initiative.id,
                owner_id=initiative.owner_id,
                allocated_points=initiative.effort_points,
            )
        )

    unplanned = [initiative.id for initiative in priorities if initiative.id not in planned_ids]

    return WeeklyPlan(items=items, unplanned_initiatives=unplanned)


def critical_chain_points(initiatives: Sequence[Initiative]) -> Tuple[List[str], int]:
    order = topological_order(initiatives)
    idx = _index_initiatives(initiatives)

    score: Dict[str, int] = {}
    parent: Dict[str, str] = {}

    for initiative_id in order:
        initiative = idx[initiative_id]
        if not initiative.dependencies:
            score[initiative_id] = initiative.effort_points
            continue

        best_dep = max(initiative.dependencies, key=lambda dep: score[dep])
        score[initiative_id] = score[best_dep] + initiative.effort_points
        parent[initiative_id] = best_dep

    end_node = max(order, key=lambda node: score[node])
    points = score[end_node]

    chain = [end_node]
    while chain[-1] in parent:
        chain.append(parent[chain[-1]])
    chain.reverse()

    return chain, points
