import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bkw_py.io.bkwdata import load_bkwdata


def _run(cmd: list[str], repo: Path, timeout: int = 120, stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(repo),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_stage6_legacy_page1_page2_parity_core():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_legacy01_", dir=str(repo)))
    out = tdir / "BKWDATA.legacy01"
    try:
        # Flow:
        # - legacy page1: set through=2 (ipvc=2), toggle graph
        # - legacy page2: choose RDX preset
        # - save + exit
        script_input = "\n".join(
            [
                "12",   # legacy page1
                "4", "2",
                "5",
                "+",
                "13",   # legacy page2
                "1",
                "+",
                "7",
                str(out),
                "none",
                "0",
            ]
        ) + "\n"

        cp = _run(
            [sys.executable, str(repo / "bkw_py" / "userbkw.py"), "--template", "CHNO", "--interactive"],
            repo,
            timeout=240,
            stdin_text=script_input,
        )
        assert cp.returncode == 0, cp.stderr
        assert out.exists() and out.stat().st_size > 0

        d = load_bkwdata(out)
        assert d.ipvc == 2
        assert d.igrp in {1, 2}
        assert abs(d.alpha - 0.5) < 1.0e-12
        assert abs(d.beta - 0.16) < 1.0e-12
        assert abs(d.theta - 400.0) < 1.0e-12
        assert abs(d.kappa - 10.9097784436) < 1.0e-8
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
