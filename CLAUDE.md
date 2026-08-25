# CM Library — 작업 컨텍스트

## 무엇을 만들고 있나

트러스테이 사내 Culture Master(CM) 활동 아카이브. 매월 타운홀 덱(Google Slides)에서
CM 활동 보고서 부분만 뽑아 요약하고, 정적 사이트에 쌓는다. 서버 없이 GitHub Actions로만
돌린다. 참고한 원본 사이트: `https://cm-library-archive.trustay-ax-t-1998.chatgpt.site/`

작업자는 프론트엔드 개발자다. 백엔드/클라우드 콘솔 경험이 없다는 전제로,
GCP나 인프라 관련 안내는 단계를 건너뛰지 말 것.

## 파이프라인

```
매주 월요일 Actions
  → Drive 폴더에서 최신 타운홀 덱 찾기        (extract_cm_block.py)
  → Slides 텍스트에서 CM 블록만 잘라내기      (코드, 결정론적)
  → 잘린 블록만 요약해 JSON 항목 만들기       (summarize_to_json.py, Gemini API)
  → data/activities.json 병합해 브랜치 push → Slack 알림
  → 사람이 링크 클릭해 PR 생성 → diff 확인 후 Merge → Pages 배포
```

## 반드시 유지해야 하는 설계 결정

이 셋은 실제 사고를 막기 위한 것이다. 리팩터링하다 무너뜨리지 말 것.

**1. 범위는 코드가 정한다. LLM에 맡기지 않는다.**
타운홀 덱에는 CM 파트 앞뒤로 신규 입사자 실명, 수습 평가 코멘트, 사업부 KPI(객단가,
전환율, 유저 수)가 붙어 있다. 사이트가 public이므로 요약 범위를 모델이 판단하면
그게 유출 경로가 된다. `extract_cm_block.py`가 앵커로 슬라이드를 먼저 자르고,
모델은 잘린 블록만 본다.

**2. 앵커를 못 찾으면 넓게 잡는 대신 실패한다.**
조용히 엉뚱한 슬라이드를 읽는 쪽이 더 위험하다. 종료 코드로 구분한다.
- `4` = 그 달에 CM 발표가 없었다 (정상. 워크플로우가 no-op으로 넘긴다)
- `3` = 구조가 깨졌다 (진짜 실패)

**3. 날짜를 계산하지 않는다.**
"매월 1일에 직전월"이 아니라 "폴더 최신 덱이 미등록 월이면 처리"로 동작한다.
2026.07 덱은 7/16 생성 8/21 수정이었다. 타운홀이 월 중순이고 이후에도 손질되므로
날짜 고정 방식은 미완성 덱을 읽거나 한 달을 놓친다.

**4. 카테고리/상태는 enum 고정.**
자유 생성하게 두면 매달 분류가 흔들려 아카이브의 검색 가치가 사라진다.
`data/activities.json`의 `categories` / `statuses` 참조.

**5. 요약 모델은 Gemini다. Claude(Anthropic)가 아니다. (2026-08-25 결정)**
이 파일 이름이 CLAUDE.md라고 헷갈리지 말 것 — `summarize_to_json.py`가 호출하는
모델과는 무관하다. 회사 정책상 Anthropic Console에 새로 결제 수단을 등록해서
과금하는 게 불가능해서 바꿨다. Gemini API(ai.google.dev 발급 키)는 이 정도
사용량(매주 1회, 슬라이드 몇 장)이면 무료 티어로 충분하다. 무료 티어 요청은
구글이 제품 개선에 쓸 수 있다는 약관이 있는데, CM 블록은 이미 설계 결정 1번으로
실명 외 민감 정보가 제거된 상태라 감수 가능하다고 판단했다. `GEMINI_API_KEY`
시크릿, `google-genai` SDK, `response_schema`로 구조 강제 — 그래도 enum은
파싱 후 코드로 다시 검증한다(설계 결정 4번과 같은 이유).

