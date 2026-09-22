from __future__ import annotations

import secrets

from .allocator import ACTIVE_STATUSES, AllocationError, _available
from .models import Cycle, Deferral, Employee, month_range


def _employees(payload: dict) -> dict[str, Employee]:
    return {
        employee.employee_id: employee
        for employee in (Employee.from_dict(item) for item in payload.get("employees", []))
    }


def draw_presenters(payload: dict, month: str, chooser=None) -> list[str]:
    cycle = Cycle.from_dict(payload["cycle"])
    cycle_months = month_range(cycle.start_month, cycle.end_month)
    if month not in cycle_months:
        raise AllocationError(f"assignment month is outside cycle: {month}")
    if month < cycle.allocation_start_month:
        raise AllocationError(
            f"draw month must be {cycle.allocation_start_month} or later"
        )

    draw_months = [item for item in cycle_months if item >= cycle.allocation_start_month]
    position = draw_months.index(month)
    if position:
        previous_month = draw_months[position - 1]
        previous_completed = sum(
            str(item.get("month", "")).strip() == previous_month
            for item in payload.get("completions", [])
        )
        if previous_completed < cycle.monthly_target:
            raise AllocationError(
                f"complete {previous_month} before drawing presenters for {month}"
            )

    employees = _employees(payload)
    deferrals = [Deferral.from_dict(item) for item in payload.get("deferrals", [])]
    used = {
        str(item["employee_id"]).strip()
        for key in ("completions", "assignments")
        for item in payload.get(key, [])
    }
    occupied = sum(
        str(item.get("month", "")).strip() == month
        for key in ("completions", "assignments")
        for item in payload.get(key, [])
    )
    slots = cycle.monthly_target - occupied
    if slots <= 0:
        raise AllocationError(f"{month} already has {occupied} presenters")

    candidates = [
        employee.employee_id
        for employee in employees.values()
        if employee.employee_id not in used
        and employee.employment_status.lower() in ACTIVE_STATUSES
        and (employee.joined_on is None or employee.joined_on <= cycle.snapshot_date)
        and _available(employee, month, deferrals)
    ]
    if len(candidates) < slots:
        raise AllocationError(
            f"{month} needs {slots} presenters but only {len(candidates)} are available"
        )
    picker = chooser or secrets.SystemRandom().sample
    return list(picker(candidates, slots))


def resolve_presenters(payload: dict, identifiers: list[str]) -> list[str]:
    employees = _employees(payload)
    names: dict[str, list[str]] = {}
    for employee in employees.values():
        names.setdefault(employee.name, []).append(employee.employee_id)

    result = []
    for identifier in identifiers:
        value = identifier.strip()
        if value in employees:
            employee_id = value
        elif value in names and len(names[value]) == 1:
            employee_id = names[value][0]
        elif value in names:
            raise AllocationError(f"duplicate employee name; use employee_id: {value}")
        else:
            raise AllocationError(f"unknown employee: {value}")
        if employee_id in result:
            raise AllocationError(f"duplicate presenter: {value}")
        result.append(employee_id)
    return result


def set_month_completions(payload: dict, month: str, employee_ids: list[str]) -> None:
    cycle = Cycle.from_dict(payload["cycle"])
    if month not in month_range(cycle.start_month, cycle.end_month):
        raise AllocationError(f"completion month is outside cycle: {month}")
    if len(employee_ids) > cycle.monthly_target:
        raise AllocationError(
            f"{month} cannot have more than {cycle.monthly_target} completed presenters"
        )

    selected = set(employee_ids)
    payload["completions"] = [
        item
        for item in payload.get("completions", [])
        if str(item.get("month", "")).strip() != month
        and str(item.get("employee_id", "")).strip() not in selected
    ] + [{"employee_id": employee_id, "month": month} for employee_id in employee_ids]
    payload["assignments"] = [
        item
        for item in payload.get("assignments", [])
        if str(item.get("month", "")).strip() != month
        and str(item.get("employee_id", "")).strip() not in selected
    ]
