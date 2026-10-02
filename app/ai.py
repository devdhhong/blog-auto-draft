"""Google Gemini API (무료 등급 사용 가능) 호출."""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:  # certifi 없음
    _CTX = ssl.create_default_context()

import os
BASE = os.environ.get("NBH_GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")


class AIError(Exception):
    pass


def _req(url: str, key: str, body: dict | None = None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return json.loads(r.read().decode())


def _parse_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s:e + 1])
        raise


_MODELS_CACHE: dict = {}


def _fallback_models(key: str, first: str) -> list[str]:
    """선택한 모델이 붐빌 때(503 등) 차례로 시도할 무료 flash 계열 모델 목록."""
    out = [first]
    try:
        if key not in _MODELS_CACHE:
            _MODELS_CACHE[key] = list_models(key)
        names = _MODELS_CACHE[key]
    except Exception:
        names = []
    skip = ("image", "tts", "live", "audio", "embedding", "vision", "preview-tts", "transcribe", "robotics")
    flash = [m for m in names if "flash" in m and not any(x in m for x in skip)]
    # 별칭(latest) 우선, 그다음 이름순 최신
    flash.sort(key=lambda m: (0 if m.endswith("-latest") else 1, m), reverse=False)
    for m in ["gemini-flash-latest", "gemini-flash-lite-latest"] + flash:
        if m not in out:
            out.append(m)
    return out[:5]


def _one(model: str, key: str, body: dict, tries: int):
    """한 모델로 시도. 붐빔(429/5xx)이면 ('busy', 메시지)를 돌려준다."""
    url = f"{BASE}/models/{model}:generateContent"
    last = None
    for attempt in range(tries):
        try:
            d = _req(url, key, body)
            cands = d.get("candidates") or []
            if cands and not cands[0].get("content", {}).get("parts"):
                raise AIError(f"AI가 답을 주지 않았습니다 (사유: {cands[0].get('finishReason')})")
            if not cands:
                raise AIError("AI 응답이 비어 있습니다: " + json.dumps(d.get("promptFeedback", {}), ensure_ascii=False))
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            return "ok", _parse_json(text)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            last = f"HTTP {e.code}: {msg[:200]}"
            if e.code in (429, 500, 502, 503, 504):
                wait = 8 * (attempt + 1)
                m = re.search(r'"retryDelay":\s*"(\d+)', msg)
                if m:
                    wait = min(int(m.group(1)) + 2, 40)
                if attempt < tries - 1:
                    time.sleep(wait)
                continue
            if e.code in (400, 403) and "API key" in msg:
                raise AIError("Gemini API 키가 올바르지 않습니다.")
            if e.code == 404:
                return "busy", f"모델 '{model}' 없음"
            raise AIError(last)
        except (json.JSONDecodeError, KeyError) as e:
            last = f"응답 해석 실패: {e}"
            time.sleep(2)
        except urllib.error.URLError as e:
            last = f"네트워크 오류: {e.reason}"
            time.sleep(5)
        except (TimeoutError, OSError) as e:
            last = f"AI 응답 시간 초과/연결 오류: {e}"
            time.sleep(5)
    return "busy", last


def generate_json(prompt: str, key: str, model: str = "gemini-flash-latest", retries: int = 3) -> dict:
    if not key:
        raise AIError("Gemini API 키가 설정되지 않았습니다. 설정에서 키를 넣어 주세요.")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}
    tried = []
    for m in _fallback_models(key, model or "gemini-flash-latest"):
        status, res = _one(m, key, body, retries if m == model else 2)
        if status == "ok":
            return res
        tried.append(f"{m}: {res}")
    raise AIError("Gemini 서버가 지금 붐벼서(503/429) 처리하지 못했어요. 1~2분 뒤 다시 실행해 주세요.\n"
                  "시도한 모델 — " + " / ".join(tried)[:400])


def list_models(key: str) -> list[str]:
    d = _req(f"{BASE}/models?pageSize=200", key)
    out = []
    for m in d.get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            out.append(m["name"].split("/", 1)[-1])
    return sorted(out)
