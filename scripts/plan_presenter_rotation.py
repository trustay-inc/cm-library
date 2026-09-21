from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cm_rotation import AllocationError, build_public_projection, build_rotation
from cm_rotation.sheets import load_sheet_payload


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the CM presenter rotation")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", help="Private local JSON input")
    source.add_argument("--sheet-id")
    parser.add_argument("--config", default="config/presenter-rotation.json")
    parser.add_argument("--out", default="data/presenter-rotation.json")
    parser.add_argument("--generated-at")
    parser.add_argument(
        "--private-plan-out",
        help="Optional ignored path for a private plan containing employee names",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = _read_json(args.config)
        sheet_id = args.sheet_id or os.environ.get("CM_ROSTER_SHEET_ID")
        if not args.input and not sheet_id:
            parser.error("one of --input, --sheet-id, or CM_ROSTER_SHEET_ID is required")
        payload = _read_json(args.input) if args.input else load_sheet_payload(sheet_id, config)
        payload.setdefault("cycle", config)
        rotation = build_rotation(payload)
        public = build_public_projection(rotation, generated_at=args.generated_at)
    except (AllocationError, KeyError, TypeError, ValueError) as error:
        print(f"발표자 배정 실패: {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(public, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        print(rendered, end="")
        return 0
    if args.private_plan_out:
        private_plan = {
            "cycle": rotation["cycle"].cycle_id,
            "assignments": [
                {
                    "employee_id": item.employee_id,
                    "name": rotation["employees"][item.employee_id].name,
                    "month": item.month,
                    "status": item.status,
                    "source": item.source,
                }
                for item in rotation["assignments"]
            ],
        }
        os.makedirs(os.path.dirname(args.private_plan_out) or ".", exist_ok=True)
        with open(args.private_plan_out, "w", encoding="utf-8") as handle:
            json.dump(private_plan, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"비공개 검토 계획 생성: {args.private_plan_out}")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    print(f"공개용 발표 일정 생성: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
