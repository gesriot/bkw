import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


RE_BLOCK = re.compile(
    r"THE CHAMBER OR EXHAUST PRESSURE IS\s*([+-]?\d\.\d+E[+-]\d+)\s+BARS.*?"
    r"THE ISP IS\s*([+-]?\d\.\d+E[+-]\d+)\s+POUNDS THURST/POUND MASS/SEC.*?"
    r"The Temperature is\s*([+-]?\d\.\d+E[+-]\d+)\s+degrees Kelvin.*?"
    r"The Computed\s+Volume\s*([+-]?\d\.\d+E[+-]\d+)\s+cc/gm of propellant",
    re.S,
)


REFERENCE_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (REFERENCE_ROOT / "ispbkw").exists(),
    reason="reference Fortran tree absent",
)


def run_reference_isp(isp_src_dir: Path, temp_root: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="isp_stage5_f_", dir=str(temp_root)))
    try:
        rt = tdir / "isp_runtime"
        shutil.copytree(isp_src_dir, rt)
        subprocess.run(
            [str(rt / "abispbkw.exe")],
            cwd=str(rt),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        out = rt / "isp.out"
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("reference run did not produce isp.out")
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def run_python_isp(repo: Path, case: Path, temp_root: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="isp_stage5_py_", dir=str(temp_root)))
    out = tdir / "isp_py.out"
    try:
        subprocess.run(
            [sys.executable, str(repo / "bkw_py" / "ispbkw.py"), "--input", str(case), "--output", str(out)],
            cwd=str(repo),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=True,
        )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Python run did not produce isp output")
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def parse_points(text: str) -> list[tuple[float, float, float, float]]:
    rows = [tuple(float(m.group(i)) for i in range(1, 5)) for m in RE_BLOCK.finditer(text)]
    if len(rows) < 2:
        raise ValueError("Expected at least two ISP points (chamber and exhaust)")
    return rows


def close(a: float, b: float, rtol: float, atol: float) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def test_stage5_isp_regression():
    repo = Path(__file__).resolve().parents[1]
    src = repo / "ispbkw"
    case = src / "bkwdata"

    ftxt = run_reference_isp(src, repo)
    ptxt = run_python_isp(repo, case, repo)

    reference_rows = parse_points(ftxt)[:2]
    python_rows = parse_points(ptxt)[:2]

    for i in range(2):
        fp, fi, ft, fv = reference_rows[i]
        pp, pi, pt, pv = python_rows[i]
        assert close(pp, fp, rtol=2e-3, atol=2e-3)  # pressure in bars
        assert close(pi, fi, rtol=5e-2, atol=0.5)   # ISP
        assert close(pt, ft, rtol=1.0e-1, atol=30.0)   # temperature
        assert close(pv, fv, rtol=1.0e-1, atol=20.0)   # specific volume
