import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

from bkw_py.io.bkwdata import load_bkwdata


def test_stage6_userbkw_cli_noninteractive():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_stage6_", dir=str(repo)))
    out = tdir / "BKWDATA.out"
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--set-label",
                "stage6 test",
                "--set-ioeq",
                "2",
                "--set-temp",
                "3333",
                "--output",
                str(out),
            ],
            cwd=str(repo),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )

        d = load_bkwdata(out)
        assert d.label.strip().startswith("stage6")
        assert d.ioeq == 2
        assert abs(d.temp - 3333.0) < 1.0e-8
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
