from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from bkw_py import bkw, ispbkw
from bkw_py._cancel import CancelledError

from ..paths import LOG_DIR


class CalcRunner:
    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._timeout_sec = int(os.environ.get("BKW_UI_CALC_TIMEOUT_SEC", "1800"))

    def cancel(self) -> None:
        self._cancel.set()

    def run(
        self,
        *,
        mode: str,
        bkwdata_path: Path,
        report_path: Path,
        on_log: Callable[[str], None],
        on_progress: Callable[[int, str], None] | None = None,
        timeout_sec: int | None = None,
    ) -> int:
        self._cancel.clear()
        engine_run = bkw.run if mode == "bkw" else ispbkw.run

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "app.log"
        deadline = float(timeout_sec if timeout_sec is not None else self._timeout_sec)
        timeout_timer = threading.Timer(deadline, self._cancel.set)
        timeout_timer.daemon = True

        with open(log_file, "w", encoding="utf-8") as lf:
            log_lock = threading.Lock()

            def emit(msg: str) -> None:
                with log_lock:
                    lf.write(msg + "\n")
                    lf.flush()
                on_log(msg)

            emit(f"RUN: in-process {mode} input={bkwdata_path} output={report_path}")
            emit(f"timeout_sec={int(deadline)}")
            if on_progress:
                on_progress(2, "Запуск процесса")

            timeout_timer.start()
            try:
                rc = engine_run(
                    bkwdata_path,
                    report_path,
                    on_log=emit,
                    cancel_event=self._cancel,
                )
            except CancelledError:
                rc = 124
                emit("cancelled or timed out")
            except Exception as exc:
                rc = 1
                emit(f"engine error: {exc}")
            finally:
                timeout_timer.cancel()

            emit(f"exit_code={rc}")
            if on_progress:
                if rc == 0:
                    on_progress(100, "Завершено")
                elif rc == 124:
                    on_progress(0, "Отменено")
                else:
                    on_progress(0, "Завершено с ошибкой")
            return rc
