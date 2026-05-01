from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QTableWidgetItem
from bkw_py.io.bkwdata import load_bkwdata


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_until(app: QApplication, cond, timeout_sec: float = 90.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_ui_e2e_smoke_bkw_generate_run_export(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    ui_root = repo / "bkw_ui"
    sys.path.insert(0, str(ui_root))

    from bkw_ui_app.ui.main_window import MainWindow

    out_dir = Path(tempfile.mkdtemp(prefix="ui_e2e_", dir=str(repo)))
    out_bkwdata = out_dir / "BKWDATA.ui"
    out_report = out_dir / "bkw.ui.out"
    out_export = out_dir / "exports"
    out_export.mkdir(parents=True, exist_ok=True)

    app = _app()
    w = MainWindow()
    try:
        # Avoid blocking modal dialogs in test.
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out_export))

        # Project source/template.
        w.source_mode_combo.setCurrentText("template")
        if w.template_combo.findText("CHNO") >= 0:
            w.template_combo.setCurrentText("CHNO")

        # Mix setup required for template flow.
        w.mix_table.setRowCount(0)
        w.mix_table.insertRow(0)
        w.mix_table.setItem(0, 0, QTableWidgetItem("rdx"))
        w.mix_table.setItem(0, 1, QTableWidgetItem("100"))
        w._on_mix_apply()
        assert w.project.mix, "mix should be accepted"

        # Species/legacy sync (defaults).
        w._on_species_apply()

        # Output paths.
        w.export_bkwdata.setText(str(out_bkwdata))
        w.export_report.setText(str(out_report))

        # Generate BKWDATA.
        w._on_generate_bkwdata()
        assert out_bkwdata.exists(), "BKWDATA should be generated"
        assert Path(w.project.last_output_bkwdata).exists()

        # Run BKW.
        w.mode_combo.setCurrentText("bkw")
        w._on_run_calc()
        ok = _wait_until(app, lambda: w.btn_run.isEnabled(), timeout_sec=120.0)
        assert ok, "calculation did not finish in time"
        assert out_report.exists(), "report should be generated"
        assert "завершен" in w.calc_status.text().lower()

        # Graphs/text should be loaded after run.
        if w.graph_container is not None:
            assert w.graph_container.count() >= 1
        assert len(w.result_text.toPlainText()) > 0

        # Export CSV and PNG.
        w._on_export_csv()
        csv_files = list(out_export.glob("*.csv"))
        assert csv_files, "CSV export should produce files"

        if w.graph_container is not None and w.graph_container.count() > 0:
            w._on_export_png()
            png_files = list(out_export.glob("*.png"))
            assert png_files, "PNG export should produce files when graphs are available"
    finally:
        w.close()


def test_ui_e2e_smoke_isp_generate_run_export(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    ui_root = repo / "bkw_ui"
    sys.path.insert(0, str(ui_root))

    from bkw_ui_app.ui.main_window import MainWindow

    out_dir = Path(tempfile.mkdtemp(prefix="ui_e2e_isp_", dir=str(repo)))
    out_bkwdata = out_dir / "BKWDATA.ui.isp"
    out_report = out_dir / "isp.ui.out"
    out_export = out_dir / "exports"
    out_export.mkdir(parents=True, exist_ok=True)

    app = _app()
    w = MainWindow()
    try:
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out_export))

        w.source_mode_combo.setCurrentText("template")
        if w.template_combo.findText("CHNO") >= 0:
            w.template_combo.setCurrentText("CHNO")

        w.mix_table.setRowCount(0)
        w.mix_table.insertRow(0)
        w.mix_table.setItem(0, 0, QTableWidgetItem("rdx"))
        w.mix_table.setItem(0, 1, QTableWidgetItem("100"))
        w._on_mix_apply()
        assert w.project.mix

        w._on_species_apply()
        w.export_bkwdata.setText(str(out_bkwdata))
        w.export_report.setText(str(out_report))

        w._on_generate_bkwdata()
        assert out_bkwdata.exists()
        assert Path(w.project.last_output_bkwdata).exists()

        w.mode_combo.setCurrentText("isp")
        w._on_run_calc()
        ok = _wait_until(app, lambda: w.btn_run.isEnabled(), timeout_sec=120.0)
        assert ok, "isp calculation did not finish in time"
        assert out_report.exists()
        assert "завершен" in w.calc_status.text().lower()

        if w.graph_container is not None:
            assert w.graph_container.count() >= 1
        assert len(w.result_text.toPlainText()) > 0

        w._on_export_csv()
        csv_files = list(out_export.glob("*.csv"))
        assert any("isp_summary" in x.name for x in csv_files), "isp_summary.csv expected"
    finally:
        w.close()


