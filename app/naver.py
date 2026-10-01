"""네이버 블로그 자동화: 계정별 로그인 → 글쓰기 → 제목/꾸민 본문 붙여넣기 → 태그 → 임시저장.

- 브라우저: PC에 설치된 Edge/Chrome을 화면에 띄워서 사용 (Playwright).
- 계정마다 별도 브라우저 프로필을 써서 로그인 상태가 계정별로 유지된다.
- 본문은 기존 웹 도구에서 '전체 복사 → 붙여넣기' 하던 것과 똑같이 HTML 클립보드 붙여넣기로 넣는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from common import IS_MAC, IS_WIN, data_dir, log_dir, resource

if IS_WIN:
    import winclip

NODE_VERSION = "v22.12.0"


class StopRequested(Exception):
    pass


def load_selectors(override: dict | None = None) -> dict:
    with open(resource("selectors.json"), encoding="utf-8") as f:
        sel = json.load(f)
    sel.update(override or {})
    return sel


def ensure_node(log):
    """exe에 브라우저 제어 엔진(node)이 없으면 공식 사이트에서 한 번 받아 둔다 (Windows 경량 빌드용)."""
    if not getattr(sys, "frozen", False) or os.environ.get("PLAYWRIGHT_NODEJS_PATH"):
        return
    exe = "node.exe" if IS_WIN else "node"
    if os.path.exists(resource("playwright", "driver", exe)):
        return
    if not IS_WIN:
        raise RuntimeError("브라우저 제어 엔진이 없습니다. 정식 배포판을 다시 받아 주세요.")
    dest = os.path.join(data_dir(), "driver", "node.exe")
    if not os.path.exists(dest):
        import ssl
        import urllib.request
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        base = f"https://nodejs.org/dist/{NODE_VERSION}/"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        log(f"처음 실행: 브라우저 제어 엔진(Node.js {NODE_VERSION}, 약 80MB)을 내려받습니다...")
        with urllib.request.urlopen(base + "SHASUMS256.txt", timeout=30, context=ctx) as r:
            sums = r.read().decode()
        expected = next(l.split()[0] for l in sums.splitlines() if l.strip().endswith("win-x64/node.exe"))
        h, tmp = hashlib.sha256(), dest + ".part"
        with urllib.request.urlopen(base + "win-x64/node.exe", timeout=60, context=ctx) as r, open(tmp, "wb") as f:
            total, done, last = int(r.headers.get("Content-Length") or 0), 0, -20
            while chunk := r.read(1 << 20):
                f.write(chunk); h.update(chunk); done += len(chunk)
                pct = int(done * 100 / total) if total else 0
                if pct >= last + 20:
                    log(f"  엔진 다운로드 {pct}%"); last = pct
        if h.hexdigest() != expected:
            os.remove(tmp)
            raise RuntimeError("엔진 파일 검증(체크섬) 실패")
        os.replace(tmp, dest)
        log("  엔진 준비 완료")
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = dest


class Naver:
    def __init__(self, log, sel: dict, browser: str = "auto", stop_flag=None):
        self.log = log
        self.sel = sel
        self.browser = browser
        self.stop_flag = stop_flag or (lambda: False)
        self.pw = None
        self.ctx = None
        self.page = None
        self.current_id = None

    # ------------------------------------------------------------ 브라우저
    def _channels(self):
        if os.environ.get("NBH_TEST_CHROMIUM"):
            return [None]
        if self.browser == "edge":
            return ["msedge", "chrome"]
        if self.browser == "chrome":
            return ["chrome", "msedge"]
        return ["msedge", "chrome"] if IS_WIN else ["chrome", "msedge"]

    def open_for(self, naver_id: str):
        """계정 전용 프로필로 브라우저를 연다(같은 계정이면 그대로 사용)."""
        if self.ctx and self.current_id == naver_id:
            return
        self.close_browser()
        if self.pw is None:
            ensure_node(self.log)
            self.pw = sync_playwright().start()
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", naver_id)
        last = None
        for ch in self._channels():
            try:
                self.ctx = self.pw.chromium.launch_persistent_context(
                    os.path.join(data_dir(), "profiles", f"{safe}-{ch}"),
                    channel=ch, headless=False, no_viewport=True, locale="ko-KR",
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                    ignore_default_args=["--enable-automation"],
                    permissions=["clipboard-read", "clipboard-write"],
                )
                self.log(f"브라우저 실행: {'Edge' if ch == 'msedge' else 'Chrome'} ({naver_id})")
                break
            except Exception as e:
                last = e
        if self.ctx is None:
            raise RuntimeError(f"Edge 또는 Chrome을 실행할 수 없습니다. 둘 중 하나를 설치해 주세요. ({last})")
        self.ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.on("dialog", lambda d: d.accept())
        self.page.set_default_timeout(15000)
        self.current_id = naver_id

    def close_browser(self):
        try:
            if self.ctx:
                self.ctx.close()
        except Exception:
            pass
        self.ctx, self.page, self.current_id = None, None, None

    def shutdown(self):
        self.close_browser()
        try:
            if self.pw:
                self.pw.stop()
        except Exception:
            pass
        self.pw = None

    def check_stop(self):
        if self.stop_flag():
            raise StopRequested()

    def shot(self, name: str) -> str | None:
        path = os.path.join(log_dir(), f"{datetime.now():%m%d_%H%M%S}_{name}.png")
        try:
            self.page.screenshot(path=path)
            self.log(f"  화면 저장: {path}")
            return path
        except Exception:
            return None

    # ------------------------------------------------------------ 도우미
    def find(self, root, key: str, timeout: float = 8.0):
        cands = self.sel[key] if isinstance(self.sel[key], list) else [self.sel[key]]
        end = time.time() + timeout
        while True:
            for c in cands:
                try:
                    loc = root.locator(c)
                    for i in range(loc.count()):
                        el = loc.nth(i)
                        if el.is_visible():
                            return el
                except Exception:
                    continue
            if time.time() > end:
                return None
            time.sleep(0.3)

    def _clipboard(self, frame, text: str, html: str | None = None):
        """클립보드에 텍스트(+HTML)를 넣는다."""
        if IS_WIN:
            winclip.set_clipboard(text, html)
            return
        frame.evaluate(
            """async ([t, h]) => {
                const items = {'text/plain': new Blob([t], {type: 'text/plain'})};
                if (h !== null) items['text/html'] = new Blob([h], {type: 'text/html'});
                await navigator.clipboard.write([new ClipboardItem(items)]);
            }""", [text, html])

    def _paste_key(self):
        self.page.keyboard.press("Meta+V" if IS_MAC else "Control+V")

    def _clear_clipboard(self, frame):
        try:
            if IS_WIN:
                winclip.clear_clipboard()
            else:
                frame.evaluate("navigator.clipboard.writeText(' ')")
        except Exception:
            pass

    # ------------------------------------------------------------ 로그인
    def logged_in_as(self) -> bool:
        return any(c["name"] == self.sel["로그인_확인_쿠키"] for c in self.ctx.cookies(self.sel.get("로그인_쿠키_주소", "https://naver.com")))

    def login(self, naver_id: str, pw: str):
        self.open_for(naver_id)
        if self.logged_in_as():
            self.log("  로그인 상태 유지 중")
            return
        self.log("  네이버 로그인 중...")
        p = self.page
        p.goto(self.sel["로그인_주소"], wait_until="domcontentloaded")
        idbox, pwbox = self.find(p, "로그인_아이디칸"), self.find(p, "로그인_비번칸")
        if not idbox or not pwbox:
            self.shot("로그인화면")
            raise RuntimeError("로그인 입력칸을 찾지 못했습니다.")
        for box, val in ((idbox, naver_id), (pwbox, pw)):
            box.click(); box.fill("")
            try:
                self._clipboard(p.main_frame, val)
                self._paste_key()
                time.sleep(0.4)
            except Exception:
                pass
            if box.input_value() != val:   # 붙여넣기가 안 먹힌 경우 (맥 등)
                box.fill(val)
                time.sleep(0.3)
        self._clear_clipboard(p.main_frame)
        keep = self.find(p, "로그인_상태유지", timeout=1)
        if keep:
            try:
                if not keep.is_checked():
                    keep.check()
            except Exception:
                pass
        btn = self.find(p, "로그인_버튼")
        (btn.click() if btn else p.keyboard.press("Enter"))
        end, warned = time.time() + 300, False
        while time.time() < end:
            self.check_stop()
            if self.logged_in_as():
                self.log("  로그인 성공")
                return
            if not warned and time.time() > end - 290:
                self.log("  ※ 자동입력 방지 문자·기기 인증 등이 뜨면 열린 브라우저에서 직접 완료해 주세요 (최대 5분 대기)")
                warned = True
            time.sleep(1)
        self.shot("로그인실패")
        raise RuntimeError("로그인하지 못했습니다. 아이디/비밀번호 또는 추가 인증을 확인하세요.")

    # ------------------------------------------------------------ 에디터
    def editor(self, blog_id: str):
        p = self.page
        p.goto(self.sel["글쓰기_주소"].format(blogId=blog_id), wait_until="domcontentloaded")
        end = time.time() + 30
        while time.time() < end:
            self.check_stop()
            frames = [f for f in p.frames if f.name == self.sel["에디터_프레임"]] + [p.main_frame]
            for f in frames:
                try:
                    if any(f.locator(c).count() for c in self.sel["제목칸"]):
                        return f
                except Exception:
                    pass
            time.sleep(0.5)
        self.shot("에디터없음")
        raise RuntimeError("글쓰기 화면을 열지 못했습니다. 블로그 주소 아이디를 확인하세요.")

    def dismiss_popups(self, fr):
        for _ in range(3):
            el = self.find(fr, "팝업_닫기", timeout=1.5)
            if not el:
                return
            try:
                el.click()
            except Exception:
                return
            time.sleep(0.5)

    def body_len(self, fr) -> int:
        for c in self.sel["본문_전체영역"]:
            try:
                if fr.locator(c).count():
                    return len(fr.locator(c).first.inner_text())
            except Exception:
                pass
        return 0

    def paste_html(self, fr, html: str, plain: str):
        before = self.body_len(fr)
        try:
            self._clipboard(fr, plain, html)
            self._paste_key()
        except Exception as e:
            self.log(f"  클립보드 사용 실패({e}) → 다른 방식 시도")
        time.sleep(1.5)
        if self.body_len(fr) > before + 5:
            return
        self.log("  클립보드 붙여넣기가 반영되지 않아 다른 방식으로 시도합니다")
        fr.evaluate(
            """([h, t]) => {
                const dt = new DataTransfer();
                dt.setData('text/html', h); dt.setData('text/plain', t);
                (document.activeElement || document.body).dispatchEvent(
                    new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""", [html, plain])
        time.sleep(1.5)
        if self.body_len(fr) > before + 5:
            return
        self.log("  다른 방식(insertHTML)으로 다시 시도합니다")
        fr.evaluate("h => document.execCommand('insertHTML', false, h)", html)
        time.sleep(1.5)
        if self.body_len(fr) > before + 5:
            return
        raise RuntimeError("본문 붙여넣기에 실패했습니다.")

    def set_tags(self, fr, tags: list[str]):
        btn = self.find(fr, "발행_버튼", timeout=5)
        if not btn:
            self.log("  ⚠ 발행 버튼을 찾지 못해 태그 등록을 건너뜁니다")
            return
        btn.click()
        box = self.find(fr, "태그_입력칸", timeout=6)
        if not box:
            self.shot("태그칸없음")
            self.log("  ⚠ 태그 입력칸을 찾지 못했습니다")
            self.page.keyboard.press("Escape")
            return
        for t in tags[:30]:
            box.click()
            self.page.keyboard.insert_text(t)
            self.page.keyboard.press("Enter")
            time.sleep(0.2)
        self.log(f"  태그 {min(len(tags), 30)}개 등록")
        close = self.find(fr, "발행창_닫기", timeout=2)
        (close.click() if close else btn.click())
        time.sleep(0.6)

    def save_draft(self, fr):
        btn = self.find(fr, "임시저장_버튼", timeout=5)
        if not btn:
            self.shot("저장버튼없음")
            raise RuntimeError("임시저장 버튼을 찾지 못했습니다.")
        btn.click()
        ok = False
        for c in self.sel["임시저장_완료문구"]:
            try:
                fr.locator(c).first.wait_for(timeout=4000)
                ok = True
                break
            except PWTimeout:
                continue
        time.sleep(1)
        self.log("  임시저장 완료" if ok else "  임시저장 버튼 누름 (완료 문구는 확인 못함)")

    # ------------------------------------------------------------ 작업 하나
    def post(self, account: dict, title: str, html: str, plain: str, tags: list[str], tag_mode: str):
        self.login(account["id"], account["pw"])
        fr = self.editor(account["blogId"])
        time.sleep(1.5)
        self.dismiss_popups(fr)
        t = self.find(fr, "제목칸")
        if not t:
            self.shot("제목칸없음")
            raise RuntimeError("제목 입력칸을 찾지 못했습니다.")
        t.click()
        self.page.keyboard.insert_text(title)
        self.log("  제목 입력")
        b = self.find(fr, "본문칸")
        if not b:
            self.shot("본문칸없음")
            raise RuntimeError("본문 입력칸을 찾지 못했습니다.")
        b.click()
        self.check_stop()
        self.paste_html(fr, html, plain)
        self.log("  꾸민 본문 붙여넣기 완료")
        if tags and tag_mode in ("both", "dialog"):
            self.set_tags(fr, tags)
        self.check_stop()
        self.save_draft(fr)
        return self.shot("완료")
