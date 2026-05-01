"""
Detonation calculations.

  - sys2   (state properties from equilibrium solution)
  - sys2a  (Hugoniot temperature solve at fixed pressure)
  - sys3   (C-J point search using MIND)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .eos import R1, R3, R5, ses_entropy
from .equil import Sys1State, sys1
from .fitting import pfts
from .solvers import lfb
from .thermo import tdf


@dataclass
class Sys2Result:
    etot: float
    vtot: float
    vpg: float


@dataclass
class Sys3Result:
    ind: int
    press: float
    temp: float
    detvel: float
    gamma: float
    pcj: float
    vcj: float
    cjt: float
    ucj: float
    vpg: float
    mind_ok: bool
    hug_ok: bool


@dataclass
class IsentropeResult:
    ind: int
    asp: list[float]
    asv: list[float]
    ast: list[float]
    ase: list[float]
    asg: list[float]
    asup: list[float]
    fitp: list[float]
    fitt: list[float]
    fite: list[float]
    pcoef: list[float]
    tcoef: list[float]
    ecoef: list[float]
    it: int
    iw: int
    scj: float
    comp_rows: list[list[float]]


@dataclass
class HugoniotResult:
    ind: int
    hugp: list[float]
    hugt: list[float]
    hugv: list[float]
    hugup: list[float]
    hugus: list[float]
    it: int
    iw: int
    comp_rows: list[list[float]]


def sys2(state: Sys1State, amolwt: float) -> Sys2Result:
    """Compute total energy/volume from current equilibrium."""
    xbar = sum(state.x[: state.n])
    if xbar <= 0.0:
        return Sys2Result(etot=0.0, vtot=0.0, vpg=0.0)

    r1t = R1 * state.temp

    # Gas contribution
    egt = 0.0
    for i in range(state.n):
        hmho = tdf(state.temp, state.therc[i], 1)
        egt += (state.x[i] / xbar) * (hmho - r1t + state.therc[i][6])
    egt += r1t * (state.alpha * state.temp * (state.fx - 1.0) / (state.temp + state.theta))

    # Solid contribution
    est = 0.0
    vst = 0.0
    nsf = state.nt - state.n
    for k in range(nsf):
        j = state.n + k
        hmho = tdf(state.temp, state.therc[j], 1)
        # ses(..., ind=2) already includes molecular weight in eos.ses_energy
        esp = 0.0
        from .eos import ses_energy

        esp = ses_energy(state.temp, state.vsol[k], state.soleqs[k])
        es_j = hmho + state.therc[j][6] + R3 * esp
        est += state.x[j] * es_j
        vst += state.x[j] * state.vsol[k] * state.soleqs[k][11]

    etot = xbar * egt + est
    vtot = xbar * state.vgas + vst
    vpg = vtot / amolwt
    return Sys2Result(etot=etot, vtot=vtot, vpg=vpg)


def sys4_entropy(state: Sys1State) -> tuple[float, float, float, list[float]]:
    """Compute entropy of mixture at current equilibrium state."""
    xbar = sum(state.x[: state.n])
    if xbar <= 0.0:
        return 0.0, 0.0, 0.0, [0.0] * state.nt

    spg = R1 * (state.fgp + (state.alpha * state.temp * (state.fx - 1.0) / (state.temp + state.theta))) - R1 * state.alnp

    mixlog = 0.0
    for i in range(state.n):
        yi = state.x[i] / xbar
        if yi > 0.0:
            mixlog += yi * math.log(yi)
    spg -= R1 * mixlog

    s = [0.0] * state.nt
    sum_g = 0.0
    for i in range(state.n):
        s[i] = tdf(state.temp, state.therc[i], 0)
        sum_g += (state.x[i] / xbar) * s[i]
    sgas = sum_g + spg
    stot = xbar * sgas

    nsf = state.nt - state.n
    for k in range(nsf):
        j = state.n + k
        s[j] = tdf(state.temp, state.therc[j], 0)
        ss = ses_entropy(state.temp, state.vsol[k], state.soleqs[k])
        s[j] = s[j] + (R3 / R5) * ss
        stot += state.x[j] * s[j]

    return sgas, stot, spg, s


def _mind_reference(func_pd, p0: float, ratio: float, tol: float, cntmax: int) -> tuple[float, float, bool]:
    """MIND minimization helper."""
    # Initial three points for the bracket.
    p3 = p0
    d3 = func_pd(p3)

    p2 = p0 * ratio
    d2 = func_pd(p2)

    p1 = p2 * ratio
    d1 = func_pd(p1)

    count = 4
    last_p = p1
    last_d = d1

    while True:
        denom = p1 * (d3 - d2) + p2 * (d1 - d3) + p3 * (d2 - d1)
        if denom == 0.0:
            return last_p, last_d, False

        p = 0.5 * (
            p1 * p1 * (d3 - d2) + p2 * p2 * (d1 - d3) + p3 * p3 * (d2 - d1)
        ) / denom
        d = func_pd(p)
        last_p, last_d = p, d

        # Convergence: any pair close enough.
        if abs(d1 - d2) < tol or abs(d1 - d3) < tol or abs(d3 - d2) < tol:
            return p, d, True

        # Bracket update logic.
        if d3 > d2:
            if d3 > d1:
                p3, d3 = p, d
            else:
                p1, d1 = p, d
        else:
            if d2 < d1:
                p1, d1 = p, d
            else:
                p2, d2 = p, d

        count += 1
        if count >= cntmax:
            return p, d, False


def sys2a(
    state: Sys1State,
    *,
    rho: float,
    amolwt: float,
    eo: float,
    po: float = 1.0e-6,
    scalf: float = 1.0e-5,
    hug_temp_guess: float = 3.0e3,
    hug_ratio: float = 1.1,
    hug_tol: float = 1.0e-6,
) -> tuple[int, bool, Sys2Result]:
    """Solve Hugoniot temperature at fixed pressure."""
    vo = 1.0 / rho
    last = Sys2Result(etot=0.0, vtot=0.0, vpg=0.0)

    def f_temp(T: float) -> float:
        state.temp = T
        ind = sys1(state)
        if ind < 0:
            raise RuntimeError(str(ind))
        nonlocal last
        last = sys2(state, amolwt)
        return scalf * (last.etot - eo - 0.5 * (state.press + po) * (vo - last.vpg) * R3 * amolwt)

    try:
        temp, ok = lfb(f_temp, hug_temp_guess, ratio=hug_ratio, tol=hug_tol)
    except RuntimeError as exc:
        try:
            return int(str(exc)), False, last
        except Exception:
            return -3, False, last

    # Keep the established behavior: accept the last estimate if needed.
    state.temp = temp
    ind = sys1(state)
    if ind < 0:
        return ind, ok, last
    last = sys2(state, amolwt)
    return 0, ok, last


def sys3(
    state: Sys1State,
    *,
    rho: float,
    amolwt: float,
    eo: float,
    po: float = 1.0e-6,
    apgcj: float = 0.15,
    bpgcj: float = 0.25,
    cj_ratio: float = 0.8,
    cj_tol: float = 1.0e-6,
    cj_cntmax: int = 25,
    hug_temp_guess: float = 3.0e3,
    hug_ratio: float = 1.1,
    hug_tol: float = 1.0e-6,
) -> Sys3Result:
    """Compute C-J state."""
    vo = 1.0 / rho
    p0 = apgcj + bpgcj * (rho - 1.0)

    last_hug_ok = True
    last_state = Sys2Result(etot=0.0, vtot=0.0, vpg=0.0)

    def d_of_p(p: float) -> float:
        nonlocal last_hug_ok, last_state
        state.press = p
        ind, hug_ok, s2 = sys2a(
            state,
            rho=rho,
            amolwt=amolwt,
            eo=eo,
            po=po,
            hug_temp_guess=hug_temp_guess,
            hug_ratio=hug_ratio,
            hug_tol=hug_tol,
        )
        if ind < 0:
            raise RuntimeError(str(ind))
        last_hug_ok = last_hug_ok and hug_ok
        last_state = s2
        return vo * math.sqrt((state.press - po) / (vo - s2.vpg))

    try:
        p_cj, d_cj, mind_ok = _mind_reference(d_of_p, p0, cj_ratio, cj_tol, cj_cntmax)
    except RuntimeError as exc:
        try:
            ind = int(str(exc))
        except Exception:
            ind = -3
        return Sys3Result(
            ind=ind,
            press=state.press,
            temp=state.temp,
            detvel=0.0,
            gamma=0.0,
            pcj=state.press,
            vcj=0.0,
            cjt=state.temp,
            ucj=0.0,
            vpg=0.0,
            mind_ok=False,
            hug_ok=False,
        )

    # Synchronize state exactly at chosen p_cj.
    state.press = p_cj
    ind, hug_ok, s2 = sys2a(
        state,
        rho=rho,
        amolwt=amolwt,
        eo=eo,
        po=po,
        hug_temp_guess=hug_temp_guess,
        hug_ratio=hug_ratio,
        hug_tol=hug_tol,
    )
    if ind < 0:
        return Sys3Result(
            ind=ind,
            press=state.press,
            temp=state.temp,
            detvel=d_cj,
            gamma=0.0,
            pcj=state.press,
            vcj=0.0,
            cjt=state.temp,
            ucj=0.0,
            vpg=0.0,
            mind_ok=mind_ok,
            hug_ok=False,
        )

    detvel = vo * math.sqrt((state.press - po) / (vo - s2.vpg))
    gamma = (rho * (detvel * detvel) / state.press) - 1.0
    pcj = state.press
    vcj = s2.vpg
    cjt = state.temp
    ucj = math.sqrt(pcj * (vo - vcj))

    return Sys3Result(
        ind=0,
        press=state.press,
        temp=state.temp,
        detvel=detvel,
        gamma=gamma,
        pcj=pcj,
        vcj=vcj,
        cjt=cjt,
        ucj=ucj,
        vpg=vcj,
        mind_ok=mind_ok,
        hug_ok=(last_hug_ok and hug_ok),
    )


def _solve_isentrope_temp(
    state: Sys1State,
    target_s: float,
    *,
    temp_guess: float,
    ratio: float,
    tol: float,
) -> tuple[int, float, bool]:
    """Solve temperature at fixed pressure to match total entropy target."""

    def f_temp(T: float) -> float:
        state.temp = T
        ind = sys1(state)
        if ind < 0:
            raise RuntimeError(str(ind))
        _, stot, _, _ = sys4_entropy(state)
        return stot - target_s

    try:
        temp, ok = lfb(f_temp, temp_guess, ratio=ratio, tol=tol)
    except RuntimeError as exc:
        try:
            return int(str(exc)), state.temp, False
        except Exception:
            return -3, state.temp, False

    state.temp = temp
    ind = sys1(state)
    if ind < 0:
        return ind, temp, ok
    return 0, temp, ok


def sys4a(
    state: Sys1State,
    *,
    rho: float,
    amolwt: float,
    eo: float,
    pcj: float,
    cjt: float,
    ucj: float,
    ipvc: int = 1,
    aispr: float = 0.0,
    po: float = 1.0e-6,
    cprime: float = 0.1,
    decip: float = 0.5,
    aminp: float = 1.0e-4,
    aincp: float = 1.20,
    amaxp: float = 1.0,
    vbos2: float = 15.0,
    as_ratio_down: float = 0.9,
    as_tol_down: float = 0.5,
    as_ratio_up: float = 1.1,
    as_tol_up: float = 0.5,
) -> IsentropeResult:
    """Compute C-J isentrope."""
    vo = 1.0 / rho

    # special option: isentrope through input (P,T)
    if ipvc == 3:
        pcj = state.press
        cjt = state.temp
        ucj = 0.0
    else:
        state.press = pcj
        state.temp = cjt
        if ipvc != 1:
            # through isp chamber pressure
            state.press = aispr
            ind, _, s2 = sys2a(state, rho=rho, amolwt=amolwt, eo=eo, po=po, hug_temp_guess=cjt)
            if ind < 0:
                return IsentropeResult(ind=ind, asp=[], asv=[], ast=[], ase=[], asg=[], asup=[],
                                       fitp=[], fitt=[], fite=[], pcoef=[], tcoef=[], ecoef=[],
                                       it=0, iw=0, scj=0.0, comp_rows=[])
            cjt = state.temp
            pcj = aispr
            ucj = math.sqrt(state.press * (vo - s2.vpg))

    # C-J entropy target
    ind = sys1(state)
    if ind < 0:
        return IsentropeResult(ind=ind, asp=[], asv=[], ast=[], ase=[], asg=[], asup=[],
                               fitp=[], fitt=[], fite=[], pcoef=[], tcoef=[], ecoef=[],
                               it=0, iw=0, scj=0.0, comp_rows=[])
    _, scj, _, _ = sys4_entropy(state)
    s2 = sys2(state, amolwt)

    asp: list[float] = [state.press]
    asv: list[float] = [s2.vpg]
    ast: list[float] = [state.temp]
    ase: list[float] = [(s2.etot - eo) / (R3 * amolwt) + cprime]
    comp_rows: list[list[float]] = [list(float(v) for v in state.x)]

    # downward pressure branch
    while True:
        p_next = asp[-1] * decip
        if p_next < aminp:
            break
        state.press = p_next
        ind, _, _ = _solve_isentrope_temp(
            state, scj, temp_guess=ast[-1], ratio=as_ratio_down, tol=as_tol_down
        )
        if ind < 0:
            return IsentropeResult(ind=ind, asp=asp, asv=asv, ast=ast, ase=ase, asg=[], asup=[],
                                   fitp=[], fitt=[], fite=[], pcoef=[], tcoef=[], ecoef=[],
                                   it=len(asp), iw=0, scj=scj, comp_rows=comp_rows)
        s2 = sys2(state, amolwt)
        asp.append(state.press)
        asv.append(s2.vpg)
        ast.append(state.temp)
        ase.append((s2.etot - eo) / (R3 * amolwt) + cprime)
        comp_rows.append(list(float(v) for v in state.x))
        if len(asp) >= 99:
            break
        if ast[-1] < 300.0:
            break

    l = len(asp)

    # upward branch
    state.press = pcj
    state.temp = cjt
    while len(asp) < 99:
        p_next = state.press * aincp
        if p_next > amaxp:
            break
        state.press = p_next
        ind, _, _ = _solve_isentrope_temp(
            state, scj, temp_guess=ast[0], ratio=as_ratio_up, tol=as_tol_up
        )
        if ind < 0:
            return IsentropeResult(ind=ind, asp=asp, asv=asv, ast=ast, ase=ase, asg=[], asup=[],
                                   fitp=[], fitt=[], fite=[], pcoef=[], tcoef=[], ecoef=[],
                                   it=len(asp), iw=l, scj=scj, comp_rows=comp_rows)
        s2 = sys2(state, amolwt)
        asp.append(state.press)
        asv.append(s2.vpg)
        ast.append(state.temp)
        ase.append((s2.etot - eo) / (R3 * amolwt) + cprime)
        comp_rows.append(list(float(v) for v in state.x))

    i = len(asp)

    # Polynomial fits in log-space.
    algv = [math.log(v) for v in asv]
    sigma, pcoef, fitp_log, _ = pfts(i, 4, 0, algv, [math.log(p) for p in asp])
    _, tcoef, fitt_log, _ = pfts(i, 4, 0, algv, [math.log(t) for t in ast])
    algp = [math.log(p) for p in asp]
    _, ecoef, fite_log, _ = pfts(i, 4, 0, algp, [math.log(e) for e in ase])
    _ = sigma

    fitp = [math.exp(v) for v in fitp_log]
    fitt = [math.exp(v) for v in fitt_log]
    fite = [math.exp(v) for v in fite_log]

    asg: list[float] = []
    for av in algv:
        asg.append(
            -pcoef[1] - av * (2.0 * pcoef[2] + av * (3.0 * pcoef[3] + 4.0 * av * pcoef[4]))
        )

    # particle velocity integral (downward branch only)
    asup = [0.0] * i
    asup[0] = ucj
    for k in range(1, l):
        delv = (asv[k] - asv[k - 1]) * 0.01
        alx = [asv[k - 1] + delv * mz for mz in range(101)]
        dpdv = []
        for vx in alx:
            av = math.log(vx)
            ap = math.exp(pcoef[0] + av * (pcoef[1] + av * (pcoef[2] + av * (pcoef[3] + av * pcoef[4]))))
            der = pcoef[1] + av * (2.0 * pcoef[2] + av * (3.0 * pcoef[3] + 4.0 * av * pcoef[4]))
            val = -(ap / vx) * der
            dpdv.append(math.sqrt(max(0.0, val)))

        sm = dpdv[0] + dpdv[100] + 4.0 * dpdv[99]
        for mz in range(1, 98, 2):
            sm += 4.0 * dpdv[mz] + 2.0 * dpdv[mz + 1]
        asup[k] = asup[k - 1] + (delv / 3.0) * sm

    return IsentropeResult(
        ind=0,
        asp=asp,
        asv=asv,
        ast=ast,
        ase=ase,
        asg=asg,
        asup=asup,
        fitp=fitp,
        fitt=fitt,
        fite=fite,
        pcoef=pcoef,
        tcoef=tcoef,
        ecoef=ecoef,
        it=i,
        iw=l,
        scj=scj,
        comp_rows=comp_rows,
    )


def sys5(
    state: Sys1State,
    *,
    rho: float,
    amolwt: float,
    eo: float,
    amhugp: float = 0.50,
    delp: float = 0.05,
    po: float = 1.0e-6,
    vbos2: float = 15.0,
    hugb2: float = 3000.0,
) -> HugoniotResult:
    """Compute Hugoniot curve."""
    vo = 1.0 / rho
    press = amhugp

    hugp: list[float] = []
    hugt: list[float] = []
    hugv: list[float] = []
    hugup: list[float] = []
    hugus: list[float] = []
    comp_rows: list[list[float]] = []

    for _ in range(19):
        state.press = press
        ind, _, s2 = sys2a(
            state,
            rho=rho,
            amolwt=amolwt,
            eo=eo,
            po=po,
            hug_temp_guess=hugb2,
        )
        if ind < 0:
            return HugoniotResult(ind=ind, hugp=hugp, hugt=hugt, hugv=hugv, hugup=hugup, hugus=hugus,
                                  it=len(hugp), iw=len(hugp), comp_rows=comp_rows)

        hugp.append(press)
        hugt.append(state.temp)
        hugv.append(s2.vpg)
        comp_rows.append(list(float(v) for v in state.x))

        if vo >= s2.vpg:
            hus = vo * math.sqrt((press - po) / (vo - s2.vpg))
            hup = math.sqrt((press - po) * (vo - s2.vpg))
            hugus.append(hus)
            hugup.append(hup)
            iw = len(hugp)
        else:
            hugus.append(0.0)
            hugup.append(0.0)
            iw = len(hugp)

        press = press - delp
        if press < delp:
            break

    return HugoniotResult(
        ind=0,
        hugp=hugp,
        hugt=hugt,
        hugv=hugv,
        hugup=hugup,
        hugus=hugus,
        it=len(hugp),
        iw=iw if hugp else 0,
        comp_rows=comp_rows,
    )