def test_ui_e2e_smoke_import_bkwdata_run_export(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    ui_root = repo / "bkw_ui"
    sys.path.insert(0, str(ui_root))

    from bkw_ui_app.ui.main_window import MainWindow

    out_dir = Path(tempfile.mkdtemp(prefix="ui_e2e_import_", dir=str(repo)))
    src_bkwdata = out_dir / "BKWDATA.src"
    out_report = out_dir / "bkw.import.out"
    out_export = out_dir / "exports"
    out_export.mkdir(parents=True, exist_ok=True)

    # Prepare source BKWDATA via CLI (same data path as real workflow).
    cp = __import__("subprocess").run(
        [
            sys.executable,
            str(repo / "bkw_py" / "userbkw.py"),
            "--template",
            "CHNO",
            "--mix",
            "rdx=100",
            "--output",
            str(src_bkwdata),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
    assert src_bkwdata.exists()

    app = _app()
    w = MainWindow()
    try:
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out_export))

        # Import mode should allow run flow without filling mix table.
        w.source_mode_combo.setCurrentText("import")
        w.input_bkwdata_edit.setText(str(src_bkwdata))
        w.project.source_mode = "import"
        w.project.source_bkwdata = str(src_bkwdata)
        w._refresh_flow_state()

        # Ensure output report goes to isolated folder.
        w.export_report.setText(str(out_report))
        w.project.last_output_bkwdata = str(src_bkwdata)
        w.mode_combo.setCurrentText("bkw")
        w._on_run_calc()

        ok = _wait_until(app, lambda: w.btn_run.isEnabled(), timeout_sec=120.0)
        assert ok, "import/bkw calculation did not finish in time"
        assert out_report.exists()
        assert "завершен" in w.calc_status.text().lower()

        # Export tables after run.
        w._on_export_csv()
        csv_files = list(out_export.glob("*.csv"))
        assert csv_files, "CSV export should produce files in import flow"
    finally:
        w.close()


def test_ui_e2e_corner_custom_species_solids_legacy(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    ui_root = repo / "bkw_ui"
    sys.path.insert(0, str(ui_root))

    from bkw_ui_app.ui.main_window import MainWindow

    out_dir = Path(tempfile.mkdtemp(prefix="ui_e2e_corner1_", dir=str(repo)))
    out_bkwdata = out_dir / "BKWDATA.corner1"
    out_report = out_dir / "bkw.corner1.out"

    app = _app()
    w = MainWindow()
    try:
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

        w.source_mode_combo.setCurrentText("template")
        if w.template_combo.findText("CHNO") >= 0:
            w.template_combo.setCurrentText("CHNO")

        w.mix_table.setRowCount(0)
        w.mix_table.insertRow(0)
        w.mix_table.setItem(0, 0, QTableWidgetItem("rdx"))
        w.mix_table.setItem(0, 1, QTableWidgetItem("80"))
        w.mix_table.insertRow(1)
        w.mix_table.setItem(1, 0, QTableWidgetItem("tnt"))
        w.mix_table.setItem(1, 1, QTableWidgetItem("20"))
        w._on_mix_apply()
        assert len(w.project.mix) == 2

        w.gas_custom_edit.setPlainText(
            "xg1|1,1,1,1,1,1,1,1|c=1,o=1"
        )
        w.solid_custom_edit.setPlainText(
            "xs1|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|c=1\n"
            "xs2|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|o=1"
        )

        w.legacy_ipvc_combo.setCurrentIndex(w.legacy_ipvc_combo.findData(2))
        w.legacy_igrp_combo.setCurrentIndex(w.legacy_igrp_combo.findData(2))
        w.legacy_eos_preset_combo.setCurrentText("rdx")
        w.legacy_athrho_edit.setText("1.70, 1.85")
        w.legacy_aispr_edit.setText("0.45")
        w.legacy_constants_edit.setPlainText("29=1.25\n1=-1")
        w.legacy_twins_edit.setPlainText("xs1=tb1\nxs2=tb2")
        w._on_species_apply()

        w.export_bkwdata.setText(str(out_bkwdata))
        w.export_report.setText(str(out_report))
        w._on_generate_bkwdata()
        assert out_bkwdata.exists()

        d = load_bkwdata(out_bkwdata)
        names = [x.strip().lower() for x in d.nam]
        solid_twins = [x.strip().lower() for x in d.nams]
        assert "xg1" in names
        assert "xs1" in names and "xs2" in names
        assert "tb1" in solid_twins and "tb2" in solid_twins
        assert d.ipvc == 2
        assert d.igrp == 2
        assert d.iext >= 1 and 29 in d.novar
        assert abs(d.aispr - 0.45) < 1e-12
        assert d.irho == 2
        assert len(d.athrho) == 2

        w.mode_combo.setCurrentText("bkw")
        w._on_run_calc()
        ok = _wait_until(app, lambda: w.btn_run.isEnabled(), timeout_sec=120.0)
        assert ok, "corner1 bkw did not finish"
        assert out_report.exists()
    finally:
        w.close()


def test_ui_e2e_corner_many_solids_with_legacy(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    ui_root = repo / "bkw_ui"
    sys.path.insert(0, str(ui_root))

    from bkw_ui_app.ui.main_window import MainWindow

    out_dir = Path(tempfile.mkdtemp(prefix="ui_e2e_corner2_", dir=str(repo)))
    out_bkwdata = out_dir / "BKWDATA.corner2"

    w = MainWindow()
    try:
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)

        w.source_mode_combo.setCurrentText("template")
        if w.template_combo.findText("CHNO") >= 0:
            w.template_combo.setCurrentText("CHNO")

        w.mix_table.setRowCount(0)
        w.mix_table.insertRow(0)
        w.mix_table.setItem(0, 0, QTableWidgetItem("rdx"))
        w.mix_table.setItem(0, 1, QTableWidgetItem("100"))
        w._on_mix_apply()
        assert w.project.mix

        w.solid_custom_edit.setPlainText(
            "s01|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|c=1\n"
            "s02|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|o=1\n"
            "s03|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|n=1\n"
            "s04|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|h=1"
        )
        w.legacy_constants_edit.setPlainText("29=1.2")
        w.legacy_twins_edit.setPlainText("s01=t01\ns02=t02\ns03=t03\ns04=t04")
        w._on_species_apply()

        w.export_bkwdata.setText(str(out_bkwdata))
        w._on_generate_bkwdata()
        assert out_bkwdata.exists()

        d = load_bkwdata(out_bkwdata)
        # CHNO template already has one solid; +4 custom should stay within nsf<=5.
        assert d.nsf <= 5
        names = [x.strip().lower() for x in d.nam]
        assert "s01" in names and "s04" in names
        twins = [x.strip().lower() for x in d.nams]
        assert "t01" in twins and "t04" in twins
        assert 29 in d.novar
    finally:
        w.close()
