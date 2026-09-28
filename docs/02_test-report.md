# 테스트 리포트

| 항목 | 내용 |
|---|---|
| 작성 | 김성태 (AI 코딩 도구 Claude 와 함께 실행) |
| 로컬 점검일 | 2026-09-29 |
| 로컬 환경 | Python 3.11 · Playwright 1.56 + Chromium(헤드리스) · 목업 AI 응답 |
| 배포 환경 | Vercel Python 3.12.14 (2026-09-29 `/api/health` 로 확인, 결과는 7장) |

---

## 1. 결과 요약 (KPI)

| 지표 | 결과 | 기준 |
|---|---|---|
| API 단위 테스트 | **59 / 59 통과** | 전부 통과 |
| 브라우저 화면 점검 | **46 / 46 통과** | 전부 통과 |
| 점검한 화면 크기 | 1440px(데스크톱), 768px(태블릿), 390px(모바일) | 요구사항: 2가지 이상 |
| 실패 처리 확인 | 빈 입력, 4xx(400·404·429), 5xx(500·502·504), 네트워크 끊김, 지연, 타임아웃 | 요구사항: 1가지 이상 |
| 테스트로 찾아 고친 결함 | 3건 (로그 키 노출 가능성, hidden 무시, 첫 클릭 무시) | 재발 방지 테스트 포함 |
| 독립 검토로 고친 항목 | 6건 (구분 기호 우회, health 오판, 서버 호출 제한 없음, CLI 배포 시 .env 업로드 위험, 결과 표시 오류 구분, 문서 불일치) | 별도 AI 검토 에이전트가 코드·문서 감사 |
| 실제 AI API 호출 | **배포 URL 에서 확인 완료** (Gemini `gemini-3.5-flash-lite`, 응답 15.4초) | 7장 P5·P6 |

> 목업(mock) 응답을 쓴 이유: API 키 없이도 화면과 흐름을 반복 확인하고, 429·504 같은 실패 상황을 마음대로 재현하기 위해서입니다. 실제 AI 연결은 배포 URL 에서 따로 확인합니다.

---

## 2. 실행 방법

```bash
# 1) API 단위 테스트 (설치 필요 없음, 키 없이 실행)
python -m unittest discover -s tests -v

# 2) 브라우저 화면 점검 + 스크린샷 (선택, 처음 한 번 설치)
pip install playwright
python -m playwright install chromium
python scripts/check_ui.py
```

단위 테스트 중간에 보이는 `[ax-radar] ...` 줄은 서버 로그 예시입니다. 키 대신 `***` 가 찍히는지, 사용자 문장이 로그에 남지 않는지 눈으로 확인할 수 있게 그대로 둡니다.

---

## 3. API 단위 테스트 (`tests/test_api.py`, 59개)

| 분류 | 개수 | 확인 내용 |
|---|---|---|
| 입력 검증 `ValidationTests` | 8 | 업종·규모·점수·고민 누락, 잘못된 선택지, 점수 0·6·3.5·True·"3점" 거절, 10자·500자 경계, JSON 객체가 아닌 본문 |
| 단계 계산 `LevelTests` | 3 | 합계 8/9, 12/13, 16/17, 20/21 경계, 평균, 가장 낮은/높은 영역, 모든 점수가 같을 때 |
| 제공자 선택 `ProviderTests` | 6 | 키 없음 → 500, Gemini > Claude > OpenAI 순서, 별칭(claude, gpt), 모델 이름 검사, 대기 시간 5~55초 제한 |
| 요청 형식 `RequestShapeTests` | 6 | Gemini·Claude·OpenAI 공식 REST 주소·헤더·본문 형식, 키가 URL 에 들어가지 않음, 사고 과정(thought) 제외, OpenAI 추론 강도 허용 값 |
| 오류 변환 `ErrorMappingTests` | 4 | 429 → 429, 401·403·키 오류 → 인증 오류, 404 → 모델 오류, 5xx·529 → 502, 시간 초과 → 504, 연결 실패, 로그의 키 가림 |
| 응답 정리 `ParsingTests` | 4 | 코드블록·앞뒤 설명이 붙은 JSON 추출, 개수·길이 자르기, KPI 3개 제한, 필수 항목 누락 시 형식 오류 |
| 전체 흐름 `RunDiagnosisTests` | 4 | AI 가 단계를 지어내도 코드 계산 값 사용, 프롬프트 주입 문장이 따옴표 안에 갇힘, 따옴표 5개·10개로 구분 기호를 되살리는 우회 차단, 회사명 한 줄 처리 |
| 호출 빈도 제한 `RateLimitTests` | 3 | 같은 IP 1분 N회 초과 시 429, 다른 IP·60초 경과 후 허용, 기본 6회·0이면 끔, 잘못된 입력은 횟수에 포함 안 함 |
| 웹훅 `WebhookTests` | 4 | 주소 없으면 건너뜀, 회사명·고민 문장 미전송, Discord 형식, 웹훅 실패해도 진단은 성공 |
| HTTP 처리 `HttpHandlerTests` | 8 | 실제 HTTP 서버로 200/400/405/413/429/500/502, `Cache-Control: no-store`, 예상 못한 오류 내용 숨김, `X-Forwarded-For` 기준 호출 제한, `/api/health` 가 키 값을 노출하지 않음 |
| 프론트·백엔드 일치 `FrontendContractTests` | 5 | HTML 선택지·점수 버튼·글자 수 제한·메뉴 대상·API 경로가 Python 설정과 같은지 |
| 설정·보안 `ConsistencyAndSecurityTests` | 4 | health/diagnose 설정값 일치, 설정 조합 8가지에서 health 의 `config_ok` 와 진단 함수 판단 일치, `.env` 가 `.gitignore`·`.vercelignore` 모두에 있음, `.env.example` 에 값 없음, 저장소 전체에 실제 키 형식 문자열 없음 |

