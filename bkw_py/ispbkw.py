from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bkw_py._cancel import CancelledError
from bkw_py.core.equil import Sys1State
from bkw_py.core.isp import IspPoint, isp
from bkw_py.io.bkwdata import BKWData, load_bkwdata


@dataclass
class RuntimeConfig:
    vbos1: float = 15.0
    vbos_ratio: float = 1.1
    vbos_tol: float = 1.0e-6
    exitme: float = 2.0e-5
    hugb1: float = 3000.0
    hugb_ratio: float = 1.1
    hugb_tol: float = 1.0e-6
    po: float = 1.0e-6
    cj_ratio: float = 0.8
    cj_tol: float = 1.0e-6
    apgcj: float = 0.15
    bpgcj: float = 0.25
    amhugp: float = 0.50
    delp: float = 0.05
    cprime: float = 0.1
    decip: float = 0.5
    aminp: float = 1.0e-4
    aincp: float = 1.20
    amaxp: float = 1.0
    as_ratio_down: float = 0.9
    as_tol_down: float = 0.5
    as_ratio_up: float = 1.1
    as_tol_up: float = 0.5
    vbos2: float = 15.0
    hugb2: float = 3000.0
    amaxe: float = 1.0e-6
    aminx: float = 1.0e-8
    aminy: float = 1.0e-5
    tx_ratio: float = 1.1
    tx_tol: float = 1.0e-6


def a6(s: str) -> str:
    return f"{s[:6]:<6s}"


def e(val: float, width: int = 14, prec: int = 7) -> str:
    return f"{val:{width}.{prec}E}"


def build_state(d: BKWData, cfg: RuntimeConfig) -> Sys1State:
    s = Sys1State(
        x=list(float(v) for v in d.x),
        therc=[[float(v) for v in row] for row in d.therc],
        soleqs=[[float(v) for v in row] for row in d.soleqs],
        aik=[[float(v) for v in row] for row in d.aik],
        elem=[float(v) for v in d.elem],
        n=d.n,
        nt=d.nt,
        m=d.m,
        alpha=float(d.alpha),
        beta=float(d.beta),
        theta=float(d.theta),
        kappa=float(d.kappa),
        temp=float(d.temp),
        press=float(d.press),
    )
    s.v_guess = cfg.vbos2
    s.v_ratio = cfg.vbos_ratio
    s.v_tol = cfg.vbos_tol
    s.exitme = cfg.exitme
    s.amaxe = cfg.amaxe
    s.aminx = cfg.aminx
    s.aminy = cfg.aminy
    return s


def apply_overrides(d: BKWData, cfg: RuntimeConfig) -> list[str]:
    notes: list[str] = []
    for novar, var in zip(d.novar, d.var):
        notes.append(f"  constant with idenity no {novar:5d} is {var:18.11E}")
        if novar == 1:
            cfg.vbos1 = var
        elif novar == 2:
            cfg.vbos_ratio = var
        elif novar == 3:
            cfg.vbos_tol = var
        elif novar == 4:
            cfg.exitme = var
        elif novar == 5:
            cfg.hugb1 = var
        elif novar == 6:
            cfg.hugb_ratio = var
        elif novar == 7:
            cfg.hugb_tol = var
        elif novar == 8:
            cfg.po = var
        elif novar == 9:
            cfg.cj_ratio = var
        elif novar == 10:
            cfg.cj_tol = var
        elif novar == 11:
            cfg.apgcj = var
        elif novar == 12:
            cfg.bpgcj = var
        elif novar == 13:
            cfg.amhugp = var
        elif novar == 14:
            cfg.delp = var
        elif novar == 15:
            cfg.cprime = var
        elif novar == 16:
            cfg.decip = var
        elif novar == 17:
            cfg.aminp = var
        elif novar == 18:
            cfg.aincp = var
        elif novar == 19:
            cfg.amaxp = var
        elif novar == 20:
            cfg.as_ratio_down = var
        elif novar == 21:
            cfg.as_tol_down = var
        elif novar == 22:
            cfg.as_ratio_up = var
        elif novar == 23:
            cfg.as_tol_up = var
        elif novar == 24:
            cfg.vbos2 = var
            cfg.vbos1 = var
        elif novar == 25:
            cfg.hugb2 = var
            cfg.hugb1 = var
        elif novar == 26:
            cfg.amaxe = var
        elif novar == 27:
            cfg.aminx = var
        elif novar == 28:
            cfg.aminy = var
        elif novar == 29:
            cfg.tx_ratio = var
        elif novar == 30:
            cfg.tx_tol = var
    return notes


