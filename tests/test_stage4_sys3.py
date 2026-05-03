import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from bkw_py.core.detonation import sys3
from bkw_py.core.equil import Sys1State
from bkw_py.io.bkwdata import load_bkwdata


REFERENCE_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (REFERENCE_ROOT / "bkw").exists(),
    reason="reference Fortran tree absent",
)

RE_CJ_PRESS = re.compile(r"The Computed CJ Pressure is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_CJ_TEMP = re.compile(r"The Computed CJ Temperature is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_DETVEL = re.compile(r"The Computed Detonation Velocity is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_CJ_VOL = re.compile(r"The Computed CJ Volume\s+([+-]?\d\.\d+E[+-]\d+)")


def run_reference_bkw(case_path: Path, bkw_src_dir: Path, temp_root: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="bkw_stage4_", dir=str(temp_root)))
    try:
        rt = tdir / "bkw_runtime"
        shutil.copytree(bkw_src_dir, rt)
        shutil.copy2(case_path, rt / "BKWDATA")
        subprocess.run(
            [str(rt / "abbkw.exe")],
            cwd=str(rt),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
        out = rt / "bkw.out"
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("reference run did not produce bkw.out")
        return out.read_text(encoding="ascii", errors="replace")
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def parse_reference_cj(text: str) -> dict[str, float]:
    mp = RE_CJ_PRESS.search(text)
    mt = RE_CJ_TEMP.search(text)
    md = RE_DETVEL.search(text)
    mv = RE_CJ_VOL.search(text)
    if not (mp and mt and md and mv):
        raise ValueError("Could not parse CJ block from reference output")
    return {
        "pcj": float(mp.group(1)),
        "cjt": float(mt.group(1)),
        "detvel": float(md.group(1)),
        "vcj": float(mv.group(1)),
    }


def rel_close(a: float, b: float, rtol: float, atol: float) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def test_sys3_cj_regression_bkwdata():
    repo = Path(__file__).resolve().parents[1]
    case = repo / "bkw" / "BKWDATA"
    bkw_src = repo / "bkw"
    tmp_root = repo

    ftxt = run_reference_bkw(case, bkw_src, tmp_root)
    gold = parse_reference_cj(ftxt)

    d = load_bkwdata(case)
    state = Sys1State(
        x=list(d.x),
        therc=d.therc,
        soleqs=d.soleqs,
        aik=d.aik,
        elem=d.elem,
        n=d.n,
        nt=d.nt,
        m=d.m,
        alpha=d.alpha,
        beta=d.beta,
        theta=d.theta,
        kappa=d.kappa,
        temp=d.temp,
        press=d.press,
    )

    res = sys3(state, rho=d.rho, amolwt=d.amolwt, eo=d.eo)
    assert res.ind == 0

    # Minimal regression tolerances for the stage-4 solver.
    assert rel_close(res.pcj, gold["pcj"], rtol=2e-2, atol=1e-4)
    assert rel_close(res.cjt, gold["cjt"], rtol=2e-2, atol=2.0)
    assert rel_close(res.vcj, gold["vcj"], rtol=3e-2, atol=2e-3)
    assert rel_close(res.detvel, gold["detvel"], rtol=2e-2, atol=2e-3)
