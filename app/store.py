"""프리셋·계정·설정 저장소.

구글 드라이브 폴더 안의 NaverBlogHelper/data.json 하나를 윈도우·맥이 같이 쓴다.
- 비밀번호와 API 키는 '동기화 비밀번호'로 암호화(PBKDF2 + Fernet)해서 저장.
- 저장할 때마다 파일을 다시 읽어 프리셋 단위로 최신 것을 합친다(두 컴퓨터가 번갈아 써도 안전).
"""
from __future__ import annotations

import base64
import glob
import json
import os
import string
import threading
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import secret
from common import IS_MAC, IS_WIN, data_dir

SYNC_FOLDER_NAME = "NaverBlogHelper"
DATA_FILE = "data.json"
LOCAL_FILE = os.path.join(data_dir(), "local.json")

# 기존 웹 도구의 스타일 필드
STYLE_FIELDS = ["mode", "bs", "lh", "ba", "hs", "hb", "st", "kc", "kc2", "use2", "hl", "qs", "qon",
                "qch", "deco", "kw", "swid", "note", "memo"]


def now() -> float:
    return time.time()


def google_drive_candidates() -> list[str]:
    """설치된 구글 드라이브의 '내 드라이브' 폴더 후보."""
    names = ["My Drive", "내 드라이브"]
    out = []
    if IS_WIN:
        for letter in string.ascii_uppercase[3:]:
            for n in names:
                p = f"{letter}:\\{n}"
                if os.path.isdir(p):
                    out.append(p)
        home = os.path.expanduser("~")
        for p in [os.path.join(home, "Google Drive"), os.path.join(home, "Google Drive", "My Drive")]:
            if os.path.isdir(p):
                out.append(p)
    elif IS_MAC:
        for n in names:
            out += glob.glob(os.path.expanduser(f"~/Library/CloudStorage/GoogleDrive-*/{n}"))
            if os.path.isdir(f"/Volumes/GoogleDrive/{n}"):
                out.append(f"/Volumes/GoogleDrive/{n}")
        if os.path.isdir(os.path.expanduser("~/Google Drive")):
            out.append(os.path.expanduser("~/Google Drive"))
    return out


def _key(master: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(master.encode("utf-8"))))


