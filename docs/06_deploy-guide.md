# 배포·재현 가이드 (GitHub push → Vercel 배포 → 확인 → 제출)

Windows PowerShell 기준입니다. (macOS 는 `Copy-Item` 대신 `cp`, `notepad` 대신 `open -e`)
총 소요 시간: 약 40분. 각 단계 끝의 **확인** 이 보이면 다음 단계로 넘어갑니다.

---

## 0. 준비물 체크리스트 (5분)

- [ ] GitHub 계정 로그인 (`Sungtae10`)
- [ ] Git 설치 확인: PowerShell 에서 `git --version` → 버전이 나오면 OK
- [ ] Python 3.10 이상: `python --version` (안 되면 `py --version`)
- [ ] Gemini API 키: <https://aistudio.google.com/apikey> → **Create API key** → 복사
  - 키는 Vercel·`.env` 입력칸에만 붙여넣습니다. 채팅, 스크린샷, README 에 절대 넣지 않습니다.
- [ ] Vercel 계정: <https://vercel.com/signup> → **Continue with GitHub** (Hobby 무료 플랜)

---

## 1. 압축 풀기와 커밋 이력 확인 (2분)

1. `codyssey-a1-3-ax-radar.zip` 을 풀고, 그 폴더에서 PowerShell 을 엽니다.
   (폴더 빈 곳에서 Shift + 마우스 오른쪽 → "PowerShell 창 열기", 또는 `cd 폴더경로`)
2. 커밋 이력을 확인합니다. 숨김 폴더 `.git` 에 이력이 들어 있으니 지우지 마세요.

```powershell
git log --oneline
```

**확인**: `chore: 프로젝트 초기 구조와 배포 설정 추가` 부터 여러 줄의 커밋이 보이면 OK

---

## 2. 로컬에서 실행해 보기 (권장, 10분)

```powershell
python -m pip install -r requirements.txt     # requests 설치
Copy-Item .env.example .env                  # 키 파일 만들기
notepad .env                                  # GEMINI_API_KEY= 뒤에 키를 붙여넣고 저장 (따옴표·공백 없이)
python scripts/dev_server.py                  # 로컬 서버 실행
```

브라우저에서 <http://localhost:3000> → **예시로 채우기** → **AI 진단 받기**

**확인**: 결과 하단에 `분석 엔진: gemini · gemini-3.5-flash-lite` 가 보이면 실제 AI 연동 성공
(종료는 PowerShell 에서 Ctrl + C)

| 추가로 확인하는 방법 | 명령 |
|---|---|
| 키 없이 화면만 보기 | `python scripts/dev_server.py --mock` |
| 오류 안내 화면 보기 | `python scripts/dev_server.py --mock-error 429` (또는 500, 502, 504, bad-json, no-key) |
| 지연 안내 보기 | `python scripts/dev_server.py --mock --mock-delay 12` |
| 단위 테스트 59개 | `python -m unittest discover -s tests -v` → 마지막 줄 `OK` |

---

## 3. GitHub 저장소 만들고 올리기 (5분)

1. <https://github.com/new> 에서
   - Repository name: `codyssey-a1-3-ax-radar`
   - Public 선택
   - **Add a README file 체크 해제**, .gitignore: None, License: None (빈 저장소여야 이력이 그대로 올라갑니다)
   - **Create repository**
2. PowerShell 에서:

```powershell
git remote add origin https://github.com/Sungtae10/codyssey-a1-3-ax-radar.git
git push -u origin main
```

- 로그인 창이 뜨면 GitHub 로 로그인합니다. 비밀번호를 물으면 Personal access token(classic, `repo` 권한)을 붙여넣습니다.

**확인**: 저장소 페이지에 파일과 커밋 이력이 보이고, **`.env` 파일이 없어야** 합니다.

---

## 4. Vercel 배포 (5분)

1. <https://vercel.com/new> → **Import Git Repository**
   - 처음이면 GitHub 연결 창에서 **Install** → "Only select repositories" 에 `codyssey-a1-3-ax-radar` 선택
2. `codyssey-a1-3-ax-radar` 옆 **Import**
3. Configure Project 화면
   - Project Name: `codyssey-a1-3-ax-radar`
   - Framework Preset: **Other**
   - Root Directory: `./` (그대로)
   - Build and Output Settings: 건드리지 않음
   - **Environment Variables**: Key `GEMINI_API_KEY` / Value 에 키 붙여넣기 → **Add**
4. **Deploy** 클릭 → 1~2분 뒤 완료 화면 → **Continue to Dashboard**
5. 대시보드의 **Domains** 에 적힌 주소가 배포 URL 입니다. (보통 `https://codyssey-a1-3-ax-radar.vercel.app`, 이미 쓰는 이름이면 뒤에 글자가 붙습니다)

---

## 5. 배포 환경 확인 (5분)

`docs/02_test-report.md` 7장 표(P1~P10)를 채우면서 확인합니다.

