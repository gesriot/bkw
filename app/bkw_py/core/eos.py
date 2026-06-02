"""
Equations of State for the BKW detonation code.

bkw_*   — BKW gas-phase EOS (Becker-Kistiakowsky-Wilson)
ses_*   — Cowan solid/condensed-phase EOS

Physical constants:
    r1 = 1.98718   cal/(mol·K)     gas constant
    r2 = 8.31439e-5  Mbar·cm³/(mol·K)  = R in (Mbar, cm³) units
    r3 = 2.39004905e+4  cal/Mbar·cm³  = 1/(cm³·Mbar/cal)
    r5 = 1.16056e+4  K/eV   (= eV→K)
    r6 = log10(e) = 0.4342944819

BKW EOS (pressure in Mbar, volume in cm³/mol):
    P · V = R·T · fx
    fx    = 1 + aw · exp(β·aw)
    aw    = κ · z_sum / (V · (T + θ)^α)
    z_sum = Σ (xᵢ/x̄) · b_char_i    (weighted characteristic parameter)

Cowan solid EOS:
    P(ρ) = a2 + a3·ρ + a4·ρ² + a5·ρ³ + a6·ρ⁴
          + (a7 + a8·ρ)·Tv
          + (a9 + a10/ρ + a11/ρ²)·Tv²
    where ρ = 1/V  (cm³/g)⁻¹,  Tv = T/11605.6  (eV)
"""
from __future__ import annotations
import math
from .solvers import lfb

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
R1    = 1.98718          # cal / (mol·K)
R2    = 8.31439e-5       # Mbar·cm³ / (mol·K)
R3    = 2.39004905e+4    # cal / (Mbar·cm³)   = 1 / (Mbar·cm³ / cal)
R5    = 1.16056e+4       # K / eV
R6    = 0.4342944819     # log10(e)
ABTOA = 0.98692e+6       # atm/Mbar

# Cowan Tv denominator (K/eV)
TV_DENOM = 11605.6


# ---------------------------------------------------------------------------
# BKW gas EOS
# ---------------------------------------------------------------------------

def bkw_z_sum(x: list[float], therc: list[list[float]], n_gas: int) -> float:
    """Compute z_sum = Σ (xᵢ/x̄) · therc[i][7]  for gas species.

    therc[i][7] (0-based) is the characteristic temperature parameter bᵢ
    used in the BKW EOS x-parameter.
    """
    xbar = sum(x[:n_gas])
    if xbar == 0.0:
        return 0.0
    return sum((x[i] / xbar) * therc[i][7] for i in range(n_gas))


def bkw_aw(v_gas: float, T: float, alpha: float, beta: float,
           theta: float, kappa: float, z_sum: float) -> float:
    """Compute aw = κ·z_sum / (V·(T+θ)^α) — the BKW x-parameter."""
    tta = (T + theta) ** alpha
    return kappa * z_sum / (v_gas * tta)


def bkw_fx(aw: float, beta: float) -> float:
    """Compute fx = 1 + aw·exp(β·aw) — the BKW compressibility factor."""
    baw = beta * aw
    baw = max(-37.0, min(37.0, baw))
    return 1.0 + aw * math.exp(baw)


def bkw_pressure(v_gas: float, T: float, alpha: float, beta: float,
                 theta: float, kappa: float, z_sum: float) -> float:
    """Compute gas pressure P [Mbar] from V [cm³/mol], T [K], BKW params."""
    aw = bkw_aw(v_gas, T, alpha, beta, theta, kappa, z_sum)
    fx = bkw_fx(aw, beta)
    return R2 * T * fx / v_gas


def bkw_fgp(aw: float, beta: float) -> float:
    """Free energy EOS correction: fgp = -(exp(β·aw)-1)/β + ln(fx)."""
    baw = beta * aw
    baw = max(-37.0, min(37.0, baw))
    fx  = 1.0 + aw * math.exp(baw)
    return -(math.exp(baw) - 1.0) / beta + math.log(fx)


