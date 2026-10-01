"""화면(웹 UI)과 통신하는 로컬 서버 + 업로드 작업 큐."""
from __future__ import annotations

import json
import os
import queue
import ssl
import subprocess
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ai
from common import APP_VERSION, GITHUB_REPO, IS_MAC, IS_WIN, log_dir, resource
from naver import Naver, StopRequested, load_selectors
from store import LockedError, Store

STORE = Store()
STORE.try_auto_unlock()
LAST_PING = [time.time()]
BYE = [0.0]   # 화면이 닫힐 때 받은 시각


# ------------------------------------------------------------------ 작업 큐
class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.items: list[dict] = []
        self.q: queue.Queue = queue.Queue()
        self.stop = threading.Event()
        self.seq = 0
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def add(self, job: dict) -> dict:
        # 새로 업로드를 요청했으면 이전의 '중지' 상태는 풀어 준다
        if self.q.empty() and not self.busy():
            self.stop.clear()
        with self.lock:
            self.seq += 1
            job = {**job, "id": self.seq, "status": "대기", "log": [], "t": time.time()}
            self.items.append(job)
        self.q.put(job)
        return job

    def public(self):
        with self.lock:
            return [{k: v for k, v in j.items() if k not in ("html", "plain")} for j in self.items[-100:]]

    def busy(self) -> bool:
        with self.lock:
            return any(j["status"] in ("대기", "진행 중") for j in self.items)

    def _run(self):
        nav = None
        while True:
            job = self.q.get()
            if job["status"] == "취소":
                continue
            if self.stop.is_set():
                job["status"] = "취소"
                if self.q.empty():
                    self.stop.clear()
                continue
            job["status"] = "진행 중"

            def log(m, j=job):
                j["log"].append(m)
                with open(os.path.join(log_dir(), "작업기록.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%m-%d %H:%M:%S')} [{j['preset']}] {m}\n")

            try:
                log(f"'{job['title']}' 작업 시작")
                acc = STORE.account(job["preset"])
                settings = STORE.settings_public()
                if nav is None:
                    nav = Naver(log, load_selectors(STORE.selectors_override()),
                                settings.get("browser", "auto"), self.stop.is_set)
                nav.log = log
                nav.sel = load_selectors(STORE.selectors_override())
                shot = nav.post(acc, job["title"], job["html"], job["plain"], job.get("tags") or [],
                                settings.get("tagMode", "both"))
                job["status"], job["shot"] = "완료", shot
            except StopRequested:
                job["status"] = "취소"
                log("중지됨")
            except Exception as e:
                job["status"] = "실패"
                job["error"] = str(e)
                log(f"✖ {e}")
                with open(os.path.join(log_dir(), "오류상세.txt"), "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
                if nav and nav.page:
                    nav.shot("실패")
            if self.q.empty():
                self.stop.clear()
                if nav:
                    # 다음 작업을 위해 브라우저는 열어 두되, 큐가 비면 엔진 정리
                    pass

    def stop_all(self):
        self.stop.set()
        with self.lock:
            for j in self.items:
                if j["status"] == "대기":
                    j["status"] = "취소"


JOBS = Jobs()


# ------------------------------------------------------------------ 업데이트 확인
def latest_release():
    if not GITHUB_REPO:
        return None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            d = json.loads(r.read().decode())
        tag = d.get("tag_name", "").lstrip("v")
        import re
        num = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        newer = num(tag) > num(APP_VERSION)
        return {"version": tag, "url": d.get("html_url"), "newer": newer}
    except Exception:
        return None


def pick_folder() -> str:
    """운영체제 폴더 선택 창을 띄운다. 취소하면 빈 문자열."""
    prompt = "구글 드라이브의 '내 드라이브' 폴더를 골라 주세요"
    if IS_MAC:
        r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'],
                           capture_output=True, text=True)
        return r.stdout.strip()
    if IS_WIN:
        ps = ("Add-Type -AssemblyName System.Windows.Forms;"
              "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
              f"$d.Description='{prompt}';$d.ShowNewFolderButton=$true;"
              "$f=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
              "if($d.ShowDialog($f) -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;Write-Output $d.SelectedPath}")
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True,
                           text=True, encoding="utf-8", creationflags=0x08000000)
        return r.stdout.strip()
    return ""


