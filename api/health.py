"""상태 확인 API (Vercel Serverless Function, Python)

주소 : GET /api/health
용도 : 배포 후 "서버리스 함수가 실행되는지", "AI 키가 설정됐는지"를 키 값 노출 없이 확인한다.
응답 : {"ok": true, "service": "ax-radar", "provider": "gemini", "model": "...", "key_configured": true, ...}

서버리스 함수는 파일마다 따로 배포되므로, diagnose.py 의 코드를 가져다 쓰지 않고
필요한 최소 설정(환경 변수 이름, 기본 모델)만 여기에 둔다. 두 파일의 값이 같은지는 테스트가 확인한다.
"""
from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

KEY_ENV = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
MODEL_ENV = {"gemini": "GEMINI_MODEL", "anthropic": "ANTHROPIC_MODEL", "openai": "OPENAI_MODEL"}
DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5.4-mini",
}
PROVIDER_ORDER = ("gemini", "anthropic", "openai")
PROVIDER_ALIASES = {"google": "gemini", "claude": "anthropic", "gpt": "openai", "chatgpt": "openai"}


def detect_provider(env=None) -> dict:
    """어떤 AI 제공자를 쓸 예정인지 알려 준다. 키 값 자체는 절대 돌려주지 않는다."""
    env = os.environ if env is None else env
    wanted = (env.get("LLM_PROVIDER") or "").strip().lower()
    wanted = PROVIDER_ALIASES.get(wanted, wanted)
    candidates = [wanted] if wanted in KEY_ENV else list(PROVIDER_ORDER)
    for provider in candidates:
        if (env.get(KEY_ENV[provider]) or "").strip():
            model = (env.get(MODEL_ENV[provider]) or "").strip() or DEFAULT_MODELS[provider]
            return {"provider": provider, "model": model, "key_configured": True}
    fallback = wanted if wanted in KEY_ENV else None
    return {"provider": fallback, "model": None, "key_configured": False}


def build_status(env=None) -> dict:
    info = detect_provider(env)
    return {
        "ok": True,
        "service": "ax-radar",
        "provider": info["provider"],
        "model": info["model"],
        "key_configured": info["key_configured"],
        "notify_webhook": bool(((os.environ if env is None else env).get("NOTIFY_WEBHOOK_URL") or "").strip()),
        "runtime": f"python {platform.python_version()}",
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(build_status(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
