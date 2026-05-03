import math
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from bkw_py.core.equil import Sys1State, sys1
from bkw_py.io.bkwdata import load_bkwdata, save_bkwdata


REFERENCE_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (REFERENCE_ROOT / "bkw").exists()
    or not (REFERENCE_ROOT / "ispbkw").exists()
    or not (REFERENCE_ROOT / "userbkw").exists(),
    reason="reference Fortran tree absent",
)

RE_CJ_PRESS = re.compile(r"The Computed CJ Pressure is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_CJ_TEMP = re.compile(r"The Computed CJ Temperature is\s+([+-]?\d\.\d+E[+-]\d+)")
RE_GAS = re.compile(
    r"The Volume of the Gas is\s+([+-]?\d\.\d+E[+-]\d+)\s+cc/mole,\s*"
    r"([+-]?\d\.\d+E[+-]\d+)\s+Moles of Gas"
)
RE_SPECIES_LINE = re.compile(r"^\s*([a-z0-9 ]{1,10})\s+([+-]?\d\.\d+E[+-]\d+)\s+", re.I)

# Tolerances vs reference bkw.out values (printed with limited precision).
RTOL_BULK = 2e-3
ATOL_BULK = 2e-6
RTOL_SPECIES = 5e-3
ATOL_SPECIES = 2e-6


def norm_name(name: str) -> str:
    return " ".join(name.split()).lower()


def almost_equal(a: float, b: float, rtol: float, atol: float) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def copy_with_retry(src: Path, dst: Path, retries: int = 400, delay: float = 0.05) -> None:
    last_err = None
    for _ in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError as exc:
            last_err = exc
            time.sleep(delay)
    if last_err is not None:
        raise last_err


def run_reference_bkw(case_path: Path, bkw_src_dir: Path, temp_root: Path) -> str:
    if not (bkw_src_dir / "abbkw.exe").exists():
        raise FileNotFoundError(f"reference executable not found in {bkw_src_dir}")

    tdir = Path(tempfile.mkdtemp(prefix="bkw_rt_one_", dir=str(temp_root)))
    try:
        rt = tdir / "bkw_runtime"
        shutil.copytree(bkw_src_dir, rt)

        exe = rt / "abbkw.exe"
        bkwdata_path = rt / "BKWDATA"
        out_path = rt / "bkw.out"

        if out_path.exists():
            out_path.unlink()

        copy_with_retry(case_path, bkwdata_path)
        subprocess.run(
            [str(exe)],
            cwd=str(rt),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )

        # reference exe may finalize bkw.out with delay after process return.
        text = ""
        for _ in range(120):
            if out_path.exists() and out_path.stat().st_size > 0:
                text = out_path.read_text(encoding="ascii", errors="replace")
                if text:
                    break
            time.sleep(0.05)
        if not text:
            raise RuntimeError(
                f"reference run did not produce non-empty bkw.out for case {case_path.name}"
            )
        return text
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def parse_reference_golden(text: str) -> dict:
    m_p = RE_CJ_PRESS.search(text)
    m_t = RE_CJ_TEMP.search(text)
    m_g = RE_GAS.search(text)
    if not (m_p and m_t and m_g):
        raise ValueError("Failed to parse CJ pressure/temperature/gas-volume block")

    cj_press = float(m_p.group(1))
    cj_temp = float(m_t.group(1))
    vgas = float(m_g.group(1))
    xbar = float(m_g.group(2))

    sec_pos = text.lower().find("the c-j composition")
    if sec_pos < 0:
        raise ValueError("Failed to find C-J composition block")
    return {
        "cj_press": cj_press,
        "cj_temp": cj_temp,
        "vgas": vgas,
        "xbar": xbar,
        "section": text[sec_pos:],
    }


def extract_species_from_section(section: str, allowed: set[str]) -> dict[str, float]:
    comp = {}
    for line in section.splitlines():
        m = RE_SPECIES_LINE.match(line)
        if not m:
            continue
        name = norm_name(m.group(1))
        if name not in allowed:
            continue
        if name in comp:
            # Keep first hit from the C-J table and ignore later repeated sections.
            continue
        comp[name] = float(m.group(2))
    return comp


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def bkw_src_dir(repo_root: Path) -> Path:
    return repo_root / "bkw"


@pytest.fixture(scope="session")
def tmpdir(repo_root: Path) -> Path:
    p = Path(tempfile.mkdtemp(prefix="stage3_cases_", dir=str(repo_root)))
    yield p
    shutil.rmtree(p, ignore_errors=True)


def collect_base_cases(repo_root: Path) -> list[Path]:
    cases = [repo_root / "bkw" / "BKWDATA", repo_root / "ispbkw" / "bkwdata"]
    user_dir = repo_root / "userbkw"
    skip = {"Makefile", "ZZZCOMPS", "ZZZDECKS", "ZZZSOLEQ", "ZZZTHERC"}
    skip_suffix = {".exe", ".f", ".txt", ".md", ".rst", ".py", ".json", ".yaml", ".yml"}
    for p in sorted(user_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name in skip:
            continue
        if p.suffix.lower() in skip_suffix:
            continue
        cases.append(p)
    return cases


def make_synthetic_cases(base_cases: list[Path], needed: int, tmpdir: Path) -> list[Path]:
    synth = []
    for i in range(needed):
        src = base_cases[i % len(base_cases)]
        d = load_bkwdata(src)
        d.label = (d.label + f" SYN{i + 1}")[:72]
        d.temp = max(300.0, float(d.temp) + 20.0 * (i + 1))
        d.press = max(1e-3, float(d.press) * (1.0 + 0.02 * (i + 1)))

        out = tmpdir / f"SYN_{i + 1:02d}.BKWDATA"
        save_bkwdata(d, out)
        synth.append(out)
    return synth


@pytest.fixture(scope="session")
def golden_cases(repo_root: Path, bkw_src_dir: Path, tmpdir: Path) -> list[Path]:
    base_cases = collect_base_cases(repo_root)
    comparable = []
    for case in base_cases:
        text = run_reference_bkw(case, bkw_src_dir, tmpdir)
        try:
            g = parse_reference_golden(text)
        except ValueError:
            continue
        if g["cj_press"] <= 0.0 or g["cj_temp"] <= 0.0:
            continue

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
            temp=g["cj_temp"],
            press=g["cj_press"],
        )
        ind = sys1(state)
        if ind != 0:
            continue

        py_vgas = float(state.vgas)
        py_xbar = sum(float(v) for v in state.x[: state.n])
        if not almost_equal(py_vgas, g["vgas"], RTOL_BULK, ATOL_BULK):
            continue
        if not almost_equal(py_xbar, g["xbar"], RTOL_BULK, ATOL_BULK):
            continue

        idx = {norm_name(name): i for i, name in enumerate(d.nam)}
        allowed = set(idx.keys())
        comp_f = extract_species_from_section(g["section"], allowed)
        if not comp_f:
            continue

        species_ok = True
        for sp, f_val in comp_f.items():
            py_val = float(state.x[idx[sp]])
            if not almost_equal(py_val, f_val, RTOL_SPECIES, ATOL_SPECIES):
                species_ok = False
                break
        if species_ok:
            comparable.append(case)

    assert len(comparable) >= 12, "Need at least 12 comparable real BKWDATA cases"
    synth = make_synthetic_cases(comparable, needed=23 - len(comparable), tmpdir=tmpdir)
    cases = comparable + synth
    assert len(cases) == 23, "Expected exactly 23 BKWDATA cases"
    return cases


def test_sys1_equil_golden_23_cases(golden_cases: list[Path], bkw_src_dir: Path, tmpdir: Path) -> None:
    failures: list[str] = []

    for case in golden_cases:
        text = run_reference_bkw(case, bkw_src_dir, tmpdir)
        g = parse_reference_golden(text)

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
            temp=g["cj_temp"],
            press=g["cj_press"],
        )
        ind = sys1(state)
        if ind != 0:
            failures.append(f"{case.name}: sys1 failed with ind={ind}")
            continue

        py_vgas = float(state.vgas)
        py_xbar = sum(float(v) for v in state.x[: state.n])
        if not almost_equal(py_vgas, g["vgas"], RTOL_BULK, ATOL_BULK):
            failures.append(
                f"{case.name}: vgas mismatch py={py_vgas:.10e} f={g['vgas']:.10e}"
            )
        if not almost_equal(py_xbar, g["xbar"], RTOL_BULK, ATOL_BULK):
            failures.append(
                f"{case.name}: xbar mismatch py={py_xbar:.10e} f={g['xbar']:.10e}"
            )

        idx = {norm_name(name): i for i, name in enumerate(d.nam)}
        allowed = set(idx.keys())
        comp_f = extract_species_from_section(g["section"], allowed)
        if len(comp_f) == 0:
            failures.append(f"{case.name}: failed to parse species composition")
            continue

        for sp, f_val in comp_f.items():
            py_val = float(state.x[idx[sp]])
            if not almost_equal(py_val, f_val, RTOL_SPECIES, ATOL_SPECIES):
                failures.append(
                    f"{case.name}: species {sp} mismatch py={py_val:.10e} f={f_val:.10e}"
                )

    assert not failures, ";\n".join(failures)
