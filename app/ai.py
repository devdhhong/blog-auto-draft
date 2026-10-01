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


def _req(url: str, key: str, body: dict | None = None, timeout=120):
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


def generate_json(prompt: str, key: str, model: str = "gemini-flash-latest", retries: int = 4) -> dict:
    if not key:
        raise AIError("Gemini API 키가 설정되지 않았습니다. 설정에서 키를 넣어 주세요.")
    url = f"{BASE}/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}
    last = None
    for attempt in range(retries):
        try:
            d = _req(url, key, body)
            cands = d.get("candidates") or []
            if not cands:
                raise AIError("AI 응답이 비어 있습니다: " + json.dumps(d.get("promptFeedback", {}), ensure_ascii=False))
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            return _parse_json(text)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            last = f"HTTP {e.code}: {msg[:300]}"
            if e.code in (429, 500, 502, 503, 504):
                wait = 15 * (attempt + 1)
                m = re.search(r'"retryDelay":\s*"(\d+)', msg)
                if m:
                    wait = int(m.group(1)) + 2
                time.sleep(min(wait, 70))
                continue
            if e.code in (400, 403) and "API key" in msg:
                raise AIError("Gemini API 키가 올바르지 않습니다.")
            if e.code == 404:
                raise AIError(f"모델 '{model}'을 찾을 수 없습니다. 설정에서 모델 목록을 불러와 다시 고르세요.")
            raise AIError(last)
        except (json.JSONDecodeError, KeyError) as e:
            last = f"응답 해석 실패: {e}"
            time.sleep(2)
        except urllib.error.URLError as e:
            last = f"네트워크 오류: {e.reason}"
            time.sleep(5)
    raise AIError(last or "AI 호출 실패")


def list_models(key: str) -> list[str]:
    d = _req(f"{BASE}/models?pageSize=200", key)
    out = []
    for m in d.get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            out.append(m["name"].split("/", 1)[-1])
    return sorted(out)
