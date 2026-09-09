"""Make the bundled Qt DLL directory visible before PyQt6 is imported.

PyInstaller's stock PyQt6 runtime hook adds the temporary/application root to
PATH.  The Qt wheel used by this project keeps the actual Qt DLLs one level
deeper (``PyQt6/Qt6/bin``), so a machine without Python installed can still
fail while loading ``QtWidgets.pyd``.  This hook runs before ``main.py`` and
registers the real directory explicitly.
"""

from __future__ import annotations

import os
import sys


def _add_dll_dir(path: str) -> None:
    if not os.path.isdir(path):
        return
    try:
        os.add_dll_directory(path)
    except (AttributeError, OSError):
        # PATH is still useful on older Windows/Python combinations.
        pass
    current = os.environ.get("PATH", "")
    if path not in current.split(os.pathsep):
        os.environ["PATH"] = path + os.pathsep + current


if sys.platform.startswith("win"):
    root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    qt_bin = os.path.join(root, "PyQt6", "Qt6", "bin")
    if not os.path.isdir(qt_bin):
        qt_bin = os.path.join(root, "Qt6", "bin")
    _add_dll_dir(qt_bin)
    _add_dll_dir(root)

    qt_plugins = os.path.join(root, "PyQt6", "Qt6", "plugins")
    if os.path.isdir(qt_plugins):
        os.environ.setdefault("QT_PLUGIN_PATH", qt_plugins)
