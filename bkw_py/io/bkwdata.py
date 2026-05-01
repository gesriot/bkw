"""
BKWDATA file reader.

Fixed-width file format:

  rec  1: ioeq icjc ihug ipvc igrp idic irho ionl imis iext  (10 × I5)
  rec  2: label                                               (12 × A6)
  rec  3: m  n  nt                                            (3 × I5)
  rec  4: alpha  beta  theta  kappa                           (4 × E18.11)
  recs  : name(1..m)          element symbols                 (11 × A6/rec)
  recs  : elem(1..m)          element counts in explosive     (4 × E18.11/rec)
  rec   : rho  amolwt  eo                                     (4 × E18.11)
  rec   : temp  press          initial T and P                (4 × E18.11)
  recs  : nam(1..nt)           product species names          (11 × A6/rec)
  recs  : x(1..nt)             initial mole guesses           (4 × E18.11/rec)
  recs  : therc(1..8, i) for i=1..nt  (2 lines × 4 = 8 per species)
  [if nsf > 0]:
    recs: nams(1..nsf)         solid species names            (11 × A6/rec)
    recs: soleqs(1..12, i) for i=1..nsf  (3 lines × 4 = 12 per solid)
  recs  : aik(1..nt*m)         stoichiometry matrix flat      (4 × E18.11/rec)
  [if ipvc == 2]:
    rec : aispr                specific volume ISP             (E18.11)
  [if irho >= 1]:
    recs: athrho(1..irho)      density table                   (4 × E18.11/rec)
  [if iext >= 1]:
    for i=1..iext:
      rec: novar(i)  var(i)    variable override               (I5, E18.11)

Dimensions:
  m   ≤ 10  elements
  n   ≤ 25  gas species
  nt  ≤ 25  total species (gas + solid)
  nsf ≤  5  solid species (nsf = nt - n)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from .reference_io import (
    read_e18, read_i5,
    read_a6_records, read_e18_records,
)


@dataclass
class BKWData:
    # --- control flags (rec 1) ---
    ioeq:  int = 0   # 0=equilibrium, 1=frozen
    icjc:  int = 1   # 1=compute C-J
    ihug:  int = 0   # 1=compute Hugoniot
    ipvc:  int = 0   # 0=none, 2=ISP with aispr
    igrp:  int = 0   # graphics flag
    idic:  int = 0   # dictionary output flag
    irho:  int = 0   # number of density overrides
    ionl:  int = 0   # online flag
    imis:  int = 0   # missing species flag
    iext:  int = 0   # number of variable overrides

    # --- label (rec 2) ---
    label: str = ""

    # --- dimensions (rec 3) ---
    m:  int = 0      # number of elements
    n:  int = 0      # number of gas product species
    nt: int = 0      # total product species (gas + solid)

    # --- BKW EOS parameters (rec 4) ---
    alpha:  float = 0.0
    beta:   float = 0.0
    theta:  float = 0.0
    kappa:  float = 0.0

    # --- explosive composition ---
    name: list[str]   = field(default_factory=list)  # element symbols, len=m
    elem: list[float] = field(default_factory=list)  # moles of each element, len=m
    rho:    float = 0.0    # density, g/cm³
    amolwt: float = 0.0    # molecular weight, g/mol
    eo:     float = 0.0    # heat of formation, cal/mol

    # --- initial conditions ---
    temp:  float = 0.0    # initial temperature, K
    press: float = 0.0    # initial pressure, Mbar

    # --- product species ---
    nam:  list[str]         = field(default_factory=list)  # species names, len=nt
    x:    list[float]       = field(default_factory=list)  # initial mole guesses, len=nt
    therc: list[list[float]] = field(default_factory=list) # therc[i][0..7], len=nt

    # --- solid species (nsf = nt - n) ---
    nams:   list[str]         = field(default_factory=list)  # solid names, len=nsf
    soleqs: list[list[float]] = field(default_factory=list)  # soleqs[i][0..11], len=nsf

    # --- stoichiometry matrix ---
    # aik[i][j] = moles of element j in species i
    # stored flat as aik(nt*m), row-major (species × elements)
    aik: list[list[float]] = field(default_factory=list)  # aik[nt][m]

    # --- optional fields ---
    aispr: float = 0.0                      # ISP specific volume (if ipvc==2)
    athrho: list[float] = field(default_factory=list)  # density table (irho entries)
    novar: list[int]   = field(default_factory=list)   # override variable indices
    var:   list[float] = field(default_factory=list)   # override values

    @property
    def nsf(self) -> int:
        """Number of solid species."""
        return self.nt - self.n


def load_bkwdata(path: str | Path) -> BKWData:
    """Read a BKWDATA file and return a BKWData instance."""
    path = Path(path)
    with open(path, encoding="ascii", errors="replace") as f:
        raw_lines = f.readlines()

    # Strip newlines, keep list; iterator
    lines = [l.rstrip('\n') for l in raw_lines]
    it = iter(lines)

    def nextline() -> str:
        return next(it)

    d = BKWData()

    # rec 1: 10 × I5
    line = nextline()
    flags = read_i5(line, 10)
    (d.ioeq, d.icjc, d.ihug, d.ipvc,
     d.igrp, d.idic, d.irho, d.ionl, d.imis, d.iext) = flags

    # rec 2: 12 × A6 = label
    line = nextline()
    d.label = line[:72].rstrip()

    # rec 3: 3 × I5 → m, n, nt
    line = nextline()
    ints = read_i5(line, 3)
    d.m, d.n, d.nt = ints[0], ints[1], ints[2]

    # rec 4: 4 × E18.11 → alpha, beta, theta, kappa
    line = nextline()
    vals = read_e18(line, 4)
    d.alpha, d.beta, d.theta, d.kappa = vals

    # element symbols: m values, 11 A6 per record
    d.name = _read_a6_n(it, d.m)

    # element moles in explosive: m floats
    d.elem = read_e18_records(it, d.m)

    # rho, amolwt, eo
    vals = read_e18_records(it, 4)  # format reads 4 but only 3 used
    d.rho, d.amolwt, d.eo = vals[0], vals[1], vals[2]

    # temp, press
    vals = read_e18_records(it, 4)
    d.temp, d.press = vals[0], vals[1]

    # product species names: nt values, 11 A6 per record
    d.nam = _read_a6_n(it, d.nt)

    # initial mole guesses: nt floats
    d.x = read_e18_records(it, d.nt)

    # therc: nt × 8  (2 lines of 4 per species)
    d.therc = []
    for _ in range(d.nt):
        coeffs = read_e18_records(it, 8)
        d.therc.append(coeffs)

    # solid species (if any)
    nsf = d.nsf
    if nsf > 0:
        d.nams = _read_a6_n(it, nsf)
        d.soleqs = []
        for _ in range(nsf):
            coeffs = read_e18_records(it, 12)
            d.soleqs.append(coeffs)

    # stoichiometry matrix: nt × m values, flat row-major
    naik = d.nt * d.m
    flat = read_e18_records(it, naik)
    d.aik = []
    for i in range(d.nt):
        row = flat[i * d.m:(i + 1) * d.m]
        d.aik.append(row)

    # optional: aispr
    if d.ipvc == 2:
        vals = read_e18_records(it, 1)
        d.aispr = vals[0]

    # optional: density table
    if d.irho >= 1:
        d.athrho = read_e18_records(it, d.irho)

    # optional: variable overrides
    if d.iext >= 1:
        for _ in range(d.iext):
            line = nextline()
            novar_val = int(line[:5].strip()) if line[:5].strip() else 0
            var_val = parse_e18_single(line[5:])
            d.novar.append(novar_val)
            d.var.append(var_val)

    return d


# ---------------------------------------------------------------------------
# BKWDATA writer
# ---------------------------------------------------------------------------

def save_bkwdata(d: BKWData, path: str | Path) -> None:
    """Write a BKWData instance to a BKWDATA file.

    Produces output identical in format to what USERBKW generates,
    so it can be fed directly to bkw.exe / ispbkw.exe.
    """
    from .reference_io import fmt_e18_11, fmt_i5, fmt_a6

    path = Path(path)
    lines = []

    def w(s: str) -> None:
        lines.append(s)

    # rec 1: 10 × I5
    flags = [d.ioeq, d.icjc, d.ihug, d.ipvc,
             d.igrp, d.idic, d.irho, d.ionl, d.imis, d.iext]
    w("".join(fmt_i5(v) for v in flags))

    # rec 2: label padded to 72 chars
    w(f"{d.label:<72s}")

    # rec 3: m, n, nt
    w(fmt_i5(d.m) + fmt_i5(d.n) + fmt_i5(d.nt))

    # rec 4: alpha, beta, theta, kappa
    w("".join(fmt_e18_11(v) for v in [d.alpha, d.beta, d.theta, d.kappa]))

    # element names: 11 A6 per line
    _write_a6_n(lines, d.name)

    # element moles: 4 E18.11 per line
    _write_e18_n(lines, d.elem)

    # rho, amolwt, eo (+ padding to 4 floats)
    _write_e18_n(lines, [d.rho, d.amolwt, d.eo, 0.0])

    # temp, press
    _write_e18_n(lines, [d.temp, d.press])

    # species names
    _write_a6_n(lines, d.nam)

    # initial moles
    _write_e18_n(lines, d.x)

    # therc per species
    for coeffs in d.therc:
        _write_e18_n(lines, coeffs)

    # solid species
    if d.nsf > 0:
        _write_a6_n(lines, d.nams)
        for coeffs in d.soleqs:
            _write_e18_n(lines, coeffs)

    # aik (flat)
    flat_aik = [v for row in d.aik for v in row]
    _write_e18_n(lines, flat_aik)

    # optional
    if d.ipvc == 2:
        _write_e18_n(lines, [d.aispr])
    if d.irho >= 1:
        _write_e18_n(lines, d.athrho)
    for nv, var in zip(d.novar, d.var):
        lines.append(fmt_i5(nv) + fmt_e18_11(var))

    with open(path, "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_a6_n(it, count: int) -> list[str]:
    """Read `count` A6 fields from iterator, 11 per record."""
    names = []
    per_line = 11
    remaining = count
    while remaining > 0:
        line = next(it)
        take = min(per_line, remaining)
        for i in range(take):
            start = i * 6
            end = start + 6
            field = line[start:end] if start < len(line) else ""
            names.append(field.strip())
        remaining -= take
    return names


def _write_a6_n(lines: list, names: list[str]) -> None:
    """Write names as A6 fields, 11 per line."""
    from .reference_io import fmt_a6
    per_line = 11
    buf = ""
    for idx, nm in enumerate(names):
        buf += fmt_a6(nm)
        if (idx + 1) % per_line == 0:
            lines.append(buf)
            buf = ""
    if buf:
        lines.append(buf)


def _write_e18_n(lines: list, vals: list[float]) -> None:
    """Write floats as E18.11, 4 per line."""
    from .reference_io import fmt_e18_11
    per_line = 4
    buf = ""
    for idx, v in enumerate(vals):
        buf += fmt_e18_11(v)
        if (idx + 1) % per_line == 0:
            lines.append(buf)
            buf = ""
    if buf:
        lines.append(buf)


def parse_e18_single(s: str) -> float:
    """Parse one E18.11 field from a string."""
    from .reference_io import parse_reference_float
    field = s[:18] if len(s) >= 18 else s
    return parse_reference_float(field) if field.strip() else 0.0
