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


def test_stage6_interactive_menu_branches_page5_page6_page7():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_menu_", dir=str(repo)))
    out = tdir / "BKWDATA.menu"
    try:
        # Covers interactive branches:
        # - page 5 custom component add
        # - page 3/4 mix setup+apply
        # - page 6 sub=1 (replace gas THERC), sub=3 (replace solid SOLEQ)
        # - page 7 save (run=none)
        script_input = "\n".join(
            [
                "5",            # page 5
                "xcomp",
                "1.70",
                "-10000",
                "100",
                "c=1,h=2,n=1,o=1",
                "3",            # page 3
                "rdx=60,tnt=40",
                "4",            # page 4
                "wt",
                "6",            # page 6
                "1",            # sub 1 replace gas THERC
                "h2o",
                "h2o",
                "6",            # page 6 again
                "3",            # sub 3 replace solid SOLEQ
                "sol c",
                "sol c",
                "7",            # page 7
                str(out),
                "none",
                "0",            # exit
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
        assert d.label.strip() != ""
        assert d.nsf >= 1
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def test_stage6_multisolid_up_to_limit_and_overflow_rejected():
    repo = Path(__file__).resolve().parents[1]
    tdir = Path(tempfile.mkdtemp(prefix="userbkw_multisolid_", dir=str(repo)))
    ok_out = tdir / "BKWDATA.ok"
    bad_out = tdir / "BKWDATA.bad"
    try:
        # CHNO template already has 1 solid; add 4 customs => nsf should become 5 (max).
        good_args = [
            sys.executable,
            str(repo / "bkw_py" / "userbkw.py"),
            "--template",
            "CHNO",
            "--add-solid-custom",
            "xs1|10,0.02,0,0,0,800,0,0|0.25,0,0,0,0,0,0,0,0,0,0,12|c=1",
            "--add-solid-custom",
            "xs2|11,0.02,0,0,0,810,0,0|0.26,0,0,0,0,0,0,0,0,0,0,12|c=1",
            "--add-solid-custom",
            "xs3|12,0.02,0,0,0,820,0,0|0.27,0,0,0,0,0,0,0,0,0,0,12|c=1",
            "--add-solid-custom",
            "xs4|13,0.02,0,0,0,830,0,0|0.28,0,0,0,0,0,0,0,0,0,0,12|c=1",
            "--output",
            str(ok_out),
        ]
        cp = _run(good_args, repo, timeout=180)
        assert cp.returncode == 0, cp.stderr

        d = load_bkwdata(ok_out)
        assert d.nsf == 5
        names = [x.strip().lower() for x in d.nams]
        for nm in ("xs1", "xs2", "xs3", "xs4"):
            assert nm in names

        # One more solid must fail with nsf overflow.
        bad_args = good_args[:-2] + [
            "--add-solid-custom",
            "xs5|14,0.02,0,0,0,840,0,0|0.29,0,0,0,0,0,0,0,0,0,0,12|c=1",
            "--output",
            str(bad_out),
        ]
        cp_bad = _run(bad_args, repo, timeout=180)
        assert cp_bad.returncode != 0
    finally:
        shutil.rmtree(tdir, ignore_errors=True)

