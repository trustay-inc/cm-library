from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def month_key(value: str) -> str:
    year, month = value.split("-")
    parsed = date(int(year), int(month), 1)
    return parsed.strftime("%Y-%m")


def month_range(start: str, end: str) -> list[str]:
    cursor = date.fromisoformat(f"{month_key(start)}-01")
    finish = date.fromisoformat(f"{month_key(end)}-01")
    if cursor > finish:
        raise ValueError("cycle start_month must not be after end_month")

    result = []
    while cursor <= finish:
        result.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return result


@dataclass(frozen=True)
class Cycle:
    cycle_id: str
    start_month: str
    end_month: str
    allocation_start_month: str
    planning_end_month: str
    reset_month: str
    snapshot_date: date
    monthly_target: int = 3
    seed: str = "cm-presenter-rotation"
    show_names: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "Cycle":
        target = int(raw.get("monthly_target", 3))
        if target < 1:
            raise ValueError("monthly_target must be at least 1")
        cycle = cls(
            cycle_id=str(raw["cycle_id"]),
            start_month=month_key(raw["start_month"]),
            end_month=month_key(raw["end_month"]),
            allocation_start_month=month_key(raw["allocation_start_month"]),
            planning_end_month=month_key(
                raw.get("planning_end_month", raw["end_month"])
            ),
            reset_month=month_key(raw["reset_month"]),
            snapshot_date=date.fromisoformat(raw["snapshot_date"]),
            monthly_target=target,
            seed=str(raw.get("seed", "cm-presenter-rotation")),
            show_names=bool(raw.get("show_names", False)),
        )
        months = month_range(cycle.start_month, cycle.end_month)
        if cycle.allocation_start_month not in months:
            raise ValueError("allocation_start_month must be inside the cycle")
        if cycle.planning_end_month not in months:
            raise ValueError("planning_end_month must be inside the cycle")
        if cycle.planning_end_month < cycle.allocation_start_month:
            raise ValueError("planning_end_month must not precede allocation_start_month")
        return cycle


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    joined_on: date | None
    employment_status: str = "active"
    department: str | None = None
    job_title: str | None = None
    probation_until: date | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "Employee":
        probation = raw.get("probation_until") or None
        joined = raw.get("joined_on") or None
        return cls(
            employee_id=str(raw["employee_id"]).strip(),
            name=str(raw["name"]).strip(),
            joined_on=date.fromisoformat(joined) if joined else None,
            employment_status=str(raw.get("employment_status", "active")).strip(),
            department=(str(raw["department"]).strip() if raw.get("department") else None),
            job_title=(str(raw["job_title"]).strip() if raw.get("job_title") else None),
            probation_until=date.fromisoformat(probation) if probation else None,
        )


@dataclass(frozen=True)
class Deferral:
    employee_id: str
    start_month: str
    end_month: str
    reason: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "Deferral":
        return cls(
            employee_id=str(raw["employee_id"]).strip(),
            start_month=month_key(raw["start_month"]),
            end_month=month_key(raw["end_month"]),
            reason=(str(raw["reason"]).strip() if raw.get("reason") else None),
        )


@dataclass(frozen=True)
class Assignment:
    employee_id: str
    month: str
    status: str
    source: str


@dataclass(frozen=True)
class Override:
    kind: str
    employee_id: str
    with_employee_id: str | None = None
    replacement_employee_id: str | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "Override":
        return cls(
            kind=str(raw["type"]).strip().lower(),
            employee_id=str(raw["employee_id"]).strip(),
            with_employee_id=(
                str(raw["with_employee_id"]).strip()
                if raw.get("with_employee_id")
                else None
            ),
            replacement_employee_id=(
                str(raw["replacement_employee_id"]).strip()
                if raw.get("replacement_employee_id")
                else None
            ),
            reason=(str(raw["reason"]).strip() if raw.get("reason") else None),
        )
