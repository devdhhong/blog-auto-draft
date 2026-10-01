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
    if os.environ.get("NBH_APP_BROWSER"):   # 테스트용
        return os.environ["NBH_APP_BROWSER"]
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


def kill_ui_window(ui_dir: str):
    """이전에 띄운 앱 창(전용 프로필의 크롬/엣지)이 남아 있으면 정리한다.
    맥은 창을 닫아도 크롬이 꺼지지 않아, 다음 실행 때 새 창이 옛 프로세스로 넘어가 버리는 문제를 막는다."""
    try:
        if IS_MAC:
            subprocess.run(["pkill", "-f", f"user-data-dir={ui_dir}"], capture_output=True)
        elif IS_WIN:
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*NaverBlogHelper*ui-window*' } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=0x08000000)
        time.sleep(0.5)
    except Exception:
        pass


def main():
    srv = server.serve(int(os.environ.get("NBH_PORT", "0")))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("UI:", url, flush=True)
    if os.environ.get("NBH_NO_WINDOW"):
        while True:
            time.sleep(3600)

    ui_dir = os.path.join(data_dir(), "ui-window")
    br = find_app_browser()
    if br:
        kill_ui_window(ui_dir)
        subprocess.Popen([br, f"--app={url}", f"--user-data-dir={ui_dir}", "--no-first-run",
                          "--no-default-browser-check", "--window-size=1100,900",
                          "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                          "--disable-backgrounding-occluded-windows"])
    else:
        webbrowser.open(url)

    # 종료 판단은 화면이 보내는 신호로만 한다:
    #  - 창을 닫으면 화면이 '닫힘' 신호를 보내고, 10초 안에 다시 연결되지 않으면 종료 (새로고침은 유지)
    #  - 신호 없이 3분 넘게 연락이 없으면 종료
    #  - 업로드 진행 중이면 끝날 때까지 기다림
    started = time.time()
    while True:
        time.sleep(2)
        now = time.time()
        idle = now - server.LAST_PING[0]
        bye = server.BYE[0] and now - server.BYE[0] > 10 and server.BYE[0] >= server.LAST_PING[0]
        if (bye or (idle > 180 and now - started > 180)) and not server.JOBS.busy():
            break
    if br:
        kill_ui_window(ui_dir)
    os._exit(0)


if __name__ == "__main__":
    main()
