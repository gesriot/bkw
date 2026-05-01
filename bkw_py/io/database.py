"""
Readers for USERBKW database files:
  ZZZCOMPS  — component library (explosives/propellants)
  ZZZSOLEQ  — solid/condensed-phase EOS coefficients
  ZZZTHERC  — thermochemical coefficients (therc + elemental composition)

All three files are created and maintained by USERBKW.
They are used to generate BKWDATA input files.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .reference_io import read_e18, parse_reference_float


# ---------------------------------------------------------------------------
# ZZZCOMPS
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """One entry from ZZZCOMPS.

    Fixed-width format per entry:
        Line  1: 1x, a20, 2e18.11  → name (20), density (g/cm³), ΔHf (cal/mol)
        Lines …: 1x, a20, e18.11   → element symbol (20), stoichiometry
        Sentinel: element == 'zzz', stoichiometry = molecular_weight
    """
    name: str
    density: float          # g/cm³
    delta_hf: float         # cal/mol, heat of formation
    elements: dict          # {symbol: stoichiometry_count}  e.g. {'c':3,'h':6,'n':6,'o':6}
    mol_weight: float       # g/mol (from 'zzz' sentinel line)


def load_zzzcomps(path: str | Path) -> list[Component]:
    """Load all entries from a ZZZCOMPS file.

    Returns a list of Component objects in file order.
    """
    path = Path(path)
    components = []
    with open(path, encoding="ascii", errors="replace") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        # format: 1x, a20, 2e18.11
        # field layout: col 1 = space, col 2-21 = name, col 22-39 = density,
        #               col 40-57 = dhf
        if len(line.rstrip('\n')) < 22:
            i += 1
            continue
        name_field = line[1:21].rstrip()
        if not name_field:
            i += 1
            continue

        # Read density and ΔHf from the same line (cols 22-57, two E18.11)
        data_part = line[21:].rstrip('\n')
        density = parse_reference_float(data_part[:18]) if len(data_part) >= 18 else 0.0
        delta_hf = parse_reference_float(data_part[18:36]) if len(data_part) >= 36 else 0.0

        elements = {}
        mol_weight = 0.0
        i += 1

        while i < len(lines):
            eline = lines[i]
            if len(eline.rstrip('\n')) < 22:
                break
            elem_name = eline[1:21].rstrip()
            if not elem_name:
                break
            quant_str = eline[21:21+18].rstrip('\n') if len(eline) > 21 else ""
            quant = parse_reference_float(quant_str) if quant_str.strip() else 0.0

            if elem_name == 'zzz':
                mol_weight = quant
                i += 1
                break
            else:
                elements[elem_name] = quant
                i += 1

        components.append(Component(
            name=name_field,
            density=density,
            delta_hf=delta_hf,
            elements=elements,
            mol_weight=mol_weight,
        ))

    return components


# ---------------------------------------------------------------------------
# ZZZSOLEQ
# ---------------------------------------------------------------------------

@dataclass
class SolidEOS:
    """One entry from ZZZSOLEQ (solid/condensed phase EOS coefficients).

    Fixed-width format per entry:
        Line 1:    a10           → species name
        Lines 2-4: 4e18.11 each → soleqs[0..11]  (12 coefficients total)

    The Cowan EOS uses soleqs[0..10]; soleqs[11] = molecular weight.
    """
    name: str
    soleqs: list[float]     # 12 coefficients


def load_zzzsoleq(path: str | Path) -> dict[str, SolidEOS]:
    """Load all entries from a ZZZSOLEQ file.

    Returns {name: SolidEOS}.
    """
    path = Path(path)
    result = {}
    with open(path, encoding="ascii", errors="replace") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        name = line[:10].rstrip()
        if not name:
            i += 1
            continue
        i += 1

        soleqs = []
        for _ in range(3):          # 3 lines × 4 values = 12
            if i >= len(lines):
                break
            soleqs.extend(read_e18(lines[i].rstrip('\n'), 4))
            i += 1

        result[name] = SolidEOS(name=name, soleqs=soleqs)

    return result


# ---------------------------------------------------------------------------
# ZZZTHERC
# ---------------------------------------------------------------------------

@dataclass
class ThermSpecies:
    """One entry from ZZZTHERC (thermochemical data for one species).

    Fixed-width format per entry:
        Line 1:    a10         → species name
        Line 2:    4e18.11     → therc[0..3]
        Line 3:    4e18.11     → therc[4..7]
        Line 4:    a (free)    → phase: ' gas' or ' solid'
        Then alternating lines until sentinel -999:
            e18.11  → coefficient value (if -999.0 → end of list)
            a       → element symbol

    therc[0..4]  = polynomial coefficients a1..a5 for Cp/R
    therc[5]     = integration constant (ic) for entropy
    therc[6]     = ΔHf at 298 K (cal/mol)
    therc[7]     = characteristic temperature parameter (used in BKW EOS)
    """
    name: str
    therc: list[float]          # 8 values
    phase: str                  # 'gas' or 'solid'
    composition: dict[str, float]   # {element: stoichiometry}


def load_zzztherc(path: str | Path) -> dict[str, ThermSpecies]:
    """Load all entries from a ZZZTHERC file.

    Returns {name: ThermSpecies}.
    """
    path = Path(path)
    result = {}
    with open(path, encoding="ascii", errors="replace") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        # Line 1: species name (A10)
        line = lines[i].rstrip('\n')
        name = line[:10].rstrip()
        if not name:
            i += 1
            continue
        i += 1

        # Lines 2-3: therc[0..7]
        therc = []
        for _ in range(2):
            if i >= len(lines):
                break
            therc.extend(read_e18(lines[i].rstrip('\n'), 4))
            i += 1

        # Line 4: phase
        phase = "gas"
        if i < len(lines):
            phase = lines[i].strip().lower()
            i += 1

        # Alternating: value → element → value → element → ... → -999
        composition = {}
        while i < len(lines):
            val_line = lines[i].rstrip('\n')
            val = parse_reference_float(val_line[:18]) if val_line.strip() else -999.0
            i += 1
            if abs(val - (-999.0)) < 1e-3:
                break
            # read element name
            if i < len(lines):
                elem = lines[i].strip()
                i += 1
                if elem:
                    composition[elem] = val

        result[name] = ThermSpecies(
            name=name,
            therc=therc,
            phase=phase,
            composition=composition,
        )

    return result


# ---------------------------------------------------------------------------
# Convenience: load all three databases from a directory
# ---------------------------------------------------------------------------

@dataclass
class Databases:
    components: list[Component]
    soleqs: dict[str, SolidEOS]
    therc: dict[str, ThermSpecies]


def load_databases(db_dir: str | Path) -> Databases:
    """Load ZZZCOMPS, ZZZSOLEQ, ZZZTHERC from `db_dir`."""
    db_dir = Path(db_dir)
    return Databases(
        components=load_zzzcomps(db_dir / "ZZZCOMPS"),
        soleqs=load_zzzsoleq(db_dir / "ZZZSOLEQ"),
        therc=load_zzztherc(db_dir / "ZZZTHERC"),
    )
