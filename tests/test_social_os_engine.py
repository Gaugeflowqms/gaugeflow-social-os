import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from gaugeflow_social_os.data import INITIATIVES, RITUAL_SLOTS, SIGNALS, TEAM_MEMBERS
from gaugeflow_social_os.engine import (
    ValidationError,
    build_weekly_plan,
    critical_chain_points,
    member_health_scores,
    validate_inputs,
)
from gaugeflow_social_os.models import Initiative


class SocialOSEngineTests(unittest.TestCase):
    def test_validate_inputs_passes_for_seed_data(self):
        validate_inputs(TEAM_MEMBERS, INITIATIVES)

    def test_validate_inputs_fails_on_missing_dependency(self):
        broken = [
            Initiative(
                id="BROKEN",
                title="Broken initiative",
                owner_id="M-01",
                effort_points=1,
                impact=5,
                urgency=5,
                confidence=5,
                dependencies=["MISSING"],
            )
        ]
        with self.assertRaises(ValidationError):
            validate_inputs(TEAM_MEMBERS, broken)

    def test_health_scores_within_bounds(self):
        scores = member_health_scores(TEAM_MEMBERS, SIGNALS)
        self.assertEqual(set(scores.keys()), {member.id for member in TEAM_MEMBERS})
        for value in scores.values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_weekly_plan_respects_capacity(self):
        plan = build_weekly_plan(TEAM_MEMBERS, INITIATIVES, RITUAL_SLOTS)
        total_allocated = sum(item.allocated_points for item in plan.items)
        total_slot_capacity = sum(slot.capacity_points for slot in RITUAL_SLOTS)
        self.assertLessEqual(total_allocated, total_slot_capacity)

    def test_critical_chain_includes_dependency_root(self):
        chain, points = critical_chain_points(INITIATIVES)
        self.assertGreater(points, 0)
        self.assertIn("GF-17-01", chain)


if __name__ == "__main__":
    unittest.main()
