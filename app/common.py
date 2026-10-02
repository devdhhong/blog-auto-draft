"""공통 경로/버전 정보."""
from __future__ import annotations

import os
import sys

APP_NAME = "블로그 자동 임시저장"
APP_ID = "NaverBlogHelper"
APP_VERSION = "1.0.2"
# GitHub 저장소 (owner/repo). 새 버전 알림에 사용. 비워두면 확인하지 않음.
try:  # 빌드할 때 GitHub Actions가 만들어 넣는 파일
    from _build_info import REPO as _REPO, VERSION as _VER
    APP_VERSION = _VER or APP_VERSION
except ImportError:
    _REPO = ""
GITHUB_REPO = os.environ.get("NBH_REPO", _REPO)

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def resource(*parts: str) -> str:
    """프로그램에 함께 묶인 파일 경로 (PyInstaller 대응)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def data_dir() -> str:
    """이 컴퓨터 전용 데이터 폴더 (브라우저 프로필, 로그, 로컬 설정)."""
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    p = os.path.join(base, APP_ID)
    os.makedirs(p, exist_ok=True)
    return p


def log_dir() -> str:
    p = os.path.join(data_dir(), "logs")
    os.makedirs(p, exist_ok=True)
    return p
