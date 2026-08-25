# CM Library

타운홀 덱에서 Culture Master 활동을 뽑아 사내 아카이브로 쌓는다.
정적 사이트 + GitHub Actions로만 동작한다. 서버가 없다.

```
매주 월요일  Actions
  → Drive 폴더에서 최신 타운홀 덱 찾기
  → Slides 텍스트에서 CM 블록만 잘라내기      (코드, 결정론적)
  → 잘린 블록만 요약해 JSON 항목 만들기        (Gemini API)
  → activities.json에 병합해 브랜치 push → Slack 알림
  → 사람이 링크 클릭해 PR 생성 → diff 확인하고 Merge
  → GitHub Pages 배포
```

## 설계상 중요한 두 가지

**1. 범위는 코드가 정한다.** 타운홀 덱에는 신규 입사자 실명, 수습 평가 코멘트,
사업부 KPI가 CM 파트 앞뒤로 붙어 있다. 그래서 "덱에서 CM 내용을 골라줘"라고
모델에 맡기지 않는다. `extract_cm_block.py`가 앵커 텍스트로 슬라이드 범위를 먼저
자르고, 모델은 잘린 블록만 본다. 유출 경로를 구조적으로 없앤 것이다.

앵커는 `scripts/extract_cm_block.py` 상단에 있다.

```python
START_ANCHORS = ["CM 활동 보고서"]
END_ANCHORS   = ["Culture Master 선정"]
```

덱 구성이 바뀌면 여기만 고치면 된다. 시작 앵커를 못 찾으면 스크립트는
넓게 잡는 대신 **실패한다**. 조용히 엉뚱한 슬라이드를 읽는 쪽이 더 위험하다.

**2. 날짜를 계산하지 않는다.** "매월 1일에 직전월을 읽는다"가 아니라
"폴더의 최신 덱을 보고, 이미 등록된 월이면 넘어간다"로 동작한다.
2026.07 덱은 7월 16일에 만들어져 8월 21일에도 수정됐다. 타운홀이 월 중순에
열리고 이후에도 손질된다는 뜻이라, 날짜 고정 방식은 미완성 덱을 읽거나
한 달을 놓치기 쉽다. 매주 확인하고 새 월이 보일 때만 움직이는 쪽이 안전하다.

## 로컬에서 먼저 돌려보기

인증 설정을 하기 전에 파싱이 되는지부터 확인하는 게 좋다.

gcloud의 기본 ADC 클라이언트는 **Drive 스코프를 더 이상 허용하지 않는다.**
`gcloud auth application-default login --scopes=.../drive.readonly`는 실패한다.
그래서 OAuth 클라이언트를 직접 만들어 쓴다. 한 번만 하면 된다.

**1. GCP 프로젝트 준비**

Cloud Console에서 프로젝트를 만들고 두 API를 활성화한다.

- Google Drive API
- Google Slides API

**2. OAuth 동의 화면**

APIs & Services → OAuth consent screen에서 **User type을 Internal**로 둔다.
사내 Workspace 계정만 쓰므로 Google 검수(verification)가 필요 없다.
External로 두면 Drive 스코프가 민감 스코프로 잡혀 검수 절차가 붙는다.

**3. OAuth 클라이언트 ID 발급**

APIs & Services → Credentials → Create credentials → OAuth client ID →
Application type을 **Desktop app**으로 선택하고 JSON을 내려받는다.

```bash
mkdir -p credentials
mv ~/Downloads/client_secret_*.json credentials/oauth_client.json
```

`credentials/`는 `.gitignore`에 있다. 시크릿과 토큰은 커밋되지 않는다.

**4. 실행**

`credentials/oauth_client.json`이 있으면 스크립트가 알아서 OAuth 흐름을 탄다.
최초 1회만 브라우저가 열리고, 이후에는 `credentials/token.json`을 재사용한다.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 폴더에 어떤 덱이 있나
python3 scripts/extract_cm_block.py --list

# 특정 월의 CM 블록이 제대로 잘리는지
python3 scripts/extract_cm_block.py --month 2026.07
head -40 build/cm_block.json

