# 트러블슈팅 기록

AI 코딩 도구가 만든 코드라도 **왜 틀렸는지 말로 설명하고 고칠 수 있어야** 한다는 미션 목표에 맞춰, 실제로 겪은 문제와 배포 뒤 생길 수 있는 문제를 정리했습니다.

---

## A. 개발 중 실제로 겪은 문제

### D1. 예상 못한 오류가 나면 로그에 API 키가 찍힐 수 있었음

| 단계 | 내용 |
|---|---|
| 증상 | 단위 테스트 `test_unexpected_error_is_hidden` 실패: 로그에 `fake-gemini-key-...` 가 그대로 출력됨 |
| 원인 | `traceback.print_exc()` 는 예외 메시지를 그대로 출력한다. 예외 메시지에 키가 섞이면 Vercel 로그(Logs 탭)에 키가 남는다. |
| 확인 | 수정 전 코드로 되돌려 같은 테스트를 돌리면 실패, 수정 후 통과 (커밋 `test:` → `fix(api):` 순서) |
| 수정 | traceback 문자열을 `redact()` 로 가린 뒤 출력. 사용자 응답에는 오류 종류만 알리고 내부 내용은 숨김 |
| 배운 점 | "키를 코드에 안 쓰는 것"만으로는 부족하다. **로그·오류 메시지·스크린샷**도 키가 새는 통로다. |

### D2. 로딩·오류·결과 카드가 처음부터 화면에 보였음

| 단계 | 내용 |
|---|---|
| 증상 | 화면 점검 43개 중 13개 실패. 빈 입력만 제출해도 로딩 카드와 "요청을 처리하지 못했어요" 카드가 보임 |
| 원인 | HTML 의 `hidden` 속성은 브라우저 기본 CSS `[hidden] { display: none }` 으로 숨겨진다. 그런데 `.status-card { display: flex }` 처럼 내가 쓴 CSS 가 더 우선이라 숨김이 풀렸다. |
| 확인 | 개발자 도구에서 `#loading` 요소의 계산된 display 값이 `flex` 인 것 확인 |
| 수정 | `[hidden] { display: none !important; }` 한 줄 추가 |
| 배운 점 | HTML(구조)·CSS(모양)·JS(동작)는 서로 영향을 준다. JS 가 `hidden` 을 바꿔도 CSS 규칙이 이기면 화면은 그대로다. |

### D3. 오류를 고친 뒤 "AI 진단 받기" 첫 클릭이 무시됨

| 단계 | 내용 |
|---|---|
| 증상 | 고민 칸 오류("고민이나 목표를 적어 주세요")를 본 뒤 글을 쓰고 버튼을 누르면 아무 일도 없고, 두 번째 클릭에야 제출됨 |
| 원인 | 오류 문구를 `change` 이벤트(칸에서 포커스가 빠질 때)에서 지웠다. 버튼을 **누르는 순간**(mousedown) 포커스가 빠지며 오류 문구가 사라지고, 그만큼 버튼이 위로 이동했다. 손을 떼는 순간(mouseup)은 버튼 밖이라 click 이 발생하지 않았다. |
| 확인 | 제출 이벤트에 로그를 달아 두 번째 제출이 실행되지 않는 것 확인 (`SUBMIT fired` 가 1번만 찍힘) |
| 수정 | 글자 칸은 `input` 이벤트(타이핑 중)에서 오류를 지우고, 선택 상자·점수 버튼만 `change` 사용. 남은 오류가 없으면 위쪽 안내도 닫음 |
| 배운 점 | 사용자는 "버튼이 고장났다"고 느낀다. 레이아웃이 움직이는 시점과 클릭 시점이 겹치면 안 된다. |

### D4. (점검 도구) 스크린샷에서 상단 메뉴가 결과 위에 겹쳐 찍힘

- 원인: 상단 메뉴가 `position: sticky` 라서 긴 요소를 찍을 때 화면 위에 계속 붙어 있음. 서비스 결함은 아님.
- 수정: `scripts/check_ui.py` 가 요소를 찍는 동안만 메뉴 고정을 풀고, 찍은 뒤 되돌림.

### D5. (점검 도구) 부드러운 스크롤 도중에 클릭·촬영이 일어남

- 원인: `scroll-behavior: smooth` 로 화면이 움직이는 중에 자동 클릭이 다른 위치를 누르거나 흐린 화면이 찍힘.
- 수정: 이동 뒤 0.6~1.5초 기다린 다음 클릭·촬영. 실제 사용자는 스크롤이 끝난 뒤 누르므로 서비스 결함은 아님.

