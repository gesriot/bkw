from __future__ import annotations

import sys
from pathlib import Path


WINDOWS_APP_ID = "BKW.BKW"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


def _find_icon_path() -> Path | None:
    here = Path(__file__).resolve()
    exe_dir = Path(sys.executable).resolve().parent
    bundle_dir = Path(getattr(sys, "_MEIPASS", exe_dir))
    candidates = [
        exe_dir / "icon.png",
        bundle_dir / "icon.png",
        here.parents[2] / "icon.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_window_icon():
    try:
        from PySide6.QtGui import QIcon
    except Exception:
        return None

    icon_path = _find_icon_path()
    if icon_path is None:
        return None
    icon = QIcon(str(icon_path))
    return None if icon.isNull() else icon


def run() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        print("PySide6 is not installed. Install project dependencies first:")
        print("  uv sync")
        print("or:")
        print("  pip install -e .")
        return 2

    from .i18n import i18n
    from .paths import APP_NAME, ensure_dirs
    from .ui.main_window import MainWindow

    _set_windows_app_id()
    ensure_dirs()
    app = QApplication([])
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    icon = _load_window_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    i18n.load_from_settings()
    w = MainWindow()
    if icon is not None:
        w.setWindowIcon(icon)
    w.show()
    return app.exec()