**6. PR은 Actions가 못 연다. Slack 알림 + 사람이 클릭해서 연다. (2026-08-25 결정)**
`trustay-inc` 조직 정책이 "GitHub Actions가 PR을 직접 생성/승인하는 것"을
막아뒀다(조직 전체 설정, repo 단위로 못 풂 — 시도했다가 409 `Write permissions
for workflows are disabled by the organization` 받음). 대안을 세 가지 검토했다:
- **조직 정책 변경 요청**: 조직 전체 보안 설정을 건드리는 큰 부탁이라 보류.
- **Fine-grained PAT**: 최대 1년마다 갱신해야 하고(만료 없음 옵션이 없음),
  이 조직은 조직 소유 저장소에 대한 PAT 접근도 관리자 승인이 필요할 가능성이 큼
  ("Generate token and **request access**" 문구로 확인 가능). 반복 갱신이
  귀찮아서 보류.
- **GitHub App**: PAT보다 나음(설치 후엔 갱신 불필요, private key는 만료 없음)
  이지만, 이 조직은 멤버의 앱 설치 요청 자체를 막아뒀다(Install 페이지에
  조직이 선택지에 안 뜸 — 관리자 계정으로만 설치 가능). 관리자에게 "이 앱
  하나만 설치해달라"는 가벼운 부탁이면 되지만, 그 부탁조차 안 하기로 함.

그래서 **워크플로우는 브랜치 push까지만 하고, Slack Incoming Webhook으로
compare 링크(제목/본문 쿼리 파라미터로 미리 채움)를 보낸다.** 사람이 그 링크를
열고 "Create pull request"만 누르면 된다 — 리뷰 관문(설계 결정 없음 목록에는
안 적었지만 실질적 안전장치)은 그대로 유지된다. `SLACK_WEBHOOK_URL` 시크릿 필요.

## 확인된 사실

| 항목 | 값 |
|---|---|
| 타운홀 폴더 ID | `1XJk2GWFRFEfR9-b-uiz7weqGOLmBznXv` |
| 덱 제목 패턴 | `트러스테이 타운홀미팅(YYYY.MM)` |
| 파일 형식 | 네이티브 Google Slides |
| 2026.07 덱 크기 | 19.9MB → **`files.export` 10MB 제한 초과** |
| 폴더 내 덱 | 20개 (2025.02 ~ 2026.08), 일부 "의 사본" 중복. `extract_cm_block.py`가 이름에 "사본" 포함된 파일은 쿼리 단계에서 제외 → 실제 대상 18개 |
| 2025.12 덱 | **폴더에 존재하지 않음.** 이름 패턴 문제 아님(직접 확인) — 그 달은 타운홀 자체가 없었던 것으로 보임 |
| 참고 사이트 활동 수 | 8개 → **CM 파트가 없는 덱이 12개쯤 있다는 뜻** |
| CM 블록 위치 (2026.07) | 슬라이드 8-13 |
| 시작 앵커 | `CM 활동 보고서` (신규 포맷, 2025.08~). 2025 상반기는 이 앵커 자체가 없다 |
| 종료 앵커 | `Culture Master 선정` (제외. 다음 CM 발표 코너라 보고서가 아니다) |
| 앵커 전수 검증 (2026-08-25) | `--audit` 결과 CM 있음 **8개**로 참고 사이트와 정확히 일치. 검증 완료. 상세는 아래 참고 |

**pptx로 export하려는 시도는 하지 말 것.** 19.9MB로 10MB 제한을 넘는다.
Slides API로 텍스트를 직접 읽는 현재 방식이 정답이다.

## 인증

- **로컬**: `credentials/oauth_client.json`(Desktop app OAuth 클라이언트)이 있으면
  스크립트가 자동으로 OAuth 흐름을 탄다. 토큰은 `credentials/token.json`에 캐시.
- **CI**: Workload Identity Federation. 서비스 계정 JSON 키는 만들지 않는다.
- `gcloud auth application-default login --scopes=...drive.readonly`는 **동작하지 않는다.**
  Google이 기본 ADC 클라이언트에서 Drive 스코프를 막았다. 이 방법을 다시 제안하지 말 것.
