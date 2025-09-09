# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller配置文件 - 岭南师范学院教务管理助手
用于将Python应用程序打包成独立的exe文件
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 获取项目根目录
project_root = os.path.dirname(os.path.abspath(SPEC))

# 主程序入口
main_script = os.path.join(project_root, 'main.py')

# 收集所有需要的数据文件
datas = []

# 添加配置文件示例
config_example = os.path.join(project_root, 'config.ini.example')
if os.path.exists(config_example):
    datas.append((config_example, '.'))

# 添加UI资源文件（如果存在）
ui_assets_dir = os.path.join(project_root, 'ui', 'assets')
if os.path.exists(ui_assets_dir):
    for root, dirs, files in os.walk(ui_assets_dir):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, project_root)
            datas.append((file_path, os.path.dirname(rel_path)))

# 收集PyQt6相关的隐藏导入
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui', 
    'PyQt6.QtWidgets',
    'PyQt6.QtNetwork',
    'requests',
    'pyquery',
    'rsa',
    'Crypto',
    'Crypto.Cipher',
    'Crypto.PublicKey',
    'Crypto.Hash',
    'Crypto.Signature',
]

# 收集所有子模块
hiddenimports.extend(collect_submodules('ui'))
hiddenimports.extend(collect_submodules('core'))
hiddenimports.extend(collect_submodules('api'))
hiddenimports.extend(collect_submodules('utils'))

# 分析阶段配置
a = Analysis(
    [main_script],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 去除重复的二进制文件
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 创建可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='岭南师范学院教务管理助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 设置为False隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'ui', 'assets', 'icon.ico') if os.path.exists(os.path.join(project_root, 'ui', 'assets', 'icon.ico')) else None,
    version_file=None,
)

# 如果需要创建目录分发版本，取消注释以下代码
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='ZFN_Assistant'
# )