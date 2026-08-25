"""
잘라낸 CM 블록을 activities.json 항목으로 변환한다.

모델은 "이미 잘린 블록"만 본다. 덱 전체를 넘기지 않는다.
카테고리와 상태는 enum으로 고정한다. 자유 생성하게 두면 매달 분류가 흔들려서
아카이브의 검색 가치가 사라진다. Gemini의 response_schema로 구조를 강제하지만,
enum은 모델이 새어나갈 수 있으니 파싱 후에도 코드로 다시 검증한다.

Claude API가 아니라 Gemini API를 쓰는 이유: 회사 정책상 Anthropic Console에
새로 결제 수단을 등록해 과금하는 게 불가능하다. Gemini API(ai.google.dev에서
발급한 키)는 이 정도 사용량(매주 1회, 슬라이드 몇 장)이면 무료 티어 안에서
해결된다. 무료 티어 요청은 구글이 제품 개선에 활용할 수 있다는 점은 감안할 것 —
CM 블록은 이미 실명 외 민감 정보(KPI, 인사 정보)가 제거된 상태라 감수 가능한
수준으로 판단했다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

CATEGORIES = [
    "행사",
    "관계형성",
    "오피스문화",
    "커뮤니케이션",
    "사내도구",
    "자동화",
]
STATUSES = ["운영중", "일회성", "개선 필요", "중단됨"]

SYSTEM = f"""당신은 사내 문화 활동 아카이브의 기록 담당자다.
주어진 것은 타운홀 덱에서 이미 잘라낸 "CM 활동 보고서" 슬라이드 텍스트다.

규칙:
- 주어진 텍스트에 있는 내용만 쓴다. 추측하거나 보충하지 않는다.
- 알 수 없는 필드는 null로 둔다. 그럴듯하게 채우지 않는다.
- category는 정확히 다음 중 하나: {", ".join(CATEGORIES)}
- status는 정확히 다음 중 하나: {", ".join(STATUSES)}
- purpose는 "무엇을 위해 했는가"를 한 문장으로. 활동 설명이 아니라 목적이다.
- background는 해결하려던 문제를 최대 4개 항목으로. 없으면 빈 배열.
- retrospective는 다음 담당자가 알아야 할 인수인계 사항. 없으면 null.
- 개인 평가, 인사 정보, 사업 지표는 쓰지 않는다. CM 활동과 무관하다."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "활동명"},
        "purpose": {"type": "string", "description": "목적 한 문장"},
        "category": {"type": "string", "enum": CATEGORIES},
        "status": {"type": "string", "enum": STATUSES},
        "members": {"type": "array", "items": {"type": "string"}},
        "background": {"type": "array", "items": {"type": "string"}},
        "usage": {
            "type": "string",
            "nullable": True,
            "description": "구성원이 실제로 어떻게 쓰는지. 없으면 null",
        },
        "retrospective": {
            "type": "string",
            "nullable": True,
            "description": "인수인계 사항. 없으면 null",
        },
        "resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "url": {"type": "string", "nullable": True},
                },
                "required": ["label", "url"],
            },
        },
    },
    "required": [
        "title",
        "purpose",
        "category",
        "status",
        "members",
        "background",
        "usage",
        "retrospective",
        "resources",
    ],
}


def summarize(block: dict) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    slides = "\n\n".join(
        f"[슬라이드 {s['index']}]\n{s['text']}" for s in block["slides"]
    )

    user_content = (
        f"대상 월: {block['month']}\n"
        f"출처: {block['file_title']} "
        f"(슬라이드 {block['slide_start']}-{block['slide_end']})\n\n"
        f"--- CM 블록 ---\n{slides}"
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )

    text = response.text
    if not text:
        reason = response.candidates[0].finish_reason if response.candidates else "?"
        raise ValueError(f"모델이 빈 응답을 반환했다 (finish_reason={reason})")

    try:
        item = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"모델 응답 파싱 실패: {e}\n응답: {text[:500]}", file=sys.stderr)
        raise

    # enum 검증. response_schema를 거쳤어도 조용히 통과시키지 않는다.
    if item.get("category") not in CATEGORIES:
        raise ValueError(f"category가 enum 밖: {item.get('category')!r}")
    if item.get("status") not in STATUSES:
        raise ValueError(f"status가 enum 밖: {item.get('status')!r}")

    item["month"] = block["month"]
    item["source"] = {
        "title": block["file_title"],
        "slides": f"{block['slide_start']}-{block['slide_end']}",
    }
    return item


def merge(archive_path: str, item: dict) -> bool:
    """activities.json에 병합. 이미 있는 월이면 건드리지 않는다."""
    with open(archive_path, encoding="utf-8") as f:
        archive = json.load(f)

    months = {a["month"] for a in archive["activities"]}
    if item["month"] in months:
        print(f"{item['month']}은 이미 등록됨. 변경 없음.")
        return False

    archive["activities"].append(item)
    archive["activities"].sort(key=lambda a: a["month"], reverse=True)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{item['month']} 추가: {item['title']}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", default="build/cm_block.json")
    ap.add_argument("--archive", default="data/activities.json")
    ap.add_argument(
        "--dry-run", action="store_true", help="병합하지 않고 결과만 출력"
    )
    args = ap.parse_args()

    with open(args.block, encoding="utf-8") as f:
        block = json.load(f)

    item = summarize(block)

    if args.dry_run:
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    changed = merge(args.archive, item)
    # 워크플로우가 PR 생성 여부를 판단하도록 신호를 남긴다.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
            f.write(f"month={item['month']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
