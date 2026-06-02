"""
Chemical equilibrium solver for the BKW detonation code.

equil()  — Gibbs free energy minimisation via Lagrange multipliers.

sys1()   — Given P, T → compute gas volume V and equilibrium composition.

== Mathematical background ==

equil solves the linearised first-order optimality conditions
(KKT system) for:

    min  G = Σ_i fe_i · x_i
    s.t. Σ_i aik[i][j] · x_i = elem[j]  for j=0..m-1

The nm1 × nm1 linear system (nm1 = n_tot + m + 1):

Unknowns (columns):
  0..n_tot-1   : new mole numbers  x_i
  n_tot        : μ (sum-constraint multiplier = new gas total Σx_gas)
  n_tot+1..nm1-1: λ_j (Lagrange multipliers for element constraints)

Equations (rows):
  Gas i (0..n_gas-1):
    (1/y_i)·x_i  - (1/ybar)·μ  + Σ_j aik[i][j]·λ_j
       = -(fe_i + ln(y_i/ybar))

  Solid i (n_gas..n_tot-1):
    Σ_j aik[i][j]·λ_j = -fe_i

  Element j (n_tot+j):
    Σ_i aik[i][j]·x_i = elem[j]

  Sum / normalisation (nm1-1):
    Σ_{gas} x_i - μ = 0

== sys1 algorithm ==

Outer loop (up to 50 iterations):
  1. z_sum = Σ_i (x_i/xbar)·therc[i][7]  (gas only)
  2. Solve BKW EOS: f(V_gas) = fx - P·V/(R2·T) = 0  for V_gas
  3. Compute fgp (EOS free energy correction)
  4. Compute free energies fe[i] for all species
     Gas:   fe_i = tdf(T,therc_i,2)/R1 + ΔHf_i/(R1·T) + ln(P·atm/bar) - EOS_corr
     Solid: fe_i = tdf(T,therc_i,2)/R1 + ΔHf_i/(R1·T) + F_solid/(R2·T)
  5. Call equil() → new mole numbers
  6. Converge on  Σ|x_new - x_old| < exitme

Physical constants:
  r1 = 1.98718        cal/(mol·K)
  r2 = 8.31439e-5     Mbar·cm³/(mol·K)
  abtoa = 0.98692e+6  atm/Mbar
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

from .thermo import tdf
from .eos import (bkw_z_sum, bkw_aw, bkw_fx, bkw_fgp,
                  bkw_volume, ses_volume, ses_free_energy,
                  R1, R2, ABTOA)
from .solvers import lss


# ---------------------------------------------------------------------------
# equil — chemical equilibrium via Lagrange linearisation
# ---------------------------------------------------------------------------

def equil(aik: list, y: list, fe: list, elem: list,
          m: int, n_gas: int, n_tot: int,
          amaxe: float = 1e-6,
          aminx: float = 1e-8,
          aminy: float = 1e-5,
          max_iter: int = 50) -> int:
    """Solve chemical equilibrium (Gibbs minimisation, linearised Newton).

    Parameters
    ----------
    aik     : stoichiometry matrix, aik[species][element], shape (n_tot, m)
    y       : mole numbers, len=n_tot; updated in-place to new equilibrium
    fe      : dimensionless free energies, len=n_tot; not modified
    elem    : elemental mole counts, len=m
    m       : number of elements
    n_gas   : number of gas species
    n_tot   : total number of species (gas + solid)
    amaxe   : convergence tolerance  Σ|x_new - y_old|
    aminx   : minimum gas mole number
    aminy   : minimum any mole number (floor before iteration)
    max_iter: maximum outer iterations (default 50)

    Returns
    -------
    0   : converged normally
    -1  : non-last solid disappeared (equil error)
    -7  : singular matrix

    y is modified in-place. n_tot may logically decrease (last solid removal)
    but the list length is unchanged; disappeared solid is set to 0.
    """
    import numpy as np

    n_sol = n_tot - n_gas

    # Floor: ensure no mole number is below aminy
    for i in range(n_tot):
        if y[i] < aminy:
            y[i] = aminy

    sst = False           # flag: a solid disappeared
    active_tot = n_tot    # current active species count (may shrink)

    for cpt in range(max_iter + 1):
        n_gas_a = n_gas
        n_tot_a = active_tot

        nm1  = n_tot_a + m + 1   # system size
        n_sol_a = n_tot_a - n_gas_a

        ybar  = sum(y[:n_gas_a])
        if ybar == 0.0:
            ybar = 1e-30
        rbary = 1.0 / ybar

        # ----------------------------------------------------------------
        # Build right-hand side b  (length nm1)
        # ----------------------------------------------------------------
        b = [0.0] * nm1

        for i in range(n_gas_a):
            b[i] = -(fe[i] + math.log(rbary * y[i]))
        for i in range(n_gas_a, n_tot_a):
            b[i] = -fe[i]
        for j in range(m):
            b[n_tot_a + j] = elem[j]
        # b[nm1-1] = 0.0  (sum constraint RHS, already 0)

        # ----------------------------------------------------------------
        # Build matrix A  (nm1 × nm1, stored col-major flat list)
        # ----------------------------------------------------------------
        # Using numpy for clarity; convert to col-major flat for lss()
        A = [[0.0] * nm1 for _ in range(nm1)]   # A[row][col]

        # Gas diagonal: A[i][i] = 1/y[i]
        for i in range(n_gas_a):
            A[i][i] = 1.0 / y[i]

        # Species columns: element rows and sum row
        for i_sp in range(n_tot_a):
            # Element rows
            for j_el in range(m):
                A[n_tot_a + j_el][i_sp] = aik[i_sp][j_el]
            # Sum row (gas only)
            if i_sp < n_gas_a:
                A[nm1 - 1][i_sp] = 1.0

        # μ column (index n_tot_a): -rbary for gas rows, -1 for sum row
        for i in range(n_gas_a):
            A[i][n_tot_a] = -rbary
        A[nm1 - 1][n_tot_a] = -1.0

        # λ columns (indices n_tot_a+1 .. nm1-1)
        for j_el in range(m):
            col = n_tot_a + 1 + j_el
            for i_sp in range(n_tot_a):
                A[i_sp][col] = aik[i_sp][j_el]

        # ----------------------------------------------------------------
        # Solve with numpy (more robust than lss_direct for large systems)
        # ----------------------------------------------------------------
        A_np = np.array(A)
        b_np = np.array(b)
        try:
            x_all = np.linalg.solve(A_np, b_np)
        except np.linalg.LinAlgError:
            return -7

        x = list(x_all[:n_tot_a])

        # Floor gas moles
        for i in range(n_gas_a):
            if x[i] < aminx:
                x[i] = aminx

        # ----------------------------------------------------------------
        # Check if any solid disappeared
        # ----------------------------------------------------------------
        solid_ok = True
        if n_sol_a > 0:
            for i in range(n_gas_a, n_tot_a):
                if x[i] < 0.0:
                    if i == n_tot_a - 1:
                        # Last solid disappeared → remove it
                        active_tot -= 1
                        sst = True
                        # Keep y unchanged for this solid (will be zeroed at end)
                        solid_ok = False
                        break
                    else:
                        return -1   # non-last solid disappeared: error

        # ----------------------------------------------------------------
        # Check convergence
        # ----------------------------------------------------------------
        err = sum(abs(y[i] - x[i]) for i in range(n_tot_a))

        # Update y for next iteration
        for i in range(n_tot_a):
            y[i] = x[i]

        if not solid_ok:
            # Re-run with reduced active_tot
            for i in range(n_tot_a):
                if y[i] < aminy:
                    y[i] = aminy
            continue

        if err < amaxe:
            break

        if cpt >= max_iter:
            break  # Accept last iterate after max_iter

    # If a solid disappeared, add it back with 0 moles
    if sst:
        for i in range(active_tot, n_tot):
            y[i] = 0.0

    return 0


# ---------------------------------------------------------------------------
# sys1 — given P, T compute gas volume and equilibrium composition
# ---------------------------------------------------------------------------

@dataclass
class Sys1State:
    """Mutable state produced and consumed by sys1.

    Initialise from BKWData before first call; sys1 updates it in-place.
    """
    # --- inputs (read from BKWData) ---
    x:      list        # mole numbers, len=nt  (updated by equil)
    therc:  list        # therc[i][0..7], len=nt
    soleqs: list        # soleqs[k][0..11], len=nsf
    aik:    list        # aik[i][j] stoichiometry, shape (nt, m)
    elem:   list        # element moles, len=m
    n:      int         # gas species count
    nt:     int         # total species count
    m:      int         # element count
    alpha:  float
    beta:   float
    theta:  float
    kappa:  float
    temp:   float       # K
    press:  float       # Mbar

    # --- outputs (filled by sys1) ---
    vgas:   float = 0.0       # gas volume, cm³/mol
    vsol:   list  = field(default_factory=list)  # solid volumes, cm³/g (len=nsf)
    freene: list  = field(default_factory=list)  # free energies (len=nt)
    xn1:    list  = field(default_factory=list)  # previous moles (len=nt)
    fx:     float = 0.0       # BKW compressibility factor
    fgp:    float = 0.0       # free energy EOS correction
    alnp:   float = 0.0       # ln(P · abtoa)  = ln(P in atm)
    xbar:   float = 0.0       # total gas moles
    r1t:    float = 0.0       # R1 * T
    r2t:    float = 0.0       # R2 * T

    # --- solver parameters ---
    v_guess:  float = 15.0    # initial V_gas guess (cm³/mol)
    v_ratio:  float = 1.1     # lfb ratio for second V point
    v_tol:    float = 1e-6    # lfb convergence tolerance
    exitme:   float = 2e-5    # sys1 outer convergence tolerance
    amaxe:    float = 1e-6    # equil inner convergence tolerance
    aminx:    float = 1e-8    # minimum gas mole count
    aminy:    float = 1e-5    # minimum any mole count


def sys1(s: Sys1State) -> int:
    """Compute chemical equilibrium at given (T, P).

    Updates s.x (mole numbers), s.vgas, s.vsol, s.freene,
    s.fx, s.fgp, s.alnp, s.xbar, s.r1t, s.r2t in-place.

    Returns
    -------
    0   : success
    -1  : lfb gas volume failure
    -2  : lfb solid volume failure
    -3  : equil error
    -7  : equil singular matrix
    """
    T    = s.temp
    P    = s.press
    nsf  = s.nt - s.n

    # Ensure output lists are the right size
    if len(s.vsol) < nsf:
        s.vsol   = [0.0] * nsf
    if len(s.freene) < s.nt:
        s.freene = [0.0] * s.nt
    if len(s.xn1) < s.nt:
        s.xn1    = [0.0] * s.nt

    s.r1t = R1 * T
    s.r2t = R2 * T

    cpt = 0.0

    # -----------------------------------------------------------------------
    # Outer convergence loop
    # -----------------------------------------------------------------------
    while True:
        # 1. Compute z_sum (characteristic parameter for BKW EOS)
        z_sum = bkw_z_sum(s.x, s.therc, s.n)

        # 2. Solve for gas volume V_gas via lfb
        vgas, ok = bkw_volume(P, T, s.alpha, s.beta, s.theta, s.kappa,
                               z_sum,
                               v_guess=s.v_guess,
                               ratio=s.v_ratio,
                               tol=s.v_tol)
        if not ok:
            # Accepted with warning; continue with last vgas estimate
            pass   # use last vgas estimate
        s.vgas = vgas

        # Recompute aw, fx, baw for the found volume
        tta  = (T + s.theta) ** s.alpha
        z    = s.kappa * z_sum
        aw   = z / (vgas * tta)
        baw  = max(-37.0, min(37.0, s.beta * aw))
        s.fx = 1.0 + aw * math.exp(baw)

        # 3. Compute fgp and alnp
        s.fgp  = -(math.exp(baw) - 1.0) / s.beta + math.log(s.fx)
        s.alnp = math.log(P * ABTOA)

        # 4. Compute dimensionless free energies for all species
        #
        # Gas species:
        #   fe_i = (F-H0)/(R·T) / R1  +  ΔHf/(R1·T)  +  ln(P_atm)
        #          - (fgp - κ·bchar_i·(fx-1)/z_sum_unnorm)
        #
        # where z = kappa * z_sum  (already multiplied by kappa above)
        for j in range(s.n):
            fho_t = tdf(T, s.therc[j], 2)   # (F-H0)/(R·T) in R units
            fe = (fho_t / R1
                  + s.therc[j][6] / s.r1t
                  + s.alnp
                  - (s.fgp - s.kappa * s.therc[j][7] * (s.fx - 1.0) / z))
            s.freene[j] = fe

        # Solid species:
        #   fe_i = (F-H0)/(R·T) / R1  +  ΔHf/(R1·T)
        #          + F_solid(P,T,V) / (R2·T)
        for k in range(nsf):
            j = s.n + k
            fho_t = tdf(T, s.therc[j], 2)
            fe_gas_part = fho_t / R1 + s.therc[j][6] / s.r1t

            # Solid volume from ses
            sesp = [P, T, 0.0]
            V_sol, ok2 = ses_volume(P, T, s.soleqs[k])
            if not ok2:
                return -2
            s.vsol[k] = V_sol

            # Solid free energy contribution
            fsp = ses_free_energy(P, T, V_sol, s.soleqs[k])
            s.freene[j] = fe_gas_part + fsp / s.r2t

        # Save current moles for convergence check
        for i in range(s.nt):
            s.xn1[i] = s.x[i]

        # 5. Chemical equilibrium
        ind = equil(s.aik, s.x, s.freene, s.elem,
                    s.m, s.n, s.nt,
                    amaxe=s.amaxe,
                    aminx=s.aminx,
                    aminy=s.aminy)

        if ind == -1:
            return -3
        if ind == -7:
            return -7

        # 6. Check outer convergence: Σ|x_new - x_old| < exitme
        amoler = sum(abs(s.x[i] - s.xn1[i]) for i in range(s.nt))
        if amoler < s.exitme:
            return 0

        cpt += 1.0
        if cpt > 50.0:
            return 0   # Accept after 50 iterations (reference grace exit)

        # Continue outer loop
