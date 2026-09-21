from __future__ import annotations

import hashlib
from dataclasses import replace

from .models import Assignment, Cycle, Deferral, Employee, Override, month_range


class AllocationError(ValueError):
    pass


ACTIVE_STATUSES = {"active", "재직"}


def _stable_rank(seed: str, employee_id: str) -> str:
    return hashlib.sha256(f"{seed}:{employee_id}".encode()).hexdigest()


def _available(employee: Employee, month: str, deferrals: list[Deferral]) -> bool:
    if employee.probation_until and month <= employee.probation_until.strftime("%Y-%m"):
        return False
    return not any(
        d.employee_id == employee.employee_id and d.start_month <= month <= d.end_month
        for d in deferrals
    )


def _parse_assignments(raw: list[dict], status: str, source: str) -> list[Assignment]:
    return [
        Assignment(
            employee_id=str(item["employee_id"]).strip(),
            month=str(item["month"]).strip(),
            status=status,
            source=source,
        )
        for item in raw
    ]


def _apply_overrides(
    assignments: list[Assignment], overrides: list[Override], employees: dict[str, Employee]
) -> list[Assignment]:
    result = list(assignments)
    for override in overrides:
        positions = {a.employee_id: index for index, a in enumerate(result)}
        if override.kind == "swap":
            other = override.with_employee_id
            if override.employee_id not in positions or not other or other not in positions:
                raise AllocationError("swap requires two existing scheduled employees")
            left = positions[override.employee_id]
            right = positions[other]
            if result[left].status == "completed" or result[right].status == "completed":
                raise AllocationError("completed assignments cannot be swapped")
            left_month, right_month = result[left].month, result[right].month
            result[left] = replace(result[left], month=right_month, source="override:swap")
            result[right] = replace(result[right], month=left_month, source="override:swap")
        elif override.kind == "replace":
            replacement = override.replacement_employee_id
            if override.employee_id not in positions or not replacement:
                raise AllocationError("replace requires an existing assignment and replacement")
            if replacement not in employees:
                raise AllocationError(f"unknown replacement employee: {replacement}")
            if replacement in positions:
                raise AllocationError("replacement employee is already assigned in this cycle")
            target = positions[override.employee_id]
            if result[target].status == "completed":
                raise AllocationError("completed assignments cannot be replaced")
            result[target] = replace(
                result[target], employee_id=replacement, source="override:replace"
            )
        else:
            raise AllocationError(f"unsupported override type: {override.kind}")
    return result


def build_rotation(payload: dict) -> dict:
    cycle = Cycle.from_dict(payload["cycle"])
    employees_list = [Employee.from_dict(item) for item in payload.get("employees", [])]
    employees = {employee.employee_id: employee for employee in employees_list}
    if len(employees) != len(employees_list):
        raise AllocationError("employee_id values must be unique")

    deferrals = [Deferral.from_dict(item) for item in payload.get("deferrals", [])]
    completions = _parse_assignments(
        payload.get("completions", []), status="completed", source="history"
    )
    pinned = _parse_assignments(
        payload.get("assignments", []), status="scheduled", source="pinned"
    )
    overrides = [Override.from_dict(item) for item in payload.get("overrides", [])]

    cycle_months = month_range(cycle.start_month, cycle.end_month)
    eligible = {
        key: employee
        for key, employee in employees.items()
        if employee.employment_status.lower() in ACTIVE_STATUSES
        and (employee.joined_on is None or employee.joined_on <= cycle.snapshot_date)
    }

    assignments = completions + pinned
    for assignment in assignments:
        if assignment.employee_id not in employees:
            raise AllocationError(f"assignment references unknown employee: {assignment.employee_id}")
        if assignment.month not in cycle_months:
            raise AllocationError(f"assignment month is outside cycle: {assignment.month}")

    assignments = _apply_overrides(assignments, overrides, employees)
    assigned_ids = [assignment.employee_id for assignment in assignments]
    if len(assigned_ids) != len(set(assigned_ids)):
        raise AllocationError("an employee may only appear once in a cycle")

    for assignment in assignments:
        employee = employees[assignment.employee_id]
        if assignment.status == "scheduled":
            if assignment.employee_id not in eligible:
                raise AllocationError(
                    f"scheduled employee is not eligible: {assignment.employee_id}"
                )
            if not _available(employee, assignment.month, deferrals):
                raise AllocationError(
                    f"scheduled employee is deferred or on probation: {assignment.employee_id}"
                )

    remaining = [employee for key, employee in eligible.items() if key not in assigned_ids]
    remaining.sort(key=lambda employee: _stable_rank(cycle.seed, employee.employee_id))

    all_future_months = [
        month for month in cycle_months if month >= cycle.allocation_start_month
    ]
    for month in all_future_months:
        assigned = sum(1 for assignment in assignments if assignment.month == month)
        if assigned > cycle.monthly_target:
            raise AllocationError(
                f"{month} has {assigned} fixed assignments; monthly group size is "
                f"{cycle.monthly_target}"
            )

    planning_months = [
        month
        for month in all_future_months
        if month <= cycle.planning_end_month
    ]
    for month in planning_months:
        occupied = sum(1 for assignment in assignments if assignment.month == month)
        for _ in range(max(0, cycle.monthly_target - occupied)):
            selected_index = next(
                (
                    index
                    for index, employee in enumerate(remaining)
                    if _available(employee, month, deferrals)
                ),
                None,
            )
            if selected_index is None:
                break
            employee = remaining.pop(selected_index)
            assignments.append(
                Assignment(employee.employee_id, month, "scheduled", "automatic")
            )

    assignments.sort(key=lambda item: (item.month, item.employee_id))
    return {
        "cycle": cycle,
        "employees": employees,
        "eligible_count": len(set(eligible) | {item.employee_id for item in completions}),
        "assignments": assignments,
    }
