from __future__ import annotations

import math
from dataclasses import dataclass

from .detonation import sys2, sys4_entropy
from .eos import R3
from .equil import Sys1State, sys1
from .solvers import lfb


ALSOL = [
    -5.34441068912e-1,
    6.17168032701e-2,
    -2.00636731698e-5,
    3.34554768655e-9,
    -2.10658107571e-13,
    -343.0,
    -397500.0,
]

ALLIQ = [
    8.82742624474e0,
    6.60509571225e-2,
    -2.21587529290e-5,
    3.75946241578e-9,
    -2.39276413847e-13,
    950.0,
    -372680.0,
]


@dataclass
class IspPoint:
    press: float
    pcj: float
    temp: float
    vpg: float
    vgas: float
    vsol: list[float]
    x: list[float]
    detvel: float
    gamma: float


@dataclass
class IspResult:
    ind: int
    chamber: IspPoint
    exhaust: IspPoint
    tc: float
    te: float
    vc: float
    ve: float
    sc: float
    ec: float
    ee: float
    eisp: float
    exhtv: float


def _apply_al_phase_switch(state: Sys1State, temp: float, altemp: float = 2250.0) -> None:
    """Apply temperature-dependent Al2O3 phase coefficient swap."""
    if altemp < 1.0 or state.nt < 20:
        return
    i19 = 18
    i20 = 19
    if temp > altemp:
        src19, src20 = ALLIQ, ALSOL
    else:
        src19, src20 = ALSOL, ALLIQ
    for k in range(7):
        state.therc[i19][k] = src19[k]
        state.therc[i20][k] = src20[k]


def isp(
    state: Sys1State,
    *,
    rho: float,
    amolwt: float,
    eo: float,
    chamber_press: float = 0.0000689473,
    exhaust_press: float = 0.00000101325,
) -> IspResult:
    """Compute ISP chamber and exhaust state."""
    vo = 1.0 / rho
    state.press = chamber_press
    last_s2c = None

    def chamber_f(temp: float) -> float:
        nonlocal last_s2c
        state.temp = temp
        _apply_al_phase_switch(state, temp)
        ind = sys1(state)
        if ind < 0:
            raise RuntimeError(str(ind))
        s2 = sys2(state, amolwt)
        last_s2c = s2
        return s2.etot - eo - state.press * (vo - s2.vpg) * R3 * amolwt

    try:
        temp_ch, _ = lfb(chamber_f, 3000.0, ratio=1.1, tol=0.01)
    except RuntimeError as exc:
        try:
            ind = int(str(exc))
        except Exception:
            ind = -3
        z = IspPoint(
            press=state.press,
            pcj=state.press * 1.0e6,
            temp=state.temp,
            vpg=0.0,
            vgas=0.0,
            vsol=[0.0] * (state.nt - state.n),
            x=[0.0] * state.nt,
            detvel=0.0,
            gamma=0.0,
        )
        return IspResult(
            ind=ind,
            chamber=z,
            exhaust=z,
            tc=state.temp,
            te=state.temp,
            vc=0.0,
            ve=0.0,
            sc=0.0,
            ec=0.0,
            ee=0.0,
            eisp=0.0,
            exhtv=0.0,
        )

    if last_s2c is None:
        return IspResult(
            ind=-3,
            chamber=IspPoint(
                press=state.press,
                pcj=state.press * 1.0e6,
                temp=state.temp,
                vpg=0.0,
                vgas=0.0,
                vsol=[0.0] * (state.nt - state.n),
                x=[0.0] * state.nt,
                detvel=0.0,
                gamma=0.0,
            ),
            exhaust=IspPoint(
                press=state.press,
                pcj=state.press * 1.0e6,
                temp=state.temp,
                vpg=0.0,
                vgas=0.0,
                vsol=[0.0] * (state.nt - state.n),
                x=[0.0] * state.nt,
                detvel=0.0,
                gamma=0.0,
            ),
            tc=state.temp,
            te=state.temp,
            vc=0.0,
            ve=0.0,
            sc=0.0,
            ec=0.0,
            ee=0.0,
            eisp=0.0,
            exhtv=0.0,
        )
    s2c = last_s2c
    _, sc, _, _ = sys4_entropy(state)

    tc = state.temp
    vc = s2c.vpg
    ec_raw = s2c.etot
    chamber = IspPoint(
        press=state.press,
        pcj=state.press * 1.0e6,
        temp=state.temp,
        vpg=s2c.vpg,
        vgas=state.vgas,
        vsol=list(float(v) for v in state.vsol),
        x=list(float(v) for v in state.x),
        detvel=0.0,
        gamma=0.0,
    )

    state.press = exhaust_press
    last_s2e = None

    def exhaust_f(temp: float) -> float:
        nonlocal last_s2e
        state.temp = temp
        _apply_al_phase_switch(state, temp)
        ind2 = sys1(state)
        if ind2 < 0:
            raise RuntimeError(str(ind2))
        last_s2e = sys2(state, amolwt)
        _, stot, _, _ = sys4_entropy(state)
        return stot - sc

    try:
        temp_ex, _ = lfb(exhaust_f, tc * 0.9, ratio=0.9, tol=0.1)
    except RuntimeError as exc:
        try:
            ind = int(str(exc))
        except Exception:
            ind = -3
        return IspResult(
            ind=ind,
            chamber=chamber,
            exhaust=chamber,
            tc=tc,
            te=state.temp,
            vc=vc,
            ve=0.0,
            sc=sc,
            ec=0.0,
            ee=0.0,
            eisp=0.0,
            exhtv=0.0,
        )

    if last_s2e is None:
        return IspResult(
            ind=-3,
            chamber=chamber,
            exhaust=chamber,
            tc=tc,
            te=state.temp,
            vc=vc,
            ve=0.0,
            sc=sc,
            ec=0.0,
            ee=0.0,
            eisp=0.0,
            exhtv=0.0,
        )
    s2e = last_s2e

    te = state.temp
    ve = s2e.vpg
    ee = s2e.etot / amolwt + exhaust_press * ve * R3
    ec = ec_raw / amolwt + chamber_press * vc * R3
    eisp = 9.330 * math.sqrt(max(0.0, ec - ee))
    exhtv = eisp * 32.1725

    exhaust = IspPoint(
        press=state.press,
        pcj=state.press * 1.0e6,
        temp=state.temp,
        vpg=s2e.vpg,
        vgas=state.vgas,
        vsol=list(float(v) for v in state.vsol),
        x=list(float(v) for v in state.x),
        detvel=eisp,
        gamma=0.0,
    )

    return IspResult(
        ind=0,
        chamber=chamber,
        exhaust=exhaust,
        tc=tc,
        te=te,
        vc=vc,
        ve=ve,
        sc=sc,
        ec=ec,
        ee=ee,
        eisp=eisp,
        exhtv=exhtv,
    )
