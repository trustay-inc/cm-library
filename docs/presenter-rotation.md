# CM 발표자 순환 운영

CM 발표자는 2년 주기 안에서 한 번만 배정한다. 임직원 원본 명부와 유예 사유는
공개 저장소에 넣지 않고, 접근이 제한된 Google Sheet에서만 관리한다. 저장소에는
웹 화면에 필요한 최소 집계와 승인된 이름 및 소속 정보만 생성한다.

## 기본 정책

- 현재 주기: 2026년 1월부터 2027년 12월
- 신규 배정 시작: 2026년 10월
- 최초 확정 범위: 2026년 10월부터 2027년 3월까지 6개월
- 월 배정 인원: 3명
- 명부 기준일: 2026년 9월 30일
- 다음 주기 리셋: 2028년 1월
- 기준일 이후 입사자는 다음 주기에 포함
- 완료자는 같은 주기에 다시 배정하지 않음
- CM 한 회차에는 3명을 배정
- 전체 인원에 대한 고정 상한이나 오류 기준은 두지 않으며, 주기 안에 배정되지 않은 사람은 잔여 인원으로 유지

정책 값은 `config/presenter-rotation.json`에서 관리한다. 현재 운영 설정은
`show_names`를 `true`로 두어 배정자의 실명, 부서, 직급을 공개한다.
다음 반기 일정을 확정할 때 `planning_end_month`를 늘린다. 기존 `Assignments`는
보존되며 새로 열린 기간의 빈자리만 채운다.

## Google Sheet 구조

시트 이름과 첫 행의 헤더를 아래와 정확히 맞춘다. 시트 자체는 서비스 계정에만
공유하고 링크 공개를 사용하지 않는다.

### Employees

`employee_id`, `name`, `department`, `job_title`, `joined_on`,
`employment_status`, `probation_until`

- `joined_on`, `probation_until`: 알 수 있으면 `YYYY-MM-DD`, 원본에서 제공하지 않으면 빈칸
- `employment_status`: `active` 또는 `재직`인 사람만 신규 배정 대상

입사일이 비어 있는 재직자는 기준일 이전부터 재직한 것으로 처리한다. 기준일 이후
입사자를 다음 주기로 넘기려면 실제 입사일을 반드시 입력한다.

### Deferrals

`employee_id`, `start_month`, `end_month`, `reason`

- 월 형식: `YYYY-MM`
- `reason`은 공개 데이터에 포함되지 않는다.

### Completions

`employee_id`, `month`

2026년에 이미 발표한 사람을 포함한다. 같은 사람을 두 번 입력하면 검증에 실패한다.

### Assignments

`employee_id`, `month`

이미 공지한 일정을 고정한다. 스크립트를 다시 실행해도 이 배정은 바뀌지 않고 빈
자리만 채운다.

### Overrides

`type`, `employee_id`, `with_employee_id`, `replacement_employee_id`, `reason`

- 맞교환: `type=swap`, 두 사번을 `employee_id`, `with_employee_id`에 입력
- 결원 대체: `type=replace`, 기존 사번과 `replacement_employee_id` 입력
- 완료된 발표는 교환하거나 대체할 수 없다.

## 로컬 검증

실제 명부 대신 같은 구조의 비공개 JSON 파일로 검증할 수 있다.

```bash
python scripts/plan_presenter_rotation.py \
  --input tests/fixtures/presenter-rotation-input.json \
  --dry-run

python -m unittest discover -s tests
```

`--dry-run`은 파일을 바꾸지 않는다. 실제 명부 파일은 저장소 밖에 두고 절대 커밋하지
않는다.

최초 배정 결과를 이름과 함께 검토해야 할 때는 Git에서 제외된 `private/` 아래에만
비공개 계획을 만든다.

```bash
python scripts/plan_presenter_rotation.py \
  --sheet-id "$CM_ROSTER_SHEET_ID" \
  --private-plan-out private/presenter-plan.json
```

검토가 끝난 배정은 Sheet의 `Assignments` 탭에 붙여 넣는다. 이후 실행부터 해당
일정은 고정되고, 명부가 바뀌어도 이미 공지한 사람의 월은 움직이지 않는다.

## Actions 설정

1. Google Cloud 프로젝트에서 Google Sheets API를 활성화한다.
2. 명부 Sheet를 기존 CI 서비스 계정에 뷰어로 공유한다.
3. 저장소 Secret `CM_ROSTER_SHEET_ID`에 Sheet ID를 등록한다.
4. `CM 발표 일정 갱신` workflow를 수동 실행한다.
5. Slack으로 전달된 compare 링크에서 공개 JSON diff를 확인하고 PR을 만든다.

Workflow는 매주 월요일에도 실행된다. 변경이 없으면 브랜치나 알림을 만들지 않는다.

### Action에서 추첨·완료자 수정

`CM 발표 일정 갱신` Action의 `Run workflow`에서 작업을 선택한다.

- `refresh`: Sheet의 현재 내용을 읽어 공개 일정을 다시 생성
- `draw`: `month`에 `YYYY-MM`을 입력해 해당 월의 빈자리를 3명까지 비복원 추첨하고 `Assignments`에 저장
- `set-completions`: `month`와 쉼표로 구분한 발표자 이름 또는 ID를 입력해 해당 월의 `Completions`를 교체

추첨과 완료자 수정은 Google Sheet를 변경하므로 CI 서비스 계정에 편집 권한이
필요하다. 결과 JSON은 기존과 동일하게 검토 브랜치에 생성되며, diff 확인 후
병합한다.

### HTML 관리자 모드

`rotation.html`에서도 사내 Google 계정으로 로그인해 같은 Sheet의 추첨과 완료자
편집을 수행할 수 있다. 브라우저에 서비스 계정 키를 넣지 않고 Google OAuth의
사용자 액세스 토큰만 사용한다.

1. Google Cloud Console에서 OAuth 클라이언트 유형을 **웹 애플리케이션**으로 만든다.
2. 승인된 JavaScript 원본에 `https://trustay-inc.github.io`를 등록한다.
3. 발급된 클라이언트 ID를 `data/presenter-rotation-admin.json`의
   `googleClientId`에 입력한다. 클라이언트 ID는 공개 값이며 비밀키를 입력하지 않는다.
4. Sheet를 실제 관리할 사내 계정에 편집 권한으로 공유한다.

HTML에서 저장한 직후 Sheet에는 반영되지만 공개 JSON은 자동으로 커밋되지 않는다.
화면의 `Action 열기`에서 `refresh`를 실행하고 생성된 검토 브랜치를 병합한다.
