from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bkw_py._cancel import CancelledError
from bkw_py.core.detonation import sys3, sys4a, sys5
from bkw_py.core.equil import Sys1State, sys1
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


ERROR_TEXT = {
    -1: "an error in lfb iterating on gas volume (sys1)",
    -2: "an error in lfb iterating on solid volume (sys1/sys4a)",
    -3: "an error in equil (non-last solid disappeared) or solver chain",
    -4: "an error in lfb iterating on hugoniot temp (sys2a)",
    -5: "an error in mind used by sys3",
    -6: "an error in lfb iterating on p for isentrope (sys4a)",
    -7: "an error in equil singular matrix (lss/sys1)",
}


def e(val: float, width: int = 14, prec: int = 7) -> str:
    return f"{val:{width}.{prec}E}"


def e12(val: float) -> str:
    return f"{val:12.6E}"


def a6(s: str) -> str:
    return f"{s[:6]:<6s}"


def build_state(d: BKWData, cfg: RuntimeConfig, rho_case: float) -> Sys1State:
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
    _ = rho_case
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
    return notes


def write_cjpnt(lines: list[str], d: BKWData, state: Sys1State, nsf: int, rho_case: float, *,
                pcj: float, detvel: float, cjt: float, vcj: float, gamma: float) -> None:
    xbar = sum(state.x[: state.n])
    lines.append("1 A BKW Calculation for the Explosive ")
    lines.append(f"    {d.label}")
    lines.append("")
    lines.append("")
    lines.append(f" The Number of Elements is {d.m:6d}")
    lines.append("")
    lines.append("")
    lines.append(f" The Number of Gas Species is {d.n:5d}")
    lines.append("")
    lines.append("")
    lines.append(f" The Number of Solid Species is {nsf:5d}")
    lines.append("")
    lines.append("")
    lines.append(" The BKW Equation of State Parameters are")
    lines.append(
        f"  Alpha={d.alpha:12.5E} Beta={d.beta:12.5E} Theta={d.theta:12.5E} Kappa={d.kappa:14.7E}"
    )
    lines.append("")
    lines.append("")
    lines.append(" The Composition of the Explosive is    ")
    for i in range(d.m):
        lines.append(f"      {d.elem[i]:14.7E} Moles of {a6(d.name[i])}")
    lines.append("")
    lines.append("")
    lines.append(f" The Density of the Explosive is {rho_case:14.7E}, grams/cc ")
    lines.append("")
    lines.append("")
    lines.append(f" The Molecular Weight is {d.amolwt:14.7E} grams")
    lines.append("")
    lines.append("")
    lines.append(
        f" The Heat of Formation at 0 deg K is {d.eo:14.7E} Calories per Formula Weight "
    )
    lines.append("")
    lines.append("")
    lines.append(" The Input Detonation Product Elemental CompositionMatrix")
    flat = [d.aik[i][j] for i in range(d.nt) for j in range(d.m)]
    for i in range(0, len(flat), 7):
        lines.append("".join(f"{v:10.1E}" for v in flat[i : i + 7]))
    lines.append("")
    lines.append("")
    lines.append("1 A BKW Calculation for the Explosive ")
    lines.append(f"    {d.label}")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed CJ Pressure is    {e(pcj)}    megabars ")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed Detonation Velocity is    {e(detvel)}    cm/microsecond ")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed CJ Temperature is    {e(cjt)}    Degrees Kelvin ")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed CJ Volume   {e(vcj)}  cc/gm of Explosive ")
    lines.append("")
    lines.append("")
    lines.append(f" The Computed Gamma is {e(gamma)}")
    lines.append("")
    lines.append("")
    lines.append(f" The Volume of the Gas is   {state.vgas:12.5E}   cc/mole, {xbar:12.5E}   Moles of Gas")
    lines.append("")
    lines.append("")
    lines.append(" Solid    Volume in cc/gm")
    for i in range(nsf):
        lines.append(f" {a6(d.nams[i])} {state.vsol[i]:14.7E}")
    lines.append("")
    lines.append("")
    lines.append(" The C-J Composition of the Detonation Products andthe Input Coefficients                           ")
    lines.append("")
    lines.append("")
    lines.append(" Specie   No of Moles       Coefficients A,B,C,D,E, the I C, Heat For, Covolume                                     ")
    for i in range(d.nt):
        c = d.therc[i]
        lines.append(
            f"{a6(d.nam[i])} {state.x[i]:13.6E} {c[0]:13.6E} {c[1]:13.6E} {c[2]:13.6E} {c[3]:13.6E}"
        )
        lines.append(
            f"                    {c[4]:13.6E} {c[5]:13.6E} {c[6]:13.6E} {c[7]:13.6E}"
        )


