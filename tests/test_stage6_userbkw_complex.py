import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bkw_py.io.bkwdata import load_bkwdata


def _run(cmd: list[str], repo: Path, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_stage6_many_components_mix():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_many_", dir=str(repo)))
    out = tdir / "BKWDATA.many"
    try:
        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNOCLAL",
                "--mix",
                "rdx=30,tnt=20,hmx=20,nitroglycerine=10,ammonium perchlor=20",
                "--mix-basis",
                "wt",
                "--output",
                str(out),
            ],
            repo,
        )
        assert cp.returncode == 0, cp.stderr
        d = load_bkwdata(out)
        assert d.m >= 6
        assert d.amolwt > 100.0
        assert d.rho > 1.0
        idx = {name.strip().lower(): i for i, name in enumerate(d.name)}
        assert d.elem[idx["c"]] > 0.0
        assert d.elem[idx["h"]] > 0.0
        assert d.elem[idx["n"]] > 0.0
        assert d.elem[idx["o"]] > 0.0
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_stage6_strict_elements_rejects_unknown():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_strict_", dir=str(repo)))
    out = tdir / "BKWDATA.strict"
    try:
        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--mix",
                "rdx=80,teflon=20",  # teflon introduces F not present in CHNO deck
                "--mix-basis",
                "wt",
                "--strict-elements",
                "--output",
                str(out),
            ],
            repo,
        )
        assert cp.returncode != 0
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_stage6_custom_species_and_solid_together():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_custom_", dir=str(repo)))
    out = tdir / "BKWDATA.custom"
    try:
        gas_spec = "xg|30,0.01,0,0,0,1000,0,100|c=1,h=2"
        solid_spec = "xs|10,0.02,0,0,0,800,0,0|0.25,0,0,0,0,0,0,0,0,0,0,12|c=1"
        cp = _run(
            [
                sys.executable,
                str(repo / "bkw_py" / "userbkw.py"),
                "--template",
                "CHNO",
                "--add-gas-custom",
                gas_spec,
                "--add-solid-custom",
                solid_spec,
                "--output",
                str(out),
            ],
            repo,
        )
        assert cp.returncode == 0, cp.stderr
        d = load_bkwdata(out)
        assert "xg" in [s.lower() for s in d.nam]
        assert "xs" in [s.lower() for s in d.nam]
        assert "xs" in [s.lower() for s in d.nams]
        assert d.n >= 12  # CHNO template has 11 gas species; xg should increase it
        assert d.nsf >= 2
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
