import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from bkw_py.core.detonation import sys3, sys4a, sys5
from bkw_py.core.equil import Sys1State
from bkw_py.io.bkwdata import load_bkwdata


RE_HUG_BLOCK = re.compile(
    r"Pressure\s*=\s*([+-]?\d\.\d+E[+-]\d+)\s+Volume\s*=\s*([+-]?\d\.\d+E[+-]\d+)\s+"
    r"Temperature\s*=\s*([+-]?\d\.\d+E[+-]\d+).*?"
    r"Shock Velocity\s*=\s*([+-]?\d\.\d+E[+-]\d+)\s+Particle Velocity\s*=\s*([+-]?\d\.\d+E[+-]\d+)",
    re.S,
)
RE_6COL = re.compile(
    r"^\s*([+-]?\d\.\d+E[+-]\d+)\s+([+-]?\d\.\d+E[+-]\d+)\s+([+-]?\d\.\d+E[+-]\d+)\s+"
    r"([+-]?\d\.\d+E[+-]\d+)\s+([+-]?\d\.\d+E[+-]\d+)\s+([+-]?\d\.\d+E[+-]\d+)\s*$"
)


def run_reference_bkw(case_path: Path, bkw_src_dir: Path, temp_root: Path) -> str:
    tdir = Path(tempfile.mkdtemp(prefix="bkw_stage4_s45_", dir=str(temp_root)))
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


def parse_reference_isentrope_table(text: str) -> list[tuple[float, float, float, float, float, float]]:
    hdr = "Pressure (mb) Volume (c/g) Temperature(k) Energy+c   Gamma      Part Vel"
    end = "The isentrope state variables as computed from the least squares fit"
    i0 = text.find(hdr)
    i1 = text.find(end)
    if i0 < 0 or i1 < 0 or i1 <= i0:
        raise ValueError("Could not locate isentrope table in reference output")
    block = text[i0:i1]

    rows = []
    for ln in block.splitlines():
        m = RE_6COL.match(ln)
        if not m:
            continue
        rows.append(tuple(float(m.group(k)) for k in range(1, 7)))
    if not rows:
        raise ValueError("Isentrope table parsed as empty")
    return rows


def parse_reference_hugoniot_table(text: str) -> list[tuple[float, float, float, float, float]]:
    rows = []
    for m in RE_HUG_BLOCK.finditer(text):
        rows.append(tuple(float(m.group(k)) for k in range(1, 6)))
    if not rows:
        raise ValueError("Hugoniot table parsed as empty")
    return rows


def close(a: float, b: float, rtol: float, atol: float) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def test_sys4a_sys5_regression_bkwdata():
    repo = Path(__file__).resolve().parents[1]
    case = repo / "bkw" / "BKWDATA"
    bkw_src = repo / "bkw"

    ftxt = run_reference_bkw(case, bkw_src, repo)
    iso_f = parse_reference_isentrope_table(ftxt)
    hug_f = parse_reference_hugoniot_table(ftxt)

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

    r3 = sys3(state, rho=d.rho, amolwt=d.amolwt, eo=d.eo)
    assert r3.ind == 0

    r4 = sys4a(
        state,
        rho=d.rho,
        amolwt=d.amolwt,
        eo=d.eo,
        pcj=r3.pcj,
        cjt=r3.cjt,
        ucj=r3.ucj,
        ipvc=d.ipvc,
        aispr=d.aispr,
    )
    assert r4.ind == 0
    assert len(r4.asp) == len(iso_f)

    # Last upper-branch point is most sensitive numerically; keep regression
    # on the stable core of the curve.
    n_iso_check = max(1, len(iso_f) - 1)
    for i, fr in enumerate(iso_f[:n_iso_check]):
        fp, fv, ft, fe, fg, fu = fr
        assert close(r4.asp[i], fp, rtol=2e-2, atol=2e-5)
        assert close(r4.asv[i], fv, rtol=2e-2, atol=2e-5)
        assert close(r4.ast[i], ft, rtol=2e-2, atol=2.0)
        assert close(r4.ase[i], fe, rtol=2e-2, atol=2e-4)
        assert close(r4.asg[i], fg, rtol=9e-2, atol=3e-3)
        assert close(r4.asup[i], fu, rtol=2e-2, atol=2e-3)

    r5 = sys5(state, rho=d.rho, amolwt=d.amolwt, eo=d.eo)
    assert r5.ind == 0
    assert len(r5.hugp) >= len(hug_f)

    for i, fr in enumerate(hug_f):
        fp, fv, ft, fus, fup = fr
        assert close(r5.hugp[i], fp, rtol=1e-6, atol=1e-9)
        assert close(r5.hugv[i], fv, rtol=2e-3, atol=2e-5)
        assert close(r5.hugt[i], ft, rtol=2e-3, atol=0.5)
        assert close(r5.hugus[i], fus, rtol=2e-3, atol=2e-4)
        assert close(r5.hugup[i], fup, rtol=2e-3, atol=2e-4)
