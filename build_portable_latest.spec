# -*- mode: python ; coding: utf-8 -*-
"""Reliable onedir build: keep PyQt6/Qt6 DLLs beside the executable."""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = os.path.dirname(os.path.abspath(SPEC))
main_script = os.path.join(project_root, "main.py")

pyqt_datas, pyqt_binaries, pyqt_hiddenimports = collect_all("PyQt6")
datas = list(pyqt_datas)
config_example = os.path.join(project_root, "config.ini.example")
if os.path.exists(config_example):
    datas.append((config_example, "."))

hiddenimports = [
    "requests",
    "pyquery",
    "rsa",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
]
hiddenimports.extend(pyqt_hiddenimports)
for package in ("ui", "core", "api", "utils"):
    hiddenimports.extend(collect_submodules(package))

a = Analysis(
    [main_script],
    pathex=[project_root],
    binaries=pyqt_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(project_root, "pyinstaller_qt_runtime.py")],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2"],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="岭南师范学院教务管理助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="岭南师范学院教务管理助手-文件夹版",
)
