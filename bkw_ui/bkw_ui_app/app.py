from __future__ import annotations

import json
import traceback
from pathlib import Path


def run() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        print("PySide6 is not installed. Install requirements first:")
        print("  python -m pip install -r bkw_ui/requirements.txt")
        return 2

    from .i18n import i18n
    from .paths import APP_NAME, ensure_dirs
    from .ui.main_window import MainWindow

    ensure_dirs()
    app = QApplication([])
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    i18n.load_from_settings()
    w = MainWindow()
    w.show()
    return app.exec()
