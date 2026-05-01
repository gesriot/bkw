from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bkw_py.io.bkwdata import load_bkwdata


def test_stage6_legacy_noninteractive_cli_bridge(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "BKWDATA.legacy_cli"

    cp = subprocess.run(
        [
            sys.executable,
            str(repo / "bkw_py" / "userbkw.py"),
            "--template",
            "CHNO",
            "--set-ipvc",
            "2",
            "--set-igrp",
            "2",
            "--legacy-eos-preset",
            "rdx",
            "--legacy-aispr",
            "0.45",
            "--legacy-athrho",
            "1.70,1.85",
            "--legacy-var",
            "29=1.25",
            "--legacy-solid-twin",
            "sol c=graph",
            "--output",
            str(out),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
    d = load_bkwdata(out)

    assert d.ipvc == 2
    assert d.igrp == 2
    assert abs(d.alpha - 0.5) < 1e-12
    assert abs(d.beta - 0.16) < 1e-12
    assert abs(d.theta - 400.0) < 1e-12
    assert abs(d.kappa - 10.9097784436) < 1e-9
    assert abs(d.aispr - 0.45) < 1e-12
    assert d.irho == 2
    assert len(d.athrho) == 2
    assert abs(d.athrho[0] - 1.70) < 1e-12
    assert abs(d.athrho[1] - 1.85) < 1e-12
    assert 29 in d.novar
    i = d.novar.index(29)
    assert abs(d.var[i] - 1.25) < 1e-12
    assert "graph" in [x.strip().lower() for x in d.nams]
