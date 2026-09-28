"""로컬 개발 서버: 정적 파일 + api/*.py 서버리스 함수를 한 번에 실행 (Vercel 로그인 없이 테스트)

실행 (프로젝트 폴더에서):
    python scripts/dev_server.py                      # http://localhost:3000  (.env 의 키로 실제 AI 호출)
    python scripts/dev_server.py --mock               # AI 대신 가짜 응답 (키 없이 화면 확인)
    python scripts/dev_server.py --mock --mock-delay 12    # "오래 걸리고 있어요" 안내 확인
    python scripts/dev_server.py --mock-error 429     # 실패 안내 확인
          (--mock-error 값: 429, 500, 502, 504, bad-json, no-key)

Vercel 과 비슷하게 동작시키는 방법
- /api/<이름> 요청은 api/<이름>.py 의 handler 클래스가 직접 처리한다.
  요청 첫 줄만 미리 엿보고(MSG_PEEK) 어느 handler 에 넘길지 정한다.
- 요청마다 api 파일을 새로 불러오므로 코드를 고치면 서버를 다시 켜지 않아도 반영된다.
- vercel.json 의 headers 설정을 응답에 똑같이 붙인다.
- .env 파일이 있으면 환경 변수로 읽는다. (키 이름만 출력하고 값은 출력하지 않는다)
- 점(.)으로 시작하는 파일(.env, .git 등)과 api/, scripts/, tests/ 의 소스 파일은 내려주지 않는다.

이 파일은 로컬 테스트 전용이며 .vercelignore 로 배포에서 빠진다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import socket
import sys
import time
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
BLOCKED_PREFIXES = ("/api/", "/scripts/", "/tests/")
MOCK_ERRORS = ("429", "500", "502", "504", "bad-json", "no-key")


# ---------------------------------------------------------------------------
# 설정 읽기
# ---------------------------------------------------------------------------
def load_dotenv(path: Path = ROOT / ".env") -> list:
    """KEY=VALUE 형식의 .env 를 읽어 환경 변수에 넣는다. 이미 있는 값은 덮어쓰지 않는다."""
    if not path.exists():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def load_header_rules() -> list:
    """vercel.json 의 headers 규칙을 (정규식, [(이름, 값)]) 목록으로 바꾼다."""
    try:
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rules = []
    for rule in config.get("headers", []):
        try:
            pattern = re.compile("^" + rule.get("source", "") + "$")
        except re.error:
            continue
        rules.append((pattern, [(item["key"], item["value"]) for item in rule.get("headers", [])]))
    return rules


HEADER_RULES = load_header_rules()


def headers_for(raw_path: str) -> list:
    path = raw_path.split("?", 1)[0]
    found = []
    for pattern, headers in HEADER_RULES:
        if pattern.match(path):
            found.extend(headers)
    return found


# ---------------------------------------------------------------------------
# 목업(mock) 모드: 실제 AI 대신 정해진 응답을 돌려준다
# ---------------------------------------------------------------------------
@dataclass
class MockConfig:
    delay: float = 1.2
    error: str | None = None


MOCK_RESULT = {
    "summary": "경영진의 의지는 있으나 설비 데이터가 라인별로 흩어져 있어 파일럿 성과를 넓히기 어려운 상태임. {weak} 보완이 1순위임.",
    "strengths": ["경영진이 AI 전환 필요성에 공감하고 있음", "현장 개선 활동 경험이 있어 변화 수용도가 높음"],
    "gaps": ["설비·검사 데이터가 라인마다 따로 저장돼 통합 분석이 어려움", "AI 도입 성과를 재는 기준과 담당 조직이 없음"],
    "roadmap": [
        {"phase": "0~3개월", "title": "데이터 기반 정비", "actions": ["비전검사 1개 라인의 불량 이미지·설비 데이터 한곳에 모으기", "데이터 책임자 1명 지정"]},
        {"phase": "3~6개월", "title": "파일럿 실행과 검증", "actions": ["불량 판정 보조 AI 파일럿 운영", "검출률·오검출률을 주 단위로 측정"]},
        {"phase": "6~12개월", "title": "확산 준비", "actions": ["성과가 난 방식을 2개 라인으로 확대", "AI 사용·보안 규칙 문서화"]},
    ],
    "kpis": [
        {"name": "불량률", "target": "현재 대비 20% 감소", "why": "품질 비용과 납품 신뢰도에 직결됨"},
        {"name": "데이터 자동 수집 설비 비율", "target": "대상 설비의 60% 이상", "why": "AI 확산의 전제 조건임"},
        {"name": "AI 교육 이수 인원", "target": "현장 리더 20명", "why": "파일럿 결과를 현장에 정착시키는 속도를 좌우함"},
    ],
    "quick_win": "이번 주에 최근 한 달 불량 사진을 한 폴더에 모으고 불량 유형 이름표 기준을 정하기",
    "caution": "데이터 정비 없이 솔루션부터 구매하면 파일럿이 성과 없이 끝날 위험이 큼",
}


def apply_mock(module, config: MockConfig) -> None:
    """불러온 diagnose 모듈의 AI 호출 부분만 가짜로 바꾼다 (배포 코드는 그대로)."""
    if not hasattr(module, "call_ai"):
        return
    real_pick_provider = module.pick_provider

    if config.error == "no-key":
        module.pick_provider = lambda env=None: real_pick_provider({})   # 키가 없는 서버를 흉내
        return
    module.pick_provider = lambda env=None: ("mock", "mock-key", "local-mock")

    def fake_call_ai(provider, key, model, system, user, timeout):
        if config.delay:
            time.sleep(config.delay)
        if config.error == "429":
            raise module.AiError("RATE_LIMITED", "지금 요청이 많아 AI가 잠시 쉬고 있어요. 1분 뒤 다시 시도해 주세요.", status=429)
        if config.error == "502":
            raise module.AiError("AI_UPSTREAM_ERROR", "AI 서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요.")
        if config.error == "504":
            raise module.AiError("AI_TIMEOUT", f"AI 응답이 {timeout}초 안에 오지 않았어요. 잠시 후 다시 시도해 주세요.", status=504)
        if config.error == "500":
            raise RuntimeError("dev_server --mock-error 500 (의도한 예외)")
        if config.error == "bad-json":
            return "죄송합니다. JSON 대신 평범한 문장으로 답했습니다."
        weak = re.search(r"가장 낮은 영역: (.+)", user)
        weak_text = weak.group(1).strip() if weak else "데이터 기반"
        if weak_text.startswith("없음"):
            weak_text = "모든 영역이 같은 점수라 데이터 기반"
        result = dict(MOCK_RESULT)
        result["summary"] = MOCK_RESULT["summary"].format(weak=weak_text)
        return json.dumps(result, ensure_ascii=False)

    module.call_ai = fake_call_ai


# ---------------------------------------------------------------------------
# 요청 처리기
# ---------------------------------------------------------------------------
class StaticHandler(SimpleHTTPRequestHandler):
    """정적 파일(html/css/js/images) 전용. 비밀 파일과 소스 폴더는 404."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        for name, value in headers_for(self.path):
            self.send_header(name, value)
        super().end_headers()

    def send_head(self):
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        parts = [part for part in path.split("/") if part]
        if any(part.startswith(".") for part in parts) or path.startswith(BLOCKED_PREFIXES) or path == "/api":
            self.send_error(404, "Not Found")
            return None
        return super().send_head()

    def list_directory(self, path):          # Vercel 처럼 폴더 목록은 보여 주지 않는다
        self.send_error(404, "Not Found")
        return None


