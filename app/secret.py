"""이 컴퓨터에만 '동기화 비밀번호'를 기억해 두는 기능.
Windows: DPAPI(현재 Windows 사용자만 복호화) / macOS: 키체인."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess

from common import IS_MAC, IS_WIN, APP_ID, data_dir

_FILE = os.path.join(data_dir(), "remember.json")

if IS_WIN:
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.LocalFree.argtypes = [wintypes.HLOCAL]

    def _dpapi(data: bytes, protect: bool) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        inp = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _BLOB()
        fn = _crypt32.CryptProtectData if protect else _crypt32.CryptUnprotectData
        if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            raise OSError("DPAPI 실패")
        res = ctypes.string_at(out.pbData, out.cbData)
        _kernel32.LocalFree(out.pbData)
        return res


def remember(secret: str):
    if IS_MAC:
        subprocess.run(["security", "add-generic-password", "-U", "-a", APP_ID, "-s", APP_ID, "-w", secret],
                       check=True, capture_output=True)
        return
    if IS_WIN:
        token = base64.b64encode(_dpapi(secret.encode(), True)).decode()
    else:  # 개발용(리눅스)
        token = base64.b64encode(secret.encode()).decode()
    with open(_FILE, "w") as f:
        json.dump({"t": token}, f)


def recall() -> str | None:
    try:
        if IS_MAC:
            r = subprocess.run(["security", "find-generic-password", "-a", APP_ID, "-s", APP_ID, "-w"],
                               capture_output=True, text=True)
            return r.stdout.strip() or None if r.returncode == 0 else None
        with open(_FILE) as f:
            token = base64.b64decode(json.load(f)["t"])
        return (_dpapi(token, False) if IS_WIN else token).decode()
    except Exception:
        return None


def forget():
    if IS_MAC:
        subprocess.run(["security", "delete-generic-password", "-a", APP_ID, "-s", APP_ID], capture_output=True)
    try:
        os.remove(_FILE)
    except OSError:
        pass
