#!/bin/bash
# 블로그 자동 임시저장 (맥) - 더블클릭해서 실행
# 처음 한 번: 이 프로그램 전용 파이썬 실행 환경을 내려받아 준비합니다 (1~3분).
# 그다음부터는 바로 실행됩니다. 이 터미널 창은 프로그램이 도는 동안 닫지 마세요 (최소화는 괜찮아요).
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"

RT="${NBH_RUNTIME:-$HOME/Library/Application Support/NaverBlogHelper/runtime}"
PYVER=3.12.7
PYTAG=20241016
case "${NBH_TARGET:-$(uname -m)}" in
  arm64|aarch64) TARGET=aarch64-apple-darwin ;;
  x86_64)        TARGET=x86_64-apple-darwin ;;
  *)             TARGET="${NBH_TARGET}" ;;
esac
PY="$RT/python/bin/python3"

echo "=============================================="
echo "  블로그 자동 임시저장"
echo "=============================================="

if [ ! -x "$PY" ]; then
  echo "처음 실행: 실행 환경을 준비합니다 (한 번만, 1~3분 걸려요)..."
  mkdir -p "$RT"
  URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTAG}/cpython-${PYVER}+${PYTAG}-${TARGET}-install_only.tar.gz"
  curl -fL --progress-bar -o "$RT/python.tar.gz" "$URL"
  rm -rf "$RT/python"
  tar xzf "$RT/python.tar.gz" -C "$RT"
  rm -f "$RT/python.tar.gz"
fi

# 필요한 부품 설치 (requirements가 바뀌었을 때만 다시 설치)
STAMP="$RT/.installed-$(shasum "$HERE/requirements-mac.txt" | cut -c1-12)"
if [ ! -f "$STAMP" ]; then
  echo "필요한 부품을 설치합니다..."
  "$PY" -m pip install --disable-pip-version-check -q --upgrade -r "$HERE/requirements-mac.txt"
  rm -f "$RT"/.installed-*
  touch "$STAMP"
fi

if [ ! -d "/Applications/Google Chrome.app" ] && [ ! -d "$HOME/Applications/Google Chrome.app" ] && [ ! -d "/Applications/Microsoft Edge.app" ]; then
  echo ""
  echo "※ 네이버 작업에는 Google Chrome(또는 Microsoft Edge)이 필요해요."
  echo "   https://www.google.com/chrome/ 에서 설치한 뒤 다시 실행해 주세요."
  echo ""
fi

echo "프로그램을 엽니다. (이 창은 닫지 마세요)"
exec "$PY" "$HERE/app/main.py"