# 요약 결과를 파일에 쓰지 않고 눈으로 확인 (키는 ai.google.dev에서 발급, 무료 티어로 충분)
export GEMINI_API_KEY=...
python3 scripts/summarize_to_json.py --dry-run
```

과거 덱 몇 개(`2026.06`, `2026.05`, `2026.03`, `2025.11`)에 돌려서
슬라이드 범위가 전부 맞게 잘리는지 확인할 것. 여기서 어긋나면 앵커를 조정한다.

사이트는 정적 파일이라 그냥 띄우면 된다.

```bash
python3 -m http.server 8000   # → localhost:8000
```

## Actions로 옮기기

로컬에서 검증이 끝난 다음에 한다.

1. GCP 프로젝트에서 **Google Drive API**와 **Google Slides API** 활성화
2. 서비스 계정 생성 (**키는 만들지 않는다**)
3. Workload Identity Federation 설정 — GitHub OIDC를 신뢰하도록 풀/프로바이더 생성
4. 타운홀 폴더 `1XJk2GWFRFEfR9-b-uiz7weqGOLmBznXv`를 서비스 계정 이메일에 **뷰어로 공유**
5. 저장소 Secrets 등록
   - `GCP_WIF_PROVIDER`
   - `GCP_SERVICE_ACCOUNT`
   - `GEMINI_API_KEY` (ai.google.dev에서 발급. Anthropic API가 아니라 Gemini를
     쓰는 이유는 회사 정책상 새 유료 API 계정을 못 만들어서다 — Gemini는 이 정도
     사용량이면 무료 티어로 해결된다)
   - `SLACK_WEBHOOK_URL` (Slack Incoming Webhook. 아래 참고)
6. Settings → Pages → Source를 **GitHub Actions**로

3번을 쓰는 이유는 서비스 계정 JSON 키를 저장소에 두지 않기 위해서다.
조직 정책으로 키 생성 자체가 막혀 있는 경우가 많고, 보안 검토도 이 방식이 쉽다.

**4번에서 막힐 수 있다.** 서비스 계정 이메일은 `...gserviceaccount.com`이라
Workspace 입장에서 외부 사용자다. 외부 공유가 차단돼 있으면 공유가 안 된다.
그때는 Workspace 관리자에게 해당 도메인을 신뢰 도메인으로 추가해 달라고 요청한다.

## PR은 왜 자동으로 안 열리나

GitHub Actions가 새 활동을 찾으면 브랜치까지는 push하지만, **PR은 직접 열지
않는다.** `trustay-inc` 조직이 "Actions가 PR을 생성/승인하는 것"을 정책으로
막아뒀기 때문이다(조직 전체 설정이라 이 저장소만 풀 수 없다). 대신 Slack으로
"PR 열기" 링크(제목/본문이 미리 채워진 compare 페이지)를 보내고, 사람이 그
링크를 열어 버튼 한 번 누르면 된다. 사람이 diff를 한 번 보고 넘어가게 만드는
원래 목적(요약이 범위를 잘못 잡았을 때의 안전장치)은 그대로 유지된다.

Slack 알림을 받으려면 Incoming Webhook이 필요하다:

1. `https://api.slack.com/apps` → Create New App → From scratch
2. 만든 앱에서 **Incoming Webhooks** → Activate Incoming Webhooks 켜기
3. Add New Webhook to Workspace → 알림 받을 채널 선택
4. 발급된 Webhook URL(`https://hooks.slack.com/services/...`)을 `SLACK_WEBHOOK_URL`
   시크릿으로 등록

등록 안 해도 파이프라인 자체는 안 죽는다 — 브랜치 push까지는 되고 알림만 조용히
생략된다.

## 공개 범위

Pages가 public이면 이 사이트는 로그인 없이 누구나 본다. 검색엔진도 수집한다.
`data/activities.json`의 설정으로 실명 노출을 끌 수 있다.

```json
"config": { "showMemberNames": false }
```

`false`면 이름 대신 "참여 3명"으로 렌더한다. 참여자 이름은 아카이브의 핵심
가치("누구에게 물어보면 되는지")라서 기본값은 `true`로 뒀지만, 프로필 사진은
스키마에 아예 넣지 않았다. 나중에 추가는 쉽고 제거는 어렵다.

## 남은 것

- [ ] 과거 덱으로 앵커 검증 (로컬)
- [ ] GCP 프로젝트 · WIF · 폴더 공유
- [ ] 2026.06 이하 7개 활동의 상세 백필 — 지금은 목적과 참여 인원만 있다
- [ ] 실명 공개 여부 결정
