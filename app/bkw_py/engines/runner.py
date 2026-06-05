"""Run a native engine as a headless subprocess.

The engines use fixed lowercase filenames in their working directory
(e.g. BKW reads ``bkwdata`` and writes ``bkw.out``).

- ``run_fixed_io`` runs in a fresh temp directory and copies one input in and
  one output out so engine state never leaks between runs.
- ``run_in_dir`` runs the engine in an existing directory whose inputs and
  outputs already live there — used by TDF (its engine directory is
  persistent and holds tdfdata/tdf.out/scoef together).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from bkw_py._cancel import CancelledError

from .paths import resolve_engine

_POLL_SEC = 0.1
_TERM_GRACE_SEC = 5.0


def _log(on_log: Callable[[str], None] | None, msg: str) -> None:
    if on_log is not None:
        on_log(msg)


def _run_process(
    exe: Path,
    workdir: Path,
    *,
    on_log: Callable[[str], None] | None,
    cancel_event: threading.Event | None,
    timeout_sec: float | None,
) -> int:
    """Run ``exe`` in ``workdir``; stream stdout to ``on_log``; honor cancellation."""
    _log(on_log, f"engine={exe} workdir={workdir}")
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def _drain() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            _log(on_log, line.rstrip("\n"))

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()

    deadline = (time.monotonic() + timeout_sec) if timeout_sec else None
    cancelled = False
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        if deadline is not None and time.monotonic() > deadline:
            cancelled = True
            break
        time.sleep(_POLL_SEC)

    if cancelled:
        proc.terminate()
        try:
            proc.wait(timeout=_TERM_GRACE_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=_TERM_GRACE_SEC)
        raise CancelledError(f"{exe.name} run cancelled")

    rc = proc.wait()
    reader.join(timeout=_TERM_GRACE_SEC)
    return rc


def run_fixed_io(
    engine: str,
    *,
    input_path: str | Path,
    input_name: str,
    output_name: str,
    output_path: str | Path,
    on_log: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: float | None = None,
) -> int:
    """Run ``engine`` on ``input_path`` in a temp dir, returning ``output_name``.

    Parameters
    ----------
    engine       : engine base name, e.g. ``"abbkw"``.
    input_path   : source file to feed the engine.
    input_name   : filename the engine expects to read (e.g. ``"bkwdata"``).
    output_name  : filename the engine writes (e.g. ``"bkw.out"``).
    output_path  : where to copy the produced output.
    cancel_event : if set during the run, the process is terminated and
                   ``CancelledError`` is raised.
    timeout_sec  : optional wall-clock limit; on expiry the run is cancelled.
    """
    exe = resolve_engine(engine)
    workdir = Path(tempfile.mkdtemp(prefix=f"{engine}_"))
    try:
        shutil.copy2(str(input_path), str(workdir / input_name))
        rc = _run_process(
            exe, workdir, on_log=on_log, cancel_event=cancel_event, timeout_sec=timeout_sec
        )
        produced = workdir / output_name
        if produced.is_file() and produced.stat().st_size > 0:
            Path(output_path).write_bytes(produced.read_bytes())
        elif rc == 0:
            _log(on_log, f"engine produced no {output_name}")
            return 1
        return rc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_in_dir(
    engine: str,
    *,
    workdir: str | Path,
    on_log: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: float | None = None,
    extra_engine_dirs: Iterable[str | Path] | None = None,
) -> int:
    """Run ``engine`` in ``workdir``; its inputs/outputs already live there."""
    exe = resolve_engine(engine, extra_dirs=extra_engine_dirs)
    return _run_process(
        exe, Path(workdir), on_log=on_log, cancel_event=cancel_event, timeout_sec=timeout_sec
    )