---

## 4. 브라우저 화면 점검 (`scripts/check_ui.py`, 46개)

| 구분 | 점검 항목 (모두 통과) | 스크린샷 |
|---|---|---|
| 데스크톱 1440px | 페이지 제목, 섹션 5개, 가로 스크롤 없음, 홈 예시 차트, 콘솔 오류 없음 | [01](screenshots/01_desktop_home.png), [14](screenshots/14_desktop_diagnose.png) |
| 메뉴 | 메뉴 클릭 시 해당 섹션으로 이동, 현재 섹션 메뉴 강조 | [02](screenshots/02_desktop_model.png) |
| 빈 입력 | "필수값을 입력하세요" 안내, 칸별 오류 8개, 서버 호출 안 함 | [05](screenshots/05_validation_empty.png) |
| 짧은·긴 입력 | 10자 미만 안내, 600자 입력 시 500자로 제한, 250자 정상 처리 | |
| 정상 결과 | 로딩·버튼 잠금, 단계 배지, 레이더 차트, 로드맵 3단계, KPI 3개, 점수 표, 목업 표시 | [07](screenshots/07_result_desktop_mock.png) |
| 호출 빈도 | 응답 뒤 3초 재요청 제한, 3초 뒤 다시 활성 | |
| 복사·보안 | 결과 텍스트 복사, AI 응답 속 `<img onerror>` 가 실행되지 않음 | |
| 서버 오류 6종 | 429 요청 과다, 502 AI 서버, 504 AI 시간 초과, 500 서버 오류, AI 형식 오류, 키 누락 | [09](screenshots/09_error_rate_limit.png) |
| 브라우저 감지 오류 | 네트워크 끊김, JSON 이 아닌 504 화면, 404 API 없음, 서버 검증 오류를 해당 칸에 표시 | |
| 지연·타임아웃 | 오래 걸리면 지연 안내 후 결과 표시, 제한 시간 넘으면 요청 중단 안내 | [06](screenshots/06_loading_slow.png), [10](screenshots/10_error_timeout.png) |
| 태블릿 768px | 가로 스크롤 없음, 폼 한 줄 배치 | [12](screenshots/12_tablet_diagnose.png) |
| 모바일 390px | 가로 스크롤 없음, 햄버거 메뉴 열기·닫기, 결과 화면, 콘솔 오류 없음 | [03](screenshots/03_mobile_home.png), [04](screenshots/04_mobile_menu.png), [08](screenshots/08_result_mobile_mock.png) |
| 다크 모드 | 버튼 전환, 새로고침 후 유지 | [11](screenshots/11_dark_mode.png), [13](screenshots/13_result_dark_mock.png) |

> 점검 환경에서는 외부 글꼴(Pretendard CDN) 연결을 막아 두어 스크린샷이 시스템 한글 글꼴로 보입니다. 배포 사이트에서는 Pretendard 로 표시됩니다.

---

## 5. 미션 예시 테스트 케이스 대응

| 케이스 | 입력 | 기대 결과 | 확인 결과 |
|---|---|---|---|
| 정상 입력 | "예시로 채우기" (자동차·부품 / 중소기업 / 3·2·2·3·2 / 고민 115자) | 결과 화면 표시 | 통과: 2단계 실험, 로드맵 3단계, KPI 3개 |
| 빈 입력 | 아무것도 입력하지 않고 제출 | "필수값을 입력하세요" 안내 | 통과: 상단 안내 + 칸별 안내 8개, 서버 미호출 |
| 긴 입력 | 250자 고민 / 600자 붙여넣기 | 정상 표시, 또는 제한 안내 | 통과: 250자는 결과 표시, 600자는 500자로 잘림 (서버도 501자 이상은 400) |
| 지연 | AI 응답 4초 지연 + 지연 기준 1초로 축소 | 지연 안내 문구 | 통과: "평소보다 오래 걸리고 있어요" 후 결과 표시 |