class FunctionFailedHandler(BaseHTTPRequestHandler):
    """api 파일을 불러오다 실패했을 때 (예: 문법 오류). Vercel 의 500 오류 화면을 흉내 낸다."""

    def _fail(self):
        body = "500 FUNCTION_INVOCATION_FAILED (dev_server): 터미널의 오류 메시지를 확인하세요.".encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _fail


def _end_headers_with_rules(self):
    for name, value in headers_for(self.path):
        self.send_header(name, value)
    BaseHTTPRequestHandler.end_headers(self)


def peek_path(sock: socket.socket) -> str:
    """요청 데이터를 소비하지 않고(MSG_PEEK) 첫 줄의 경로만 읽는다."""
    data = b""
    sock.settimeout(5)
    try:
        for _ in range(100):
            data = sock.recv(8192, socket.MSG_PEEK)
            if not data or b"\r\n" in data:
                break
            time.sleep(0.01)
    except (socket.timeout, OSError):
        pass
    finally:
        sock.settimeout(None)
    first_line = data.split(b"\r\n", 1)[0].decode("latin-1", "replace").split(" ")
    return first_line[1] if len(first_line) >= 2 else "/"


def api_name(raw_path: str):
    path = unquote(raw_path.split("?", 1)[0])
    match = re.fullmatch(r"/api/([A-Za-z0-9-][A-Za-z0-9_-]*)/?", path)
    if not match or not (API_DIR / f"{match.group(1)}.py").exists():
        return None
    return match.group(1)


