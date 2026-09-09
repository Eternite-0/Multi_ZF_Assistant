#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
岭南师范学院教务管理助手
主程序入口文件

Author: Developer
License: MIT
"""

import sys
import os
from typing import NoReturn


def _prepare_qt_runtime() -> None:
    """Make bundled Qt and VC runtime DLLs discoverable before PyQt imports.

    PyInstaller/Nuitka layouts differ (some use ``_internal`` and some keep
    Qt under ``PyQt6/Qt6/bin``).  Register every relevant location before the
    first ``QtWidgets`` import so Windows does not fall back to an unrelated
    system DLL.
    """
    if not sys.platform.startswith("win"):
        return

    roots = {
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(sys.executable),
        getattr(sys, "_MEIPASS", ""),
    }
    candidates = set()
    for root in roots:
        if not root:
            continue
        candidates.update(
            {
                root,
                os.path.join(root, "_internal"),
                os.path.join(root, "PyQt6"),
                os.path.join(root, "PyQt6", "Qt6", "bin"),
                os.path.join(root, "PyQt6", "Qt6", "plugins"),
                os.path.join(root, "_internal", "PyQt6"),
                os.path.join(root, "_internal", "PyQt6", "Qt6", "bin"),
                os.path.join(root, "_internal", "PyQt6", "Qt6", "plugins"),
            }
        )

    dll_dirs = []
    plugin_dirs = []
    for path in candidates:
        if not os.path.isdir(path):
            continue
        if path.endswith(os.path.join("Qt6", "plugins")):
            plugin_dirs.append(path)
        else:
            dll_dirs.append(path)
            try:
                os.add_dll_directory(path)
            except (AttributeError, OSError):
                pass

    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(dll_dirs + [current_path])
    if plugin_dirs:
        os.environ.setdefault("QT_PLUGIN_PATH", plugin_dirs[0])


_prepare_qt_runtime()
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import ZFN_GUI


def setup_application() -> QApplication:
    """
    设置应用程序基本配置
    
    Returns:
        QApplication: 配置好的应用程序实例
    """
    app = QApplication(sys.argv)
    
    # 设置应用程序基本信息
    app.setApplicationName("岭南师范学院教务管理助手")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ZFN Assistant")
    
    # PyQt6中高DPI支持默认启用，无需额外设置
    
    # 设置应用程序图标（如果存在）
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    return app


def main() -> NoReturn:
    """
    应用程序主入口函数
    
    初始化应用程序并启动主窗口
    """
    try:
        # 创建应用程序实例
        app = setup_application()

        # 创建主窗口
        window = ZFN_GUI()
        window.show()
        
        # 启动事件循环
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"应用程序启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