### D6. (조사) 기본 AI 모델 선택

- 2026년 9월 Gemini 공식 문서 기준, 2.5 계열 모델은 "과거에 사용한 계정 위주로 제한"되고 새 프로젝트에는 **3.5 Flash-Lite 또는 3.8 Flash** 를 권장한다.
- 그래서 기본값을 `gemini-3.5-flash-lite` 로 정했다. (빠르고 저렴, 무료 등급 제공) 다른 모델은 `GEMINI_MODEL` 환경 변수로 바꾼다.

### D7. (조사) Vercel 이 Python 파일을 "앱 진입점"으로 착각하지 않게 하기

- Vercel 은 루트의 `app.py`, `index.py`, `server.py`, `main.py` 등을 FastAPI/Flask 같은 **앱 진입점**으로 찾는다. 또 `requirements.txt` 에 FastAPI·Flask 가 있으면 앱 방식이 우선이라 `api/` 파일이 개별 함수가 되지 않는다.
- 그래서 루트에는 Python 파일을 두지 않고, 로컬 서버는 `scripts/dev_server.py` 로 이름과 위치를 정했다. `requirements.txt` 에는 `requests` 만 둔다.

---

## A-2. 독립 검토로 찾아 고친 문제

코드를 만든 과정을 모르는 **별도 AI 검토 에이전트**에게 과제 문서와 저장소만 주고 감사를 맡겼습니다. (스스로 만든 결과를 스스로 채점하지 않기 위해)

| 번호 | 발견 내용 | 원인 (말로 설명) | 수정 |
|---|---|---|---|
| R1 | 고민 칸에 따옴표 5개(`"""""`)를 넣으면 프롬프트의 구분 기호가 되살아남 | `replace('"""', '"')` 는 한 번 훑기만 해서 5개 중 3개만 1개로 바뀌고 `"""` 가 남음 | `re.sub(r'"{3,}', '"', …)` 로 3개 이상을 모두 1개로. 회사명도 줄바꿈을 한 칸으로 바꿔 한 줄로 고정. 새 테스트가 수정 전 코드에서 실패하는 것 확인 |
| R2 | `/api/health` 가 "정상"인데 진단은 설정 오류(500)가 날 수 있음 | health 는 키 유무만 보고, `LLM_PROVIDER`·모델 이름 검사는 하지 않았음 | 진단 함수와 같은 규칙으로 검사해 `config_ok`·`config_error` 를 돌려줌. 설정 조합 8가지에서 두 함수 판단이 같은지 테스트 |
| R3 | 서버 쪽 호출 빈도 제한이 없음 | 3초 제한은 브라우저에만 있어 직접 요청으로 우회 가능 | 같은 IP 1분 6회 제한 (`RATE_LIMIT_PER_MINUTE`, 429 `TOO_MANY_REQUESTS`). 인스턴스별 메모리 기준이라 완벽한 전역 제한은 아님 |
| R4 | Vercel CLI 로 로컬 폴더를 배포하면 `.env` 가 올라갈 수 있음 | `.vercelignore` 가 있으면 CLI 는 그 목록만 보는데 `.env` 가 빠져 있었음 | `.vercelignore` 에 `.env`, `.env.*` 추가 + 테스트로 확인 |
| R5 | 결과 표시 중 오류가 나도 "인터넷 연결 확인"으로 안내 | 결과 그리기 오류와 fetch 실패를 같은 catch 에서 처리 | 결과 그리기 오류는 `RENDER_ERROR` 로 따로 안내, 빈 입력으로 멈출 때 이전 오류 카드 닫기 |
| R6 | 문서 수치 불일치 (예시 고민 120자 → 실제 115자, KPI 최대 4개 저장, 일부 오류 코드·환경 변수 누락) | 코드를 고친 뒤 문서를 같이 고치지 않음 | KPI 3개로 통일, README·기획서·리포트 수정, 항상 통과하던 테스트 단언 1개 교체 |

---

## B. 배포 후 생길 수 있는 문제와 해결 방법