| 순서 | 할 일 | 정상 모습 |
|---|---|---|
| 1 | `https://배포주소/api/health` 열기 | `"config_ok": true`, `"provider": "gemini"` (false 면 `config_error` 에 이유) |
| 2 | 배포 주소 → 메뉴 5개 눌러 보기 | 섹션 이동, 메뉴 강조 |
| 3 | 빈 상태로 **AI 진단 받기** | "필수값을 입력하세요" |
| 4 | **예시로 채우기** → 제출 | 5~20초 뒤 결과, 하단에 `분석 엔진: gemini` |
| 5 | 휴대폰으로 같은 주소 접속 | 햄버거 메뉴, 결과 화면이 잘리지 않음 |
| 6 | 주소창에 `https://배포주소/api/diagnose` | `METHOD_NOT_ALLOWED` JSON (POST 만 받는다는 뜻, 정상) |

문제가 있으면 `docs/03_troubleshooting.md` 의 B 표에서 화면에 뜬 오류 코드를 찾습니다.
**환경 변수를 고쳤다면 Deployments → 최신 배포의 ⋯ → Redeploy** 를 눌러야 적용됩니다.

---

## 6. 제출용 스크린샷 찍기 (10분)

`docs/screenshots/` 에 아래 이름으로 저장합니다. (저장소의 01~14번은 로컬 목업 화면이고, 아래는 **배포 사이트의 실제 AI 화면**입니다)

| 파일 이름 | 내용 | 찍는 방법 |
|---|---|---|
| `20_deployed_desktop.png` | 배포 사이트 첫 화면 (주소창 포함) | Win + Shift + S |
| `21_deployed_mobile.png` | 휴대폰 화면 | 휴대폰 캡처, 또는 크롬 F12 → Ctrl + Shift + M → iPhone 선택 |
| `22_deployed_ai_result.png` | 실제 AI 결과 (하단 `분석 엔진: gemini` 보이게) | 결과 화면 캡처 |
| `23_deployed_health.png` | `/api/health` 응답 | 브라우저 캡처 |
| `24_deployed_error.png` | 빈 입력 안내 | 빈 상태로 제출 후 캡처 |

- API 키가 보이는 화면(Vercel 환경 변수 값, `.env`)은 찍지 않습니다.
- AI 코딩 도구 증빙 캡처(`30~32번`)는 `docs/04_ai-coding-log.md` 5장을 참고합니다.

---

## 7. README 에 배포 URL 적고 다시 올리기 (5분) = "수정 후 재배포" 증빙

1. `README.md` 맨 위의 배포 URL 줄을 실제 주소로 고칩니다. (다르면)
2. `README.md` 의 "배포 환경 스크린샷" 표에 있는 이미지 줄 앞의 주석 표시를 지웁니다.
3. 올립니다:

```powershell
git add README.md docs/screenshots docs/02_test-report.md docs/04_ai-coding-log.md
git commit -m "docs: 배포 URL, 배포 환경 점검 결과와 스크린샷 추가"
git push
```

**확인**: Vercel 대시보드 Deployments 에 새 배포가 자동으로 생기고 **Ready** 가 됩니다. (코드를 고칠 때도 똑같이 push 만 하면 재배포됩니다)

---

## 8. 코디세이 제출 체크리스트 (필수 5종)

- [ ] 배포된 웹 서비스: Vercel URL (동료가 접속해 AI 기능을 실행할 수 있어야 함)
- [ ] GitHub 저장소: `https://github.com/Sungtae10/codyssey-a1-3-ax-radar`
- [ ] README.md: 소개, 기술 스택, 실행/배포 방법, **배포 URL**, 환경 변수 설정
- [ ] 서비스 기획서: `docs/01_service-plan.md`
- [ ] 증빙: 데스크톱·모바일·AI 동작 스크린샷(20~24번) + AI 코딩 도구 사용 기록(`docs/04_ai-coding-log.md` + 대화 캡처)

---

## 9. (선택) 보너스: 진단 알림 웹훅 켜기

1. Discord 채널 → 채널 편집 → 연동 → 웹후크 → 새 웹후크 → **웹후크 URL 복사**
2. Vercel → Settings → Environment Variables → `NOTIFY_WEBHOOK_URL` 에 붙여넣기 → Save → **Redeploy**
3. 진단을 한 번 실행하면 Discord 에 `AX 레이더 새 진단 | 업종: … | 합계 12점 (평균 2.4) → 2단계 실험` 메시지가 옵니다.
   (회사명과 고민 문장은 보내지 않습니다. Make·Zapier 웹훅 주소를 넣으면 JSON 전체가 전달돼 구글 시트 저장 등으로 연결할 수 있습니다)

---

## 10. 보안 수칙 (항상)

- 키는 `.env` 와 Vercel 환경 변수에만 둡니다. `git status` 에 `.env` 가 보이면 커밋하지 않습니다.
- 키가 노출되면: ① AI Studio 에서 즉시 삭제 ② 새 키로 Vercel 환경 변수 교체 + Redeploy ③ 커밋에 들어갔다면 이력 정리 (`docs/03_troubleshooting.md` B 참고)
