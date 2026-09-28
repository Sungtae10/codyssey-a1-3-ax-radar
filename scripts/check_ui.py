"""브라우저 화면 자동 점검 + 스크린샷 (선택 도구)

무엇을 하나요?
- 로컬 개발 서버(scripts/dev_server.py)를 목업 모드로 여러 개 띄우고, 크롬(헤드리스)으로
  데스크톱 1440px / 태블릿 768px / 모바일 390px 화면에서 메뉴·반응형·입력 검사·AI 결과·실패 안내를 확인한다.
- 확인하면서 docs/screenshots/ 에 스크린샷을 저장한다.

실행 (프로젝트 폴더에서, 처음 한 번만 설치):
    pip install playwright
    python -m playwright install chromium
    python scripts/check_ui.py

실제 AI 는 부르지 않는다 (목업 응답 사용). 실제 AI 동작 화면은 배포 URL 에서 따로 캡처한다.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dev_server import MockConfig, create_server  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
DESKTOP = {"width": 1440, "height": 900}
TABLET = {"width": 768, "height": 1024}
MOBILE = {"width": 390, "height": 844}

results = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, bool(passed), detail))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" | {detail}" if detail else ""))


def start(mock: MockConfig):
    server = create_server("127.0.0.1", 0, mock)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def new_page(browser, viewport, scheme="light", scale=1):
    context = browser.new_context(viewport=viewport, device_scale_factor=scale, color_scheme=scheme, locale="ko-KR")
    # 외부 글꼴 CDN 은 이 점검 환경에서 막혀 있을 수 있어 바로 실패 처리 (시스템 한글 글꼴로 표시됨)
    context.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" and "Failed to load resource" not in msg.text else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return context, page, errors


def no_horizontal_scroll(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def fill_sample_and_submit(page):
    page.click("#fill-sample")
    page.click("#submit-btn")


def shot(page, selector, name):
    """요소 스크린샷. 고정 헤더가 요소 위에 겹쳐 찍히지 않도록 찍는 동안만 고정을 푼다."""
    page.evaluate("document.querySelector('.site-header').style.position = 'relative'")
    page.locator(selector).screenshot(path=str(SHOTS / name))
    page.evaluate("document.querySelector('.site-header').style.position = ''")


def error_text(page):
    return page.inner_text("#request-error-title"), page.inner_text("#request-error-code")


def open_with_attrs(page, base_url, replacements):
    """index.html 을 받아 오면서 일부 속성 값을 바꿔 연다 (예: 지연 안내 기준 10초 → 1초)."""
    def rewrite(route):
        response = route.fetch()
        body = response.text()
        for old, new in replacements.items():
            body = body.replace(old, new)
        route.fulfill(response=response, body=body)

    page.route(base_url + "/", rewrite)
    page.goto(base_url + "/", wait_until="networkidle")
    page.click("nav a[href='#diagnose']")
    page.wait_for_timeout(600)


def run() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    ok_server, ok_url = start(MockConfig(delay=1.0))
    slow_server, slow_url = start(MockConfig(delay=4.0))
    error_servers = {code: start(MockConfig(delay=0.3, error=code)) for code in ("429", "500", "502", "504", "bad-json", "no-key")}

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------------- 데스크톱 ----------------
        context, page, errors = new_page(browser, DESKTOP)
        page.goto(ok_url + "/", wait_until="networkidle")
        check("데스크톱: 페이지 제목", "AX 레이더" in page.title(), page.title())
        check("데스크톱: 섹션 5개", page.locator("main > section").count() == 5)
        check("데스크톱: 가로 스크롤 없음", no_horizontal_scroll(page))
        check("데스크톱: 홈 예시 차트 그려짐", page.locator("#hero-radar svg polygon.radar-area").count() == 1)
        page.screenshot(path=str(SHOTS / "01_desktop_home.png"))

        page.click("nav a[href='#model']")
        page.wait_for_timeout(900)
        check("메뉴 이동: 진단 모델 섹션으로 스크롤", page.evaluate("Math.abs(document.querySelector('#model').getBoundingClientRect().top) < 80"))
        check("메뉴 강조: 진단 모델", page.get_attribute("nav a[href='#model']", "aria-current") == "true")
        page.screenshot(path=str(SHOTS / "02_desktop_model.png"))

        page.click("nav a[href='#diagnose']")
        page.wait_for_timeout(900)
        page.click("#submit-btn")                                   # 빈 입력 제출
        page.wait_for_timeout(500)
        alert = page.inner_text("#form-alert")
        check("빈 입력: 필수값 안내 문구", alert.startswith("필수값을 입력하세요"), alert)
        check("빈 입력: 칸별 오류 8개(업종·규모·점수5·고민)", page.locator(".field-error:not(:empty)").count() == 8)
        check("빈 입력: 서버를 부르지 않음(로딩 숨김)", page.is_hidden("#loading"))
        shot(page, "#diagnose-form", "05_validation_empty.png")

        page.fill("#goal", "짧은글")
        page.wait_for_timeout(800)                                  # 부드러운 스크롤이 끝난 뒤 클릭
        page.click("#submit-btn")
        page.wait_for_timeout(300)
        check("짧은 입력: 10자 안내", "10자 이상" in page.inner_text("#error-goal"), page.inner_text("#error-goal"))

        fill_sample_and_submit(page)
        page.wait_for_selector("#loading", state="visible", timeout=3000)
        check("요청 중: 로딩 표시와 버튼 잠금", page.is_disabled("#submit-btn"))
        page.wait_for_selector("#result", state="visible", timeout=10000)
        check("AI 결과: 단계 배지", page.inner_text("#result-level") == "2단계 · 실험", page.inner_text("#result-level"))
        check("AI 결과: 레이더 차트", page.locator("#result-chart svg .radar-point").count() == 5)
        check("AI 결과: 로드맵 3단계", page.locator("#result-roadmap > li").count() == 3)
        check("AI 결과: KPI 3개", page.locator("#result-kpis tr").count() == 3)
        check("AI 결과: 점수 표 5행 + 보완 표시 3개", page.locator("#result-scores tr").count() == 5 and page.locator("#result-scores .flag span").count() == 3)
        check("AI 결과: 목업 표시", "로컬 목업" in page.inner_text("#result-meta"), page.inner_text("#result-meta"))
        check("응답 후: 3초 재요청 제한", page.is_disabled("#submit-btn") and "초 후" in page.inner_text("#submit-btn"))
        page.wait_for_timeout(700)
        shot(page, "#result", "07_result_desktop_mock.png")
        page.wait_for_timeout(2800)
        check("응답 후: 3초 뒤 버튼 다시 활성", page.is_enabled("#submit-btn"))

        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=ok_url)
        page.click("#copy-btn")
        page.wait_for_timeout(300)
        copied = page.evaluate("navigator.clipboard.readText()")
        check("결과 복사: 텍스트 보고서", copied.startswith("[AX 레이더 진단 결과]") and "추천 KPI" in copied)

        # 화면에 나타난 모든 결과 글자가 textContent 로 들어갔는지 (HTML 태그가 실행되지 않음)
        page.route("**/api/diagnose", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "ok": True,
            "result": {"level": 2, "level_name": "실험", "level_desc": "설명", "total": 12, "average": 2.4,
                       "scores": {"strategy": 3, "data": 2, "tech": 2, "people": 3, "governance": 2},
                       "weakest": ["data"], "strongest": ["strategy"],
                       "summary": "<img src=x onerror=\"window.__xss=1\">요약", "strengths": ["<b>강점</b>"], "gaps": ["보완"],
                       "roadmap": [{"phase": "0~3개월", "title": "t", "actions": ["a"]}],
                       "kpis": [{"name": "k", "target": "t", "why": "w"}], "quick_win": "q", "caution": "c"},
            "meta": {"provider": "test", "model": "m", "elapsed_ms": 10}}, ensure_ascii=False)))
        page.wait_for_timeout(300)
        page.click("#submit-btn")
        page.wait_for_selector("#result", state="visible", timeout=5000)
        page.wait_for_timeout(300)
        check("보안: AI 응답 속 HTML 이 실행되지 않음", page.evaluate("window.__xss === undefined") and "<img" in page.inner_text("#result-summary"))
        page.unroute("**/api/diagnose")
        check("데스크톱: 콘솔 오류 없음", not errors, "; ".join(errors[:3]))
        context.close()

        # ---------------- 실패 처리 (서버 오류 코드별) ----------------
        expected = {
            "429": ("요청이 많아요", "RATE_LIMITED · HTTP 429"),
            "502": ("AI 서버 오류", "AI_UPSTREAM_ERROR · HTTP 502"),
            "504": ("응답 시간 초과", "AI_TIMEOUT · HTTP 504"),
            "500": ("서버 오류", "SERVER_ERROR · HTTP 500"),
            "bad-json": ("AI 응답 형식 오류", "AI_BAD_OUTPUT · HTTP 502"),
            "no-key": ("서버 설정이 필요해요", "CONFIG_MISSING_KEY · HTTP 500"),
        }
        for code, (title, code_text) in expected.items():
            context, page, errors = new_page(browser, DESKTOP)
            page.goto(error_servers[code][1] + "/#diagnose", wait_until="networkidle")
            fill_sample_and_submit(page)
            page.wait_for_selector("#request-error", state="visible", timeout=8000)
            got_title, got_code = error_text(page)
            check(f"실패 안내 [{code}]", got_title == title and code_text in got_code, f"{got_title} / {got_code}")
            if code == "429":
                shot(page, "#request-error", "09_error_rate_limit.png")
            context.close()

        # ---------------- 브라우저에서 감지하는 실패 ----------------
        context, page, errors = new_page(browser, DESKTOP)
        page.goto(ok_url + "/#diagnose", wait_until="networkidle")
        page.route("**/api/diagnose", lambda route: route.abort())
        fill_sample_and_submit(page)
        page.wait_for_selector("#request-error", state="visible", timeout=5000)
        check("네트워크 끊김 안내", error_text(page)[1] == "오류 코드: NETWORK_ERROR", error_text(page)[1])
        page.unroute("**/api/diagnose")
        page.wait_for_timeout(3200)

        page.route("**/api/diagnose", lambda route: route.fulfill(status=504, content_type="text/html", body="<html>An error occurred with your deployment. FUNCTION_INVOCATION_TIMEOUT</html>"))
        page.click("#submit-btn")
        page.wait_for_selector("#request-error-code:has-text('HTTP 504')", timeout=5000)
        check("JSON 이 아닌 504(Vercel 기본 오류 화면) 안내", error_text(page) == ("응답 시간 초과", "오류 코드: HTTP 504"))
        page.unroute("**/api/diagnose")
        page.wait_for_timeout(3200)

        page.route("**/api/diagnose", lambda route: route.fulfill(status=404, content_type="text/plain", body="The page could not be found"))
        page.click("#submit-btn")
        page.wait_for_selector("#request-error-code:has-text('HTTP 404')", timeout=5000)
        check("API 없음(404) 안내", error_text(page)[0] == "API를 찾을 수 없어요")
        page.unroute("**/api/diagnose")
        page.wait_for_timeout(3200)

        page.route("**/api/diagnose", lambda route: route.fulfill(status=400, content_type="application/json", body=json.dumps(
            {"ok": False, "error": {"code": "INVALID_INPUT", "message": "고민·목표를 10자 이상 적어 주세요. (지금 9자)", "field": "goal"}}, ensure_ascii=False)))
        page.click("#submit-btn")
        page.wait_for_selector("#request-error", state="visible", timeout=5000)
        check("서버 검증 오류(400)를 해당 칸에 표시", "10자 이상" in page.inner_text("#error-goal"))
        page.unroute("**/api/diagnose")
        context.close()

        # 지연·타임아웃 기준(초)은 스크립트가 페이지를 열 때 한 번 읽으므로, HTML 을 가로채 값을 줄여서 연다
        context, page, errors = new_page(browser, DESKTOP)
        open_with_attrs(page, slow_url, {'data-slow-ms="10000"': 'data-slow-ms="1000"'})
        fill_sample_and_submit(page)
        page.wait_for_selector("#loading-slow", state="visible", timeout=4000)
        check("지연 안내: 오래 걸리면 안내 문구 표시", "오래 걸리고" in page.inner_text("#loading-slow"))
        shot(page, "#loading", "06_loading_slow.png")
        page.wait_for_selector("#result", state="visible", timeout=10000)
        check("지연 후: 결과 정상 표시", page.is_visible("#result"))
        context.close()

        context, page, errors = new_page(browser, DESKTOP)
        open_with_attrs(page, slow_url, {'data-timeout-ms="50000"': 'data-timeout-ms="2000"'})
        fill_sample_and_submit(page)
        page.wait_for_selector("#request-error", state="visible", timeout=6000)
        check("브라우저 타임아웃: 요청 중단 안내", error_text(page)[1] == "오류 코드: CLIENT_TIMEOUT", error_text(page)[1])
        shot(page, "#request-error", "10_error_timeout.png")
        context.close()

        # ---------------- 태블릿·모바일 ----------------
        context, page, errors = new_page(browser, TABLET)
        page.goto(ok_url + "/", wait_until="networkidle")
        check("태블릿 768px: 가로 스크롤 없음", no_horizontal_scroll(page))
        page.goto(ok_url + "/#diagnose", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "12_tablet_diagnose.png"))
        context.close()

        context, page, errors = new_page(browser, MOBILE, scale=2)
        page.goto(ok_url + "/", wait_until="networkidle")
        check("모바일 390px: 가로 스크롤 없음", no_horizontal_scroll(page))
        check("모바일: 메뉴 접힘 + 햄버거 버튼", page.is_hidden("#site-nav") and page.is_visible("#menu-toggle"))
        page.screenshot(path=str(SHOTS / "03_mobile_home.png"))
        page.click("#menu-toggle")
        check("모바일: 햄버거로 메뉴 열기", page.is_visible("#site-nav") and page.get_attribute("#menu-toggle", "aria-expanded") == "true")
        page.wait_for_timeout(400)                                  # 메뉴가 펼쳐지는 동작이 끝난 뒤 촬영
        page.screenshot(path=str(SHOTS / "04_mobile_menu.png"))
        page.click("#site-nav a[href='#diagnose']")
        page.wait_for_timeout(900)
        check("모바일: 메뉴 선택 후 닫힘", page.is_hidden("#site-nav"))
        fill_sample_and_submit(page)
        page.wait_for_selector("#result", state="visible", timeout=10000)
        page.wait_for_timeout(800)
        check("모바일: 결과 화면 가로 스크롤 없음", no_horizontal_scroll(page))
        shot(page, "#result", "08_result_mobile_mock.png")
        check("모바일: 콘솔 오류 없음", not errors, "; ".join(errors[:3]))
        context.close()

        # ---------------- 다크 모드 ----------------
        context, page, errors = new_page(browser, DESKTOP)
        page.goto(ok_url + "/", wait_until="networkidle")
        page.click("#theme-toggle")
        check("다크 모드: 버튼으로 전환", page.get_attribute("html", "data-theme") == "dark")
        page.reload(wait_until="networkidle")
        check("다크 모드: 새로고침 후 유지", page.get_attribute("html", "data-theme") == "dark")
        page.screenshot(path=str(SHOTS / "11_dark_mode.png"))
        fill_sample_and_submit(page)
        page.wait_for_selector("#result", state="visible", timeout=10000)
        page.wait_for_timeout(800)
        shot(page, "#result", "13_result_dark_mock.png")
        context.close()

        browser.close()

    for server in [ok_server, slow_server] + [pair[0] for pair in error_servers.values()]:
        server.shutdown()
        server.server_close()

    failed = [name for name, passed, _ in results if not passed]
    print("-" * 60)
    print(f"총 {len(results)}개 점검 | 통과 {len(results) - len(failed)} | 실패 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    started = time.time()
    code = run()
    print(f"소요 시간 {time.time() - started:.1f}초")
    sys.exit(code)
