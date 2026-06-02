"""
Numerical solvers for the BKW equilibrium system.

lss   — Gaussian elimination for Ax = B
lfb   — Powell's secant root finder

The public helpers keep the established BKW calling conventions while exposing
regular Python functions.
"""
from __future__ import annotations
import math


# ---------------------------------------------------------------------------
# lss — linear system solver
# ---------------------------------------------------------------------------

def lss(n: int, a: list, b: list) -> tuple[float, int]:
    """Solve the n×n linear system  A · x = b  using numpy.

    Parameters
    ----------
    n : system size
    a : flat list of n*n floats, column-major layout
        a[row + col*n]  (0-based)
    b : list of n floats (RHS), overwritten with solution on return

    Returns
    -------
    det : determinant of A
    ind : 0 on success; -7 if matrix is singular

    The solution x is written into b in-place.
    """
    import numpy as np

    # Reshape from column-major flat → numpy 2D (row-major)
    A = np.array(a[:n*n], dtype=float).reshape((n, n), order='F')
    B = np.array(b[:n],   dtype=float)

    try:
        det = float(np.linalg.det(A))
        if abs(det) == 0.0:
            return 0.0, -7
        x = np.linalg.solve(A, B)
        for i in range(n):
            b[i] = x[i]
        return det, 0
    except np.linalg.LinAlgError:
        return 0.0, -7


def lss_direct(n: int, a: list, b: list) -> tuple[float, int]:
    """Gaussian elimination with partial pivoting.

    Same interface as lss(). Provided for cross-checking; in production
    use lss() (numpy-based) which is more robust.

    a is a flat column-major array modified in-place.
    b is modified in-place; solution on return.
    """
    # Work with modifiable copies in the same layout
    # Indexing: element (row r, col c) is at index r + c*n  (0-based)
    def idx(r, c): return r + c * n

    nn = n
    mm = 1  # single RHS column

    # Find max element for initial check
    x = 0.0
    for j in range(nn):
        for k in range(nn):
            t = abs(a[idx(k, j)])
            if t > x:
                x = t
    if x == 0.0:
        return 0.0, -7

    sn = 1.0
    for j in range(nn):
        l = j                          # l = j-1 (0-based offset)
        if j == nn - 1:
            goto_11 = True
        else:
            goto_11 = False

        if not goto_11:
            t  = abs(a[idx(j, j)])
            m1 = j
            m2 = j + 1
            for k in range(m2, nn):
                xv = abs(a[idx(k, j)])
                if xv > t:
                    t  = xv
                    m1 = k

            if m1 != j:               # swap rows j and m1
                for k in range(nn):
                    a[idx(j, k)], a[idx(m1, k)] = a[idx(m1, k)], a[idx(j, k)]
                b[j], b[m1] = b[m1], b[j]
                sn = -sn

            if a[idx(j, j)] == 0.0:
                return 0.0, -7

            for k in range(m2, nn):
                # s1 = sum_{m3=0}^{l-1} a(j,m3)*a(m3,k)
                s1 = 0.0
                if l > 0:
                    for m3 in range(l):
                        s1 += a[idx(j, m3)] * a[idx(m3, k)]
                a[idx(j, k)] = (a[idx(j, k)] - s1) / a[idx(j, j)]

                # s2 = sum_{m3=0}^{j} a(k,m3)*a(m3, m2)
                s2 = 0.0
                for m3 in range(j + 1):
                    s2 += a[idx(k, m3)] * a[idx(m3, m2)]
                a[idx(k, m2)] = a[idx(k, m2)] - s2

        # label 11: process b
        # Single RHS column.
        s1 = 0.0
        if l > 0:
            for m3 in range(l):
                s1 += a[idx(j, m3)] * b[m3]
        b[j] = (b[j] - s1) / a[idx(j, j)]

    # Compute determinant
    det = a[idx(0, 0)] * sn
    if det == 0.0:
        return 0.0, -7
    if n == 1:
        return det, 0

    for j in range(1, nn):
        ajj = a[idx(j, j)]
        # Overflow guard.
        if ajj >  1e18: ajj =  1e18
        if ajj < -1e18: ajj = -1e18
        if det >  1e18: det =  1e18
        if det < -1e18: det = -1e18
        det *= ajj
    if det == 0.0:
        return 0.0, -7

    # Back substitution.
    m3 = nn - 1
    for l in range(m3):
        m1 = nn - 1 - l
        s1 = 0.0
        m2 = m1 + 1
        for k in range(m2, nn):
            s1 += a[idx(m1, k)] * b[k]
        b[m1] = b[m1] - s1

    return det, 0


# ---------------------------------------------------------------------------
# lfb — Powell's secant root finder
# ---------------------------------------------------------------------------

