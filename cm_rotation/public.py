from __future__ import annotations

from .models import month_range


def build_public_projection(rotation: dict, generated_at: str | None = None) -> dict:
    cycle = rotation["cycle"]
    employees = rotation["employees"]
    assignments = rotation["assignments"]

    months = []
    for month in month_range(cycle.start_month, cycle.end_month):
        monthly = [assignment for assignment in assignments if assignment.month == month]
        presenters = []
        if cycle.show_names:
            presenters = [
                {
                    "name": employees[assignment.employee_id].name,
                    "department": employees[assignment.employee_id].department,
                    "jobTitle": employees[assignment.employee_id].job_title,
                    "status": assignment.status,
                }
                for assignment in monthly
            ]
        months.append(
            {
                "month": month,
                "target": cycle.monthly_target,
                "assignedCount": len(monthly),
                "completedCount": sum(a.status == "completed" for a in monthly),
                "presenters": presenters,
            }
        )

    completed = sum(assignment.status == "completed" for assignment in assignments)
    scheduled = sum(assignment.status == "scheduled" for assignment in assignments)
    return {
        "version": 1,
        "generatedAt": generated_at,
        "cycle": {
            "id": cycle.cycle_id,
            "startMonth": cycle.start_month,
            "endMonth": cycle.end_month,
            "allocationStartMonth": cycle.allocation_start_month,
            "resetMonth": cycle.reset_month,
            "planningEndMonth": cycle.planning_end_month,
            "monthlyTarget": cycle.monthly_target,
            "showNames": cycle.show_names,
            "autoAllocate": cycle.auto_allocate,
        },
        "summary": {
            "eligibleCount": rotation["eligible_count"],
            "completedCount": completed,
            "scheduledCount": scheduled,
            "remainingCount": rotation["eligible_count"] - completed - scheduled,
        },
        "months": months,
        "warnings": [],
    }
