"""
Polynomial fitting utilities.

pfts: least-squares polynomial fit up to degree 5, using orthogonal
      polynomials (modified Gram-Schmidt).

poly: Horner-scheme polynomial evaluation.
"""
from __future__ import annotations
import math


def poly(x: float, n: int, a: list) -> float:
    """Evaluate polynomial of degree n-1 at x using Horner's method.

    Coefficients a[1..n] (1-based internal indexing).
    Returns: a[n] + x*(a[n-1] + x*(...a[1]...))

    Parameters
    ----------
    x : evaluation point
    n : number of coefficients (degree = n-1)
    a : 1-based list, a[1..n] are the coefficients
    """
    y = a[n]
    for i in range(2, n + 1):
        j = n - i + 1
        y = a[j] + y * x
    return y


def pfts(m: int, km: int, iw: int, x_in: list, f2_in: list,
         w_in: list | None = None):
    """Polynomial least-squares fit (degree <= 5, up to 100 pts).

    Parameters
    ----------
    m    : number of data points
    km   : degree of fit (max 5, but can go up to km+1 in loop)
    iw   : 0 = uniform weights; 1 = use w_in weights
    x_in : x data (list of m floats, 0-based external)
    f2_in: y data (list of m floats, 0-based external)
    w_in : weight data (list of m floats, 0-based external); used if iw=1

    Returns
    -------
    sigma : standard deviation of fit
    b     : list of km+1 coefficients b[0..km] (0-based external)
            Polynomial: f(x) = b[0] + b[1]*x + ... + b[km]*x^km
    y_fit : list of m fitted values (0-based external)
    dely  : list of m residuals y_fit - f2  (0-based external)
    """
    # Use 1-based work arrays to preserve the established operation order.
    x  = [0.0] + list(x_in)
    f2 = [0.0] + list(f2_in)

    s    = [0.0] * 6
    st   = [0.0] * 6
    sb   = [0.0] * 6
    f    = [0.0] * (m + 1)
    pm   = [0.0] * (m + 1)
    p    = [0.0] * (m + 1)
    b    = [0.0] * 6
    dely = [0.0] * (m + 1)
    w    = [0.0] * (m + 1)
    a    = [[0.0] * 6 for _ in range(6)]   # a[0..5][0..5], 1-based used
    t    = [0.0] * 6
    y    = [0.0] * (m + 1)

    # --- initialise ---
    fm   = 0.0
    a[1][1] = 1.0
    a[2][2] = 1.0
    fbar = 0.0
    xbar = 0.0

    for i in range(1, m + 1):
        if iw == 0:
            w2   = 1.0
            w[i] = 1.0
        else:
            w[i] = w_in[i - 1]
            w2   = math.sqrt(w[i])
        fm   += w[i]
        f[i]  = w2 * f2[i]
        pm[i] = w2
        fbar += f[i] * pm[i]
        xbar += x[i] * (pm[i] ** 2)

    xbar /= fm
    t[1]   = fbar / fm
    a[2][1] = -xbar
    pxf  = 0.0
    pxp  = 0.0

    for i in range(1, m + 1):
        p[i] = (x[i] - xbar) * pm[i]
        pxf += p[i] * f[i]
        pxp += p[i] * p[i]

    t[2]    = pxf / pxp
    pmxpm   = fm
    s[1]    = pmxpm
    km1     = km + 1

    b[1]    = t[1] * a[1][1] + t[2] * a[2][1]
    b[2]    = t[2] * a[2][2]

    sigma   = 0.0
    for k in range(2, km1 + 1):
        if k > 2:
            xpxp  = 0.0
            xpxpm = 0.0
            b[k]  = 0.0
            for j in range(1, m + 1):
                xp     = x[j] * p[j]
                xpxp  += xp * p[j]
                xpxpm += xp * pm[j]

            alpha   = xpxp  / pxp
            beta    = xpxpm / pmxpm
            ppxf    = 0.0
            ppxpp   = 0.0

            for i in range(1, m + 1):
                pt       = p[i]
                p[i]     = x[i] * pt - alpha * pt - beta * pm[i]
                ppxf    += p[i] * f[i]
                ppxpp   += p[i] * p[i]
                pm[i]    = pt

            t[k]    = ppxf  / ppxpp
            pmxpm   = pxp
            pxp     = ppxpp
            a[k][1] = -alpha * a[k-1][1] - beta * a[k-2][1]
            a[k][k-1] = a[k-1][k-2] - a[k-1][k-1] * alpha
            a[k][k] = 1.0

            if k > 3:
                k1 = k - 2
                for i in range(2, k1 + 1):
                    a[k][i] = (a[k-1][i-1]
                               - alpha * a[k-1][i]
                               - beta  * a[k-2][i])

            for i in range(1, k + 1):
                b[i] += t[k] * a[k][i]

        # --- compute sigma at degree k ---
        sig2 = 0.0
        for i in range(1, m + 1):
            y[i]     = poly(x[i], k, b)
            dely[i]  = y[i] - f2[i]
            sig2    += (dely[i] ** 2) * w[i]

        sig2  /= float(m - k)
        sigma  = math.sqrt(sig2)
        s[k]   = pxp

        for i in range(1, k + 1):
            st[i] = sigma / math.sqrt(s[i])

        for i in range(1, k + 1):
            sb[i] = 0.0
            for j in range(i, k + 1):
                sb[i] += (a[j][i] * st[j]) ** 2
            sb[i] = math.sqrt(sb[i])

    # Convert back to 0-based external lists
    km_out = km              # km1 - 1
    return (
        sigma,
        [b[i] for i in range(1, km_out + 2)],       # b[0..km]
        [y[i] for i in range(1, m + 1)],             # y_fit
        [dely[i] for i in range(1, m + 1)],          # residuals
    )
