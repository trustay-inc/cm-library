from __future__ import annotations

import unittest

from cm_rotation import AllocationError, build_public_projection, build_rotation
from cm_rotation.admin import draw_presenters, resolve_presenters, set_month_completions
from cm_rotation.models import month_range


def employee(number: int, **overrides) -> dict:
    item = {
        "employee_id": f"E{number:03d}",
        "name": f"구성원 {number}",
        "joined_on": "2025-01-01",
        "employment_status": "active",
        "department": "비공개 부서",
        "job_title": "비공개 직급",
    }
    item.update(overrides)
    return item


def payload(count: int = 6) -> dict:
    return {
        "cycle": {
            "cycle_id": "test-cycle",
            "start_month": "2026-01",
            "end_month": "2026-02",
            "allocation_start_month": "2026-01",
            "reset_month": "2026-03",
            "snapshot_date": "2025-12-31",
            "monthly_target": 3,
            "seed": "test-seed",
            "show_names": False,
        },
        "employees": [employee(index) for index in range(1, count + 1)],
        "deferrals": [],
        "completions": [],
        "assignments": [],
        "overrides": [],
    }


class RotationTests(unittest.TestCase):
    def test_draw_fills_only_the_three_monthly_slots(self):
        data = payload(7)
        selected = draw_presenters(data, "2026-01", chooser=lambda items, count: items[:count])
        self.assertEqual(selected, ["E001", "E002", "E003"])

    def test_set_completions_replaces_month_and_removes_scheduled_duplicates(self):
        data = payload(4)
        data["assignments"] = [
            {"employee_id": "E001", "month": "2026-01"},
            {"employee_id": "E004", "month": "2026-02"},
        ]
        data["completions"] = [{"employee_id": "E002", "month": "2026-01"}]
        selected = resolve_presenters(data, ["구성원 3", "E004"])
        set_month_completions(data, "2026-01", selected)
        self.assertEqual(
            data["completions"],
            [
                {"employee_id": "E003", "month": "2026-01"},
                {"employee_id": "E004", "month": "2026-01"},
            ],
        )
        self.assertEqual(data["assignments"], [])

    def test_non_replacement_assignment_is_deterministic(self):
        first = build_rotation(payload())
        second = build_rotation(payload())
        first_pairs = [(item.employee_id, item.month) for item in first["assignments"]]
        second_pairs = [(item.employee_id, item.month) for item in second["assignments"]]
        self.assertEqual(first_pairs, second_pairs)
        self.assertEqual(len({item.employee_id for item in first["assignments"]}), 6)

    def test_completed_employee_is_not_selected_again(self):
        data = payload(4)
        data["completions"] = [{"employee_id": "E001", "month": "2026-01"}]
        rotation = build_rotation(data)
        ids = [item.employee_id for item in rotation["assignments"]]
        self.assertEqual(ids.count("E001"), 1)

    def test_deferral_moves_employee_to_a_later_month(self):
        data = payload(2)
        data["cycle"]["monthly_target"] = 1
        data["deferrals"] = [
            {
                "employee_id": "E001",
                "start_month": "2026-01",
                "end_month": "2026-01",
                "reason": "private",
            }
        ]
        rotation = build_rotation(data)
        assigned = {item.employee_id: item.month for item in rotation["assignments"]}
        self.assertEqual(assigned["E001"], "2026-02")

    def test_more_than_monthly_capacity_remains_unassigned(self):
        rotation = build_rotation(payload(7))
        counts = [
            sum(item.month == month for item in rotation["assignments"])
            for month in ("2026-01", "2026-02")
        ]
        self.assertEqual(counts, [3, 3])
        public = build_public_projection(rotation)
        self.assertEqual(public["summary"]["remainingCount"], 1)

    def test_73_people_do_not_expand_monthly_groups_or_raise_an_error(self):
        data = payload(73)
        data["cycle"]["end_month"] = "2027-12"
        data["cycle"]["monthly_target"] = 3
        rotation = build_rotation(data)
        counts = [
            sum(item.month == month for item in rotation["assignments"])
            for month in month_range("2026-01", "2027-12")
        ]
        self.assertEqual(sum(counts), 72)
        self.assertEqual(set(counts), {3})
        public = build_public_projection(rotation)
        self.assertEqual(public["summary"]["remainingCount"], 1)

    def test_fixed_assignments_cannot_exceed_monthly_group_size(self):
        data = payload(4)
        data["assignments"] = [
            {"employee_id": f"E{index:03d}", "month": "2026-01"}
            for index in range(1, 5)
        ]
        with self.assertRaisesRegex(AllocationError, "monthly group size is 3"):
            build_rotation(data)

    def test_people_after_snapshot_are_left_for_the_next_cycle(self):
        data = payload(2)
        data["employees"][1]["joined_on"] = "2026-01-01"
        rotation = build_rotation(data)
        self.assertEqual([a.employee_id for a in rotation["assignments"]], ["E001"])

    def test_missing_join_date_is_allowed_for_verified_active_employee(self):
        data = payload(1)
        data["employees"][0]["joined_on"] = ""
        rotation = build_rotation(data)
        self.assertEqual([a.employee_id for a in rotation["assignments"]], ["E001"])

    def test_planning_horizon_leaves_later_people_unassigned(self):
        data = payload(4)
        data["cycle"]["monthly_target"] = 2
        data["cycle"]["planning_end_month"] = "2026-01"
        rotation = build_rotation(data)
        self.assertEqual(len(rotation["assignments"]), 2)
        public = build_public_projection(rotation)
        self.assertEqual(public["summary"]["remainingCount"], 2)

    def test_swap_preserves_people_and_changes_months(self):
        data = payload(2)
        data["cycle"]["monthly_target"] = 1
        data["assignments"] = [
            {"employee_id": "E001", "month": "2026-01"},
            {"employee_id": "E002", "month": "2026-02"},
        ]
        data["overrides"] = [
            {"type": "swap", "employee_id": "E001", "with_employee_id": "E002"}
        ]
        rotation = build_rotation(data)
        assigned = {item.employee_id: item.month for item in rotation["assignments"]}
        self.assertEqual(assigned, {"E002": "2026-01", "E001": "2026-02"})

    def test_public_projection_does_not_leak_private_employee_fields(self):
        data = payload(1)
        public = build_public_projection(
            build_rotation(data), generated_at="2026-09-18T00:00:00+00:00"
        )
        serialized = str(public)
        self.assertNotIn("비공개 부서", serialized)
        self.assertNotIn("비공개 직급", serialized)
        self.assertNotIn("E001", serialized)
        self.assertNotIn("구성원 1", serialized)
        self.assertEqual(public["months"][0]["assignedCount"], 1)

    def test_names_are_only_published_when_enabled(self):
        data = payload(1)
        data["cycle"]["show_names"] = True
        public = build_public_projection(build_rotation(data))
        presenter = public["months"][0]["presenters"][0]
        self.assertEqual(presenter["name"], "구성원 1")
        self.assertEqual(presenter["department"], "비공개 부서")
        self.assertEqual(presenter["jobTitle"], "비공개 직급")


if __name__ == "__main__":
    unittest.main()
