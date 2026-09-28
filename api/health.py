"""상태 확인 API (Vercel Serverless Function, Python)

주소 : GET /api/health
용도 : 배포 후 "서버리스 함수가 실행되는지", "AI 키가 설정됐는지"를 키 값 노출 없이 확인한다.
응답 : {"ok": true, "service": "ax-radar", "provider": "gemini", "model": "...",
        "key_configured": true, "config_ok": true, "config_error": null, ...}

서버리스 함수는 파일마다 따로 배포되므로, diagnose.py 의 코드를 가져다 쓰지 않고
필요한 최소 설정(환경 변수 이름, 기본 모델)만 여기에 둔다. 두 파일의 값이 같은지는 테스트가 확인한다.
"""
from __future__ import annotations

import json
import os
import platform
import re
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


MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,79}")


def detect_provider(env=None) -> dict:
    """어떤 AI 제공자를 쓸 예정인지, 설정이 올바른지 알려 준다. 키 값 자체는 절대 돌려주지 않는다.

    diagnose.py 의 pick_provider 와 같은 규칙으로 판단한다. (config_ok 가 true 여야 진단이 동작)
    """
    env = os.environ if env is None else env
    wanted = (env.get("LLM_PROVIDER") or "").strip().lower()
    wanted = PROVIDER_ALIASES.get(wanted, wanted)
    if wanted and wanted not in KEY_ENV:
        return {"provider": None, "model": None, "key_configured": False, "config_ok": False,
                "config_error": "LLM_PROVIDER 값은 gemini, anthropic, openai 중 하나여야 해요."}
    for provider in ([wanted] if wanted else list(PROVIDER_ORDER)):
        if (env.get(KEY_ENV[provider]) or "").strip():
            model = (env.get(MODEL_ENV[provider]) or "").strip() or DEFAULT_MODELS[provider]
            if model.startswith("models/"):
                model = model[len("models/"):]
            if not MODEL_PATTERN.fullmatch(model):
                return {"provider": provider, "model": None, "key_configured": True, "config_ok": False,
                        "config_error": f"{MODEL_ENV[provider]} 값이 올바르지 않아요."}
            return {"provider": provider, "model": model, "key_configured": True, "config_ok": True, "config_error": None}
    missing = KEY_ENV[wanted] if wanted else "GEMINI_API_KEY 등"
    return {"provider": wanted or None, "model": None, "key_configured": False, "config_ok": False,
            "config_error": f"AI 키({missing})가 설정되지 않았어요."}


def build_status(env=None) -> dict:
    info = detect_provider(env)
    return {
        "ok": True,
        "service": "ax-radar",
        "provider": info["provider"],
        "model": info["model"],
        "key_configured": info["key_configured"],
        "config_ok": info["config_ok"],
        "config_error": info["config_error"],
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
