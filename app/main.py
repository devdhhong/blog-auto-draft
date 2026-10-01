"""프로그램 시작점: 로컬 서버를 띄우고 앱 창(Edge/Chrome 앱 모드)을 연다.
창을 닫으면 프로그램도 종료된다 (진행 중인 업로드가 있으면 끝날 때까지 기다림)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser

from common import IS_MAC, IS_WIN, data_dir, log_dir

# 창 모드 실행 시 stdout/stderr가 없으면 로그 파일로 연결 (브라우저 제어 엔진이 필요로 함)
if sys.stdout is None or sys.stderr is None:
    _f = open(os.path.join(log_dir(), "program.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _f
    sys.stderr = sys.stderr or _f

import server  # noqa: E402


def find_app_browser() -> str | None:
    cands = []
    if IS_WIN:
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif IS_MAC:
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        cands += [shutil.which(x) or "" for x in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def main():
    srv = server.serve(int(os.environ.get("NBH_PORT", "0")))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("UI:", url, flush=True)
    if os.environ.get("NBH_NO_WINDOW"):
        while True:
            time.sleep(3600)

    br = find_app_browser()
    proc = None
    if br:
        proc = subprocess.Popen([br, f"--app={url}", f"--user-data-dir={os.path.join(data_dir(), 'ui-window')}",
                                 "--no-first-run", "--no-default-browser-check", "--window-size=1100,900"])
    else:
        webbrowser.open(url)

    while True:
        time.sleep(2)
        # 창 프로세스가 끝났거나(윈도우), 화면이 60초 넘게 응답이 없으면(맥은 창을 닫아도 프로세스가 남음) 종료
        closed = (proc is not None and proc.poll() is not None) or time.time() - server.LAST_PING[0] > 60
        if closed and not server.JOBS.busy():
            break
    if proc is not None and proc.poll() is None:
        proc.terminate()
    os._exit(0)


if __name__ == "__main__":
    main()
