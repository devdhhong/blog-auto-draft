"""Windows 클립보드(텍스트/HTML) - ctypes만 사용."""
from __future__ import annotations

import base64
import ctypes
import sys
import time

available = sys.platform == "win32"

if available:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002


def _open():
    for _ in range(20):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise RuntimeError("클립보드를 열 수 없습니다 (다른 프로그램이 사용 중)")


def _put(fmt: int, data: bytes):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    if not user32.SetClipboardData(fmt, h):
        raise RuntimeError("클립보드 쓰기 실패")


def _cf_html(fragment: str) -> bytes:
    header = ("Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\n"
              "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n")
    pre = "<html><body><!--StartFragment-->"
    post = "<!--EndFragment--></body></html>"
    dummy = header.format(0, 0, 0, 0)
    start_html = len(dummy.encode("utf-8"))
    start_frag = start_html + len(pre.encode("utf-8"))
    end_frag = start_frag + len(fragment.encode("utf-8"))
    end_html = end_frag + len(post.encode("utf-8"))
    return (header.format(start_html, end_html, start_frag, end_frag) + pre + fragment + post).encode("utf-8") + b"\0"


def set_clipboard(text: str, html_fragment: str | None = None):
    _open()
    try:
        user32.EmptyClipboard()
        _put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        if html_fragment is not None:
            fmt = user32.RegisterClipboardFormatW("HTML Format")
            _put(fmt, _cf_html(html_fragment))
    finally:
        user32.CloseClipboard()


def clear_clipboard():
    _open()
    try:
        user32.EmptyClipboard()
    finally:
        user32.CloseClipboard()