---

## 6. 테스트로 찾아 고친 결함

| 번호 | 증상 | 발견 방법 | 수정 커밋 |
|---|---|---|---|
| D1 | 예상 못한 오류의 traceback 로그에 API 키가 그대로 찍힐 수 있음 | 단위 테스트 `test_unexpected_error_is_hidden` 실패 | `fix(api): 예상 못한 오류 로그에서 API 키 가리기` |
| D2 | 로딩·오류·결과 카드가 처음부터 보임 (hidden 무시) | 화면 점검 13건 실패 | `fix(web): hidden 속성이 CSS display 에 가려 …` |
| D3 | 오류를 고친 뒤 제출 버튼 첫 클릭이 무시됨 | 화면 점검 "짧은 입력" 실패 → 직접 재현 | `fix(web): 오류 문구가 사라지며 제출 버튼이 밀려 …` |
| R1~R6 | 프롬프트 구분 기호 우회, health 오판, 서버 호출 제한 없음, CLI 배포 시 .env 업로드 위험, 결과 표시 오류를 네트워크 오류로 안내, 문서 수치 불일치 | 별도 AI 검토 에이전트의 감사 (R1 은 새 테스트로 수정 전 실패 확인) | `fix: 독립 검토 결과 반영 …` |

원인과 수정 이유는 [03_troubleshooting.md](03_troubleshooting.md) 에 정리했습니다.

---

## 7. 배포 환경 점검표 (배포 후 작성)

배포 URL: `https://codyssey-a1-3-ax-radar-ofpt.vercel.app`  (점검일: 2026-09-29)

| 번호 | 항목 | 방법 | 결과 (O/X, 메모) |
|---|---|---|---|
| P1 | 함수 실행·키·모델 설정 | `/api/health` 열기 → `"config_ok": true` | O · `provider: gemini`, `model: gemini-3.5-flash-lite`, `key_configured: true`, `config_ok: true`, `runtime: python 3.12.14` (2026-09-29 03:53 KST) |
| P2 | 메뉴 이동 | 상단 메뉴 5개 차례로 누르기 | O · 배포 사이트에서 "AI 진단" 메뉴 이동과 강조 확인 (스크린샷 22, 24). 5개 메뉴 전체 이동은 로컬 화면 점검에서 확인 |
| P3 | 반응형 | 휴대폰으로 접속 + PC 브라우저 개발자 도구 390px | O · 휴대폰 접속 시 햄버거 메뉴·한 줄 배치 정상, 다크 모드 적용 (스크린샷 21) |
| P4 | 빈 입력 | 아무것도 입력하지 않고 제출 | O · "필수값을 입력하세요: 업종, 기업 규모, …" 안내와 칸별 빨간 안내 표시, 요청은 보내지 않음 (스크린샷 24) |
| P5 | 실제 AI 결과 | "예시로 채우기" 후 제출 → 결과 하단에 `분석 엔진: gemini` 표시 | O · 한빛정밀(가상) 예시 → 2단계·실험(합계 12, 평균 2.4), 로드맵 3단계, KPI 3개, 이번 주 할 일, 주의할 점 표시. 하단 `분석 엔진: gemini · gemini-3.5-flash-lite · 15.4초` (스크린샷 22, 23) |
| P6 | 응답 시간 | P5 를 3번 반복, 결과 하단 초 기록 → 평균 20초 이하인가 | 1회 15.4초 / 2회 미측정 / 3회 미측정 (1회 기준 20초 이하) |
| P7 | 결과 복사·인쇄 | 결과 복사 후 메모장에 붙여넣기 | |
| P8 | 405 확인 | 브라우저 주소창에 `/api/diagnose` 입력 → METHOD_NOT_ALLOWED JSON | O · GET 요청에 HTTP 405 응답 확인 |
| P9 | 동료 재현 | 동료 1명이 자기 기기로 접속해 P5 수행 | |
| P10 | 재배포 흐름 | README 에 배포 URL 기입 → push → Vercel 자동 재배포 확인 | O · README 주소 수정 커밋 `cca20d0` push → Vercel 자동 배포 성공 (GitHub 커밋 상태 "Vercel: Deployment has completed", Production 배포 2건: 03:47 첫 배포, 03:56 재배포) |