| 화면·증상 | 가장 흔한 원인 | 확인 방법 | 해결 |
|---|---|---|---|
| "서버 설정이 필요해요" `CONFIG_MISSING_KEY · HTTP 500` | Vercel 에 키를 안 넣었거나, 넣은 뒤 **재배포를 안 함** | `/api/health` 의 `config_ok` 가 `false`, `config_error` 에 이유 | Settings > Environment Variables 에 `GEMINI_API_KEY` 추가 → Deployments > 최신 배포 ⋯ > **Redeploy** (환경 변수는 새 배포부터 적용) |
| "AI 서비스 인증 오류" `AI_AUTH_ERROR` | 키 오타, 앞뒤 공백, 폐기된 키 | Vercel Logs 에서 `ai_http_error status=400/401/403` | AI Studio 에서 새 키 발급 → 환경 변수 교체 → Redeploy |
| "AI 모델 설정 오류" `AI_MODEL_NOT_FOUND` | `GEMINI_MODEL` 오타 또는 종료된 모델 | Logs 에서 `status=404` | `GEMINI_MODEL` 을 지우거나 공식 모델 목록의 이름으로 수정 |
| "요청이 많아요" `RATE_LIMITED · HTTP 429` | 무료 등급 한도 초과 (하루 한도는 태평양 시간 자정에 초기화) | AI Studio > Rate limit 화면 | 잠시 뒤 재시도, 동료 테스트 시간 분산 |
| "요청이 너무 잦아요" `TOO_MANY_REQUESTS · HTTP 429` | 같은 IP 에서 1분에 6번 넘게 요청 (우리 서버의 제한) | 오류 코드로 구분 | 1분 뒤 재시도, 시연·동료 평가가 겹치면 `RATE_LIMIT_PER_MINUTE` 를 잠시 올리고 Redeploy |
| "API를 찾을 수 없어요" `HTTP 404` | `api/` 폴더가 배포에 없음, Root Directory 설정 오류 | 배포 상세 화면의 함수 목록(Resources 또는 Functions)에 `api/diagnose.py` 가 있는지 | Framework Preset **Other**, Root Directory **./** 로 다시 배포 |
| "서버 오류" `HTTP 500` (JSON 아님) | 함수가 시작하다 실패 (예: `requirements.txt` 누락으로 `ModuleNotFoundError: requests`) | Logs 의 Traceback | 루트에 `requirements.txt` 가 있는지 확인 후 push |
| "응답 시간 초과" `HTTP 504` | AI 응답이 함수 제한 시간 초과 | Logs 의 `ai_timeout` | `vercel.json` maxDuration(60) 확인, 더 빠른 모델 사용 |
| 화면은 뜨는데 디자인이 깨짐 | 파일 이름 대소문자 불일치 (Vercel 은 대소문자를 구분) | 개발자 도구 Network 탭에서 css 404 | 링크와 실제 파일 이름을 똑같이 |
| 로컬은 되는데 배포에서 키 오류 | `.env` 는 로컬에만 있고 GitHub·Vercel 에 올라가지 않음 (의도된 동작) | `/api/health` | Vercel 환경 변수에 따로 입력 |
| `git push` 거절 (fetch first) | GitHub 저장소를 README 포함으로 만들어 이력이 다름 | 오류 문구 | 빈 저장소로 다시 만들거나 `git pull --rebase origin main` 후 push |

### 키가 노출됐을 때 (즉시, 이 순서대로)

1. **폐기**: Google AI Studio > API keys 에서 노출된 키 삭제 (가장 먼저)
2. **재발급**: 새 키를 만들어 Vercel 환경 변수에 교체 → Redeploy
3. **이력 정리**: 커밋에 들어갔다면 이력에서도 지운다

```bash
pip install git-filter-repo
echo "노출된키값==>***REMOVED***" > replacements.txt
git filter-repo --replace-text replacements.txt
git remote add origin https://github.com/Sungtae10/codyssey-a1-3-ax-radar.git   # filter-repo 가 origin 을 지우므로 다시 연결
git push --force origin main
```

> 이력을 지워도 이미 복사된 곳이 있을 수 있으므로 **1번 폐기가 핵심**입니다. `replacements.txt` 는 작업 후 삭제합니다.

---

## C. 오류 원인을 찾는 순서 (5단계)

1. **화면의 오류 코드**를 읽는다. 예: `RATE_LIMITED · HTTP 429` → 요청 과다
2. **개발자 도구 Network 탭**에서 `/api/diagnose` 요청의 Status 와 Response 를 본다.
3. **`/api/health`** 로 함수 실행과 키 설정 여부를 본다.
4. **Vercel 대시보드 > Logs** 에서 `[ax-radar]` 로 시작하는 줄을 찾는다. (키와 사용자 문장은 로그에 남지 않음)
5. **로컬에서 재현**한다: `python scripts/dev_server.py --mock-error 429` 처럼 같은 오류를 일부러 만들어 고친 코드를 확인한 뒤 push 한다.
