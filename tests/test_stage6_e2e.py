import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


RE_BKW_CJ_P = re.compile(r"The Computed CJ Pressure is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_BKW_CJ_T = re.compile(r"The Computed CJ Temperature is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_BKW_CJ_D = re.compile(r"The Computed Detonation Velocity is\s+([+-]?\d\.\d+E[+-]\d+)")

RE_ISP_BLOCK = re.compile(
    r"THE CHAMBER OR EXHAUST PRESSURE IS\s*([+-]?\d\.\d+E[+-]\d+)\s+BARS.*?"
    r"THE ISP IS\s*([+-]?\d\.\d+E[+-]\d+)\s+POUNDS THURST/POUND MASS/SEC.*?"
    r"The Temperature is\s*([+-]?\d\.\d+E[+-]\d+)\s+degrees Kelvin.*?"
    r"The Computed\s+Volume\s*([+-]?\d\.\d+E[+-]\d+)\s+cc/gm of propellant",
    re.S,
)


def _close(a: float, b: float, rtol: float, atol: float) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def _run(cmd: list[str], repo: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _parse_bkw_keyvals(text: str) -> tuple[float, float, float]:
    mp = RE_BKW_CJ_P.search(text)
    mt = RE_BKW_CJ_T.search(text)
    md = RE_BKW_CJ_D.search(text)
    if not (mp and mt and md):
        raise ValueError("failed to parse CJ pressure/temperature/detonation velocity")
    return float(mp.group(1)), float(mt.group(1)), float(md.group(1))


def _parse_isp_blocks(text: str) -> list[tuple[float, float, float, float]]:
    rows = [tuple(float(m.group(i)) for i in range(1, 5)) for m in RE_ISP_BLOCK.finditer(text)]
    if len(rows) < 2:
        raise ValueError("expected at least chamber/exhaust blocks in ISP output")
    return rows[:2]


def _run_reference_bkw(repo: Path, bkwdata: Path, out: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="e2e_bkw_f_", dir=str(repo)))
    try:
        rt = tdir / "bkw_runtime"
        shutil.copytree(repo / "bkw", rt)
        shutil.copy2(bkwdata, rt / "BKWDATA")
        subprocess.run(
            [str(rt / "abbkw.exe")],
            cwd=str(rt),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        f_out = rt / "bkw.out"
        if not f_out.exists() or f_out.stat().st_size == 0:
            raise RuntimeError("reference bkw run did not produce bkw.out")
        shutil.copy2(f_out, out)
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def _run_reference_isp(repo: Path, bkwdata: Path, out: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="e2e_isp_f_", dir=str(repo)))
    try:
        rt = tdir / "isp_runtime"
        shutil.copytree(repo / "ispbkw", rt)
        shutil.copy2(bkwdata, rt / "bkwdata")
        shutil.copy2(bkwdata, rt / "BKWDATA")
        subprocess.run(
            [str(rt / "abispbkw.exe")],
            cwd=str(rt),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        f_out = rt / "isp.out"
        if not f_out.exists() or f_out.stat().st_size == 0:
            raise RuntimeError("reference isp run did not produce isp.out")
        shutil.copy2(f_out, out)
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_e2e_userbkw_to_bkw_reference_compare():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="e2e_userbkw_bkw_", dir=str(repo)))
    try:
        bkwdata = tdir / "BKWDATA.e2e"
        py_out = tdir / "bkw_py.out"
        f_out = tdir / "bkw_f.out"

        cp = _run(
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
                str(bkwdata),
            ],
            repo,
        )
        assert cp.returncode == 0, cp.stderr

        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "bkw.py"),
                "--input",
                str(bkwdata),
                "--output",
                str(py_out),
            ],
            repo,
        )
        assert cp.returncode == 0, cp.stderr
        assert py_out.exists() and py_out.stat().st_size > 0

        py_txt = py_out.read_text(encoding="ascii", errors="replace")
        f_txt = _run_reference_bkw(repo, bkwdata, f_out)

        pp, pt, pd = _parse_bkw_keyvals(py_txt)
        fp, ft, fd = _parse_bkw_keyvals(f_txt)

        assert _close(pp, fp, rtol=2.0e-2, atol=2.0e-4)
        assert _close(pt, ft, rtol=2.0e-2, atol=5.0)
        assert _close(pd, fd, rtol=2.0e-2, atol=2.0e-3)
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_e2e_userbkw_to_isp_reference_compare():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="e2e_userbkw_isp_", dir=str(repo)))
    try:
        bkwdata = tdir / "BKWDATA.e2e"
        py_out = tdir / "isp_py.out"
        f_out = tdir / "isp_f.out"

        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--input",
                str(repo / "ispbkw" / "bkwdata"),
                "--set-ioeq",
                "2",
                "--set-label",
                "e2e isp case",
                "--output",
                str(bkwdata),
            ],
            repo,
            timeout=240,
        )
        assert cp.returncode == 0, cp.stderr

        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "ispbkw.py"),
                "--input",
                str(bkwdata),
                "--output",
                str(py_out),
            ],
            repo,
            timeout=240,
        )
        assert cp.returncode == 0, cp.stderr
        assert py_out.exists() and py_out.stat().st_size > 0

        py_txt = py_out.read_text(encoding="ascii", errors="replace")
        f_txt = _run_reference_isp(repo, bkwdata, f_out)

        py_rows = _parse_isp_blocks(py_txt)
        f_rows = _parse_isp_blocks(f_txt)
        for i in range(2):
            pp, pi, pt, pv = py_rows[i]
            fp, fi, ft, fv = f_rows[i]
            assert _close(pp, fp, rtol=3.0e-2, atol=2.0e-2)
            assert _close(pi, fi, rtol=8.0e-2, atol=2.0)
            assert _close(pt, ft, rtol=1.5e-1, atol=50.0)
            assert _close(pv, fv, rtol=1.5e-1, atol=30.0)
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
