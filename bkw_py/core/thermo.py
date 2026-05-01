"""
Thermodynamic functions for BKW detonation products.

The therc array (8 values per species):
    therc[0..4]  = polynomial coefficients a1..a5 for Cp/R(T)
    therc[5]     = integration constant ic (for entropy / free energy)
    therc[6]     = ΔHf at 298 K (cal/mol)   — used outside this module
    therc[7]     = characteristic temperature parameter (BKW EOS z-sum)

Units: R = 1.987 cal/(mol·K)
"""
from __future__ import annotations
import math


# Gas constant used in BKW (cal / mol·K)
R = 1.987


def entropy(T: float, therc: list[float]) -> float:
    """Compute S/R (dimensionless entropy) for one species.

    For ind=0:
        ans = a1 + a2*T + a3*T^2 + a4*T^3 + a5*T^4
    """
    a1, a2, a3, a4, a5, ic = therc[0], therc[1], therc[2], therc[3], therc[4], therc[5]
    return a1 + T * (a2 + T * (a3 + T * (a4 + T * a5)))


def enthalpy(T: float, therc: list[float]) -> float:
    """Compute (H - H0) / R  [K]  for one species.

    For ind=1:
        ans = ic + T^2 * (0.5*a2 + T*(2/3*a3 + T*(3/4*a4 + T*4/5*a5)))
    """
    a2, a3, a4, a5, ic = therc[1], therc[2], therc[3], therc[4], therc[5]
    return ic + T * T * (0.5 * a2 + T * (2.0/3.0 * a3 + T * (0.75 * a4 + T * 0.8 * a5)))


def free_energy(T: float, therc: list[float]) -> float:
    """Compute (F - H0) / (R·T)  [dimensionless]  for one species.

    For ind=2:
        ans = ic/T - (a1 + T*(0.5*a2 + T*(1/3*a3 + T*(1/4*a4 + T*1/5*a5))))
    """
    a1, a2, a3, a4, a5, ic = therc[0], therc[1], therc[2], therc[3], therc[4], therc[5]
    return (ic / T) - (a1 + T * (0.5 * a2 + T * (1.0/3.0 * a3 + T * (0.25 * a4 + T * 0.2 * a5))))


def heat_capacity(T: float, therc: list[float]) -> float:
    """Compute Cp/R (dimensionless) for one species.

    Derived from d(H)/dT:
        Cp/R = a1 + a2*T + a3*T^2 + a4*T^3 + a5*T^4
    Note: same polynomial as entropy (ind=0) — this is the Cp/R polynomial.
    """
    a1, a2, a3, a4, a5 = therc[0], therc[1], therc[2], therc[3], therc[4]
    return a1 + T * (a2 + T * (a3 + T * (a4 + T * a5)))


def tdf(T: float, therc: list[float], ind: int) -> float:
    """Unified TDF interface.

    Parameters
    ----------
    T     : temperature in K
    therc : list of at least 6 floats [a1, a2, a3, a4, a5, ic, ...]
    ind   : 0 → entropy S/R
            1 → enthalpy (H-H0)/R  [K]
            2 → free energy (F-H0)/(R·T)

    Returns
    -------
    float : the computed thermodynamic quantity
    """
    if ind == 0:
        return entropy(T, therc)
    elif ind == 1:
        return enthalpy(T, therc)
    elif ind == 2:
        return free_energy(T, therc)
    else:
        raise ValueError(f"tdf: ind must be 0, 1 or 2; got {ind}")


# ---------------------------------------------------------------------------
# Mixture properties
# ---------------------------------------------------------------------------

def mixture_entropy(T: float, species_x: list[float], all_therc: list[list[float]],
                    n_gas: int) -> float:
    """Entropy of ideal gas mixture S/R (per mole of mixture).

    S_mix/R = Σ (xᵢ/x̄) · S_i/R   for gas species only
    where x̄ = Σ xᵢ (total moles of gas)

    Parameters
    ----------
    T         : temperature (K)
    species_x : mole amounts x[0..nt-1]
    all_therc : therc coefficients for all species
    n_gas     : number of gas species (first n_gas entries are gas)
    """
    xbar = sum(species_x[:n_gas])
    if xbar == 0.0:
        return 0.0
    return sum((species_x[i] / xbar) * entropy(T, all_therc[i])
               for i in range(n_gas))


def mixture_enthalpy(T: float, species_x: list[float], all_therc: list[list[float]],
                     n_gas: int) -> float:
    """Enthalpy of ideal gas mixture (H-H0)/R  [K] per mole of mixture."""
    xbar = sum(species_x[:n_gas])
    if xbar == 0.0:
        return 0.0
    return sum((species_x[i] / xbar) * enthalpy(T, all_therc[i])
               for i in range(n_gas))