def bkw_volume(press: float, T: float, alpha: float, beta: float,
               theta: float, kappa: float, z_sum: float,
               v_guess: float = 15.0, ratio: float = 1.1,
               tol: float = 1e-6) -> tuple[float, bool]:
    """Solve for gas volume V [cm³/mol] given P [Mbar] and T [K].

    Solves  fx - P·V/(R2·T) = 0  for V via lfb iteration.

    Returns (v_gas, converged).
    """
    tta = (T + theta) ** alpha
    z   = kappa * z_sum          # kappa already multiplied

    def f(v):
        aw  = z / (v * tta)
        baw = beta * aw
        baw = max(-37.0, min(37.0, baw))
        fx  = 1.0 + aw * math.exp(baw)
        return fx - press * v / (R2 * T)

    return lfb(f, v_guess, ratio=ratio, tol=tol)


# ---------------------------------------------------------------------------
# Cowan solid EOS  (subroutine ses)
# ---------------------------------------------------------------------------
# soleqs array (12 values, 0-based):
#   [0]  = V0   (reference specific volume, cm³/g)
#   [1]  = a    polynomial coefficient (pressure)
#   [2]  = b    polynomial coefficient
#   [3]  = c    polynomial coefficient
#   [4]  = d    polynomial coefficient
#   [5]  = e    polynomial coefficient
#   [6]  = a1   thermal coefficient
#   [7]  = a2   thermal coefficient
#   [8]  = c1   electronic coefficient
#   [9]  = c2   electronic coefficient
#   [10] = c3   electronic coefficient
#   [11] = molwt  molecular weight (g/mol)
# ---------------------------------------------------------------------------

def ses_volume(press: float, T: float, soleqs: list[float],
               v_guess_ratio: float = 1.1, tol: float = 1e-6
               ) -> tuple[float, bool]:
    """Compute specific volume V [cm³/g] for solid at (P [Mbar], T [K]).

    If soleqs[1] == 0 (incompressible): returns V0 = soleqs[0].
    """
    V0 = soleqs[0]
    if soleqs[1] == 0.0:
        return V0, True

    Tv = T / TV_DENOM       # temperature in eV

    def f(rho):             # rho = 1/V (density, g/cm³)
        # cold EOS + thermal + electronic
        cold    = (soleqs[1] + rho * (soleqs[2] + rho * (soleqs[3]
                  + rho * (soleqs[4] + rho * soleqs[5]))))
        thermal = (soleqs[6] + soleqs[7] * rho) * Tv
        elec    = (soleqs[8] + soleqs[9] / rho + soleqs[10] / (rho * rho)) * Tv * Tv
        return cold + thermal + elec - press

    x0 = v_guess_ratio / V0      # initial density guess
    rho, ok = lfb(f, x0, ratio=v_guess_ratio, tol=tol)
    if ok and rho > 0.0:
        return 1.0 / rho, True

    # Fallback: bracket on log scale + bisection (robust for hard states).
    grid = []
    for k in range(-8, 9):
        grid.append(max(1e-12, x0 * (10.0 ** k)))

    vals = []
    for g in grid:
        try:
            vals.append(f(g))
        except Exception:
            vals.append(float("nan"))

    lo = hi = None
    for i in range(len(grid) - 1):
        a, b = vals[i], vals[i + 1]
        if math.isnan(a) or math.isnan(b):
            continue
        if a == 0.0:
            return 1.0 / grid[i], True
        if a * b < 0.0:
            lo, hi = grid[i], grid[i + 1]
            break

    if lo is None or hi is None:
        # keep previous behavior signal
        return (1.0 / rho if rho > 0.0 else V0), False

    flo = f(lo)
    fhi = f(hi)
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol:
            return 1.0 / mid, True
        if flo * fm <= 0.0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm

    mid = 0.5 * (lo + hi)
    return 1.0 / mid, True


def _ses_integral(V: float, Tv: float, soleqs: list[float]) -> float:
    """Compute the integral F(V) used in ses free energy / energy / entropy.

    Free energy form:
        f(i) = (a2·V + a3·lnV - a4/V - a5/(2·V²) - a6/(3·V³))
               + (a7·V + a8·lnV)·Tv
               + (a9·V + a10·V²/2 + a11·V³/3)·Tv²
    """
    lnV  = math.log(V)
    rho  = 1.0 / V
    cold = (soleqs[1] * V + soleqs[2] * lnV
            - soleqs[3] * rho - soleqs[4] * 0.5 * rho**2
            - soleqs[5] / 3.0 * rho**3)
    therm = (soleqs[6] * V + soleqs[7] * lnV) * Tv
    elec  = (soleqs[8] * V + 0.5 * soleqs[9] * V**2
             + soleqs[10] / 3.0 * V**3) * Tv**2
    return cold + therm + elec


