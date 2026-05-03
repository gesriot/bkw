from __future__ import annotations


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

    ensure_dirs()
    app = QApplication([])
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    i18n.load_from_settings()
    w = MainWindow()
    w.show()
    return app.exec()