def load_api_module(name: str):
    spec = importlib.util.spec_from_file_location(f"dev_api_{name}", API_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DevServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, mock: MockConfig | None = None):
        super().__init__(address, StaticHandler)
        self.mock = mock

    def handle_error(self, request, client_address):
        # 브라우저가 응답을 기다리다 먼저 연결을 끊은 경우(타임아웃 등)는 정상 상황이라 조용히 넘긴다
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

    def finish_request(self, request, client_address):
        name = api_name(peek_path(request))
        if name is None:
            StaticHandler(request, client_address, self)
            return
        try:
            module = load_api_module(name)             # 요청마다 새로 불러와 코드 수정이 바로 반영됨
            if self.mock and name == "diagnose":
                apply_mock(module, self.mock)
            handler_class = type(f"DevApi_{name}", (module.handler,), {"end_headers": _end_headers_with_rules})
        except Exception:
            traceback.print_exc()
            FunctionFailedHandler(request, client_address, self)
            return
        handler_class(request, client_address, self)


def create_server(host: str = "127.0.0.1", port: int = 3000, mock: MockConfig | None = None) -> DevServer:
    return DevServer((host, port), mock)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="AX 레이더 로컬 개발 서버 (정적 파일 + api/*.py)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "3000")))
    parser.add_argument("--mock", action="store_true", help="실제 AI 대신 가짜 응답을 돌려줌 (키 불필요)")
    parser.add_argument("--mock-delay", type=float, default=1.2, help="가짜 응답 전 기다릴 초 (기본 1.2)")
    parser.add_argument("--mock-error", choices=MOCK_ERRORS, help="실패 안내 화면을 확인할 오류 종류")
    args = parser.parse_args(argv)

    loaded = load_dotenv()
    mock = MockConfig(delay=args.mock_delay, error=args.mock_error) if (args.mock or args.mock_error) else None
    server = create_server(args.host, args.port, mock)

    print("=" * 60)
    print(f" AX 레이더 로컬 서버: http://localhost:{args.port}")
    if mock:
        print(f" 모드: 목업 (지연 {mock.delay}초, 오류 {mock.error or '없음'}) | 실제 AI 를 부르지 않음")
    else:
        keys = [name for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY") if os.environ.get(name)]
        print(f" 모드: 실제 AI 호출 | 설정된 키: {', '.join(keys) if keys else '없음 (.env 를 확인하세요)'}")
    if loaded:
        print(f" .env 에서 읽은 변수 이름: {', '.join(loaded)}")
    print(" 종료: Ctrl + C")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료했어요.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
