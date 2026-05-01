from __future__ import annotations

import os
import threading
from typing import Callable

from bkw_py import tdf
from bkw_py._cancel import CancelledError

from ..paths import LOG_DIR, TDF_ENGINE_DIR


class TdfRunner:
    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._timeout_sec = int(os.environ.get("BKW_UI_TDF_TIMEOUT_SEC", "1800"))

    def cancel(self) -> None:
        self._cancel.set()

    def run(
        self,
        *,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        timeout_sec: int | None = None,
    ) -> int:
        self._cancel.clear()

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "tdf.log"
        deadline = float(timeout_sec if timeout_sec is not None else self._timeout_sec)
        timeout_timer = threading.Timer(deadline, self._cancel.set)
        timeout_timer.daemon = True

        with open(log_file, "w", encoding="utf-8") as lf:
            log_lock = threading.Lock()

            def emit(msg: str) -> None:
                with log_lock:
                    lf.write(msg + "\n")
                    lf.flush()
                if on_log is not None:
                    on_log(msg)

            emit(f"RUN: in-process tdf working_dir={TDF_ENGINE_DIR}")
            emit(f"timeout_sec={int(deadline)}")
            if on_progress is not None:
                on_progress(2, "Запуск TDF")

            timeout_timer.start()
            try:
                rc = tdf.run(TDF_ENGINE_DIR, on_log=emit, cancel_event=self._cancel)
            except CancelledError:
                rc = 124
                emit("cancelled or timed out")
            except Exception as exc:
                rc = 1
                emit(f"tdf error: {exc}")
            finally:
                timeout_timer.cancel()

            emit(f"exit_code={rc}")
            if on_progress is not None:
                if rc == 0:
                    on_progress(100, "TDF завершен")
                elif rc == 124:
                    on_progress(0, "TDF отменен")
                else:
                    on_progress(0, "TDF завершен с ошибкой")
            return rc
