from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cm_rotation import AllocationError, build_public_projection, build_rotation
from cm_rotation.admin import (
    draw_presenters,
    next_draw_month,
    resolve_presenters,
    set_month_completions,
)
from cm_rotation.sheets import load_sheet_payload, replace_sheet_records


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the CM presenter rotation")
    parser.add_argument("--sheet-id", default=os.environ.get("CM_ROSTER_SHEET_ID"))
    parser.add_argument("--config", default="config/presenter-rotation.json")
    parser.add_argument("--out", default="data/presenter-rotation.json")
    parser.add_argument(
        "--operation",
        choices=("refresh", "auto-draw", "draw", "set-completions"),
        default="refresh",
    )
    parser.add_argument("--month")
    parser.add_argument("--presenters", default="", help="Comma-separated employee names or IDs")
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    if not args.sheet_id:
        parser.error("--sheet-id or CM_ROSTER_SHEET_ID is required")
    if args.operation in ("draw", "set-completions") and not args.month:
        parser.error("--month is required for this operation")

    try:
        config = _read_json(args.config)
        payload = load_sheet_payload(args.sheet_id, config)
        draw_month = args.month
        if args.operation == "auto-draw":
            draw_month = next_draw_month(payload)
            if draw_month:
                print(f"자동 추첨 대상 월: {draw_month}")
            else:
                print("자동 추첨 가능한 다음 달이 없습니다.")

        if args.operation == "draw" or (args.operation == "auto-draw" and draw_month):
            selected = draw_presenters(payload, draw_month)
            payload["assignments"].extend(
                {"employee_id": employee_id, "month": draw_month}
                for employee_id in selected
            )
            replace_sheet_records(
                args.sheet_id,
                "Assignments",
                ["employee_id", "month"],
                payload["assignments"],
            )
            names = {item["employee_id"]: item["name"] for item in payload["employees"]}
            print("추첨 완료: " + ", ".join(names[employee_id] for employee_id in selected))
        elif args.operation == "set-completions":
            identifiers = [item.strip() for item in args.presenters.split(",") if item.strip()]
            selected = resolve_presenters(payload, identifiers)
            set_month_completions(payload, args.month, selected)
            replace_sheet_records(
                args.sheet_id,
                "Completions",
                ["employee_id", "month"],
                payload["completions"],
            )
            replace_sheet_records(
                args.sheet_id,
                "Assignments",
                ["employee_id", "month"],
                payload["assignments"],
            )

        rotation = build_rotation(payload)
        public = build_public_projection(rotation, generated_at=args.generated_at)
    except (AllocationError, KeyError, TypeError, ValueError) as error:
        print(f"발표자 관리 실패: {error}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(public, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"공개용 발표 일정 생성: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