class LockedError(Exception):
    pass


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.local = self._read_local()
        self.f: Fernet | None = None
        self.data: dict | None = None
        self.mtime = 0.0

    # ---------------------------------------------------------- 로컬 설정
    def _read_local(self) -> dict:
        try:
            with open(LOCAL_FILE, encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}

    def _write_local(self):
        with open(LOCAL_FILE, "w", encoding="utf-8") as fp:
            json.dump(self.local, fp, ensure_ascii=False, indent=1)

    @property
    def sync_dir(self) -> str | None:
        d = self.local.get("syncDir")
        if d and ("://" in d or "https:" in d or "http:" in d):
            return None
        return d

    @property
    def path(self) -> str | None:
        return os.path.join(self.sync_dir, DATA_FILE) if self.sync_dir else None

    def status(self) -> dict:
        exists = bool(self.path and os.path.exists(self.path))
        return {
            "syncDir": self.sync_dir,
            "fileExists": exists,
            "unlocked": self.f is not None,
            "candidates": [os.path.join(c, SYNC_FOLDER_NAME) for c in google_drive_candidates()],
        }

    # ---------------------------------------------------------- 파일 입출력
    def _read_file(self) -> dict:
        with open(self.path, encoding="utf-8") as fp:
            return json.load(fp)

    def _write_file(self, d: dict):
        os.makedirs(self.sync_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(d, fp, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
        self.mtime = os.path.getmtime(self.path)

    def refresh(self):
        """다른 컴퓨터에서 바뀐 내용이 있으면 다시 읽는다."""
        with self.lock:
            if not self.f or not self.path or not os.path.exists(self.path):
                return
            m = os.path.getmtime(self.path)
            if m != self.mtime:
                self.data = self._read_file()
                self.mtime = m

    def _merge_write(self, mutate):
        """파일을 새로 읽어 합친 뒤 변경을 적용하고 저장."""
        with self.lock:
            if not self.f:
                raise LockedError()
            disk = self._read_file() if os.path.exists(self.path) else self.data
            mine = self.data or disk
            # 프리셋 단위 최신값 우선 병합
            merged_p = dict(disk.get("presets", {}))
            for k, v in mine.get("presets", {}).items():
                if k not in merged_p or v.get("updatedAt", 0) > merged_p[k].get("updatedAt", 0):
                    merged_p[k] = v
            deleted = {**disk.get("deleted", {}), **mine.get("deleted", {})}
            for k, t in deleted.items():
                if k in merged_p and merged_p[k].get("updatedAt", 0) <= t:
                    del merged_p[k]
            st_d, st_m = disk.get("settings", {}), mine.get("settings", {})
            settings = st_m if st_m.get("updatedAt", 0) >= st_d.get("updatedAt", 0) else st_d
            d = {**disk, "presets": merged_p, "deleted": deleted, "settings": settings}
            mutate(d)
            self._write_file(d)
            self.data = d

    # ---------------------------------------------------------- 시작/잠금해제
    def setup(self, sync_dir: str, master: str, remember: bool) -> dict:
        """동기화 폴더 지정. 파일이 있으면 잠금해제, 없으면 새로 만든다."""
        with self.lock:
            sync_dir = self.check_folder(sync_dir)
            self.local["syncDir"] = sync_dir
            self._write_local()
            if os.path.exists(self.path):
                return self.unlock(master, remember)
            if len(master) < 4:
                raise ValueError("동기화 비밀번호는 4자 이상으로 정해 주세요.")
            salt = os.urandom(16)
            f = _key(master, salt)
            d = {"format": 1, "salt": base64.b64encode(salt).decode(),
                 "check": f.encrypt(b"ok").decode(), "presets": {}, "deleted": {},
                 "settings": {"model": "gemini-flash-latest", "updatedAt": now()}}
            self._write_file(d)
            self.f, self.data = f, d
            if remember:
                secret.remember(master)
            return self.status()

    @staticmethod
    def check_folder(raw: str) -> str:
        """입력한 동기화 폴더가 '컴퓨터 안의 폴더'인지 확인하고, 필요하면 NaverBlogHelper 하위 폴더를 붙인다."""
        raw = (raw or "").strip().strip('"').strip("'")
        if not raw:
            raise ValueError("동기화 폴더를 정해 주세요.")
        if "://" in raw or raw.lower().startswith(("http", "www.", "drive.google")):
            raise ValueError("구글 드라이브 웹 주소가 아니라, 내 컴퓨터 안의 구글 드라이브 폴더가 필요해요. "
                             "구글 드라이브 데스크톱 앱을 설치하면 생기는 '내 드라이브' 폴더를 [폴더 선택]으로 골라 주세요.")
        path = os.path.abspath(os.path.expanduser(raw))
        if os.path.basename(path.rstrip("/\\")) != SYNC_FOLDER_NAME and not os.path.exists(os.path.join(path, DATA_FILE)):
            path = os.path.join(path, SYNC_FOLDER_NAME)
        parent = os.path.dirname(path)
        if not os.path.isdir(path) and not os.path.isdir(parent):
            raise ValueError(f"폴더를 찾을 수 없어요: {parent}")
        try:
            os.makedirs(path, exist_ok=True)
            test = os.path.join(path, ".write_test")
            with open(test, "w") as fp:
                fp.write("ok")
            os.remove(test)
        except OSError as e:
            raise ValueError(f"이 폴더에 저장할 수 없어요 ({e.strerror}): {path}")
        return path

    def unlock(self, master: str, remember: bool) -> dict:
        with self.lock:
            d = self._read_file()
            f = _key(master, base64.b64decode(d["salt"]))
            try:
                f.decrypt(d["check"].encode())
            except InvalidToken:
                raise ValueError("동기화 비밀번호가 맞지 않습니다.")
            self.f, self.data = f, d
            self.mtime = os.path.getmtime(self.path)
            if remember:
                secret.remember(master)
            return self.status()

    def try_auto_unlock(self) -> bool:
        if not self.path or not os.path.exists(self.path):
            return False
        m = secret.recall()
        if not m:
            return False
        try:
            self.unlock(m, False)
            return True
        except Exception:
            return False

    def lock_now(self, forget: bool = False):
        with self.lock:
            self.f, self.data = None, None
            if forget:
                secret.forget()

    # ---------------------------------------------------------- 암호화 도우미
    def enc(self, s: str) -> str:
        return self.f.encrypt(s.encode("utf-8")).decode()

    def dec(self, s: str) -> str:
        return self.f.decrypt(s.encode()).decode("utf-8")

    # ---------------------------------------------------------- 프리셋
    def presets_public(self) -> dict:
        self.refresh()
        out = {}
        for name, p in (self.data or {}).get("presets", {}).items():
            acc = p.get("account") or {}
            out[name] = {**{k: v for k, v in p.items() if k != "account"},
                         "account": {"id": acc.get("id", ""), "blogId": acc.get("blogId", ""),
                                     "hasPw": bool(acc.get("pw"))}}
        return out

    def save_preset(self, name: str, style: dict, account: dict | None, old_name: str | None = None):
        name = name.strip()
        if not name:
            raise ValueError("업체 이름을 입력하세요.")

        def m(d):
            presets = d.setdefault("presets", {})
            prev = presets.get(old_name or name) or presets.get(name) or {}
            acc = dict(prev.get("account") or {})
            if account is not None:
                acc["id"] = (account.get("id") or "").strip()
                acc["blogId"] = (account.get("blogId") or "").strip()
                if account.get("pw"):
                    acc["pw"] = self.enc(account["pw"])
                elif account.get("clearPw"):
                    acc.pop("pw", None)
            p = {**{k: style.get(k) for k in STYLE_FIELDS if k in style}, "account": acc, "updatedAt": now()}
            if old_name and old_name != name and old_name in presets:
                del presets[old_name]
                d.setdefault("deleted", {})[old_name] = now()
            presets[name] = p
            d.get("deleted", {}).pop(name, None)

        self._merge_write(m)

    def import_presets(self, raw: dict, overwrite: bool) -> int:
        """프리셋 파일(JSON) 가져오기. 기존 웹 도구 형식({"map": {...}})과 이 프로그램의 내보내기 형식 모두 지원.
        계정 정보는 파일에 넣지 않으며, 이미 저장된 계정은 그대로 유지한다."""
        src = raw.get("map") if isinstance(raw.get("map"), dict) else raw.get("presets") if isinstance(raw.get("presets"), dict) else raw
        items = {str(k).strip(): v for k, v in src.items() if isinstance(v, dict) and str(k).strip()}
        if not items:
            raise ValueError("파일에서 프리셋을 찾지 못했습니다.")
        count = [0]

        def m(d):
            presets = d.setdefault("presets", {})
            for name, p in items.items():
                if name in presets and not overwrite:
                    continue
                prev = presets.get(name) or {}
                presets[name] = {**{k: p.get(k) for k in STYLE_FIELDS if k in p},
                                 "account": prev.get("account") or {}, "updatedAt": now()}
                d.get("deleted", {}).pop(name, None)
                count[0] += 1
        self._merge_write(m)
        return count[0]

    def export_presets(self) -> dict:
        """계정 정보를 뺀 프리셋(스타일·특이사항·메모)만 내보내기."""
        self.refresh()
        return {"format": "blog-auto-draft-presets", "map": {
            n: {k: p.get(k) for k in STYLE_FIELDS if k in p} for n, p in (self.data or {}).get("presets", {}).items()}}

    def delete_preset(self, name: str):
        def m(d):
            d.get("presets", {}).pop(name, None)
            d.setdefault("deleted", {})[name] = now()
        self._merge_write(m)

    def account(self, name: str) -> dict:
        self.refresh()
        p = (self.data or {}).get("presets", {}).get(name)
        if not p:
            raise ValueError(f"프리셋 '{name}'이 없습니다.")
        acc = p.get("account") or {}
        if not acc.get("id") or not acc.get("pw"):
            raise ValueError(f"'{name}' 프리셋에 네이버 아이디/비밀번호가 저장되어 있지 않습니다.")
        return {"id": acc["id"], "pw": self.dec(acc["pw"]), "blogId": acc.get("blogId") or acc["id"]}

    # ---------------------------------------------------------- 설정
    def settings_public(self) -> dict:
        self.refresh()
        s = (self.data or {}).get("settings", {})
        return {"model": s.get("model", "gemini-flash-latest"), "hasGeminiKey": bool(s.get("geminiKey")),
                "browser": s.get("browser", "auto"), "previewBeforeUpload": s.get("previewBeforeUpload", False),
                "tagMode": s.get("tagMode", "both")}

    def gemini_key(self) -> str | None:
        self.refresh()
        k = (self.data or {}).get("settings", {}).get("geminiKey")
        return self.dec(k) if k else None

    def save_settings(self, upd: dict):
        def m(d):
            s = dict(d.get("settings", {}))
            if upd.get("geminiKey"):
                s["geminiKey"] = self.enc(upd["geminiKey"].strip())
            for k in ("model", "browser", "previewBeforeUpload", "tagMode"):
                if k in upd:
                    s[k] = upd[k]
            s["updatedAt"] = now()
            d["settings"] = s
        self._merge_write(m)

    def selectors_override(self) -> dict:
        """동기화 폴더에 selectors.json이 있으면 기본 선택자 위에 덮어쓴다 (수정 사항이 두 컴퓨터에 공유됨)."""
        try:
            with open(os.path.join(self.sync_dir, "selectors.json"), encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}