def write_propellant_point(lines: list[str], d: BKWData, p: IspPoint, *, nsf: int) -> None:
    xbar = sum(p.x[: d.n])
    lines.append("1 A BKW calculation for the Propellant")
    lines.append(f"  {d.label}")
    lines.append("")
    lines.append("")
    lines.append(f" THE CHAMBER OR EXHAUST PRESSURE IS {p.pcj:18.11E} BARS")
    lines.append("")
    lines.append("")
    lines.append(f" THE ISP IS {p.detvel:18.11E} POUNDS THURST/POUND MASS/SEC")
    lines.append("")
    lines.append("")
    lines.append(f" The Temperature is {p.temp:18.11E} degrees Kelvin")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed    Volume   {p.vpg:18.11E}  cc/gm of propellant")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed Gamma is {e(p.gamma)}")
    lines.append("")
    lines.append("")
    lines.append(f" The Volume of the Gas is   {p.vgas:12.5E}   cc/mole, {xbar:12.5E}   Moles of Gas")
    lines.append("")
    lines.append("")
    lines.append(" Solid    Volume in cc/gm")
    for i in range(nsf):
        lines.append(f" {a6(d.nams[i])} {p.vsol[i]:14.7E}")
    lines.append("")
    lines.append("")
    lines.append(" The   Composition of the Propellant Products and the Input Coefficients")
    lines.append(" Specie   No of Moles    Coefficients A,B,C,D,E, the ICc, Heat For, Covolume")
    for i in range(d.nt):
        c = d.therc[i]
        lines.append(
            f"{a6(d.nam[i])} {p.x[i]:13.6E} {c[0]:13.6E} {c[1]:13.6E} {c[2]:13.6E} {c[3]:13.6E}"
        )
        lines.append(
            f"                    {c[4]:13.6E} {c[5]:13.6E} {c[6]:13.6E} {c[7]:13.6E}"
        )


def run(
    input_path: str | Path,
    output_path: str | Path,
    *,
    cfg: RuntimeConfig | None = None,
    on_log: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> int:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("ispbkw run cancelled")

    d = load_bkwdata(str(input_path))
    if cfg is None:
        cfg = RuntimeConfig()
    lines: list[str] = []
    lines.extend(apply_overrides(d, cfg))
    state = build_state(d, cfg)

    if d.ioeq != 2:
        raise RuntimeError("ispbkw.py currently supports BKWDATA with ioeq=2 (ISP mode)")

    if on_log is not None:
        on_log(f"isp rho={float(d.rho):.6E} amolwt={float(d.amolwt):.6E}")

    r = isp(state, rho=d.rho, amolwt=d.amolwt, eo=d.eo)
    if r.ind < 0:
        raise RuntimeError(f"isp solver failed ind={r.ind}")

    write_propellant_point(lines, d, r.chamber, nsf=d.nsf)
    write_propellant_point(lines, d, r.exhaust, nsf=d.nsf)

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Python ISPBKW entrypoint")
    ap.add_argument("--input", default="ispbkw/bkwdata", help="Path to BKWDATA for ISPBKW")
    ap.add_argument("--output", default="isp.out", help="Output isp.out path")
    args = ap.parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