def write_hugpnt(lines: list[str], d: BKWData, h) -> None:
    lines.append("1 The BKW Hugoniot for the Detonation Products of ")
    lines.append(f"  {d.label}")
    lines.append("")
    for i in range(h.it):
        lines.append("")
        lines.append(
            f" Pressure = {e(h.hugp[i])} Volume = {e(h.hugv[i])} Temperature = {e(h.hugt[i])}"
        )
        if i < h.iw:
            lines.append(
                f" Shock Velocity = {e(h.hugus[i])} Particle Velocity ={h.hugup[i]:17.10E}                                                  "
            )
        lines.append("")
        lines.append("")
        lines.append("  Specie   No of Moles")
        row = h.comp_rows[i] if i < len(h.comp_rows) else [0.0] * d.nt
        for j in range(d.nt):
            lines.append(f" {a6(d.nam[j])}   {row[j]:14.7E}")


def write_ispnt(lines: list[str], d: BKWData, r) -> None:
    lines.append("1 A BKW Isentrope thru BKW CJ Pressure for  ")
    lines.append(f"  {d.label}")
    lines.append("")
    lines.append("")
    lines.append(
        f" ln(P)= {r.pcoef[0]:14.7E}   {r.pcoef[1]:14.7E}lnV {r.pcoef[2]:14.7E}lnV*2"
    )
    lines.append(f" {r.pcoef[3]:14.7E}lnV*3 {r.pcoef[4]:14.7E}lnV*4")
    lines.append("")
    lines.append("")
    lines.append(
        f" ln(T)= {r.tcoef[0]:14.7E}   {r.tcoef[1]:14.7E}lnV {r.tcoef[2]:14.7E}lnV*2"
    )
    lines.append(f" {r.tcoef[3]:14.7E}lnV*3 {r.tcoef[4]:14.7E}lnV*4")
    lines.append("")
    lines.append("")
    lines.append(
        f" ln(E)= {r.ecoef[0]:14.7E}   {r.ecoef[1]:14.7E}lnP {r.ecoef[2]:14.7E}lnP*2"
    )
    lines.append(f" {r.ecoef[3]:14.7E}lnP*3 {r.ecoef[4]:14.7E}lnP*4")
    lines.append("")
    lines.append("")
    lines.append(" The constant added to energies was  1.0000000E-01")
    lines.append("")
    lines.append("")
    lines.append(" Pressure (mb) Volume (c/g) Temperature(k) Energy+c   Gamma      Part Vel ")
    for i in range(r.it):
        lines.append(
            f" {e12(r.asp[i])} {e12(r.asv[i])} {e12(r.ast[i])} {e12(r.ase[i])} {e12(r.asg[i])} {e12(r.asup[i])}"
        )
    lines.append("1 The isentrope state variables as computed from the least squares fit")
    lines.append("")
    lines.append("")
    lines.append(" BKW Pressure  Fit Pressure BKW Temperature Fit Temperature BKW Energy+c  Fit E")
    for i in range(r.it):
        lines.append(
            f" {e12(r.asp[i])} {e12(r.fitp[i])} {e12(r.ast[i])} {e12(r.fitt[i])} {e12(r.ase[i])} {e12(r.fite[i])}"
        )
    lines.append("1  The Isentrope Pressure and Composition of Detonation Products")
    lines.append(" " + "".join(a6(n) + " " for n in d.nam).rstrip())
    for i in range(r.it):
        vals = [r.asp[i]] + r.comp_rows[i]
        for k in range(0, len(vals), 6):
            lines.append(" " + " ".join(f"{v:12.6E}" for v in vals[k : k + 6]))


