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


def test_stage6_legacy_page3b_deep_edit_subset():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_legacy3b_", dir=str(repo)))
    out = tdir / "BKWDATA.legacy3b"
    try:
        # Edits:
        # - species h2o THERC[1]
        # - stoichiometric coefficient for element c in species #1
        # - element moles for c
        # - guess for species #1
        script_input = "\n".join(
            [
                "14",           # legacy page3b
                "2",            # edit species THERC/SOLEQ
                "h2o",
                "2",            # THERC A
                "4.300000E+01",
                "3",            # edit aik
                "c",
                "2",            # species #1 (menu is 1=all,2=first species)
                "0.123",
                "4",            # edit elem moles
                "2",            # first element
                "3.14159",
                "5",            # edit guesses
                "2",            # first species
                "0.22222",
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
        i_h2o = [x.strip().lower() for x in d.nam].index("h2o")
        assert abs(d.therc[i_h2o][0] - 43.0) < 1.0e-8
        assert abs(d.aik[0][0] - 0.123) < 1.0e-10
        assert abs(d.elem[0] - 3.14159) < 1.0e-10
        assert abs(d.x[0] - 0.22222) < 1.0e-10
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_stage6_legacy_page3b_twin_and_retry_paths():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_legacy3b_twin_", dir=str(repo)))
    out = tdir / "BKWDATA.legacy3b.twin"
    try:
        script_input = "\n".join(
            [
                "14",           # legacy page3b
                "6",            # edit twin
                "",             # invalid empty -> retry
                "sol c",        # solid species in CHNO template
                "solx",         # new second name for solid
                "5",            # edit guesses (exercise retry)
                "x",            # invalid choice -> retry
                "2",            # first species
                "0.11111",
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
        assert "solx" in [x.strip().lower() for x in d.nams]
        assert abs(d.x[0] - 0.11111) < 1.0e-10
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
