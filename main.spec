# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

import PyQt6

# Do not collect DLLs from unrelated tools on the build machine's PATH.
qt_bin = Path(PyQt6.__file__).parent / 'Qt6' / 'bin'
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join(map(str, (
    qt_bin, Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs', windows / 'System32', windows,
)))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'winrt.windows.foundation.collections',
        'winrt.windows.foundation',
        'winrt.windows.storage.streams',
        'winrt.windows.media.control',
        'winrt.windows.media',
        'keyring.backends.Windows',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='WinYandexMusicRPC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    exclude_binaries=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\YMRPC_ico.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='WinYandexMusicRPC-gui',
    strip=False,
    upx=True
)
