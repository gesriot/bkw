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


def test_stage6_legacy_page5_page6_constants():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_legacy56_", dir=str(repo)))
    out = tdir / "BKWDATA.legacy56"
    try:
        # Flow:
        # - legacy page5: set extra densities and aispr
        # - legacy page6: set const 1 then reset to original, set const 29
        # - save without run
        script_input = "\n".join(
            [
                "10",       # legacy page5
                "1", "1.90",
                "2", "2.10",
                "2", "0",   # remove slot 2 as in reference logic
                "5", "0.222",
                "+",
                "11",       # legacy page6 constants
                "1", "16.0",
                "1", "-1",  # restore original for #1
                "29", "1.25",
                "+",
                "7",
                str(out),
                "none",
                "0",
            ]
        ) + "\n"

        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--set-ipvc",
                "2",  # ensure aispr gets serialized
                "--interactive",
            ],
            repo,
            timeout=240,
            stdin_text=script_input,
        )
        assert cp.returncode == 0, cp.stderr
        assert out.exists() and out.stat().st_size > 0

        d = load_bkwdata(out)
        assert d.irho == 1
        assert len(d.athrho) == 1
        assert abs(d.athrho[0] - 1.90) < 1.0e-12
        assert d.ipvc == 2
        assert abs(d.aispr - 0.222) < 1.0e-12

        # #1 was reset to default, so only #29 override should remain.
        assert d.iext == 1
        assert d.novar == [29]
        assert len(d.var) == 1
        assert abs(d.var[0] - 1.25) < 1.0e-12
    finally:
        shutil.rmtree(tdir, ignore_errors=True)

