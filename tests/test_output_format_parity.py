import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REFERENCE_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (REFERENCE_ROOT / "bkw").exists() or not (REFERENCE_ROOT / "ispbkw").exists(),
    reason="reference Fortran tree absent",
)

RE_E = r"[+-]?\d\.\d+E[+-]\d+"
RE_6E_ROW = re.compile(rf"^\s*{RE_E}\s+{RE_E}\s+{RE_E}\s+{RE_E}\s+{RE_E}\s+{RE_E}\s*$")


def _run_reference_bkw(repo: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="fmt_bkw_f_", dir=str(repo)))
    try:
        rt = tdir / "bkw_runtime"
        shutil.copytree(repo / "bkw", rt)
        subprocess.run(
            [str(rt / "abbkw.exe")],
            cwd=str(rt),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        out = rt / "bkw.out"
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("reference bkw run did not produce bkw.out")
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def _run_reference_isp(repo: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="fmt_isp_f_", dir=str(repo)))
    try:
        rt = tdir / "isp_runtime"
        shutil.copytree(repo / "ispbkw", rt)
        subprocess.run(
            [str(rt / "abispbkw.exe")],
            cwd=str(rt),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        out = rt / "isp.out"
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("reference isp run did not produce isp.out")
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def _run_python_bkw(repo: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="fmt_bkw_py_", dir=str(repo)))
    out = tdir / "bkw_py.out"
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "bkw_py" / "bkw.py"),
                "--input",
                str(repo / "bkw" / "BKWDATA"),
                "--output",
                str(out),
            ],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=True,
        )
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def _run_python_isp(repo: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="fmt_isp_py_", dir=str(repo)))
    out = tdir / "isp_py.out"
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "bkw_py" / "ispbkw.py"),
                "--input",
                str(repo / "ispbkw" / "bkwdata"),
                "--output",
                str(out),
            ],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=True,
        )
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def _assert_ordered_markers(text: str, markers: list[str]) -> None:
    low = text.lower()
    pos = -1
    for m in markers:
        p = low.find(m.lower(), pos + 1)
        assert p >= 0, f"marker not found: {m}"
        pos = p


def test_bkw_output_format_parity():
    repo = Path(__file__).resolve().parents[1]
    ftxt = _run_reference_bkw(repo)
    ptxt = _run_python_bkw(repo)

    # Key section markers and ordering expected by downstream parsers.
    markers = [
        "BKW Calculation for the Explosive",
        "The Computed CJ Pressure is",
        "The Computed Detonation Velocity is",
        "The Computed CJ Temperature is",
        "The Computed CJ Volume",
        "The C-J Composition of the Detonation Products",
        "The BKW Hugoniot for the Detonation Products of",
        "Pressure =",
        "A BKW Isentrope thru BKW CJ Pressure for",
        "Pressure (mb) Volume (c/g) Temperature(k) Energy+c   Gamma      Part Vel",
        "The isentrope state variables as computed from the least squares fit",
        "The Isentrope Pressure and Composition of Detonation Products",
    ]
    _assert_ordered_markers(ftxt, markers)
    _assert_ordered_markers(ptxt, markers)

    # Table row shape compatibility for isentrope (6 scientific-notation columns).
    rows = [ln for ln in ptxt.splitlines() if RE_6E_ROW.match(ln)]
    assert len(rows) >= 5


def test_isp_output_format_parity():
    repo = Path(__file__).resolve().parents[1]
    ftxt = _run_reference_isp(repo)
    ptxt = _run_python_isp(repo)

    markers = [
        "BKW calculation for the Propellant",
        "THE CHAMBER OR EXHAUST PRESSURE IS",
        "THE ISP IS",
        "The Temperature is",
        "The Computed    Volume",
        "The Computed Gamma is",
        "Composition of the Propellant Products",
    ]
    _assert_ordered_markers(ftxt, markers)
    _assert_ordered_markers(ptxt, markers)

    # ISP output must contain chamber and exhaust blocks.
    assert ptxt.count("THE CHAMBER OR EXHAUST PRESSURE IS") >= 2
    assert ptxt.count("THE ISP IS") >= 2