- `credentials/`는 `.gitignore`에 있다. 절대 커밋하지 말 것.

## 지금 해야 할 일

**1. 앵커 전수 검증 — 완료 (2026-08-25)**

```bash
python3 scripts/extract_cm_block.py --audit
```

결과: CM 있음 **8개**로 참고 사이트와 정확히 일치. 세부 내용:

- 2025 상반기(02, 03, 06, 07)는 `CM 활동 보고서` 앵커 자체가 없는 구 포맷이다.
  직접 슬라이드를 열어 확인한 결과 이 4개월은 실제로 활동 보고 내용이 없었다
  (2025.03의 "25년도 2nd CM" 슬라이드는 CM 선정 발표일 뿐 활동 보고서가 아니라서
  설계 결정 1번과 같은 이유로 애초에 제외 대상). 그래서 구 포맷 전용 앵커는
  추가하지 않았다 — 앵커를 못 찾아 "CM 없음"으로 떨어지는 게 결과적으로 맞다.
- 2026.08을 포함해 6개월(2026.08, 2026.06, 2026.04, 2026.02, 2026.01, 2025.11)은
  시작 앵커는 찾았지만 본문이 제목+멤버 명단뿐이거나 "01" 같은 페이지 번호/직전
  슬라이드 반복만 있는 **미완성 덱**이었다. `extract_cm_block.py`의
  `cut_cm_block()`에 `is_block_complete()` 판정을 추가해서 이 경우도
  `CMBlockNotFound`(exit 4, no-op)로 처리하도록 고쳤다. 특히 2026.01·2026.02는
  2025.11 슬라이드가 지워지지 않고 그대로 남아있던 것이었다 — 그 두 달은 실제로
  CM 발표가 없었을 가능성이 높다.
- `list_townhall_decks()`가 이름에 "사본" 들어간 파일을 Drive 쿼리 단계에서
  제외하도록 바꿔서 중복 집계 문제도 함께 해결했다.
- 앞으로 매달 새 덱이 이 미완성 패턴(제목만 있고 본문 없음)에 걸리면 워크플로우가
  조용히 no-op으로 넘어간다. 타운홀 이후 덱이 계속 손질된다는 설계 결정 3번과
  같은 이유로, 다음 주 재실행 때 완성돼 있으면 그때 잡힌다.

**2. 남은 작업**

- [x] GitHub 저장소 생성 + 코드 push — 완료 (2026-08-25). `trustay-inc/cm-library`, public.
- [x] GCP 서비스 계정 + WIF 설정 — 완료 (2026-08-25). 프로젝트는 로컬 OAuth와
      같은 `cm-library-506606`을 그대로 썼다.
      - 서비스 계정: `cm-library-ci@cm-library-506606.iam.gserviceaccount.com`
        (프로젝트 IAM 역할은 없음 — Drive/Slides 접근은 파일 단위 공유로 제어되므로
        불필요. 아래 항목 참고)
      - Workload Identity Pool: `github-actions` / Provider: `github-provider`
        (`projects/422650727512/locations/global/workloadIdentityPools/github-actions/providers/github-provider`)
      - Provider의 `attribute-condition`을 `assertion.repository == 'trustay-inc/cm-library'`로
        좁혀서 다른 저장소의 Actions가 이 서비스 계정을 사칭 못 하게 막았다.
      - `roles/iam.workloadIdentityUser`를 서비스 계정에 바인딩하되 멤버를
        위 repo 하나로 스코프한 `principalSet://...attribute.repository/trustay-inc/cm-library`로 제한.
      - 서비스 계정 키(JSON)는 만들지 않았다 — 설계 그대로 WIF만 사용.