def open_path(p):
    if IS_WIN:
        os.startfile(p)  # noqa
    elif IS_MAC:
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


# ------------------------------------------------------------------ HTTP
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/jszip.min.js": ("jszip.min.js", "application/javascript; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        h = (self.headers.get("Host") or "").split(":")[0]
        return h in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        path = self.path.split("?")[0]
        if path in STATIC:
            name, ctype = STATIC[path]
            with open(resource("web", name), "rb") as f:
                return self._send(200, f.read(), ctype)
        if path == "/api/state":
            return self._send(200, self.state())
        if path == "/api/jobs":
            LAST_PING[0] = time.time()
            return self._send(200, {"jobs": JOBS.public(), "busy": JOBS.busy()})
        if path == "/api/update":
            return self._send(200, {"release": latest_release(), "version": APP_VERSION})
        self._send(404, {"error": "not found"})

    def state(self):
        st = {"store": STORE.status(), "version": APP_VERSION, "platform": "mac" if IS_MAC else "win" if IS_WIN else "other"}
        if STORE.f:
            st["presets"] = STORE.presets_public()
            st["settings"] = STORE.settings_public()
        return st

    def do_POST(self):
        if self.path.startswith("/api/bye") and self._host_ok():   # 창 닫힘 신호 (sendBeacon)
            BYE[0] = time.time()
            return self._send(200, {})
        if not self._host_ok() or self.headers.get("X-App") != "1":
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return self._send(400, {"error": "잘못된 요청"})
        path = self.path.split("?")[0]
        try:
            res = self.route(path, body)
            self._send(200, res if res is not None else {"ok": True})
        except LockedError:
            self._send(401, {"error": "잠겨 있습니다. 동기화 비밀번호를 입력하세요."})
        except (ValueError, ai.AIError, RuntimeError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"오류: {e}"})

    def route(self, path, b):
        if path == "/api/ping":
            LAST_PING[0] = time.time()
            BYE[0] = 0.0
            return {}
        if path == "/api/setup":
            return STORE.setup(b["syncDir"], b["master"], bool(b.get("remember")))
        if path == "/api/pick-folder":
            return {"path": pick_folder()}
        if path == "/api/unlock":
            return STORE.unlock(b["master"], bool(b.get("remember")))
        if path == "/api/lock":
            STORE.lock_now(forget=True)
            return {}
        if path == "/api/preset/save":
            STORE.save_preset(b["name"], b.get("style") or {}, b.get("account"), b.get("oldName"))
            return {"presets": STORE.presets_public()}
        if path == "/api/preset/import":
            n = STORE.import_presets(b.get("data") or {}, bool(b.get("overwrite")))
            return {"count": n, "presets": STORE.presets_public()}
        if path == "/api/preset/export":
            return STORE.export_presets()
        if path == "/api/preset/delete":
            STORE.delete_preset(b["name"])
            return {"presets": STORE.presets_public()}
        if path == "/api/settings":
            STORE.save_settings(b)
            return {"settings": STORE.settings_public()}
        if path == "/api/models":
            key = b.get("key") or STORE.gemini_key()
            if not key:
                raise ValueError("API 키를 먼저 입력하세요.")
            return {"models": ai.list_models(key)}
        if path == "/api/ai":
            s = STORE.settings_public()
            return {"result": ai.generate_json(b["prompt"], STORE.gemini_key(), s.get("model") or "gemini-flash-latest")}
        if path == "/api/upload":
            if not STORE.f:
                raise LockedError()
            STORE.account(b["preset"])  # 계정 확인 (없으면 에러)
            job = JOBS.add({"preset": b["preset"], "title": b["title"], "html": b["html"], "plain": b.get("plain", ""),
                            "tags": b.get("tags") or [], "file": b.get("file", "")})
            return {"id": job["id"]}
        if path == "/api/stop":
            JOBS.stop_all()
            return {}
        if path == "/api/open":
            target = {"logs": log_dir(), "sync": STORE.sync_dir}.get(b.get("what"))
            if b.get("what") == "shot" and b.get("path") and os.path.exists(b["path"]):
                target = b["path"]
            if target:
                open_path(target)
            return {}
        raise ValueError("알 수 없는 요청")


def serve(port: int = 0) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
