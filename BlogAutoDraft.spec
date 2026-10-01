# -*- mode: python ; coding: utf-8 -*-
# 윈도우·맥 공통 빌드 설정:  pyinstaller BlogAutoDraft.spec
import os, sys
from PyInstaller.utils.hooks import collect_all

datas = [('app/web', 'web'), ('app/selectors.json', '.')]
binaries, hiddenimports = [], ['cryptography', 'certifi']
d, b, h = collect_all('playwright')
datas += d; binaries += b; hiddenimports += h

a = Analysis(['app/main.py'], pathex=['app'], binaries=binaries, datas=datas, hiddenimports=hiddenimports)
if os.environ.get('NBH_EXCLUDE_NODE'):   # 용량 줄인 윈도우 빌드: node.exe는 첫 실행 때 내려받음
    _skip = lambda e: any(str(p).lower().endswith('node.exe') for p in e[:2])
    a.binaries = [e for e in a.binaries if not _skip(e)]
    a.datas = [e for e in a.datas if not _skip(e)]
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BlogAutoDraft', console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name='BlogAutoDraft')
    app = BUNDLE(coll, name='블로그 자동 임시저장.app', bundle_identifier='com.blogautodraft.app',
                 info_plist={'CFBundleShortVersionString': os.environ.get('NBH_VERSION', '1.0.0'),
                             'NSHighResolutionCapable': True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='BlogAutoDraft', console=False, upx=False)