def lfb(func, x0: float, ratio: float = 1.1, tol: float = 1e-6,
        cntmax: int = 25) -> tuple[float, bool]:
    """Find x such that func(x) = 0 using Powell's secant method.

    Implements the BKW secant iteration as a regular callable helper.

    Parameters
    ----------
    func    : callable f(x) → float
    x0      : initial guess
    ratio   : multiplier to get the second point (default 1.1)
    tol     : convergence tolerance |f(x)| < tol
    cntmax  : maximum iterations (default 25)

    Returns
    -------
    x    : root approximation
    ok   : True if converged, False if failed (too many iterations or
           degenerate step)
    """
    if x0 == 0.0:
        x0 = 1.0

    # --- iteration 1: evaluate at x0 ---
    xp   = x0
    fp   = func(xp)
    if abs(fp) < tol:
        return xp, True

    # --- iteration 2: second point x0 * ratio ---
    x8   = xp          # tx(8): previous x
    f9   = fp          # tx(9): f at previous x
    xp   = x0 * ratio
    fp   = func(xp)
    if abs(fp) < tol:
        return xp, True

    # --- iteration 3: first secant step ---
    x6   = xp          # tx(6)
    f7   = fp          # tx(7)
    # secant: xp = x6 - f7*(x6 - x8)/(f7 - f9)
    denom = f7 - f9
    if denom == 0.0:
        return xp, False
    xp   = x6 - f7 * (x6 - x8) / denom
    fp   = func(xp)
    if abs(fp) < tol:
        return xp, True

    # --- iterations 4+: continuing secant with bracket tracking ---
    for count in range(4, cntmax + 1):
        x4 = xp        # tx(4)
        f5 = fp        # tx(5)

        t = x4 - x6
        if t == 0.0:
            return xp, False
        if abs(f5) < tol:
            return xp, True
        r = f5 - f7
        if r == 0.0:
            return xp, False

        xp_new = x4 - f5 * (t / r)

        # Bracket update logic.
        if f5 * f7 < 0.0 or f5 * f9 >= 0.0:
            # goto 11: update bracket
            f9 = f7
            x8 = x6
            # fall through to update x6, f7
            x7_new = f5
            x6_new = x4
            x6 = x6_new
            f7 = x7_new
        else:
            # Check direction and keep the bracket useful.
            if xp_new > x4:
                # goto 6
                if xp_new <= x8:
                    # goto 8: recompute xp from x4, x8 bracket
                    xp_new = x4 - f5 * (x4 - x8) / (f5 - f9)
                # goto 10
                x6 = x4
                f7 = f5
            else:
                if xp_new > x8:
                    # goto 8
                    xp_new = x4 - f5 * (x4 - x8) / (f5 - f9)
                # goto 10
                x6 = x4
                f7 = f5

        xp = xp_new
        fp = func(xp)

    # Too many iterations; return best estimate.
    return xp, False


# ---------------------------------------------------------------------------
# mind — Chapman–Jouguet point finder
# ---------------------------------------------------------------------------
# Note: mind is placed here because it uses the same secant-method logic
# as lfb.  It will be called from core/detonation.py.

def mind(func_pd, pg0: float, ratio: float = 0.25, tol: float = 1e-6,
         cntmax: int = 25) -> tuple[float, float, bool]:
    """Find C-J pressure by minimising |D - D_CJ|.

    The C-J condition: detonation velocity D is minimum on the Hugoniot.
    We find the pressure p* where d(D)/dp = 0 using Powell's parabolic
    minimum search.

    Uses inverted-parabola (quadratic Lagrange) interpolation.

    Parameters
    ----------
    func_pd : callable(p) → D   — compute detonation velocity at pressure p
    pg0     : initial pressure guess
    ratio   : multiplier for second/third trial points
    tol     : convergence on |D1 - D2|
    cntmax  : maximum iterations

    Returns
    -------
    p_cj : C-J pressure
    d_cj : C-J detonation velocity
    ok   : True if converged
    """
    # --- Step 1: three initial points ---
    p3 = pg0
    d3 = func_pd(p3)

    p2 = pg0 * (1.0 + ratio)
    d2 = func_pd(p2)

    p1 = p2 * (1.0 + ratio)
    d1 = func_pd(p1)

    def parabola_min(p1, d1, p2, d2, p3, d3):
        """Quadratic Lagrange minimum."""
        denom = p1 * (d3 - d2) + p2 * (d1 - d3) + p3 * (d2 - d1)
        if denom == 0.0:
            return (p1 + p2 + p3) / 3.0
        num = (p1**2 * (d3 - d2) + p2**2 * (d1 - d3) + p3**2 * (d2 - d1))
        return 0.5 * num / denom

    for count in range(4, cntmax + 1):
        p = parabola_min(p1, d1, p2, d2, p3, d3)
        d = func_pd(p)

        # Convergence check
        if (abs(d1 - d2) < tol and abs(d1 - d3) < tol
                and abs(d3 - d2) < tol):
            return p, d, True

        # Update bracket: replace the worst point
        # Check ordering of d3, d2, d1.
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

    # Did not converge
    p = parabola_min(p1, d1, p2, d2, p3, d3)
    return p, func_pd(p), False
