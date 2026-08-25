"""
타운홀 덱에서 CM 활동 보고서 블록만 잘라낸다.

핵심 원칙: 어떤 슬라이드를 읽을지는 코드가 결정론적으로 정한다.
LLM에게 "CM 관련 내용을 골라줘"라고 맡기지 않는다. 덱에는 신규 입사자 실명,
수습 평가, 사업부 KPI가 섞여 있어서 범위 판단을 모델에 넘기면 유출 경로가 된다.

인증은 두 경로를 자동으로 고른다.
  - credentials/oauth_client.json 이 있으면 → 로컬 OAuth 흐름 (본인 계정)
  - 없으면                                → google.auth.default() (CI의 WIF)

gcloud의 기본 ADC 클라이언트는 Drive 스코프를 더 이상 허용하지 않으므로
로컬 검증에는 직접 만든 OAuth 클라이언트를 쓴다. 자세한 절차는 README 참고.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
]

OAUTH_CLIENT_FILE = os.environ.get(
    "OAUTH_CLIENT_FILE", "credentials/oauth_client.json"
)
OAUTH_TOKEN_FILE = os.environ.get("OAUTH_TOKEN_FILE", "credentials/token.json")

# 타운홀 자료가 모여 있는 폴더. 2026.07 덱의 parentId로 확인됨.
DEFAULT_FOLDER_ID = os.environ.get(
    "TOWNHALL_FOLDER_ID", "1XJk2GWFRFEfR9-b-uiz7weqGOLmBznXv"
)

# "트러스테이 타운홀미팅(2026.07)"
TITLE_RE = re.compile(r"타운홀미팅\s*\(\s*(\d{4})\s*\.\s*(\d{2})\s*\)")

# CM 블록 경계. Step 0에서 과거 덱 전체가 같은 패턴임을 확인했다.
# 시작은 포함, 끝은 제외한다. "Culture Master 선정"은 다음 CM 발표 코너이고
# 활동 보고서가 아니므로 블록에서 뺀다.
START_ANCHORS = ["CM 활동 보고서"]
END_ANCHORS = ["Culture Master 선정"]


@dataclass
class CMBlock:
    month: str  # "2026.07"
    file_id: str
    file_title: str
    slide_start: int  # 1-based, 사람이 덱에서 확인하기 쉽게
    slide_end: int  # inclusive
    slides: list  # [{"index": int, "text": str}]

    def as_prompt_text(self) -> str:
        parts = []
        for s in self.slides:
            parts.append(f"[슬라이드 {s['index']}]\n{s['text']}")
        return "\n\n".join(parts)


def get_credentials():
    """로컬 OAuth 클라이언트가 있으면 그걸 쓰고, 없으면 ADC/WIF로 넘어간다."""
    if os.path.exists(OAUTH_CLIENT_FILE):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if os.path.exists(OAUTH_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    OAUTH_CLIENT_FILE, SCOPES
                )
                # 브라우저가 열린다. 최초 1회만.
                creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(OAUTH_TOKEN_FILE) or ".", exist_ok=True)
            with open(OAUTH_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return creds

    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def get_services():
    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    slides = build("slides", "v1", credentials=creds, cache_discovery=False)
    return drive, slides


def list_townhall_decks(drive, folder_id: str) -> list[dict]:
    """폴더 안의 타운홀 덱을 최신월 순으로 반환."""
    decks = []
    page_token = None
    query = (
        f"'{folder_id}' in parents"
        " and mimeType = 'application/vnd.google-apps.presentation'"
        " and trashed = false"
        " and not name contains '사본'"
    )
    while True:
        resp = (
            drive.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, modifiedTime)",
                pageSize=200,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            )
            .execute()
        )
        for f in resp.get("files", []):
            m = TITLE_RE.search(f["name"])
            if not m:
                continue
            decks.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "month": f"{m.group(1)}.{m.group(2)}",
                    "modifiedTime": f.get("modifiedTime"),
                }
            )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    decks.sort(key=lambda d: d["month"], reverse=True)
    return decks


def _shape_text(element) -> str:
    """도형/표에서 텍스트를 뽑는다."""
    out = []

    shape = element.get("shape")
    if shape:
        for te in shape.get("text", {}).get("textElements", []):
            run = te.get("textRun")
            if run:
                out.append(run.get("content", ""))

    table = element.get("table")
    if table:
        for row in table.get("tableRows", []):
            cells = []
            for cell in row.get("tableCells", []):
                buf = []
                for te in cell.get("text", {}).get("textElements", []):
                    run = te.get("textRun")
                    if run:
                        buf.append(run.get("content", ""))
                cells.append("".join(buf).strip())
            if any(cells):
                out.append(" | ".join(cells) + "\n")

    for child in element.get("elementGroup", {}).get("children", []):
        out.append(_shape_text(child))

    return "".join(out)


def slide_texts(slides_api, file_id: str) -> list[str]:
    """슬라이드별 텍스트. 인덱스는 0-based."""
    deck = slides_api.presentations().get(presentationId=file_id).execute()
    texts = []
    for slide in deck.get("slides", []):
        buf = [_shape_text(el) for el in slide.get("pageElements", [])]
        cleaned = re.sub(r"\n{3,}", "\n\n", "".join(buf)).strip()
        texts.append(cleaned)
    return texts


class CMBlockNotFound(LookupError):
    """덱은 찾았지만 그 안에 CM 활동 보고서 블록이 없을 때. (내용이 없는 미완성 덱 포함)"""


def find_anchor(texts: list[str], anchors: list[str], start_at: int = 0) -> int | None:
    for i in range(start_at, len(texts)):
        for a in anchors:
            if a in texts[i]:
                return i
    return None


# 첫 슬라이드(제목 + "Member : " 명단)만 있고 발표 자료가 아직 안 채워진 슬라이드는
# 페이지 번호("01" 등)만 있거나 텅 비어 있다. 실제 발표 내용이 있는 덱과 구분하는 데 쓴다.
_PLACEHOLDER_RE = re.compile(r"^[\d\s]*$")


def is_block_complete(body_texts: list[str]) -> bool:
    """제목 슬라이드 다음(본문)에 실제로 채워진 내용이 있는지 판정한다.

    감사(--audit)에서 실측한 두 가지 미완성 패턴을 근거로 한다.
      - 본문 슬라이드가 아예 없음 (제목 슬라이드 하나로 끝남)
      - 본문 슬라이드가 전부 페이지 번호뿐이거나, 같은 문구가 그대로 복사되어
        여러 장 반복됨 (예: 이전 달 슬라이드를 지우지 않고 그대로 둔 경우)
    """
    if not body_texts:
        return False

    non_placeholder = [t.strip() for t in body_texts if not _PLACEHOLDER_RE.match(t.strip())]
    if not non_placeholder:
        return False

    if len(body_texts) > 1 and len(set(non_placeholder)) <= 1:
        return False

    return True


def cut_cm_block(texts: list[str]) -> tuple[int, int]:
    """CM 블록의 [시작, 끝] 인덱스를 0-based inclusive로 반환."""
    start = find_anchor(texts, START_ANCHORS)
    if start is None:
        raise CMBlockNotFound(
            f"시작 앵커를 찾지 못했다: {START_ANCHORS}. "
            "덱 구성이 바뀌었을 수 있으니 앵커를 확인할 것."
        )

    end_exclusive = find_anchor(texts, END_ANCHORS, start_at=start + 1)
    if end_exclusive is None:
        # 종료 앵커가 없으면 블록을 무한정 늘리지 않고 좁게 끊는다.
        # 뒤쪽에는 사업부 KPI가 있어서 넓게 잡는 쪽이 더 위험하다.
        end_exclusive = min(start + 8, len(texts))
        print(
            f"경고: 종료 앵커 {END_ANCHORS}를 찾지 못해 {end_exclusive - start}장으로 제한했다.",
            file=sys.stderr,
        )

    end = end_exclusive - 1
    if not is_block_complete(texts[start + 1 : end + 1]):
        raise CMBlockNotFound(
            "CM 블록 앵커는 찾았지만 본문이 비어 있다 (제목/멤버 명단만 있거나 "
            "이전 달 슬라이드가 그대로 남아있는 미완성 덱으로 추정). "
            "타운홀 준비가 아직 안 끝났을 가능성이 높다."
        )

    return start, end


def extract(month: str | None = None, folder_id: str = DEFAULT_FOLDER_ID) -> CMBlock:
    drive, slides_api = get_services()

    decks = list_townhall_decks(drive, folder_id)
    if not decks:
        raise LookupError(f"폴더 {folder_id}에서 타운홀 덱을 찾지 못했다.")

    if month:
        target = next((d for d in decks if d["month"] == month), None)
        if not target:
            available = ", ".join(d["month"] for d in decks[:12])
            raise LookupError(f"{month} 덱이 없다. 사용 가능: {available}")
    else:
        target = decks[0]

    texts = slide_texts(slides_api, target["id"])
    start, end = cut_cm_block(texts)

    return CMBlock(
        month=target["month"],
        file_id=target["id"],
        file_title=target["name"],
        slide_start=start + 1,
        slide_end=end + 1,
        slides=[{"index": i + 1, "text": texts[i]} for i in range(start, end + 1)],
    )


def audit(folder_id: str = DEFAULT_FOLDER_ID) -> list[dict]:
    """폴더의 덱 전체를 돌면서 CM 블록 위치를 표로 뽑는다. 앵커 검증용."""
    drive, slides_api = get_services()
    decks = list_townhall_decks(drive, folder_id)

    rows = []
    for d in decks:
        row = {"month": d["month"], "name": d["name"], "file_id": d["id"]}
        try:
            texts = slide_texts(slides_api, d["id"])
            start, end = cut_cm_block(texts)
            row.update(
                {
                    "status": "CM 있음",
                    "slide_range": f"{start + 1}-{end + 1}",
                    "num_slides": end - start + 1,
                    "text_len": sum(len(texts[i]) for i in range(start, end + 1)),
                }
            )
        except CMBlockNotFound as e:
            reason = "미완성 덱" if "미완성" in str(e) else "앵커 없음"
            row.update(
                {
                    "status": f"CM 없음({reason})",
                    "slide_range": "-",
                    "num_slides": 0,
                    "text_len": 0,
                }
            )
        except HttpError as e:
            row.update(
                {
                    "status": f"API 오류({e.resp.status if e.resp else '?'})",
                    "slide_range": "-",
                    "num_slides": 0,
                    "text_len": 0,
                }
            )
        rows.append(row)
    return rows


def print_audit_table(rows: list[dict]) -> None:
    header = f"{'월':<8} {'CM 여부':<18} {'슬라이드':<10} {'글자수':>8}  덱 제목"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['month']:<8} {r['status']:<18} {r['slide_range']:<10} "
            f"{r['text_len']:>8}  {r['name']}"
        )

    found = sum(1 for r in rows if r["status"] == "CM 있음")
    incomplete = sum(1 for r in rows if r["status"] == "CM 없음(미완성 덱)")
    print()
    print(
        f"총 {len(rows)}개 덱 중 CM 있음 {found}개"
        + (f" (미완성으로 제외 {incomplete}개 별도)" if incomplete else "")
    )


def main():
    ap = argparse.ArgumentParser(description="타운홀 덱에서 CM 블록 추출")
    ap.add_argument("--month", help="YYYY.MM. 생략하면 폴더의 최신 덱")
    ap.add_argument("--folder-id", default=DEFAULT_FOLDER_ID)
    ap.add_argument("--out", default="build/cm_block.json")
    ap.add_argument(
        "--list", action="store_true", help="폴더의 타운홀 덱 목록만 출력하고 종료"
    )
    ap.add_argument(
        "--audit",
        action="store_true",
        help="폴더 전체 덱의 CM 블록 위치를 표로 출력하고 종료 (앵커 검증용)",
    )
    args = ap.parse_args()

    try:
        if args.list:
            drive, _ = get_services()
            for d in list_townhall_decks(drive, args.folder_id):
                print(f"{d['month']}  {d['name']}")
            return 0

        if args.audit:
            print_audit_table(audit(args.folder_id))
            return 0

        block = extract(args.month, args.folder_id)
    except HttpError as e:
        print(f"Google API 오류: {e}", file=sys.stderr)
        return 2
    except CMBlockNotFound as e:
        print(f"추출 실패: {e}", file=sys.stderr)
        return 4
    except LookupError as e:
        print(f"추출 실패: {e}", file=sys.stderr)
        return 3

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(asdict(block), f, ensure_ascii=False, indent=2)

    print(
        f"{block.month}: 슬라이드 {block.slide_start}-{block.slide_end} "
        f"({len(block.slides)}장) → {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