def ses_free_energy(press: float, T: float, V: float,
                    soleqs: list[float]) -> float:
    """Compute dimensionless solid free energy  F_solid / (R2·T).

    ans = molwt * (P·V1 - (F(V1) - F(V0)))
    where V1=V (current), V0=soleqs[0] (reference).
    Result is in Mbar·cm³/mol (= molwt × Mbar·cm³/g).

    Caller divides by R2·T to get dimensionless.
    """
    if soleqs[1] == 0.0:
        return press * soleqs[0] * soleqs[11]

    Tv   = T / TV_DENOM
    V0   = soleqs[0]
    f1   = _ses_integral(V, Tv, soleqs)
    f2   = _ses_integral(V0, Tv, soleqs)
    return soleqs[11] * (press * V - (f1 - f2))


def ses_energy(T: float, V: float, soleqs: list[float]) -> float:
    """Compute solid internal energy  E_solid (Mbar·cm³/mol).

        f(i) = (a9·V + a10·V²/2 + a11·V³/3)·Tv²
               - (a2·V + a3·lnV - a4/V - a5/(2·V²) - a6/(3·V³))
    ans = molwt * (f(V1) - f(V0))
    """
    if soleqs[1] == 0.0:
        return 0.0

    Tv = T / TV_DENOM
    V0 = soleqs[0]

    def _energy_integral(Vi):
        lnV  = math.log(Vi)
        rho  = 1.0 / Vi
        elec = (soleqs[8] * Vi + 0.5 * soleqs[9] * Vi**2
                + soleqs[10] / 3.0 * Vi**3) * Tv**2
        cold = (soleqs[1] * Vi + soleqs[2] * lnV
                - soleqs[3] * rho - 0.5 * soleqs[4] * rho**2
                - soleqs[5] / 3.0 * rho**3)
        return elec - cold

    return soleqs[11] * (_energy_integral(V) - _energy_integral(V0))


def ses_entropy(T: float, V: float, soleqs: list[float]) -> float:
    """Compute solid entropy  S_solid (Mbar·cm³/(mol·K)).

        f(i) = (a7·V + a8·lnV) + 2·Tv·(a9·V + a10·V²/2 + a11·V³/3)
    ans = molwt * (f(V1) - f(V0))
    """
    if soleqs[1] == 0.0:
        return 0.0

    Tv = T / TV_DENOM
    V0 = soleqs[0]

    def _entropy_integral(Vi):
        lnV  = math.log(Vi)
        therm = soleqs[6] * Vi + soleqs[7] * lnV
        elec  = 2.0 * Tv * (soleqs[8] * Vi + 0.5 * soleqs[9] * Vi**2
                             + soleqs[10] / 3.0 * Vi**3)
        return therm + elec

    return soleqs[11] * (_entropy_integral(V) - _entropy_integral(V0))


def ses(p_arr: list[float], soleqs: list[float], ind: int,
        tol: float = 1e-6) -> tuple[float, float, int]:
    """Unified Cowan solid EOS interface.

    Parameters
    ----------
    p_arr : [press, T, V]  (Mbar, K, cm³/g)
             ind=0: p_arr[2] is OUTPUT (volume computed from P,T)
             ind=1,2,3: p_arr[2] is INPUT (volume already known)
    soleqs : 12 EOS coefficients (0-based, as loaded from BKWDATA/ZZZSOLEQ)
    ind    : 0=volume, 1=free energy, 2=energy, 3=entropy

    Returns
    -------
    ans  : computed quantity
    v    : specific volume (updated if ind=0)
    err  : 0 = OK; -1 = lfb iteration error
    """
    press = p_arr[0]
    T     = p_arr[1]
    V     = p_arr[2] if ind != 0 else 0.0

    if ind == 0:
        v, ok = ses_volume(press, T, soleqs, tol=tol)
        return v, v, 0 if ok else -1

    elif ind == 1:
        ans = ses_free_energy(press, T, V, soleqs)
        return ans, V, 0

    elif ind == 2:
        ans = ses_energy(T, V, soleqs)
        return ans, V, 0

    elif ind == 3:
        ans = ses_entropy(T, V, soleqs)
        return ans, V, 0

    else:
        raise ValueError(f"ses: ind must be 0..3; got {ind}")
