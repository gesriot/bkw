from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ui_graph_nav_empty_and_load_real_report():
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "bkw_ui"))
    from bkw_ui_app.ui.main_window import MainWindow

    report = repo / "bkw_ui" / "projects" / "report.out"
    if not report.exists():
        pytest.skip("report.out not found for graph smoke test")

    _app()
    w = MainWindow()
    try:
        # Empty graph state should be safe.
        w._set_result_graphs([])
        w._on_graph_prev()
        w._on_graph_next()
        assert "Graph 0/0" in w.graph_title.text()

        # Real report should produce graphs.
        w.project.last_output_report = str(report)
        w._load_result_graphs()
        assert w.graph_container is not None
        assert w.graph_container.count() > 0
        assert len(w.last_bkw_tables.hugoniot) > 0 or len(w.last_bkw_tables.isentrope) > 0 or len(w.last_isp_points) > 0
    finally:
        w.close()
