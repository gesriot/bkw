import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bkw_py.io.bkwdata import load_bkwdata


def test_stage6_userbkw_mix_from_zzzcomps():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_mix_", dir=str(repo)))
    out = tdir / "BKWDATA.mix"
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--mix",
                "rdx=60,tnt=40",
                "--mix-basis",
                "wt",
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
        assert d.amolwt > 200.0
        assert 1.5 < d.rho < 1.9
        assert d.eo > 0.0
        # CHNO template should have non-zero C/H/N/O after mixing.
        assert d.elem[0] > 0.0
        assert d.elem[1] > 0.0
        assert d.elem[2] > 0.0
        assert d.elem[3] > 0.0
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_stage6_userbkw_explicit_basic_overrides_win_after_mix():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_mix_override_", dir=str(repo)))
    out = tdir / "BKWDATA.mix"
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--mix",
                "rdx=100",
                "--set-label",
                "RDX rho=1.72",
                "--set-rho",
                "1.72",
                "--set-temp",
                "2500",
                "--set-press",
                "0.3",
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
        assert d.label.strip() == "RDX rho=1.72"
        assert d.rho == 1.72
        assert d.temp == 2500.0
        assert d.press == 0.3
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
