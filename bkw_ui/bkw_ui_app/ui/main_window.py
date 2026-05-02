from __future__ import annotations

import contextlib
import csv
import io
import os
import re
import shlex
from dataclasses import replace
from pathlib import Path

from bkw_py.ui.userbkw import run_cli as userbkw_run_cli
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import BkwProject, MixItem
from ..paths import PROJECTS_DIR, RUNTIME_ROOT, TDF_ENGINE_DIR
from ..services.calc_runner import CalcRunner
from ..services.data_service import list_templates
from ..services.output_parse import BkwTables, IspPoint, parse_bkw_tables, parse_isp_summary
from ..services.project_service import load_project, save_project
from ..services.tdf_parse import TdfCurve, parse_tdf_out, tdf_plot_image_paths
from ..services.tdf_runner import TdfRunner
from ..services.tdf_structured import TdfDeck, TdfMaterial, parse_tdfdata_text, render_tdfdata_text, validate_tdf_deck


class WorkerSignals(QObject):
    finished = Signal(int)
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(int, str)


class CalcTask(QRunnable):
    def __init__(self, runner: CalcRunner, mode: str, bkwdata_path: Path, report_path: Path):
        super().__init__()
        self.signals = WorkerSignals()
        self.runner = runner
        self.mode = mode
        self.bkwdata_path = bkwdata_path
        self.report_path = report_path

    @Slot()
    def run(self) -> None:
        try:
            rc = self.runner.run(
                mode=self.mode,
                bkwdata_path=self.bkwdata_path,
                report_path=self.report_path,
                on_log=lambda s: self.signals.log.emit(s),
                on_progress=lambda p, s: self.signals.progress.emit(p, s),
            )
            self.signals.finished.emit(rc)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class TdfTask(QRunnable):
    def __init__(self, runner: TdfRunner):
        super().__init__()
        self.signals = WorkerSignals()
        self.runner = runner

    @Slot()
    def run(self) -> None:
        try:
            rc = self.runner.run(
                on_log=lambda s: self.signals.log.emit(s),
                on_progress=lambda p, s: self.signals.progress.emit(p, s),
            )
            self.signals.finished.emit(rc)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    _NAME_RE = re.compile(r"^[A-Za-z0-9_+\-./ ]+$")
    _COMP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*\s*=\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
    _F_RE = re.compile(r"[+-]?(?:\d+\.\d+|\d+\.?|\.\d+)(?:[EeDd][+-]?\d+)")

    @staticmethod
    def _repo_root() -> Path:
        return RUNTIME_ROOT

    @classmethod
    def _abs_path(cls, p: str | Path) -> Path:
        x = Path(p).expanduser()
        if x.is_absolute():
            return x.resolve(strict=False)
        return (cls._repo_root() / x).resolve(strict=False)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BKW")
        self.resize(1200, 760)

        self.thread_pool = QThreadPool.globalInstance()
        self.runner = CalcRunner()
        self.tdf_runner = TdfRunner()
        self._active_calc_task: CalcTask | None = None
        self._active_tdf_task: TdfTask | None = None
        self.project = BkwProject()
        self.last_bkw_tables: BkwTables | None = None
        self.last_isp_points: list[IspPoint] = []
        self.tdf_deck = TdfDeck()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_project = QWidget()
        self.tab_mix = QWidget()
        self.tab_species = QWidget()
        self.tab_calc = QWidget()
        self.tab_results = QWidget()
        self.tab_export = QWidget()
        self.tab_tdf = QWidget()

        self.tabs.addTab(self.tab_project, "1. Проект")
        self.tabs.addTab(self.tab_mix, "2. Смесь")
        self.tabs.addTab(self.tab_species, "3. Species")
        self.tabs.addTab(self.tab_calc, "4. Расчет")
        self.tabs.addTab(self.tab_results, "5. Результаты")
        self.tabs.addTab(self.tab_export, "6. Экспорт")
        self.tabs.addTab(self.tab_tdf, "7. TDF")

        self._build_project_tab()
        self._build_mix_tab()
        self._build_species_tab()
        self._build_calc_tab()
        self._build_results_tab()
        self._build_export_tab()
        self._build_tdf_tab()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._refresh_project_ui()
        self._refresh_flow_state()
        self._load_tdf_curves()

    def _on_tab_changed(self, idx: int) -> None:
        # Refresh results from disk when user opens the tab to avoid stale/incomplete UI state.
        if idx == 4 and self.project.last_output_report:
            self._load_report_text()
            self._load_result_graphs()

    def _build_project_tab(self) -> None:
        lay = QVBoxLayout(self.tab_project)

        grid = QGridLayout()
        lay.addLayout(grid)

        self.project_name = QLineEdit(self.project.name)
        grid.addWidget(QLabel("Имя проекта"), 0, 0)
        grid.addWidget(self.project_name, 0, 1)

        self.source_mode_combo = QComboBox()
        self.source_mode_combo.addItems(["template", "import"])
        self.source_mode_combo.setCurrentText(self.project.source_mode)
        grid.addWidget(QLabel("Источник входа"), 1, 0)
        grid.addWidget(self.source_mode_combo, 1, 1)

        self.template_combo = QComboBox()
        self.template_combo.addItems(list_templates())
        idx = self.template_combo.findText(self.project.template)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
        grid.addWidget(QLabel("Шаблон BKWDATA"), 2, 0)
        grid.addWidget(self.template_combo, 2, 1)

        self.input_bkwdata_edit = QLineEdit("")
        self.btn_pick_bkwdata = QPushButton("Импорт BKWDATA...")
        r = QHBoxLayout()
        r.addWidget(self.input_bkwdata_edit)
        r.addWidget(self.btn_pick_bkwdata)
        grid.addWidget(QLabel("Входной BKWDATA"), 3, 0)
        grid.addLayout(r, 3, 1)

        self.legacy_ioeq_combo = QComboBox()
        self.legacy_ioeq_combo.addItem("inherit", None)
        self.legacy_ioeq_combo.addItem("equilibrium (0)", 0)
        self.legacy_ioeq_combo.addItem("frozen (1)", 1)
        grid.addWidget(QLabel("Legacy page1: ioeq"), 4, 0)
        grid.addWidget(self.legacy_ioeq_combo, 4, 1)

        self.legacy_icjc_combo = QComboBox()
        self.legacy_icjc_combo.addItem("inherit", None)
        self.legacy_icjc_combo.addItem("on (1)", 1)
        self.legacy_icjc_combo.addItem("off (0)", 0)
        grid.addWidget(QLabel("Legacy page1: icjc"), 5, 0)
        grid.addWidget(self.legacy_icjc_combo, 5, 1)

        self.legacy_ihug_combo = QComboBox()
        self.legacy_ihug_combo.addItem("inherit", None)
        self.legacy_ihug_combo.addItem("on (1)", 1)
        self.legacy_ihug_combo.addItem("off (0)", 0)
        grid.addWidget(QLabel("Legacy page1: ihug"), 6, 0)
        grid.addWidget(self.legacy_ihug_combo, 6, 1)

        self.legacy_ipvc_combo = QComboBox()
        self.legacy_ipvc_combo.addItem("inherit", None)
        self.legacy_ipvc_combo.addItem("nothing (0)", 0)
        self.legacy_ipvc_combo.addItem("through C-J (1)", 1)
        self.legacy_ipvc_combo.addItem("through Hugoniot P input (2)", 2)
        self.legacy_ipvc_combo.addItem("through T/P input (3)", 3)
        grid.addWidget(QLabel("Legacy page1: ipvc"), 7, 0)
        grid.addWidget(self.legacy_ipvc_combo, 7, 1)

        self.legacy_igrp_combo = QComboBox()
        self.legacy_igrp_combo.addItem("inherit", None)
        self.legacy_igrp_combo.addItem("graph off (1)", 1)
        self.legacy_igrp_combo.addItem("graph on (2)", 2)
        grid.addWidget(QLabel("Legacy page1: igrp"), 8, 0)
        grid.addWidget(self.legacy_igrp_combo, 8, 1)

        self.legacy_eos_preset_combo = QComboBox()
        self.legacy_eos_preset_combo.addItems(["default", "rdx", "tnt"])
        grid.addWidget(QLabel("Legacy page2: EOS preset"), 9, 0)
        grid.addWidget(self.legacy_eos_preset_combo, 9, 1)

        row = QHBoxLayout()
        self.btn_new_project = QPushButton("Новый проект")
        self.btn_load_project = QPushButton("Открыть .bkwproj.json")
        self.btn_save_project = QPushButton("Сохранить .bkwproj.json")
        row.addWidget(self.btn_new_project)
        row.addWidget(self.btn_load_project)
        row.addWidget(self.btn_save_project)
        lay.addLayout(row)

        self.project_info = QLabel("")
        lay.addWidget(self.project_info)
        lay.addStretch(1)

        self.source_mode_combo.currentTextChanged.connect(self._on_source_mode_changed)
        self.template_combo.currentTextChanged.connect(self._on_template_changed)
        self.project_name.textChanged.connect(self._on_project_name_changed)
        self.btn_pick_bkwdata.clicked.connect(self._on_pick_bkwdata)
        self.input_bkwdata_edit.textChanged.connect(self._on_input_bkwdata_changed)
        self.btn_new_project.clicked.connect(self._on_new_project)
        self.btn_load_project.clicked.connect(self._on_load_project)
        self.btn_save_project.clicked.connect(self._on_save_project)

    def _build_mix_tab(self) -> None:
        lay = QVBoxLayout(self.tab_mix)

        head = QHBoxLayout()
        self.mix_basis = QComboBox()
        self.mix_basis.addItems(["wt", "mol"])
        self.mix_basis.setCurrentText(self.project.mix_basis)
        self.mix_strict = QCheckBox("Строго по элементам")
        self.mix_strict.setChecked(self.project.strict_elements)
        head.addWidget(QLabel("База"))
        head.addWidget(self.mix_basis)
        head.addWidget(self.mix_strict)
        head.addStretch(1)
        lay.addLayout(head)

        self.mix_table = QTableWidget(0, 2)
        self.mix_table.setHorizontalHeaderLabels(["Компонент", "Значение"])
        lay.addWidget(self.mix_table)

        row = QHBoxLayout()
        self.btn_mix_add = QPushButton("Добавить строку")
        self.btn_mix_remove = QPushButton("Удалить строку")
        self.btn_mix_apply = QPushButton("Применить в проект")
        row.addWidget(self.btn_mix_add)
        row.addWidget(self.btn_mix_remove)
        row.addWidget(self.btn_mix_apply)
        row.addStretch(1)
        lay.addLayout(row)

        self.mix_hint = QLabel("")
        lay.addWidget(self.mix_hint)

        self.btn_mix_add.clicked.connect(self._on_mix_add)
        self.btn_mix_remove.clicked.connect(self._on_mix_remove)
        self.btn_mix_apply.clicked.connect(self._on_mix_apply)

    def _build_species_tab(self) -> None:
        lay = QVBoxLayout(self.tab_species)
        self.gas_db_edit = QLineEdit()
        self.solid_db_edit = QLineEdit()
        self.gas_custom_edit = QPlainTextEdit()
        self.solid_custom_edit = QPlainTextEdit()
        self.gas_db_edit.setPlaceholderText("например: no,hcl,co2")
        self.solid_db_edit.setPlaceholderText("например: sol c,al2o3")
        self.gas_custom_edit.setPlaceholderText("name|8therc|el=val,el=val")
        self.solid_custom_edit.setPlaceholderText("name|8therc|12soleq|el=val,el=val")

        lay.addWidget(QLabel("Add gas db (через запятую):"))
        lay.addWidget(self.gas_db_edit)
        lay.addWidget(QLabel("Add solid db (через запятую):"))
        lay.addWidget(self.solid_db_edit)

        lay.addWidget(QLabel("Add gas custom (по строкам, формат name|8therc|el=val,...):"))
        lay.addWidget(self.gas_custom_edit)
        lay.addWidget(QLabel("Add solid custom (по строкам, формат name|8therc|12soleq|el=val,...):"))
        lay.addWidget(self.solid_custom_edit)

        lay.addWidget(QLabel("Legacy page5: athrho (через запятую, до 4 значений):"))
        self.legacy_athrho_edit = QLineEdit()
        self.legacy_athrho_edit.setPlaceholderText("например: 1.7,1.8")
        self.legacy_athrho_edit.setToolTip("Формат: n1,n2,n3,n4 (до 4 чисел). Пример: 1.70,1.85")
        lay.addWidget(self.legacy_athrho_edit)
        lay.addWidget(QLabel("Legacy page5: aispr (используется при ipvc=2):"))
        self.legacy_aispr_edit = QLineEdit()
        self.legacy_aispr_edit.setPlaceholderText("например: 0.30")
        self.legacy_aispr_edit.setToolTip("Одно число. Используется, если ipvc=2.")
        lay.addWidget(self.legacy_aispr_edit)

        lay.addWidget(QLabel("Legacy page6 constants (по строкам no=val, 1..30):"))
        self.legacy_constants_edit = QPlainTextEdit()
        self.legacy_constants_edit.setPlaceholderText("например:\n29=1.25\n1=-1")
        self.legacy_constants_edit.setToolTip("Каждая строка: no=val. Значение -1 восстанавливает исходную константу.")
        self.legacy_constants_edit.setMaximumHeight(90)
        lay.addWidget(self.legacy_constants_edit)

        lay.addWidget(QLabel("Legacy page3b twin для solid (по строкам old=new):"))
        self.legacy_twins_edit = QPlainTextEdit()
        self.legacy_twins_edit.setPlaceholderText("например:\nsol c=graph")
        self.legacy_twins_edit.setToolTip("Каждая строка: old=new. old — имя solid из nam, new — second name/twin.")
        self.legacy_twins_edit.setMaximumHeight(90)
        lay.addWidget(self.legacy_twins_edit)

        row = QHBoxLayout()
        self.btn_species_apply = QPushButton("Применить species-параметры")
        row.addWidget(self.btn_species_apply)
        row.addStretch(1)
        lay.addLayout(row)

        self.species_hint = QLabel("")
        lay.addWidget(self.species_hint)

        self.btn_species_apply.clicked.connect(self._on_species_apply)

    def _build_calc_tab(self) -> None:
        lay = QVBoxLayout(self.tab_calc)

        top = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["bkw", "isp"])
        self.mode_combo.setCurrentText(self.project.run_settings.mode)
        self.btn_generate_bkwdata = QPushButton("Сгенерировать BKWDATA")
        self.btn_run = QPushButton("Запустить расчет")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setEnabled(False)
        top.addWidget(QLabel("Режим"))
        top.addWidget(self.mode_combo)
        top.addWidget(self.btn_generate_bkwdata)
        top.addWidget(self.btn_run)
        top.addWidget(self.btn_cancel)
        top.addStretch(1)
        lay.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        lay.addWidget(self.progress)

        self.calc_status = QLabel("Готов")
        lay.addWidget(self.calc_status)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view)

        self.btn_generate_bkwdata.clicked.connect(self._on_generate_bkwdata)
        self.btn_run.clicked.connect(self._on_run_calc)
        self.btn_cancel.clicked.connect(self._on_cancel_calc)

    def _build_results_tab(self) -> None:
        lay = QVBoxLayout(self.tab_results)

        nav = QHBoxLayout()
        self.btn_graph_prev = QPushButton("Prev")
        self.btn_graph_next = QPushButton("Next")
        self.graph_title = QLabel("Graph 1/3")
        nav.addWidget(self.btn_graph_prev)
        nav.addWidget(self.btn_graph_next)
        nav.addWidget(self.graph_title)
        nav.addStretch(1)
        lay.addLayout(nav)

        try:
            import pyqtgraph as pg

            self.pg = pg
            self.graph_widgets = []
            self.graph_meta: list[tuple[str, str]] = []

            self.graph_container = QTabWidget()
            self.graph_container.tabBar().hide()
            self.graph_container.setMinimumHeight(280)
            lay.addWidget(self.graph_container, 4)
            self.btn_graph_prev.clicked.connect(self._on_graph_prev)
            self.btn_graph_next.clicked.connect(self._on_graph_next)
            self._set_result_graphs([])
        except Exception as exc:
            self.pg = None
            self.graph_widgets = []
            self.graph_meta = []
            self.graph_container = None
            lay.addWidget(QLabel(f"pyqtgraph недоступен ({type(exc).__name__}: {exc}). Графики недоступны."))

        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        lay.addWidget(self.result_text, 2)

    def _build_export_tab(self) -> None:
        lay = QVBoxLayout(self.tab_export)

        self.export_bkwdata = QLineEdit(str(PROJECTS_DIR / "BKWDATA"))
        self.export_report = QLineEdit(str(PROJECTS_DIR / "report.out"))

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("BKWDATA"))
        r1.addWidget(self.export_bkwdata)
        self.btn_pick_export_bkw = QPushButton("...")
        r1.addWidget(self.btn_pick_export_bkw)
        lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Отчет (bkw.out/isp.out)"))
        r2.addWidget(self.export_report)
        self.btn_pick_export_report = QPushButton("...")
        r2.addWidget(self.btn_pick_export_report)
        lay.addLayout(r2)

        row = QHBoxLayout()
        self.btn_export_csv = QPushButton("Экспорт CSV")
        self.btn_export_png = QPushButton("Экспорт PNG")
        row.addWidget(self.btn_export_csv)
        row.addWidget(self.btn_export_png)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(QLabel("PDF в v1 не включен (позже)."))
        lay.addStretch(1)

        self.btn_pick_export_bkw.clicked.connect(self._on_pick_export_bkw)
        self.btn_pick_export_report.clicked.connect(self._on_pick_export_report)
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        self.btn_export_png.clicked.connect(self._on_export_png)

    def _build_tdf_tab(self) -> None:
        lay = QVBoxLayout(self.tab_tdf)

        data_row = QHBoxLayout()
        self.tdf_input_path = QLineEdit(str(TDF_ENGINE_DIR / "tdfdata"))
        self.tdf_input_path.setReadOnly(True)
        self.btn_tdf_open_input = QPushButton("Открыть tdfdata...")
        self.btn_tdf_save_input = QPushButton("Сохранить как...")
        self.btn_tdf_apply_input = QPushButton("Применить в tdf_engine")
        self.btn_tdf_reset_input = QPushButton("Сброс к исходному")
        data_row.addWidget(QLabel("TDF input"))
        data_row.addWidget(self.tdf_input_path, 1)
        data_row.addWidget(self.btn_tdf_open_input)
        data_row.addWidget(self.btn_tdf_save_input)
        data_row.addWidget(self.btn_tdf_apply_input)
        data_row.addWidget(self.btn_tdf_reset_input)
        lay.addLayout(data_row)

        struct_row = QHBoxLayout()
        self.btn_tdf_struct_from_text = QPushButton("Разобрать текст в формы")
        self.btn_tdf_struct_to_text = QPushButton("Сгенерировать tdfdata из форм")
        self.btn_tdf_mat_add = QPushButton("Добавить материал")
        self.btn_tdf_mat_del = QPushButton("Удалить материал")
        self.btn_tdf_mat_apply = QPushButton("Применить материал")
        struct_row.addWidget(self.btn_tdf_struct_from_text)
        struct_row.addWidget(self.btn_tdf_struct_to_text)
        struct_row.addWidget(self.btn_tdf_mat_add)
        struct_row.addWidget(self.btn_tdf_mat_del)
        struct_row.addWidget(self.btn_tdf_mat_apply)
        struct_row.addStretch(1)
        lay.addLayout(struct_row)

        struct_layout = QHBoxLayout()
        self.tdf_mat_table = QTableWidget(0, 4)
        self.tdf_mat_table.setHorizontalHeaderLabels(["Маркер", "Код", "Имя", "Комментарий"])
        self.tdf_mat_table.setMinimumHeight(180)
        struct_layout.addWidget(self.tdf_mat_table, 2)

        form = QGridLayout()
        self.tdf_mat_marker = QLineEdit()
        self.tdf_mat_code = QLineEdit()
        self.tdf_mat_name = QLineEdit()
        self.tdf_mat_comment = QLineEdit()
        self.tdf_mat_nline = QLineEdit()
        self.tdf_mat_body = QPlainTextEdit()
        self.tdf_mat_body.setPlaceholderText("Параметры материала (строки после nline)")
        self.tdf_mat_body.setMaximumHeight(180)
        form.addWidget(QLabel("Маркер"), 0, 0)
        form.addWidget(self.tdf_mat_marker, 0, 1)
        form.addWidget(QLabel("Код"), 1, 0)
        form.addWidget(self.tdf_mat_code, 1, 1)
        form.addWidget(QLabel("Имя"), 2, 0)
        form.addWidget(self.tdf_mat_name, 2, 1)
        form.addWidget(QLabel("Комментарий"), 3, 0)
        form.addWidget(self.tdf_mat_comment, 3, 1)
        form.addWidget(QLabel("nline"), 4, 0)
        form.addWidget(self.tdf_mat_nline, 4, 1)
        form.addWidget(QLabel("Body"), 5, 0)
        form.addWidget(self.tdf_mat_body, 5, 1)
        form_w = QWidget()
        form_w.setLayout(form)
        struct_layout.addWidget(form_w, 3)
        lay.addLayout(struct_layout, 2)

        self.tdf_input_editor = QPlainTextEdit()
        self.tdf_input_editor.setPlaceholderText("Содержимое tdfdata")
        lay.addWidget(self.tdf_input_editor, 2)

        row = QHBoxLayout()
        self.btn_tdf_run = QPushButton("Запустить TDF")
        self.btn_tdf_cancel = QPushButton("Отмена")
        self.btn_tdf_cancel.setEnabled(False)
        self.tdf_curve_picker = QComboBox()
        self.tdf_curve_picker.setMinimumWidth(460)
        self.btn_tdf_prev = QPushButton("Prev")
        self.btn_tdf_next = QPushButton("Next")
        row.addWidget(self.btn_tdf_run)
        row.addWidget(self.btn_tdf_cancel)
        row.addWidget(QLabel("Кривая"))
        row.addWidget(self.tdf_curve_picker, 1)
        row.addWidget(self.btn_tdf_prev)
        row.addWidget(self.btn_tdf_next)
        lay.addLayout(row)

        self.tdf_status = QLabel("TDF: готов")
        lay.addWidget(self.tdf_status)

        self.tdf_curves: list[TdfCurve] = []
        self.tdf_plot_images: list[Path | None] = []
        self.tdf_plot_label = None
        try:
            import pyqtgraph as pg

            self.tdf_plot = pg.PlotWidget()
            self.tdf_plot.setBackground("#1e1e1e")
            lay.addWidget(self.tdf_plot, 5)
        except Exception as exc:
            self.tdf_plot = None
            self.tdf_plot_label = QLabel(f"pyqtgraph недоступен ({type(exc).__name__}: {exc}). Будут показаны PNG-графики из TDF.")
            self.tdf_plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tdf_plot_label.setMinimumHeight(280)
            self.tdf_plot_label.setWordWrap(True)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.tdf_plot_label)
            lay.addWidget(scroll, 5)

        self.tdf_log = QPlainTextEdit()
        self.tdf_log.setReadOnly(True)
        self.tdf_log.setMaximumHeight(170)
        lay.addWidget(self.tdf_log, 1)

        self.btn_tdf_open_input.clicked.connect(self._on_tdf_open_input)
        self.btn_tdf_save_input.clicked.connect(self._on_tdf_save_input)
        self.btn_tdf_apply_input.clicked.connect(self._on_tdf_apply_input)
        self.btn_tdf_reset_input.clicked.connect(self._on_tdf_reset_input)
        self.btn_tdf_struct_from_text.clicked.connect(self._on_tdf_struct_from_text)
        self.btn_tdf_struct_to_text.clicked.connect(self._on_tdf_struct_to_text)
        self.btn_tdf_mat_add.clicked.connect(self._on_tdf_mat_add)
        self.btn_tdf_mat_del.clicked.connect(self._on_tdf_mat_del)
        self.btn_tdf_mat_apply.clicked.connect(self._on_tdf_mat_apply)
        self.tdf_mat_table.itemSelectionChanged.connect(self._on_tdf_mat_select)
        self.btn_tdf_run.clicked.connect(self._on_run_tdf)
        self.btn_tdf_cancel.clicked.connect(self._on_cancel_tdf)
        self.tdf_curve_picker.currentIndexChanged.connect(self._on_tdf_curve_changed)
        self.btn_tdf_prev.clicked.connect(self._on_tdf_prev)
        self.btn_tdf_next.clicked.connect(self._on_tdf_next)

        self._load_tdf_input_from_engine()
        self._on_tdf_struct_from_text()

    def _combo_set_by_data(self, combo: QComboBox, value: int | None) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _normalize_legacy_from_widgets(self) -> None:
        athrho_tokens = [x.strip() for x in self.legacy_athrho_edit.text().split(",") if x.strip()]
        self.legacy_athrho_edit.setText(",".join(athrho_tokens))
        self.legacy_aispr_edit.setText(self.legacy_aispr_edit.text().strip())

        const_lines: list[str] = []
        for line in self.legacy_constants_edit.toPlainText().splitlines():
            t = line.strip()
            if not t:
                continue
            if "=" in t:
                no_s, val_s = t.split("=", 1)
                t = f"{no_s.strip()}={val_s.strip()}"
            const_lines.append(t)
        self.legacy_constants_edit.setPlainText("\n".join(const_lines))

        twin_lines: list[str] = []
        for line in self.legacy_twins_edit.toPlainText().splitlines():
            t = line.strip()
            if not t:
                continue
            if "=" in t:
                old_s, new_s = t.split("=", 1)
                t = f"{old_s.strip().lower()}={new_s.strip()}"
            twin_lines.append(t)
        self.legacy_twins_edit.setPlainText("\n".join(twin_lines))

    def _sync_legacy_from_ui(self) -> None:
        self._normalize_legacy_from_widgets()
        self.project.legacy_ioeq = self.legacy_ioeq_combo.currentData()
        self.project.legacy_icjc = self.legacy_icjc_combo.currentData()
        self.project.legacy_ihug = self.legacy_ihug_combo.currentData()
        self.project.legacy_ipvc = self.legacy_ipvc_combo.currentData()
        self.project.legacy_igrp = self.legacy_igrp_combo.currentData()
        self.project.legacy_eos_preset = self.legacy_eos_preset_combo.currentText().strip() or "default"
        self.project.legacy_athrho = self.legacy_athrho_edit.text().strip()
        self.project.legacy_aispr = self.legacy_aispr_edit.text().strip()
        self.project.legacy_constants = [x.strip() for x in self.legacy_constants_edit.toPlainText().splitlines() if x.strip()]
        self.project.legacy_solid_twins = [x.strip() for x in self.legacy_twins_edit.toPlainText().splitlines() if x.strip()]

    def _refresh_project_ui(self) -> None:
        self.project_name.setText(self.project.name)
        self.source_mode_combo.setCurrentText(self.project.source_mode)
        idx = self.template_combo.findText(self.project.template)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
        self.input_bkwdata_edit.setText(self.project.source_bkwdata)
        self.mix_basis.setCurrentText(self.project.mix_basis)
        self.mix_strict.setChecked(self.project.strict_elements)
        self.mode_combo.setCurrentText(self.project.run_settings.mode)
        self._combo_set_by_data(self.legacy_ioeq_combo, self.project.legacy_ioeq)
        self._combo_set_by_data(self.legacy_icjc_combo, self.project.legacy_icjc)
        self._combo_set_by_data(self.legacy_ihug_combo, self.project.legacy_ihug)
        self._combo_set_by_data(self.legacy_ipvc_combo, self.project.legacy_ipvc)
        self._combo_set_by_data(self.legacy_igrp_combo, self.project.legacy_igrp)
        idx_eos = self.legacy_eos_preset_combo.findText(self.project.legacy_eos_preset or "default")
        self.legacy_eos_preset_combo.setCurrentIndex(idx_eos if idx_eos >= 0 else 0)
        self.gas_db_edit.setText(",".join(self.project.add_gas_db))
        self.solid_db_edit.setText(",".join(self.project.add_solid_db))
        self.gas_custom_edit.setPlainText("\n".join(self.project.add_gas_custom))
        self.solid_custom_edit.setPlainText("\n".join(self.project.add_solid_custom))
        self.legacy_athrho_edit.setText(self.project.legacy_athrho)
        self.legacy_aispr_edit.setText(self.project.legacy_aispr)
        self.legacy_constants_edit.setPlainText("\n".join(self.project.legacy_constants))
        self.legacy_twins_edit.setPlainText("\n".join(self.project.legacy_solid_twins))
        self.project_info.setText(
            f"Проект: {self.project.name}; источник: {self.project.source_mode}; "
            f"шаблон: {self.project.template}; input: {self.project.source_bkwdata or '-'}"
        )
        self._update_source_mode_ui()
        self._load_mix_table()

    def _refresh_flow_state(self) -> None:
        has_project = bool(
            self.project.template if self.project.source_mode == "template" else self.project.source_bkwdata
        )
        has_mix = bool(self.project.mix or self.project.source_bkwdata)
        has_generated = bool(self.project.last_output_bkwdata)
        has_results = bool(self.project.last_output_report and Path(self.project.last_output_report).exists())

        self.tabs.setTabEnabled(1, has_project)
        self.tabs.setTabEnabled(2, has_mix)
        self.tabs.setTabEnabled(3, has_mix)
        self.tabs.setTabEnabled(4, has_generated or has_mix)
        self.tabs.setTabEnabled(5, has_results)
        self.tabs.setTabEnabled(6, True)

    def _load_mix_table(self) -> None:
        self.mix_table.setRowCount(0)
        for x in self.project.mix:
            r = self.mix_table.rowCount()
            self.mix_table.insertRow(r)
            self.mix_table.setItem(r, 0, QTableWidgetItem(x.name))
            self.mix_table.setItem(r, 1, QTableWidgetItem(f"{x.value:g}"))

    def _update_source_mode_ui(self) -> None:
        mode = self.source_mode_combo.currentText()
        is_template = mode == "template"
        self.template_combo.setEnabled(is_template)
        self.input_bkwdata_edit.setEnabled(not is_template)
        self.btn_pick_bkwdata.setEnabled(not is_template)

    def _on_source_mode_changed(self, value: str) -> None:
        self.project.source_mode = value
        if value == "import" and self.input_bkwdata_edit.text().strip():
            self.project.last_output_bkwdata = self.input_bkwdata_edit.text().strip()
        self._update_source_mode_ui()
        self._refresh_flow_state()

    def _on_template_changed(self, value: str) -> None:
        self.project.template = value
        self._refresh_flow_state()

    def _on_project_name_changed(self, value: str) -> None:
        self.project.name = value.strip() or "new_project"

    def _on_input_bkwdata_changed(self, value: str) -> None:
        p = value.strip()
        self.project.source_bkwdata = p
        if self.project.source_mode == "import":
            # Import mode uses source BKWDATA directly for run when present.
            self.project.last_output_bkwdata = p
        self._refresh_flow_state()

    def _on_pick_bkwdata(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open BKWDATA", str(Path.cwd()))
        if path:
            self.project.source_bkwdata = str(self._abs_path(path))
            self.project.source_mode = "import"
            self.source_mode_combo.setCurrentText("import")
            self.input_bkwdata_edit.setText(self.project.source_bkwdata)
            self._refresh_flow_state()

    def _on_new_project(self) -> None:
        self.project = BkwProject()
        self.last_bkw_tables = None
        self.last_isp_points = []
        self._refresh_project_ui()
        self.result_text.clear()
        self._set_result_graphs([])
        self._refresh_flow_state()

    def _on_load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", str(PROJECTS_DIR), "Project (*.bkwproj.json)")
        if not path:
            return
        self.project = load_project(path)
        self._refresh_project_ui()
        self._load_report_text()
        self._load_result_graphs()
        self._refresh_flow_state()

    def _on_save_project(self) -> None:
        self._sync_legacy_from_ui()
        path, _ = QFileDialog.getSaveFileName(self, "Save project", str(PROJECTS_DIR / f"{self.project.name}.bkwproj.json"), "Project (*.bkwproj.json)")
        if not path:
            return
        save_project(path, self.project)
        QMessageBox.information(self, "Project", f"Saved: {path}")

    def _on_mix_add(self) -> None:
        r = self.mix_table.rowCount()
        self.mix_table.insertRow(r)
        self.mix_table.setItem(r, 0, QTableWidgetItem(""))
        self.mix_table.setItem(r, 1, QTableWidgetItem("0"))

    def _on_mix_remove(self) -> None:
        r = self.mix_table.currentRow()
        if r >= 0:
            self.mix_table.removeRow(r)

    def _clear_validation_marks(self) -> None:
        for w in [
            self.input_bkwdata_edit,
            self.template_combo,
            self.source_mode_combo,
            self.mix_basis,
            self.gas_db_edit,
            self.solid_db_edit,
            self.gas_custom_edit,
            self.solid_custom_edit,
            self.legacy_athrho_edit,
            self.legacy_aispr_edit,
            self.legacy_constants_edit,
            self.legacy_twins_edit,
            self.mode_combo,
            self.export_report,
        ]:
            w.setStyleSheet("")
            w.setToolTip("")
        self._clear_mix_table_marks()

    def _clear_mix_table_marks(self) -> None:
        for r in range(self.mix_table.rowCount()):
            for c in range(self.mix_table.columnCount()):
                it = self.mix_table.item(r, c)
                if it is not None:
                    it.setBackground(QBrush())
                    it.setToolTip("")

    def _mark_widget_error(self, widget: QWidget, msg: str) -> None:
        widget.setStyleSheet("border: 1px solid #d9534f; background-color: #fff1f1;")
        widget.setToolTip(msg)

    def _mark_mix_row_error(self, row: int, msg: str) -> None:
        for c in range(self.mix_table.columnCount()):
            it = self.mix_table.item(row, c)
            if it is None:
                it = QTableWidgetItem("")
                self.mix_table.setItem(row, c, it)
            it.setBackground(QColor("#ffe6e6"))
            it.setToolTip(msg)

    def _on_mix_apply(self) -> None:
        self._clear_validation_marks()
        ok, msg, items, ctx = self._validate_mix_table()
        if not ok:
            if "mix_row" in ctx:
                self._mark_mix_row_error(int(ctx["mix_row"]), msg)
            if "mix_basis" in ctx:
                self._mark_widget_error(self.mix_basis, msg)
            QMessageBox.warning(self, "Смесь", msg)
            return

        self.project.mix = items
        self.project.mix_basis = self.mix_basis.currentText()
        self.project.strict_elements = self.mix_strict.isChecked()
        self.mix_hint.setText(f"Принято компонентов: {len(items)}")
        self._refresh_flow_state()

    def _on_species_apply(self) -> None:
        self._clear_validation_marks()
        ok, msg, ctx = self._validate_species_fields()
        if not ok:
            widget = ctx.get("widget")
            if widget == "gas_db":
                self._mark_widget_error(self.gas_db_edit, msg)
            elif widget == "solid_db":
                self._mark_widget_error(self.solid_db_edit, msg)
            elif widget == "gas_custom":
                self._mark_widget_error(self.gas_custom_edit, msg)
            elif widget == "solid_custom":
                self._mark_widget_error(self.solid_custom_edit, msg)
            elif widget == "legacy_athrho":
                self._mark_widget_error(self.legacy_athrho_edit, msg)
            elif widget == "legacy_aispr":
                self._mark_widget_error(self.legacy_aispr_edit, msg)
            elif widget == "legacy_constants":
                self._mark_widget_error(self.legacy_constants_edit, msg)
            elif widget == "legacy_twins":
                self._mark_widget_error(self.legacy_twins_edit, msg)
            QMessageBox.warning(self, "Species", msg)
            return
        self.project.add_gas_db = [x.strip().lower() for x in self.gas_db_edit.text().split(",") if x.strip()]
        self.project.add_solid_db = [x.strip() for x in self.solid_db_edit.text().split(",") if x.strip()]
        self.project.add_gas_custom = [x.strip() for x in self.gas_custom_edit.toPlainText().splitlines() if x.strip()]
        self.project.add_solid_custom = [x.strip() for x in self.solid_custom_edit.toPlainText().splitlines() if x.strip()]
        self._sync_legacy_from_ui()
        self.species_hint.setText(
            f"gas_db={len(self.project.add_gas_db)}; solid_db={len(self.project.add_solid_db)}; "
            f"gas_custom={len(self.project.add_gas_custom)}; solid_custom={len(self.project.add_solid_custom)}; "
            f"legacy_const={len(self.project.legacy_constants)}; legacy_twin={len(self.project.legacy_solid_twins)}"
        )

    def _parse_db_tokens(self, text: str, *, label: str, widget_key: str) -> tuple[bool, str, list[str], dict]:
        tokens = [x.strip() for x in text.split(",") if x.strip()]
        seen: set[str] = set()
        for i, t in enumerate(tokens, start=1):
            if not self._NAME_RE.match(t):
                return False, f"{label}: недопустимое имя '{t}' (позиция {i}).", [], {"widget": widget_key}
            key = t.lower()
            if key in seen:
                return False, f"{label}: дубликат '{t}'.", [], {"widget": widget_key}
            seen.add(key)
        return True, "", tokens, {}

    def _validate_composition(self, comp: str, *, line: str, widget_key: str) -> tuple[bool, str, dict]:
        parts = [x.strip() for x in comp.split(",") if x.strip()]
        if not parts:
            return False, f"Пустой composition: {line}", {"widget": widget_key}
        elems: set[str] = set()
        for p in parts:
            if not self._COMP_RE.match(p):
                return False, f"Неверный composition-токен '{p}': {line}", {"widget": widget_key}
            el, val = [x.strip() for x in p.split("=", 1)]
            k = el.lower()
            if k in elems:
                return False, f"Повтор элемента '{el}' в composition: {line}", {"widget": widget_key}
            elems.add(k)
            try:
                f = float(val)
            except Exception:
                return False, f"Нечисловое значение элемента '{p}': {line}", {"widget": widget_key}
            if f <= 0.0:
                return False, f"Значение элемента должно быть > 0 ('{p}'): {line}", {"widget": widget_key}
        return True, "", {}

    def _validate_species_fields(self) -> tuple[bool, str, dict]:
        self._normalize_legacy_from_widgets()
        ok, msg, gas_db, ctx = self._parse_db_tokens(self.gas_db_edit.text(), label="Add gas db", widget_key="gas_db")
        if not ok:
            return False, msg, ctx
        ok, msg, solid_db, ctx = self._parse_db_tokens(self.solid_db_edit.text(), label="Add solid db", widget_key="solid_db")
        if not ok:
            return False, msg, ctx

        gas_custom_names: set[str] = set()
        solid_custom_names: set[str] = set()

        # Validate custom gas: name|8therc|composition
        for n, line in enumerate([x.strip() for x in self.gas_custom_edit.toPlainText().splitlines() if x.strip()], start=1):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                return False, f"Gas custom строка {n}: формат name|8therc|composition", {"widget": "gas_custom"}
            if not parts[0]:
                return False, f"Gas custom строка {n}: пустое имя.", {"widget": "gas_custom"}
            if not self._NAME_RE.match(parts[0]):
                return False, f"Gas custom строка {n}: недопустимое имя '{parts[0]}'.", {"widget": "gas_custom"}
            k = parts[0].lower()
            if k in gas_custom_names:
                return False, f"Gas custom: дубликат имени '{parts[0]}'.", {"widget": "gas_custom"}
            gas_custom_names.add(k)
            vals = [x.strip() for x in parts[1].split(",") if x.strip()]
            if len(vals) != 8:
                return False, f"Gas custom '{parts[0]}': нужно ровно 8 THERC.", {"widget": "gas_custom"}
            try:
                [float(v) for v in vals]
            except Exception:
                return False, f"Gas custom '{parts[0]}': THERC содержит нечисловые значения.", {"widget": "gas_custom"}
            ok_comp, msg_comp, comp_ctx = self._validate_composition(parts[2], line=line, widget_key="gas_custom")
            if not ok_comp:
                return False, msg_comp, comp_ctx

        # Validate custom solid: name|8therc|12soleq|composition
        for n, line in enumerate([x.strip() for x in self.solid_custom_edit.toPlainText().splitlines() if x.strip()], start=1):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 4:
                return False, f"Solid custom строка {n}: формат name|8therc|12soleq|composition", {"widget": "solid_custom"}
            if not parts[0]:
                return False, f"Solid custom строка {n}: пустое имя.", {"widget": "solid_custom"}
            if not self._NAME_RE.match(parts[0]):
                return False, f"Solid custom строка {n}: недопустимое имя '{parts[0]}'.", {"widget": "solid_custom"}
            k = parts[0].lower()
            if k in solid_custom_names:
                return False, f"Solid custom: дубликат имени '{parts[0]}'.", {"widget": "solid_custom"}
            solid_custom_names.add(k)
            vals_t = [x.strip() for x in parts[1].split(",") if x.strip()]
            vals_s = [x.strip() for x in parts[2].split(",") if x.strip()]
            if len(vals_t) != 8:
                return False, f"Solid custom '{parts[0]}': нужно ровно 8 THERC.", {"widget": "solid_custom"}
            if len(vals_s) != 12:
                return False, f"Solid custom '{parts[0]}': нужно ровно 12 SOLEQ.", {"widget": "solid_custom"}
            try:
                [float(v) for v in vals_t]
                [float(v) for v in vals_s]
            except Exception:
                return False, f"Solid custom '{parts[0]}': THERC/SOLEQ содержит нечисловые значения.", {"widget": "solid_custom"}
            ok_comp, msg_comp, comp_ctx = self._validate_composition(parts[3], line=line, widget_key="solid_custom")
            if not ok_comp:
                return False, msg_comp, comp_ctx

        gas_db_set = {x.lower() for x in gas_db}
        solid_db_set = {x.lower() for x in solid_db}
        if gas_db_set & gas_custom_names:
            dup = sorted(gas_db_set & gas_custom_names)[0]
            return False, f"Конфликт species: '{dup}' указан и в gas db, и в gas custom.", {"widget": "gas_db"}
        if solid_db_set & solid_custom_names:
            dup = sorted(solid_db_set & solid_custom_names)[0]
            return False, f"Конфликт species: '{dup}' указан и в solid db, и в solid custom.", {"widget": "solid_db"}

        athrho_txt = self.legacy_athrho_edit.text().strip()
        if athrho_txt:
            vals = [x.strip() for x in athrho_txt.split(",") if x.strip()]
            if len(vals) > 4:
                return False, "Legacy athrho: максимум 4 значения.", {"widget": "legacy_athrho"}
            try:
                [float(x) for x in vals]
            except Exception:
                return False, "Legacy athrho: допускаются только числа через запятую.", {"widget": "legacy_athrho"}

        aispr_txt = self.legacy_aispr_edit.text().strip()
        if aispr_txt:
            try:
                float(aispr_txt)
            except Exception:
                return False, "Legacy aispr: должно быть числом.", {"widget": "legacy_aispr"}

        seen_const: set[int] = set()
        for line in [x.strip() for x in self.legacy_constants_edit.toPlainText().splitlines() if x.strip()]:
            if "=" not in line:
                return False, f"Legacy constants: ожидается no=val, получено '{line}'.", {"widget": "legacy_constants"}
            no_s, val_s = line.split("=", 1)
            try:
                no = int(no_s.strip())
            except Exception:
                return False, f"Legacy constants: неверный номер '{no_s}'.", {"widget": "legacy_constants"}
            if no < 1 or no > 30:
                return False, f"Legacy constants: номер {no} вне диапазона 1..30.", {"widget": "legacy_constants"}
            if no in seen_const:
                return False, f"Legacy constants: дубликат номера {no}.", {"widget": "legacy_constants"}
            seen_const.add(no)
            try:
                float(val_s.strip())
            except Exception:
                return False, f"Legacy constants: неверное значение для {no}.", {"widget": "legacy_constants"}

        for line in [x.strip() for x in self.legacy_twins_edit.toPlainText().splitlines() if x.strip()]:
            if "=" not in line:
                return False, f"Legacy twin: ожидается old=new, получено '{line}'.", {"widget": "legacy_twins"}
            old_s, new_s = line.split("=", 1)
            if not old_s.strip() or not new_s.strip():
                return False, f"Legacy twin: ожидается old=new, получено '{line}'.", {"widget": "legacy_twins"}

        return True, "", {}

    def _validate_mix_table(self) -> tuple[bool, str, list[MixItem], dict]:
        items: list[MixItem] = []
        seen: set[str] = set()
        for r in range(self.mix_table.rowCount()):
            n_it = self.mix_table.item(r, 0)
            v_it = self.mix_table.item(r, 1)
            n = (n_it.text().strip() if n_it else "")
            v = (v_it.text().strip() if v_it else "")
            if not n and not v:
                continue
            if n and not v:
                return False, f"Строка смеси #{r+1}: задан компонент, но пустое значение.", [], {"mix_row": r}
            if v and not n:
                return False, f"Строка смеси #{r+1}: задано значение без имени компонента.", [], {"mix_row": r}
            if not self._NAME_RE.match(n):
                return False, f"Строка смеси #{r+1}: недопустимое имя компонента '{n}'.", [], {"mix_row": r}
            key = n.lower()
            if key in seen:
                return False, f"Строка смеси #{r+1}: дубликат компонента '{n}'.", [], {"mix_row": r}
            seen.add(key)
            try:
                fv = float(v)
            except Exception:
                return False, f"Строка смеси #{r+1}: значение не число.", [], {"mix_row": r}
            if fv <= 0.0:
                return False, f"Строка смеси #{r+1}: значение должно быть > 0.", [], {"mix_row": r}
            items.append(MixItem(name=n, value=fv))

        if self.mix_basis.currentText() not in {"wt", "mol"}:
            return False, "Неверная база смеси (должно быть wt или mol).", [], {"mix_basis": True}
        if items and sum(x.value for x in items) <= 0.0:
            return False, "Сумма значений смеси должна быть > 0.", [], {"mix_basis": True}
        return True, "", items, {}

    def _validate_mode_and_inputs(self) -> tuple[bool, str, dict]:
        mode = self.source_mode_combo.currentText().strip()
        if mode not in {"template", "import"}:
            return False, "Неверный режим источника. Допустимо: template или import.", {"source_mode": True}
        if mode == "import":
            src = self.input_bkwdata_edit.text().strip()
            if not src:
                return False, "Выбран режим import, но не указан файл BKWDATA.", {"input_bkwdata": True}
            p = self._abs_path(src)
            if not p.exists():
                return False, f"Файл BKWDATA не найден: {p}", {"input_bkwdata": True}
            if not p.is_file():
                return False, f"Путь BKWDATA не является файлом: {p}", {"input_bkwdata": True}
            self.project.source_bkwdata = str(p)
            self.input_bkwdata_edit.setText(str(p))
        else:
            if not self.template_combo.currentText().strip():
                return False, "Не выбран шаблон BKWDATA.", {"template": True}
        return True, "", {}

    def _validate_before_generate(self) -> tuple[bool, str, dict]:
        ok, msg, ctx = self._validate_mode_and_inputs()
        if not ok:
            return False, msg, ctx

        ok, msg, _items, ctx = self._validate_mix_table()
        if not ok:
            return False, msg, ctx

        ok, msg, ctx = self._validate_species_fields()
        if not ok:
            return ok, msg, ctx
        return True, "", {}

    def _validate_before_run(self) -> tuple[bool, str, dict]:
        mode = self.mode_combo.currentText().strip()
        if mode not in {"bkw", "isp"}:
            return False, "Неверный режим расчета. Допустимо: bkw или isp.", {"mode": True}
        candidate = self.project.last_output_bkwdata
        if self.source_mode_combo.currentText().strip() == "import":
            src = self.input_bkwdata_edit.text().strip()
            if src:
                candidate = src
        if not candidate:
            return False, "Сначала сгенерируйте BKWDATA или укажите импортируемый BKWDATA.", {}
        bkw = self._abs_path(candidate)
        if not bkw.exists():
            return False, f"BKWDATA для расчета не найден: {bkw}", {}
        self.project.last_output_bkwdata = str(bkw)
        report = self._abs_path(self.export_report.text().strip() or str(PROJECTS_DIR / ("bkw.out" if mode == "bkw" else "isp.out")))
        if str(report).strip() == "":
            return False, "Не задан путь для отчета.", {"report": True}
        if report.resolve() == bkw.resolve():
            return False, "Конфликт путей: отчет не должен записываться в файл BKWDATA.", {"report": True}
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return False, f"Не удалось создать каталог отчета: {exc}", {"report": True}
        return True, "", {}

    def _on_pick_export_bkw(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save BKWDATA", self.export_bkwdata.text())
        if path:
            self.export_bkwdata.setText(path)

    def _on_pick_export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save report", self.export_report.text())
        if path:
            self.export_report.setText(path)

    def _on_generate_bkwdata(self) -> None:
        try:
            self._clear_validation_marks()
            ok, msg, ctx = self._validate_before_generate()
            if not ok:
                if ctx.get("source_mode"):
                    self._mark_widget_error(self.source_mode_combo, msg)
                if ctx.get("template"):
                    self._mark_widget_error(self.template_combo, msg)
                if ctx.get("input_bkwdata"):
                    self._mark_widget_error(self.input_bkwdata_edit, msg)
                if ctx.get("mix_basis"):
                    self._mark_widget_error(self.mix_basis, msg)
                if "mix_row" in ctx:
                    self._mark_mix_row_error(int(ctx["mix_row"]), msg)
                if ctx.get("widget") == "gas_db":
                    self._mark_widget_error(self.gas_db_edit, msg)
                if ctx.get("widget") == "solid_db":
                    self._mark_widget_error(self.solid_db_edit, msg)
                if ctx.get("widget") == "gas_custom":
                    self._mark_widget_error(self.gas_custom_edit, msg)
                if ctx.get("widget") == "solid_custom":
                    self._mark_widget_error(self.solid_custom_edit, msg)
                if ctx.get("widget") == "legacy_athrho":
                    self._mark_widget_error(self.legacy_athrho_edit, msg)
                if ctx.get("widget") == "legacy_aispr":
                    self._mark_widget_error(self.legacy_aispr_edit, msg)
                if ctx.get("widget") == "legacy_constants":
                    self._mark_widget_error(self.legacy_constants_edit, msg)
                if ctx.get("widget") == "legacy_twins":
                    self._mark_widget_error(self.legacy_twins_edit, msg)
                QMessageBox.warning(self, "Проверка ввода", msg)
                return
            ok, _m, items, _ctx = self._validate_mix_table()
            if ok:
                self.project.mix = items
                self.project.mix_basis = self.mix_basis.currentText()
                self.project.strict_elements = self.mix_strict.isChecked()
            self.project.template = self.template_combo.currentText().strip()
            self.project.source_mode = self.source_mode_combo.currentText().strip()
            self.project.source_bkwdata = self.input_bkwdata_edit.text().strip()
            self._sync_legacy_from_ui()

            output = self._abs_path(self.export_bkwdata.text().strip() or (PROJECTS_DIR / "BKWDATA"))
            output.parent.mkdir(parents=True, exist_ok=True)
            self.export_bkwdata.setText(str(output))
            argv = self._build_userbkw_argv(output)
            self.log_view.clear()
            self.log_view.appendPlainText("$ userbkw " + " ".join(shlex.quote(x) for x in argv))
            stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
            prev_cwd = Path.cwd()
            try:
                os.chdir(str(RUNTIME_ROOT))
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    rc = userbkw_run_cli(argv)
            except Exception as exc:
                rc = 1
                stderr_buf.write(f"{type(exc).__name__}: {exc}\n")
            finally:
                os.chdir(str(prev_cwd))
            out_text = stdout_buf.getvalue()
            err_text = stderr_buf.getvalue()
            if out_text:
                self.log_view.appendPlainText(out_text)
            if err_text:
                self.log_view.appendPlainText(err_text)
            if rc != 0:
                QMessageBox.critical(self, "BKWDATA", f"Ошибка генерации BKWDATA (code={rc})")
                return
            self.project.last_output_bkwdata = str(output)
            self.calc_status.setText(f"BKWDATA generated: {output}")
            self._refresh_flow_state()
        except Exception as exc:
            QMessageBox.critical(self, "BKWDATA", str(exc))

    def _build_userbkw_argv(self, output: Path) -> list[str]:
        cmd: list[str] = []
        if self.project.source_mode == "import" and self.project.source_bkwdata:
            cmd += ["--input", self.project.source_bkwdata]
        else:
            cmd += ["--template", self.project.template]

        if self.project.legacy_ioeq is not None:
            cmd += ["--set-ioeq", str(self.project.legacy_ioeq)]
        if self.project.legacy_icjc is not None:
            cmd += ["--set-icjc", str(self.project.legacy_icjc)]
        if self.project.legacy_ihug is not None:
            cmd += ["--set-ihug", str(self.project.legacy_ihug)]
        if self.project.legacy_ipvc is not None:
            cmd += ["--set-ipvc", str(self.project.legacy_ipvc)]
        if self.project.legacy_igrp is not None:
            cmd += ["--set-igrp", str(self.project.legacy_igrp)]
        if self.project.legacy_eos_preset and self.project.legacy_eos_preset != "default":
            cmd += ["--legacy-eos-preset", self.project.legacy_eos_preset]
        if self.project.legacy_athrho:
            cmd += ["--legacy-athrho", self.project.legacy_athrho]
        if self.project.legacy_aispr:
            cmd += ["--legacy-aispr", self.project.legacy_aispr]
        for x in self.project.legacy_constants:
            cmd += ["--legacy-var", x]
        for x in self.project.legacy_solid_twins:
            cmd += ["--legacy-solid-twin", x]

        if self.project.mix:
            mix_spec = ",".join(f"{x.name}={x.value:g}" for x in self.project.mix)
            cmd += ["--mix", mix_spec, "--mix-basis", self.project.mix_basis]
            if self.project.strict_elements:
                cmd += ["--strict-elements"]

        for x in self.project.add_gas_db:
            cmd += ["--add-gas-db", x]
        for x in self.project.add_solid_db:
            cmd += ["--add-solid-db", x]
        for x in self.project.add_gas_custom:
            cmd += ["--add-gas-custom", x]
        for x in self.project.add_solid_custom:
            cmd += ["--add-solid-custom", x]

        cmd += ["--output", str(output)]
        return cmd

    def _on_run_calc(self) -> None:
        if self._active_calc_task is not None:
            QMessageBox.information(self, "Run", "Расчет уже выполняется.")
            return
        self._clear_validation_marks()
        ok, msg, ctx = self._validate_before_run()
        if not ok:
            if ctx.get("mode"):
                self._mark_widget_error(self.mode_combo, msg)
            if ctx.get("report"):
                self._mark_widget_error(self.export_report, msg)
            QMessageBox.warning(self, "Run", msg)
            return

        self.project.run_settings = replace(self.project.run_settings, mode=self.mode_combo.currentText())
        report_default = PROJECTS_DIR / ("bkw.out" if self.project.run_settings.mode == "bkw" else "isp.out")
        report = self._abs_path(self.export_report.text().strip() or str(report_default))
        report.parent.mkdir(parents=True, exist_ok=True)
        self.export_report.setText(str(report))

        self.progress.setRange(0, 100)
        self.progress.setValue(1)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.calc_status.setText("Расчет выполняется... (1%)")
        self.log_view.clear()

        task = CalcTask(
            self.runner,
            mode=self.project.run_settings.mode,
            bkwdata_path=self._abs_path(self.project.last_output_bkwdata),
            report_path=report,
        )
        self._active_calc_task = task
        task.signals.log.connect(self.log_view.appendPlainText)
        task.signals.progress.connect(self._on_calc_progress)
        task.signals.failed.connect(self._on_calc_failed)
        task.signals.finished.connect(lambda rc: self._on_calc_finished(rc, report))
        self.thread_pool.start(task)

    def _on_cancel_calc(self) -> None:
        self.runner.cancel()
        self.calc_status.setText("Отмена запрошена")

    def _on_calc_progress(self, pct: int, msg: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, int(pct))))
        self.calc_status.setText(f"{msg} ({int(pct)}%)")

    def _on_calc_failed(self, msg: str) -> None:
        self._active_calc_task = None
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.calc_status.setText("Ошибка расчета")
        QMessageBox.critical(self, "Run failed", msg)

    def _on_calc_finished(self, rc: int, report_path: Path) -> None:
        self._active_calc_task = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if rc == 0 else 0)
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if rc != 0:
            if rc == 124:
                self.calc_status.setText("Расчет прерван по таймауту")
            else:
                self.calc_status.setText(f"Расчет завершен с ошибкой: {rc}")
            return
        self.project.last_output_report = str(report_path)
        self.calc_status.setText(f"Расчет завершен: {report_path}")
        self._load_report_text()
        self._load_result_graphs()
        # One deferred reload makes graph rendering resilient to transient UI timing issues.
        QTimer.singleShot(120, self._load_result_graphs)
        if self.graph_container is not None and self.graph_container.count() == 0:
            h = len(self.last_bkw_tables.hugoniot) if self.last_bkw_tables else 0
            s = len(self.last_bkw_tables.isentrope) if self.last_bkw_tables else 0
            i = len(self.last_isp_points)
            self.calc_status.setText(f"Расчет завершен, но графики не извлечены (hug={h}, iso={s}, isp={i})")
        self._refresh_flow_state()

    def _load_report_text(self) -> None:
        p = self._abs_path(self.project.last_output_report) if self.project.last_output_report else Path("")
        if p.exists():
            self.result_text.setPlainText(p.read_text(encoding="ascii", errors="replace"))

    def _set_result_graphs(self, defs: list[tuple[str, str, str, list[float], list[float]]]) -> None:
        if not self.graph_container or self.pg is None:
            return
        self.graph_container.clear()
        self.graph_widgets = []
        self.graph_meta = []
        for i, (title, xlabel, ylabel, xs, ys) in enumerate(defs, start=1):
            w = self.pg.PlotWidget()
            w.setTitle(title)
            w.setLabel("bottom", xlabel)
            w.setLabel("left", ylabel)
            w.plot(xs, ys, pen="y", symbol="o", symbolSize=5)
            self.graph_container.addTab(w, f"G{i}")
            self.graph_widgets.append(w)
            self.graph_meta.append((title, f"G{i}"))
        has_graphs = self.graph_container.count() > 0
        self.btn_graph_prev.setEnabled(has_graphs)
        self.btn_graph_next.setEnabled(has_graphs)
        self._update_graph_title()

    def _set_isp_summary_graph(self, points: list[IspPoint]) -> None:
        if not self.graph_container or self.pg is None:
            return
        if not points:
            self._set_result_graphs([])
            return
        w = self.pg.PlotWidget()
        w.setTitle("ISP summary: chamber/exhaust")
        w.setLabel("bottom", "State")
        w.setLabel("left", "Value")
        w.addLegend(offset=(10, 10))

        x = list(range(len(points)))
        ticks = [[(i, p.state) for i, p in enumerate(points)]]
        w.getAxis("bottom").setTicks(ticks)
        w.plot(x, [p.pressure_bars for p in points], pen="y", symbol="o", name="Pressure (bar)")
        w.plot(x, [p.isp for p in points], pen="c", symbol="t", name="ISP")
        w.plot(x, [p.temperature_k for p in points], pen="m", symbol="s", name="Temperature (K)")
        w.plot(x, [p.volume_cc_gm for p in points], pen="g", symbol="d", name="Volume (cc/gm)")

        self.graph_container.clear()
        self.graph_container.addTab(w, "G1")
        self.graph_widgets = [w]
        self.graph_meta = [("ISP summary: chamber/exhaust", "G1")]
        self.btn_graph_prev.setEnabled(True)
        self.btn_graph_next.setEnabled(True)
        self._update_graph_title()

    def _fallback_parse_bkw_tables(self, text: str) -> tuple[list[tuple[float, float, float, float, float]], list[tuple[float, float, float, float, float, float]]]:
        hug: list[tuple[float, float, float, float, float]] = []
        iso: list[tuple[float, float, float, float, float, float]] = []
        lines = text.splitlines()

        # Hugoniot fallback: parse two-line blocks "Pressure=... Volume=... Temperature=..." + next "Shock Velocity... Particle Velocity..."
        for i in range(len(lines) - 1):
            l1 = lines[i]
            l2 = lines[i + 1]
            if "Pressure" in l1 and "Volume" in l1 and "Temperature" in l1 and "Shock Velocity" in l2 and "Particle Velocity" in l2:
                n1 = [float(x.replace("D", "E").replace("d", "e")) for x in self._F_RE.findall(l1)]
                n2 = [float(x.replace("D", "E").replace("d", "e")) for x in self._F_RE.findall(l2)]
                if len(n1) >= 3 and len(n2) >= 2:
                    hug.append((n1[0], n1[1], n1[2], n2[0], n2[1]))

        # Isentrope fallback: find block after the known header and collect 6-column numeric lines.
        start = -1
        end = len(lines)
        for i, ln in enumerate(lines):
            if "Pressure (mb)" in ln and "Part Vel" in ln:
                start = i + 1
                break
        if start >= 0:
            for j in range(start, len(lines)):
                if "least squares fit" in lines[j]:
                    end = j
                    break
            for ln in lines[start:end]:
                vals = [float(x.replace("D", "E").replace("d", "e")) for x in self._F_RE.findall(ln)]
                if len(vals) >= 6:
                    iso.append((vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]))
        return hug, iso

    def _load_result_graphs(self) -> None:
        if not self.graph_container:
            return
        p = self._abs_path(self.project.last_output_report) if self.project.last_output_report else Path("")
        if not p.exists():
            self.last_bkw_tables = None
            self.last_isp_points = []
            self._set_result_graphs([])
            return

        text = p.read_text(encoding="ascii", errors="replace")
        self.last_bkw_tables = parse_bkw_tables(text)
        self.last_isp_points = parse_isp_summary(text)
        if not self.last_bkw_tables.hugoniot and not self.last_bkw_tables.isentrope:
            fh, fi = self._fallback_parse_bkw_tables(text)
            if fh or fi:
                self.last_bkw_tables = BkwTables(hugoniot=fh, isentrope=fi)

        defs: list[tuple[str, str, str, list[float], list[float]]] = []
        if self.last_bkw_tables.hugoniot:
            h = self.last_bkw_tables.hugoniot
            defs.append(("Hugoniot P-V", "V (cc/g)", "P (mb)", [r[1] for r in h], [r[0] for r in h]))
            defs.append(("Hugoniot P-T", "T (K)", "P (mb)", [r[2] for r in h], [r[0] for r in h]))
        if self.last_bkw_tables.isentrope:
            s = self.last_bkw_tables.isentrope
            defs.append(("Isentrope P-V", "V (cc/g)", "P (mb)", [r[1] for r in s], [r[0] for r in s]))
            defs.append(("Isentrope P-T", "T (K)", "P (mb)", [r[2] for r in s], [r[0] for r in s]))
            defs.append(("Isentrope P-u", "u", "P (mb)", [r[5] for r in s], [r[0] for r in s]))

        if defs:
            self._set_result_graphs(defs)
        elif self.last_isp_points:
            self._set_isp_summary_graph(self.last_isp_points)
        else:
            self._set_result_graphs([])

    def _on_graph_prev(self) -> None:
        if not self.graph_container:
            return
        n = self.graph_container.count()
        if n <= 0:
            self.graph_title.setText("Graph 0/0")
            return
        i = self.graph_container.currentIndex()
        if i < 0:
            i = 0
        self.graph_container.setCurrentIndex((i - 1) % n)
        self._update_graph_title()

    def _on_graph_next(self) -> None:
        if not self.graph_container:
            return
        n = self.graph_container.count()
        if n <= 0:
            self.graph_title.setText("Graph 0/0")
            return
        i = self.graph_container.currentIndex()
        if i < 0:
            i = 0
        self.graph_container.setCurrentIndex((i + 1) % n)
        self._update_graph_title()

    def _update_graph_title(self) -> None:
        if not self.graph_container:
            return
        n = self.graph_container.count()
        if n == 0:
            self.graph_title.setText("Graph 0/0")
            return
        i = self.graph_container.currentIndex()
        title = self.graph_meta[i][0] if i < len(self.graph_meta) else ""
        self.graph_title.setText(f"Graph {i+1}/{n}: {title}")

    def _on_export_csv(self) -> None:
        report = Path(self.project.last_output_report) if self.project.last_output_report else None
        if not report or not report.exists():
            QMessageBox.warning(self, "CSV", "Нет отчета для экспорта. Сначала выполните расчет.")
            return
        self._load_result_graphs()
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для CSV", str(PROJECTS_DIR))
        if not out_dir:
            return
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        exported: list[Path] = []
        if self.last_bkw_tables and self.last_bkw_tables.hugoniot:
            p = out / "hugoniot.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["pressure_mb", "volume_cc_g", "temperature_k", "shock_velocity", "particle_velocity"])
                w.writerows(self.last_bkw_tables.hugoniot)
            exported.append(p)
        if self.last_bkw_tables and self.last_bkw_tables.isentrope:
            p = out / "isentrope.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["pressure_mb", "volume_cc_g", "temperature_k", "energy_plus_c", "gamma", "particle_velocity"])
                w.writerows(self.last_bkw_tables.isentrope)
            exported.append(p)
        if self.last_isp_points:
            p = out / "isp_summary.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["state", "pressure_bars", "isp", "temperature_k", "volume_cc_gm"])
                for x in self.last_isp_points:
                    w.writerow([x.state, x.pressure_bars, x.isp, x.temperature_k, x.volume_cc_gm])
            exported.append(p)

        if not exported:
            QMessageBox.warning(self, "CSV", "Табличные данные не найдены в отчете.")
            return
        QMessageBox.information(self, "CSV", "Экспортировано:\n" + "\n".join(str(x) for x in exported))

    def _on_export_png(self) -> None:
        if not self.graph_container or self.graph_container.count() == 0:
            QMessageBox.warning(self, "PNG", "Нет графиков для экспорта.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для PNG", str(PROJECTS_DIR))
        if not out_dir:
            return
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        export_all = QMessageBox.question(
            self,
            "PNG",
            "Экспортировать все графики? (Нет = только текущий)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) == QMessageBox.Yes

        targets = list(range(self.graph_container.count())) if export_all else [self.graph_container.currentIndex()]
        exported: list[Path] = []
        for i in targets:
            w = self.graph_container.widget(i)
            if w is None:
                continue
            title = self.graph_meta[i][0] if i < len(self.graph_meta) else f"graph_{i+1}"
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_") or f"graph_{i+1}"
            p = out / f"{i+1:02d}_{safe}.png"
            ok = w.grab().save(str(p))
            if ok:
                exported.append(p)

        if not exported:
            QMessageBox.warning(self, "PNG", "Экспорт не выполнен.")
            return
        QMessageBox.information(self, "PNG", "Экспортировано:\n" + "\n".join(str(x) for x in exported))

    # -------------------- TDF --------------------
    def _tdf_out_path(self) -> Path:
        return TDF_ENGINE_DIR / "tdf.out"

    def _tdf_input_path(self) -> Path:
        return TDF_ENGINE_DIR / "tdfdata"

    def _tdf_input_default_path(self) -> Path:
        return TDF_ENGINE_DIR / "tdfdata.default"

    def _load_tdf_curves(self) -> None:
        out = self._tdf_out_path()
        self.tdf_curve_picker.blockSignals(True)
        self.tdf_curve_picker.clear()
        self.tdf_curves = []
        self.tdf_plot_images = []
        if out.exists():
            self.tdf_curves = parse_tdf_out(out)
            self.tdf_plot_images = tdf_plot_image_paths(out, self.tdf_curves)
            for i, c in enumerate(self.tdf_curves):
                self.tdf_curve_picker.addItem(f"{i+1:02d}. {c.title}", i)
        self.tdf_curve_picker.blockSignals(False)
        if self.tdf_curve_picker.count() > 0:
            self.tdf_curve_picker.setCurrentIndex(0)
            self._show_tdf_curve(0)
        else:
            self.tdf_status.setText("TDF: нет кривых. Нажмите 'Запустить TDF'.")
            if self.tdf_plot:
                self.tdf_plot.clear()
            if self.tdf_plot_label:
                self.tdf_plot_label.setPixmap(QPixmap())
                self.tdf_plot_label.setText("PNG-графики TDF не найдены. Нажмите 'Запустить TDF'.")

    def _load_tdf_input_from_engine(self) -> None:
        src = self._tdf_input_path()
        if src.exists():
            txt = src.read_text(encoding="ascii", errors="replace")
            self.tdf_input_editor.setPlainText(txt)
            self.tdf_status.setText("TDF: input загружен")

        # First run bootstrap for reset button.
        dflt = self._tdf_input_default_path()
        if src.exists() and not dflt.exists():
            dflt.write_text(src.read_text(encoding="ascii", errors="replace"), encoding="ascii")

    def _refresh_tdf_mat_table(self) -> None:
        self.tdf_mat_table.setRowCount(0)
        for m in self.tdf_deck.materials:
            r = self.tdf_mat_table.rowCount()
            self.tdf_mat_table.insertRow(r)
            self.tdf_mat_table.setItem(r, 0, QTableWidgetItem(m.marker))
            self.tdf_mat_table.setItem(r, 1, QTableWidgetItem(m.code))
            self.tdf_mat_table.setItem(r, 2, QTableWidgetItem(m.name))
            self.tdf_mat_table.setItem(r, 3, QTableWidgetItem(m.comment))
        if self.tdf_mat_table.rowCount() > 0 and self.tdf_mat_table.currentRow() < 0:
            self.tdf_mat_table.setCurrentCell(0, 0)

    def _tdf_material_from_form(self) -> TdfMaterial:
        return TdfMaterial(
            marker=self.tdf_mat_marker.text().strip() or "***",
            code=self.tdf_mat_code.text().strip(),
            name=self.tdf_mat_name.text().strip(),
            comment=self.tdf_mat_comment.text().strip(),
            nline=self.tdf_mat_nline.text(),
            body_lines=self.tdf_mat_body.toPlainText().splitlines(),
        )

    def _tdf_set_form(self, m: TdfMaterial) -> None:
        self.tdf_mat_marker.setText(m.marker)
        self.tdf_mat_code.setText(m.code)
        self.tdf_mat_name.setText(m.name)
        self.tdf_mat_comment.setText(m.comment)
        self.tdf_mat_nline.setText(m.nline)
        self.tdf_mat_body.setPlainText("\n".join(m.body_lines))

    def _on_tdf_mat_select(self) -> None:
        r = self.tdf_mat_table.currentRow()
        if r < 0 or r >= len(self.tdf_deck.materials):
            return
        self._tdf_set_form(self.tdf_deck.materials[r])

    def _on_tdf_mat_add(self) -> None:
        self.tdf_deck.materials.append(
            TdfMaterial(marker="***", code="NEW", name="Material", comment="", nline="    1", body_lines=["+1.0"])
        )
        self._refresh_tdf_mat_table()
        self.tdf_mat_table.setCurrentCell(self.tdf_mat_table.rowCount() - 1, 0)
        self._on_tdf_struct_to_text()

    def _on_tdf_mat_del(self) -> None:
        r = self.tdf_mat_table.currentRow()
        if r < 0 or r >= len(self.tdf_deck.materials):
            return
        del self.tdf_deck.materials[r]
        self._refresh_tdf_mat_table()
        self._on_tdf_struct_to_text()

    def _on_tdf_mat_apply(self) -> None:
        r = self.tdf_mat_table.currentRow()
        if r < 0 or r >= len(self.tdf_deck.materials):
            QMessageBox.warning(self, "TDF forms", "Выберите материал в таблице.")
            return
        m = self._tdf_material_from_form()
        if not m.code.strip():
            QMessageBox.warning(self, "TDF forms", "Код материала не должен быть пустым.")
            return
        if not m.nline.strip():
            QMessageBox.warning(self, "TDF forms", "nline не должен быть пустым.")
            return
        self.tdf_deck.materials[r] = m
        self._refresh_tdf_mat_table()
        self.tdf_mat_table.setCurrentCell(r, 0)
        self._on_tdf_struct_to_text()

    def _on_tdf_struct_from_text(self) -> None:
        txt = self.tdf_input_editor.toPlainText()
        ok, msg = self._validate_tdf_input_text(txt)
        if not ok:
            QMessageBox.warning(self, "TDF forms", msg)
            return
        self.tdf_deck = parse_tdfdata_text(txt)
        errs = validate_tdf_deck(self.tdf_deck)
        self._refresh_tdf_mat_table()
        if errs:
            self.tdf_status.setText(f"TDF forms: разобрано {len(self.tdf_deck.materials)} материалов, ошибок: {len(errs)}")
            QMessageBox.warning(self, "TDF forms", "Найдены проблемы структуры:\n" + "\n".join(errs[:8]))
        else:
            self.tdf_status.setText(f"TDF forms: разобрано материалов {len(self.tdf_deck.materials)}")

    def _on_tdf_struct_to_text(self) -> None:
        if not self.tdf_deck.materials:
            QMessageBox.warning(self, "TDF forms", "Нет материалов для генерации.")
            return
        errs = validate_tdf_deck(self.tdf_deck)
        if errs:
            QMessageBox.warning(self, "TDF forms", "Исправьте ошибки перед генерацией:\n" + "\n".join(errs[:8]))
            return
        txt = render_tdfdata_text(self.tdf_deck)
        self.tdf_input_editor.setPlainText(txt)
        self.tdf_status.setText("TDF forms: tdfdata сгенерирован из структурной формы")

    def _validate_tdf_input_text(self, text: str) -> tuple[bool, str]:
        if not text.strip():
            return False, "tdfdata пуст."
        # very lightweight sanity check for known deck style
        has_material_marker = ("***" in text) or ("O2  Diatomic" in text)
        if not has_material_marker:
            return False, "В tdfdata не найдены заголовки материалов."
        return True, ""

    def _on_tdf_open_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть tdfdata", str(TDF_ENGINE_DIR))
        if not path:
            return
        p = Path(path)
        self.tdf_input_editor.setPlainText(p.read_text(encoding="ascii", errors="replace"))
        self.tdf_input_path.setText(str(p))
        self._on_tdf_struct_from_text()
        self.tdf_status.setText(f"TDF input загружен из: {p}")

    def _on_tdf_save_input(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить tdfdata", str(TDF_ENGINE_DIR / "tdfdata.custom"))
        if not path:
            return
        txt = self.tdf_input_editor.toPlainText()
        ok, msg = self._validate_tdf_input_text(txt)
        if not ok:
            QMessageBox.warning(self, "TDF input", msg)
            return
        Path(path).write_text(txt, encoding="ascii")
        self.tdf_status.setText(f"TDF input сохранен: {path}")

    def _on_tdf_apply_input(self) -> None:
        txt = self.tdf_input_editor.toPlainText()
        ok, msg = self._validate_tdf_input_text(txt)
        if not ok:
            QMessageBox.warning(self, "TDF input", msg)
            return
        self._tdf_input_path().write_text(txt, encoding="ascii")
        self._on_tdf_struct_from_text()
        self.tdf_input_path.setText(str(self._tdf_input_path()))
        self.tdf_status.setText("TDF input применен в tdf_engine/tdfdata")

    def _on_tdf_reset_input(self) -> None:
        dflt = self._tdf_input_default_path()
        if not dflt.exists():
            QMessageBox.warning(self, "TDF input", "Исходный tdfdata.default не найден.")
            return
        txt = dflt.read_text(encoding="ascii", errors="replace")
        self.tdf_input_editor.setPlainText(txt)
        self._tdf_input_path().write_text(txt, encoding="ascii")
        self._on_tdf_struct_from_text()
        self.tdf_input_path.setText(str(self._tdf_input_path()))
        self.tdf_status.setText("TDF input сброшен к исходному")

    def _show_tdf_curve(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.tdf_curves):
            return
        c = self.tdf_curves[idx]
        if self.tdf_plot:
            self.tdf_plot.clear()
            self.tdf_plot.setTitle(c.title)
            self.tdf_plot.setLabel("bottom", c.xlabel)
            self.tdf_plot.setLabel("left", c.ylabel)
            self.tdf_plot.plot(c.x, c.y, pen="y")
            self.tdf_status.setText(f"TDF кривая {idx+1}/{len(self.tdf_curves)}: {c.title}")
        elif self.tdf_plot_label:
            image_path = self.tdf_plot_images[idx] if idx < len(self.tdf_plot_images) else None
            if image_path is None:
                self.tdf_plot_label.setPixmap(QPixmap())
                self.tdf_plot_label.setText(f"PNG-график для кривой не найден: {c.title}")
            else:
                pixmap = QPixmap(str(image_path))
                if pixmap.isNull():
                    self.tdf_plot_label.setPixmap(QPixmap())
                    self.tdf_plot_label.setText(f"Не удалось открыть PNG-график: {image_path}")
                else:
                    self.tdf_plot_label.setText("")
                    self.tdf_plot_label.setPixmap(
                        pixmap.scaled(
                            self.tdf_plot_label.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
            self.tdf_status.setText(f"TDF PNG {idx+1}/{len(self.tdf_curves)}: {c.title}")

    def _on_tdf_curve_changed(self, idx: int) -> None:
        self._show_tdf_curve(idx)

    def _on_tdf_prev(self) -> None:
        n = self.tdf_curve_picker.count()
        if n == 0:
            return
        i = self.tdf_curve_picker.currentIndex()
        self.tdf_curve_picker.setCurrentIndex((i - 1) % n)

    def _on_tdf_next(self) -> None:
        n = self.tdf_curve_picker.count()
        if n == 0:
            return
        i = self.tdf_curve_picker.currentIndex()
        self.tdf_curve_picker.setCurrentIndex((i + 1) % n)

    def _on_run_tdf(self) -> None:
        if self._active_tdf_task is not None:
            QMessageBox.information(self, "TDF", "TDF уже выполняется.")
            return
        # Always use the current editor text for run.
        txt = self.tdf_input_editor.toPlainText()
        ok, msg = self._validate_tdf_input_text(txt)
        if not ok:
            QMessageBox.warning(self, "TDF input", msg)
            return
        deck = parse_tdfdata_text(txt)
        errs = validate_tdf_deck(deck)
        if errs:
            QMessageBox.warning(self, "TDF input", "Ошибка структуры TDF:\n" + "\n".join(errs[:10]))
            return
        self.tdf_deck = deck
        self._refresh_tdf_mat_table()
        self._tdf_input_path().write_text(txt, encoding="ascii")

        self.btn_tdf_run.setEnabled(False)
        self.btn_tdf_cancel.setEnabled(True)
        self.tdf_status.setText("TDF: выполняется...")
        self.tdf_log.clear()

        task = TdfTask(self.tdf_runner)
        self._active_tdf_task = task
        task.signals.log.connect(self.tdf_log.appendPlainText)
        task.signals.progress.connect(self._on_tdf_progress)
        task.signals.failed.connect(self._on_tdf_failed)
        task.signals.finished.connect(self._on_tdf_finished)
        self.thread_pool.start(task)

    def _on_cancel_tdf(self) -> None:
        self.tdf_runner.cancel()
        self.tdf_status.setText("TDF: запрос на отмену отправлен.")

    def _on_tdf_progress(self, pct: int, msg: str) -> None:
        self.tdf_status.setText(f"{msg} ({int(pct)}%)")

    def _on_tdf_failed(self, msg: str) -> None:
        self._active_tdf_task = None
        self.btn_tdf_run.setEnabled(True)
        self.btn_tdf_cancel.setEnabled(False)
        self.tdf_status.setText("TDF: ошибка")
        QMessageBox.critical(self, "TDF", msg)

    def _on_tdf_finished(self, rc: int) -> None:
        self._active_tdf_task = None
        self.btn_tdf_run.setEnabled(True)
        self.btn_tdf_cancel.setEnabled(False)
        if rc != 0:
            if rc == 124:
                self.tdf_status.setText("TDF: прерван по таймауту")
            else:
                self.tdf_status.setText(f"TDF: завершен с ошибкой {rc}")
            return
        self.tdf_status.setText("TDF: завершен успешно")
        self._load_tdf_curves()