- [x] 타운홀 폴더를 서비스 계정에 뷰어로 공유 — 완료 (2026-08-25 확인).
      이 폴더는 개인 폴더가 아니라 **공유 드라이브**였고, 본인 계정은 `canEdit: true`지만
      `canShare: false`라서 직접 공유를 추가할 수 없었다(스코프를 넓혀도 안 됨 — 계정
      자체의 Drive ACL 제약). 공유 관리자(organizer)는 3명뿐: `yejin.lee@trustay.me`,
      `sanghee.lee@trustay.me`, `seungo.lee@trustay.me` (모두 Culture&Growth팀) —
      이 중 한 명이 승인해준 것으로 보인다. (참고: 조직 외부 공유 자체가 막혀있지
      않았다는 뜻이므로, 앞으로 비슷한 공유가 또 필요해지면 관리자 개입 없이 이
      세 명 중 한 명에게만 요청하면 된다.)
- [x] 저장소 Secrets `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GEMINI_API_KEY`
      등록 완료 (2026-08-25). `ANTHROPIC_API_KEY`는 등록했다가 Gemini로 전환하며
      삭제함 — 워크플로우가 더 이상 참조하지 않는다.
      ⚠️ 로컬에서 dry-run 테스트하며 실제 키 값이 대화창에 평문으로 노출됐다.
      사용자가 재발급은 하지 않기로 결정함(2026-08-25) — 위험을 인지한 상태.
- [x] Settings → Pages → Source를 GitHub Actions로 — 완료 (2026-08-25).
      `https://trustay-inc.github.io/cm-library/` 배포 확인됨 (HTTP 200).
- [x] GitHub Actions 실전 테스트 — 완료 (2026-08-25). `workflow_dispatch`로
      2025.08/2025.05/2025.04 세 달을 처리해 WIF 인증, Drive/Slides 추출,
      Gemini 요약까지 CI에서 정상 동작 확인. PR 생성만 조직 정책에 막혀서
      (아래 설계 결정 6번) 수동으로 열었다 — PR #1, #2, #3.
      - PR #2(2025.05)는 원본 슬라이드 자체의 월 표기 오류(6월로 적혀있음)와
        스키마 불일치(한 달에 활동 3개가 뭉쳐 들어감)가 있어서 리뷰 필요 표시함.
      - Gemini가 503(서버 과부하)로 한 번 실패했었다 — 재시도로 해결됨. 일시적
        오류이니 재시도 로직 추가할 필요는 아직 없어 보임(관찰 필요).
- [ ] `SLACK_WEBHOOK_URL` 시크릿 등록 — 아직 안 함 (설계 결정 6번). Slack에서
      Incoming Webhook 만들어서 `gh secret set SLACK_WEBHOOK_URL --repo
      trustay-inc/cm-library`로 등록할 것. 등록 전까지는 새 활동을 찾아도
      브랜치만 push되고 알림은 안 간다 — Slack 알림 스텝이 시크릿 없으면
      바로 종료하도록 가드를 넣어놔서 실패로 뜨지도 않는다(브랜치는 이미
      push됐으니 데이터 유실은 아님). 등록 후 한 번 `workflow_dispatch`로
      실제로 알림이 오는지 확인할 것.
- [ ] 2026.06 이하 7개 활동 상세 백필 (지금은 목적과 참여 인원만 있음)
- [ ] 실명 공개 여부 최종 결정

## public 공개에 관한 제약

GitHub 플랜이 Enterprise가 아니라 **Pages 사이트는 public이다.** 비공개 게시는
Enterprise Cloud 전용이다. 브라우저 JS 비밀번호는 의미 있는 보호가 아니므로 제안하지 말 것.

- 프로필 사진은 스키마에 **아예 넣지 않았다.** 추가하지 말 것.
- 실명은 `data/activities.json`의 `config.showMemberNames`로 끌 수 있다. 기본 `true`.
- 사업 지표나 인사 정보가 요약에 섞이면 안 된다. 설계 결정 1번이 이걸 막는 장치다.

## 사내 환경 특이사항

- Confluence(`trustay.atlassian.net`)는 **IP 허용목록이 켜져 있다.** 외부에서 REST API가
  막힌다. GitHub Actions 러너 IP는 허용목록(100개 한도)에 넣을 수 없으므로,
  Confluence 자동 게시는 이 경로로는 불가능하다. Forge 앱이 대안이지만 현재 범위 밖.
- Drive는 IP 제한 없이 접근된다. 확인됨.