def run_case(d: BKWData, cfg: RuntimeConfig, rho_case: float, lines: list[str]) -> None:
    s = build_state(d, cfg, rho_case)

    icjc = d.icjc
    ihug = d.ihug
    ipvc = d.ipvc
    if ihug > 0:
        icjc = 1
    if ipvc > 0:
        icjc = 1
    if ipvc == 3:
        icjc = 0

    nsf = d.nsf

    # Optional equilibrium-at-input mode.
    if d.ioeq != 0:
        ind = sys1(s)
        if ind < 0:
            raise RuntimeError(ERROR_TEXT.get(ind, f"sys1 failed ind={ind}"))

    r3 = None
    if icjc != 0:
        r3 = sys3(
            s,
            rho=rho_case,
            amolwt=d.amolwt,
            eo=d.eo,
            po=cfg.po,
            apgcj=cfg.apgcj,
            bpgcj=cfg.bpgcj,
            cj_ratio=cfg.cj_ratio,
            cj_tol=cfg.cj_tol,
            hug_temp_guess=cfg.hugb2,
            hug_ratio=cfg.hugb_ratio,
            hug_tol=cfg.hugb_tol,
        )
        if r3.ind < 0:
            raise RuntimeError(ERROR_TEXT.get(r3.ind, f"sys3 failed ind={r3.ind}"))
        write_cjpnt(lines, d, s, nsf, rho_case, pcj=r3.pcj, detvel=r3.detvel, cjt=r3.cjt, vcj=r3.vcj, gamma=r3.gamma)

    if ihug != 0:
        h = sys5(
            s,
            rho=rho_case,
            amolwt=d.amolwt,
            eo=d.eo,
            amhugp=cfg.amhugp,
            delp=cfg.delp,
            po=cfg.po,
            vbos2=cfg.vbos2,
            hugb2=cfg.hugb2,
        )
        if h.ind < 0:
            raise RuntimeError(ERROR_TEXT.get(h.ind, f"sys5 failed ind={h.ind}"))
        write_hugpnt(lines, d, h)

    if ipvc != 0:
        if r3 is None:
            raise RuntimeError("sys4a requires C-J state (sys3), but icjc=0")
        r4 = sys4a(
            s,
            rho=rho_case,
            amolwt=d.amolwt,
            eo=d.eo,
            pcj=r3.pcj,
            cjt=r3.cjt,
            ucj=r3.ucj,
            ipvc=ipvc,
            aispr=d.aispr,
            po=cfg.po,
            cprime=cfg.cprime,
            decip=cfg.decip,
            aminp=cfg.aminp,
            aincp=cfg.aincp,
            amaxp=cfg.amaxp,
            vbos2=cfg.vbos2,
            as_ratio_down=cfg.as_ratio_down,
            as_tol_down=cfg.as_tol_down,
            as_ratio_up=cfg.as_ratio_up,
            as_tol_up=cfg.as_tol_up,
        )
        if r4.ind < 0:
            raise RuntimeError(ERROR_TEXT.get(r4.ind, f"sys4a failed ind={r4.ind}"))
        write_ispnt(lines, d, r4)


def run(
    input_path: str | Path,
    output_path: str | Path,
    *,
    cfg: RuntimeConfig | None = None,
    on_log: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> int:
    d = load_bkwdata(str(input_path))
    if cfg is None:
        cfg = RuntimeConfig()
    lines: list[str] = []
    lines.extend(apply_overrides(d, cfg))

    rho_cases = [d.rho]
    if d.irho > 0 and d.athrho:
        rho_cases = list(reversed([float(v) for v in d.athrho]))

    for rho_case in rho_cases:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("bkw run cancelled")
        if on_log is not None:
            on_log(f"rho_case={float(rho_case):.6E}")
        run_case(d, cfg, float(rho_case), lines)

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Python BKW entrypoint")
    ap.add_argument("--input", default="bkw/BKWDATA", help="Path to BKWDATA")
    ap.add_argument("--output", default="bkw.out", help="Output bkw.out path")
    args = ap.parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
