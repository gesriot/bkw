from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import bkw_py
from bkw_py.io.bkwdata import BKWData, load_bkwdata, save_bkwdata
from bkw_py.io.database import Component, Databases, load_databases


def _bkw_py_dir() -> Path:
    return Path(bkw_py.__file__).resolve().parent


def templates_dir() -> Path:
    return _bkw_py_dir() / "data" / "templates"


def db_dir() -> Path:
    return _bkw_py_dir() / "data"


def list_templates() -> list[str]:
    skip = {"Makefile", "userbkw.f", "userbkw.exe", "USERBKW.txt", "ZZZCOMPS", "ZZZDECKS", "ZZZSOLEQ", "ZZZTHERC"}
    names: list[str] = []
    for p in templates_dir().iterdir():
        if not p.is_file():
            continue
        if p.name in skip:
            continue
        names.append(p.name)
    return sorted(names)


def load_case(spec: str) -> BKWData:
    p = Path(spec)
    if p.exists():
        return load_bkwdata(p)
    tp = templates_dir() / spec
    if tp.exists():
        return load_bkwdata(tp)
    raise FileNotFoundError(f"BKWDATA source not found: {spec}")


def component_index(components: Iterable[Component]) -> dict[str, Component]:
    return {c.name.strip().lower(): c for c in components}


def print_summary(d: BKWData) -> None:
    print(f"Label: {d.label}")
    print(f"Flags: ioeq={d.ioeq} icjc={d.icjc} ihug={d.ihug} ipvc={d.ipvc}")
    print(f"Dims: m={d.m} n={d.n} nt={d.nt} nsf={d.nsf}")
    print(f"BKW: alpha={d.alpha:g} beta={d.beta:g} theta={d.theta:g} kappa={d.kappa:g}")
    print(f"State: rho={d.rho:g} amolwt={d.amolwt:g} eo={d.eo:g} temp={d.temp:g} press={d.press:g}")


@dataclass
class MixEntry:
    name: str
    amount: float


@dataclass
class UIState:
    mix_entries: list[MixEntry] = field(default_factory=list)
    mix_basis: str = "wt"
    custom_components: dict[str, Component] = field(default_factory=dict)


LEGACY_CONSTANT_DEFAULTS: dict[int, float] = {
    1: 15.0,        # vbos(1)
    2: 1.1,         # vbos(2)
    3: 1.0e-6,      # vbos(3)
    4: 2.0e-5,      # exitme
    5: 3000.0,      # hugbos(1)
    6: 1.1,         # hugbos(2)
    7: 1.0e-6,      # hugbos(3)
    8: 1.0e-6,      # po
    9: 0.8,         # cjbos(2)
    10: 1.0e-6,     # cjbos(3)
    11: 0.15,       # apgcj
    12: 0.25,       # bpgcj
    13: 0.50,       # amhugp
    14: 0.05,       # delp
    15: 0.1,        # cprime
    16: 0.5,        # decip
    17: 1.0e-4,     # aminp
    18: 1.20,       # aincp
    19: 1.0,        # amaxp
    20: 0.9,        # abos(2)
    21: 0.5,        # abos(3)
    22: 1.1,        # abosh(2)
    23: 0.5,        # abosh(3)
    24: 15.0,       # vbos2
    25: 3000.0,     # hugb2
    26: 1.0e-6,     # amaxe
    27: 1.0e-8,     # aminx
    28: 1.0e-5,     # aminy
    29: 1.1,        # tx(2)
    30: 1.0e-6,     # tx(3)
}

LEGACY_CONSTANT_HELP: dict[int, str] = {
    1: "VBOS(1): initial gas-volume guess for linear feedback (sys1).",
    2: "VBOS(2): ratio for next gas-volume guess.",
    3: "VBOS(3): accepted gas-volume error.",
    4: "EXITME: composition convergence criterion.",
    5: "HUGBOS(1): initial Hugoniot temperature guess.",
    6: "HUGBOS(2): ratio for next Hugoniot temperature guess.",
    7: "HUGBOS(3): accepted Hugoniot temperature error.",
    8: "PO: initial pressure in megabars.",
    9: "CJBOS(2): CJ search ratio for next pressure guess.",
    10: "CJBOS(3): accepted CJ search error.",
    11: "APGCJ: A coefficient for initial CJ pressure guess.",
    12: "BPGCJ: B coefficient for initial CJ pressure guess.",
    13: "AMHUGP: maximum Hugoniot pressure.",
    14: "DELP: Hugoniot pressure decrement.",
    15: "CPRIME: constant added to energy for log-fit positivity.",
    16: "DECIP: pressure decrease factor below CJ for isentrope.",
    17: "AMINP: minimum isentrope pressure.",
    18: "AINCP: pressure increase factor above CJ for isentrope.",
    19: "AMAXP: maximum isentrope pressure.",
    20: "ABOS(2): entropy solve ratio below CJ.",
    21: "ABOS(3): entropy tolerance below CJ.",
    22: "ABOSH(2): entropy solve ratio above CJ.",
    23: "ABOSH(3): entropy tolerance above CJ.",
    24: "VBOS2: replacement for VBOS(1) for next explosive.",
    25: "HUGB2: replacement for HUGBOS(1) for next explosive.",
    26: "AMAXE: maximum composition iteration error.",
    27: "AMINX: minimum new composition value.",
    28: "AMINY: minimum previous composition value.",
    29: "TX(2): factor for second solid-volume guess.",
    30: "TX(3): accepted solid-volume error.",
}


def _validate_flags(d: BKWData) -> None:
    if d.ioeq not in {0, 1, 2}:
        raise ValueError("ioeq must be 0, 1 or 2")
    if d.icjc not in {0, 1}:
        raise ValueError("icjc must be 0 or 1")
    if d.ihug not in {0, 1}:
        raise ValueError("ihug must be 0 or 1")
    if d.ipvc not in {0, 1, 2, 3}:
        raise ValueError("ipvc must be 0, 1, 2 or 3")
    if d.m <= 0 or d.m > 10:
        raise ValueError("m must be in [1, 10]")
    if d.nt <= 0 or d.nt > 25:
        raise ValueError("nt must be in [1, 25]")
    if d.n < 0 or d.n > d.nt:
        raise ValueError("n must satisfy 0 <= n <= nt")
    if d.nsf > 5:
        raise ValueError("number of solids (nt-n) must be <= 5")


def _ask_int(prompt: str, old: int) -> int:
    s = input(f"{prompt} [{old}]: ").strip()
    return old if s == "" else int(s)


def _ask_float(prompt: str, old: float) -> float:
    s = input(f"{prompt} [{old:g}]: ").strip()
    return old if s == "" else float(s)


def _ask_str(prompt: str, old: str) -> str:
    s = input(f"{prompt} [{old}]: ").strip()
    return old if s == "" else s


def edit_flags(d: BKWData) -> None:
    d.ioeq = _ask_int("ioeq", d.ioeq)
    d.icjc = _ask_int("icjc", d.icjc)
    d.ihug = _ask_int("ihug", d.ihug)
    d.ipvc = _ask_int("ipvc", d.ipvc)
    d.igrp = _ask_int("igrp", d.igrp)
    d.idic = _ask_int("idic", d.idic)
    _validate_flags(d)


def edit_basic(d: BKWData) -> None:
    d.label = _ask_str("label", d.label)
    d.alpha = _ask_float("alpha", d.alpha)
    d.beta = _ask_float("beta", d.beta)
    d.theta = _ask_float("theta", d.theta)
    d.kappa = _ask_float("kappa", d.kappa)
    d.rho = _ask_float("rho", d.rho)
    d.amolwt = _ask_float("amolwt", d.amolwt)
    d.eo = _ask_float("eo", d.eo)
    d.temp = _ask_float("temp", d.temp)
    d.press = _ask_float("press", d.press)


def edit_elements(d: BKWData) -> None:
    print("Elemental composition:")
    for i in range(d.m):
        d.name[i] = _ask_str(f"elem[{i}] name", d.name[i])[:6]
        d.elem[i] = _ask_float(f"elem[{i}] moles", d.elem[i])
    if len({_normalize_element(x) for x in d.name}) != len(d.name):
        raise ValueError("duplicate element symbols in deck are not allowed")


def parse_mix_spec(spec: str) -> list[MixEntry]:
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    out: list[MixEntry] = []
    for p in parts:
        if "=" not in p:
            raise ValueError(f"mix token must be name=value, got: {p}")
        n, v = p.split("=", 1)
        out.append(MixEntry(name=n.strip(), amount=float(v.strip())))
    if not out:
        raise ValueError("mix spec is empty")
    return out


def _normalize_element(s: str) -> str:
    return s.strip().lower()


def _parse_composition(spec: str) -> dict[str, float]:
    comp: dict[str, float] = {}
    for token in [t.strip() for t in spec.split(",") if t.strip()]:
        if "=" not in token:
            raise ValueError(f"composition token must be el=value, got: {token}")
        k, v = token.split("=", 1)
        key = _normalize_element(k)
        val = float(v.strip())
        if val < 0.0:
            raise ValueError("stoichiometric coefficients must be non-negative")
        comp[key] = val
    if not comp:
        raise ValueError("empty composition")
    return comp


def _aik_row_from_comp(d: BKWData, comp: dict[str, float]) -> list[float]:
    row: list[float] = []
    names = [_normalize_element(x) for x in d.name]
    for el in names:
        row.append(float(comp.get(el, 0.0)))
    return row


def apply_mixture_to_bkwdata(
    d: BKWData,
    entries: list[MixEntry],
    comp_index: dict[str, Component],
    *,
    basis: str = "wt",
    strict_elements: bool = False,
) -> list[str]:
    if basis not in {"wt", "mol"}:
        raise ValueError("basis must be wt or mol")
    active = [e for e in entries if e.amount > 0.0]
    if not active:
        raise ValueError("no positive amounts in mixture")

    total_amt = sum(e.amount for e in active)
    if total_amt <= 0.0:
        raise ValueError("sum of mixture amounts must be positive")

    # Basis normalization:
    # - wt: 100 g batch
    # - mol: 1 mixture-mole batch
    mol_counts: list[tuple[Component, float]] = []
    if basis == "wt":
        total_mass = 100.0
        for e in active:
            key = e.name.strip().lower()
            c = comp_index.get(key)
            if c is None:
                raise KeyError(f"component not found in database: {e.name}")
            mass_i = total_mass * (e.amount / total_amt)
            mol_i = mass_i / c.mol_weight
            mol_counts.append((c, mol_i))
    else:
        for e in active:
            key = e.name.strip().lower()
            c = comp_index.get(key)
            if c is None:
                raise KeyError(f"component not found in database: {e.name}")
            mol_counts.append((c, e.amount / total_amt))

    total_mol = sum(n for _, n in mol_counts)
    if total_mol <= 0.0:
        raise ValueError("invalid mixture: zero total moles")

    total_mass = sum(n * c.mol_weight for c, n in mol_counts)
    total_hf = sum(n * c.delta_hf for c, n in mol_counts)
    total_vol = sum((n * c.mol_weight) / c.density for c, n in mol_counts if c.density > 0.0)

    # Convert to "per mixture formula weight" quantities.
    d.amolwt = total_mass / total_mol
    d.eo = total_hf / total_mol
    if total_vol > 0.0:
        d.rho = total_mass / total_vol

    elem_tot: dict[str, float] = {}
    for c, n in mol_counts:
        for el, sto in c.elements.items():
            k = _normalize_element(el)
            elem_tot[k] = elem_tot.get(k, 0.0) + n * sto

    # Write into current template element slots.
    unknown = [k for k in elem_tot if k not in {_normalize_element(x) for x in d.name}]
    if strict_elements and unknown:
        raise ValueError(f"elements not present in template deck: {', '.join(sorted(unknown))}")

    for i in range(d.m):
        k = _normalize_element(d.name[i])
        d.elem[i] = elem_tot.get(k, 0.0) / total_mol

    mix_label = " / ".join(f"{e.name}:{e.amount:g}" for e in active)
    d.label = mix_label[:72]
    return sorted(unknown)


def add_gas_species(
    d: BKWData,
    *,
    name: str,
    therc: list[float],
    composition: dict[str, float],
    x_guess: float = 1.0e-3,
) -> None:
    if len(therc) != 8:
        raise ValueError("gas species requires 8 THERC values")
    if d.nt >= 25:
        raise ValueError("cannot add gas species: nt already at 25")
    if _normalize_element(name) in {_normalize_element(x) for x in d.nam}:
        raise ValueError(f"species already exists: {name}")
    unknown = [k for k in composition if k not in {_normalize_element(x) for x in d.name}]
    if unknown:
        raise ValueError(f"composition has unknown elements: {', '.join(sorted(unknown))}")

    insert_at = d.n  # before solids block
    d.nam.insert(insert_at, name[:6])
    d.x.insert(insert_at, max(float(x_guess), 1.0e-8))
    d.therc.insert(insert_at, [float(v) for v in therc])
    d.aik.insert(insert_at, _aik_row_from_comp(d, composition))
    d.n += 1
    d.nt += 1


def add_solid_species(
    d: BKWData,
    *,
    name: str,
    therc: list[float],
    soleq: list[float],
    composition: dict[str, float],
    x_guess: float = 1.0e-3,
) -> None:
    if len(therc) != 8:
        raise ValueError("solid species requires 8 THERC values")
    if len(soleq) != 12:
        raise ValueError("solid species requires 12 SOLEQ values")
    if d.nt >= 25:
        raise ValueError("cannot add solid species: nt already at 25")
    if d.nsf >= 5:
        raise ValueError("cannot add solid species: nsf already at 5")
    if _normalize_element(name) in {_normalize_element(x) for x in d.nam}:
        raise ValueError(f"species already exists: {name}")
    unknown = [k for k in composition if k not in {_normalize_element(x) for x in d.name}]
    if unknown:
        raise ValueError(f"composition has unknown elements: {', '.join(sorted(unknown))}")

    d.nam.append(name[:6])
    d.x.append(max(float(x_guess), 1.0e-8))
    d.therc.append([float(v) for v in therc])
    d.aik.append(_aik_row_from_comp(d, composition))
    d.nams.append(name[:6])
    d.soleqs.append([float(v) for v in soleq])
    d.nt += 1


def _select_components_page3(state: UIState, db: Databases) -> None:
    idx = component_index([*db.components, *state.custom_components.values()])
    print("Available components (first 20):")
    names = sorted(idx.keys())
    print(", ".join(names[:20]))
    if len(names) > 20:
        print(f"... total {len(names)}")
    spec = input("Enter mix spec name=value,... (example: rdx=70,teflon=20,al=10): ").strip()
    if not spec:
        return
    state.mix_entries = parse_mix_spec(spec)


def _apply_composition_page4(d: BKWData, state: UIState, db: Databases) -> None:
    if not state.mix_entries:
        print("No components selected yet (page 3).")
        return
    basis = input(f"Basis wt/mol [{state.mix_basis}]: ").strip().lower()
    if basis in {"wt", "mol"}:
        state.mix_basis = basis
    idx = component_index([*db.components, *state.custom_components.values()])
    unknown = apply_mixture_to_bkwdata(d, state.mix_entries, idx, basis=state.mix_basis, strict_elements=False)
    if unknown:
        print("Warning: elements not present in template deck:", ", ".join(unknown))
    print("Mixture applied to BKWDATA.")
    print_summary(d)


def _add_custom_component_page5(state: UIState) -> None:
    name = input("Custom component name: ").strip().lower()
    if not name:
        return
    density = float(input("density [g/cc]: ").strip())
    delta_hf = float(input("delta_hf [cal/mol]: ").strip())
    mol_weight = float(input("mol_weight [g/mol]: ").strip())
    print("Elements as symbol=value comma-separated (example: c=3,h=6,n=6,o=6)")
    spec = input("elements: ").strip()
    elems: dict[str, float] = {}
    for token in [t.strip() for t in spec.split(",") if t.strip()]:
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        elems[k.strip().lower()] = float(v.strip())
    state.custom_components[name] = Component(
        name=name,
        density=density,
        delta_hf=delta_hf,
        elements=elems,
        mol_weight=mol_weight,
    )
    print(f"Custom component saved: {name}")


def _edit_species_page6(d: BKWData, db: Databases) -> None:
    print("Page 6 species editor:")
    print("1. Replace species THERC from ZZZTHERC by name")
    print("2. Edit species THERC manually (8 coefficients)")
    print("3. Replace solid SOLEQ from ZZZSOLEQ by name")
    print("4. Add gas species from ZZZTHERC")
    print("5. Add solid species from ZZZTHERC + ZZZSOLEQ")
    sub = input("> ").strip()
    if sub == "1":
        sname = input("Species name in BKWDATA (e.g. h2o): ").strip().lower()
        dbname = input(f"DB species name [{sname}]: ").strip().lower() or sname
        if dbname not in db.therc:
            print("Not found in ZZZTHERC.")
            return
        try:
            i = [x.lower() for x in d.nam].index(sname)
        except ValueError:
            print("Species not found in current BKWDATA nam list.")
            return
        d.therc[i] = list(float(v) for v in db.therc[dbname].therc[:8])
        print("THERC replaced.")
    elif sub == "2":
        sname = input("Species name in BKWDATA: ").strip().lower()
        try:
            i = [x.lower() for x in d.nam].index(sname)
        except ValueError:
            print("Species not found.")
            return
        print("Enter 8 THERC values, empty keeps old.")
        for k in range(8):
            d.therc[i][k] = _ask_float(f"therc[{k}]", d.therc[i][k])
    elif sub == "3":
        if d.nsf <= 0:
            print("No solid species in current BKWDATA.")
            return
        sname = input("Solid name in BKWDATA nams (e.g. sol c): ").strip().lower()
        dbname = input(f"DB solid name [{sname}]: ").strip().lower() or sname
        if dbname not in db.soleqs:
            print("Not found in ZZZSOLEQ.")
            return
        try:
            i = [x.lower() for x in d.nams].index(sname)
        except ValueError:
            print("Solid not found in current BKWDATA nams list.")
            return
        d.soleqs[i] = list(float(v) for v in db.soleqs[dbname].soleqs[:12])
        print("SOLEQ replaced.")
    elif sub == "4":
        dbname = input("DB gas species name: ").strip().lower()
        if dbname not in db.therc:
            print("Not found in ZZZTHERC.")
            return
        ts = db.therc[dbname]
        add_gas_species(
            d,
            name=ts.name,
            therc=list(float(v) for v in ts.therc[:8]),
            composition={_normalize_element(k): float(v) for k, v in ts.composition.items()},
        )
        print(f"Added gas species: {ts.name}")
    elif sub == "5":
        dbname = input("DB solid species name: ").strip().lower()
        if dbname not in db.therc or dbname not in db.soleqs:
            print("Not found in both ZZZTHERC and ZZZSOLEQ.")
            return
        ts = db.therc[dbname]
        sq = db.soleqs[dbname]
        add_solid_species(
            d,
            name=ts.name,
            therc=list(float(v) for v in ts.therc[:8]),
            soleq=list(float(v) for v in sq.soleqs[:12]),
            composition={_normalize_element(k): float(v) for k, v in ts.composition.items()},
        )
        print(f"Added solid species: {ts.name}")


def _save_run_page7(d: BKWData) -> None:
    path = input("Output BKWDATA path [BKWDATA]: ").strip() or "BKWDATA"
    save_bkwdata(d, path)
    print(f"Saved: {path}")
    run = input("Run solver now? (none/bkw/isp) [none]: ").strip().lower() or "none"
    if run == "none":
        return
    from bkw_py import bkw as _bkw_engine, ispbkw as _isp_engine
    engine = _bkw_engine if run == "bkw" else _isp_engine
    out = "bkw.out" if run == "bkw" else "isp.out"
    engine.run(path, out)
    print(f"Ran {run}, output: {out}")


def _legacy_page1_modes(d: BKWData) -> None:
    def _yesno(v: bool) -> str:
        return "yes" if v else "no"

    def _through_text(ipvc: int) -> str:
        if ipvc == 1:
            return "C-J point"
        if ipvc == 2:
            return "Hugoniot pressure input"
        if ipvc == 3:
            return "input temperature and pressure"
        return "nothing"

    while True:
        print("")
        print("Advanced page1:")
        print(f"(1) Perform equilibrium calculation: {_yesno(d.ioeq == 0)}")
        print(f"(2) Perform C-J calculation: {_yesno(d.icjc == 1)}")
        print(f"(3) Perform Hugoniot calculation: {_yesno(d.ihug == 1)}")
        print(f"(4) Perform isentrope through: {_through_text(d.ipvc)}")
        gtxt = "132 columns" if d.igrp == 2 else "80 columns"
        print(f"(5) Use printer type: {gtxt}")
        print("(-) Back")
        print("(+) Apply and continue")
        choice = input("Choice: ").strip().lower()
        if choice == "-":
            return
        if choice == "+":
            return
        if choice == "1":
            # Keep project semantics: ioeq=0 means standard equilibrium path.
            d.ioeq = 1 if d.ioeq == 0 else 0
            continue
        if choice == "2":
            d.icjc = 0 if d.icjc == 1 else 1
            continue
        if choice == "3":
            d.ihug = 0 if d.ihug == 1 else 1
            continue
        if choice == "4":
            print("Through options: 1=C-J point, 2=Hugoniot pressure input, 3=input T/P, 4=nothing")
            sub = input("Choice [1..4]: ").strip()
            if sub == "1":
                d.ipvc = 1
            elif sub == "2":
                d.ipvc = 2
            elif sub == "3":
                d.ipvc = 3
            elif sub == "4":
                d.ipvc = 0
            else:
                print("You must choose a number between 1 and 4.")
            continue
        if choice == "5":
            d.igrp = 2 if d.igrp != 2 else 1
            continue
        print("You must choose a number between 1 and 5.")


def _legacy_page2_eos(d: BKWData) -> None:
    while True:
        print("")
        print("Advanced page2:")
        print(f"Alpha={d.alpha:.6E}  Beta={d.beta:.6E}  Theta={d.theta:.6E}  Kappa={d.kappa:.6E}")
        print("(1) RDX parameters")
        print("(2) TNT parameters")
        print("(3) Input parameters")
        print("(4) Default parameters (keep current)")
        print("(-) Back")
        print("(+) Apply and continue")
        choice = input("Choice: ").strip().lower()
        if choice == "-":
            return
        if choice == "+":
            return
        if choice in {"1", "r"}:
            d.alpha = 0.5
            d.beta = 0.16
            d.theta = 400.0
            d.kappa = 10.9097784436
            continue
        if choice in {"2", "t"}:
            d.alpha = 0.5
            d.beta = 0.09585
            d.theta = 400.0
            d.kappa = 12.685
            continue
        if choice in {"3", "i"}:
            try:
                d.alpha = float(input("New Alpha: ").strip())
                d.beta = float(input("New Beta: ").strip())
                d.theta = float(input("New Theta: ").strip())
                d.kappa = float(input("New Kappa: ").strip())
            except Exception:
                print("Invalid numeric input.")
            continue
        if choice in {"4", "d"}:
            # Default option means keep current values.
            continue
        print("You must choose a number between 1 and 4.")


def _legacy_page5_athrho_aispr(d: BKWData) -> None:
    dens = [float(x) for x in d.athrho[:4]]
    while True:
        vals = dens + [0.0] * (4 - len(dens))
        print("")
        print("Advanced page5:")
        print(f"1) Extra density: {vals[0]:.11E}")
        print(f"2) Extra density: {vals[1]:.11E}")
        print(f"3) Extra density: {vals[2]:.11E}")
        print(f"4) Extra density: {vals[3]:.11E}")
        if d.ipvc == 2:
            print(f"5) Hugoniot pressure (used): {float(d.aispr):.11E}")
        else:
            print(f"5) Hugoniot pressure (ignored): {float(d.aispr):.11E}")
        print("(-) Back")
        print("(+) Apply and continue")
        choice = input("Choice: ").strip()
        if choice == "-":
            return
        if choice == "+":
            d.athrho = dens[:]
            d.irho = len(dens)
            return
        if choice in {"1", "2", "3", "4"}:
            idx = int(choice) - 1
            try:
                val = float(input("New density (0 removes): ").strip())
            except Exception:
                print("Invalid number.")
                continue
            if idx < len(dens):
                dens[idx] = val
                if val == 0.0:
                    dens[idx] = dens[-1]
                    dens.pop()
            else:
                if len(dens) >= 4:
                    print("No free density slots (max 4).")
                    continue
                dens.append(val)
                if val == 0.0:
                    dens.pop()
            continue
        if choice == "5":
            prompt = "New Hugoniot pressure: " if d.ipvc == 2 else "New Hugoniot pressure (will be ignored): "
            try:
                d.aispr = float(input(prompt).strip())
            except Exception:
                print("Invalid number.")
            continue
        print("Please choose 1..5, '-' or '+'.")


def _legacy_constants_current_original(d: BKWData) -> tuple[dict[int, float], dict[int, float]]:
    original = dict(LEGACY_CONSTANT_DEFAULTS)
    current = dict(LEGACY_CONSTANT_DEFAULTS)
    for no, val in zip(d.novar, d.var):
        if no in current:
            current[int(no)] = float(val)
    return current, original


def _legacy_apply_constants_to_deck(d: BKWData, current: dict[int, float], original: dict[int, float]) -> None:
    novar: list[int] = []
    var: list[float] = []
    for k in range(1, 31):
        if abs(current[k] - original[k]) > 0.0:
            novar.append(k)
            var.append(current[k])
    d.novar = novar
    d.var = var
    d.iext = len(novar)


def _legacy_page6_constants(d: BKWData) -> None:
    current, original = _legacy_constants_current_original(d)
    while True:
        print("")
        print("Advanced page6 constants:")
        for i in range(1, 31):
            print(f"{i:2d}) {current[i]:.11E} (orig {original[i]:.11E})")
        print("(? ) Help")
        print("(-) Back")
        print("(+) Apply and continue")
        choice = input("Choice: ").strip()
        if choice == "-":
            return
        if choice == "+":
            _legacy_apply_constants_to_deck(d, current, original)
            return
        if choice == "?":
            h = input("Which constant? (1..30 or *): ").strip()
            if h == "*":
                for i in range(1, 31):
                    print(f"{i:2d}: {LEGACY_CONSTANT_HELP.get(i, '')}")
            else:
                try:
                    k = int(h)
                except Exception:
                    print("Invalid help id.")
                    continue
                if k < 1 or k > 30:
                    print("Invalid help id.")
                    continue
                print(f"{k:2d}: {LEGACY_CONSTANT_HELP.get(k, '')}")
            continue
        try:
            idx = int(choice)
        except Exception:
            print("Please choose 1..30, '?', '-', '+'.")
            continue
        if idx < 1 or idx > 30:
            print("Please choose 1..30.")
            continue
        try:
            v = float(input("New value (-1 restores original): ").strip())
        except Exception:
            print("Invalid number.")
            continue
        if v == -1.0:
            current[idx] = original[idx]
        else:
            current[idx] = v


def _legacy_page3b_editor(d: BKWData) -> None:
    def _input_int_in_range(prompt: str, lo: int, hi: int) -> int:
        while True:
            raw = input(prompt).strip()
            try:
                v = int(raw)
            except Exception:
                print("Invalid choice.")
                continue
            if v < lo or v > hi:
                print("Invalid choice.")
                continue
            return v

    def _input_float(prompt: str) -> float:
        while True:
            raw = input(prompt).strip()
            try:
                return float(raw)
            except Exception:
                print("Invalid number.")

    def _print_comp_table() -> None:
        print("Composition table:")
        print("elements:", ", ".join(f"{i+1}:{n}" for i, n in enumerate(d.name)))
        for i, nm in enumerate(d.nam, start=1):
            vals = " ".join(f"{v:6.2f}" for v in d.aik[i - 1][: d.m])
            print(f"{i:2d}) {nm:<6} {vals}")
        print("moles:", " ".join(f"{v:6.2f}" for v in d.elem[: d.m]))

    def _edit_species_therc_soleq() -> None:
        while True:
            sname = input("Species name to edit: ").strip().lower()
            if sname:
                break
            print("Invalid choice.")
        idx = None
        for i, n in enumerate(d.nam):
            if n.strip().lower() == sname:
                idx = i
                break
        if idx is None:
            print("That species is not in the product.")
            return
        is_solid = idx >= d.n
        if is_solid:
            sidx = idx - d.n
            print("1) Everything")
            print("2..9) THERC A..covol")
            print("10..21) SOLEQ V0..mol.weight")
        else:
            print("1) Everything")
            print("2..9) THERC A..covol")
        k = _input_int_in_range("Choice: ", 1, 21 if is_solid else 9)
        if k == 1:
            for j in range(8):
                d.therc[idx][j] = _input_float(f"therc[{j+1}] [{d.therc[idx][j]:.11E}]: ")
            if is_solid:
                for j in range(12):
                    d.soleqs[sidx][j] = _input_float(f"soleq[{j+1}] [{d.soleqs[sidx][j]:.11E}]: ")
            return
        if 2 <= k <= 9:
            j = k - 2
            d.therc[idx][j] = _input_float(f"New therc[{j+1}] [{d.therc[idx][j]:.11E}]: ")
            return
        if is_solid and 10 <= k <= 21:
            j = k - 10
            d.soleqs[sidx][j] = _input_float(f"New soleq[{j+1}] [{d.soleqs[sidx][j]:.11E}]: ")
            return
        print("Invalid choice.")

    def _edit_element_in_species_formula() -> None:
        ename = input("Element name to edit: ").strip().lower()
        eidx = None
        for i, n in enumerate(d.name):
            if n.strip().lower() == ename:
                eidx = i
                break
        if eidx is None:
            print("That element is not in the compound.")
            return
        print("1) Everything")
        for i, nm in enumerate(d.nam, start=2):
            print(f"{i:2d}) {nm} [{d.aik[i-2][eidx]:.11E}]")
        k = _input_int_in_range("Choice: ", 1, d.nt + 1) - 1
        if k == 0:
            for i, nm in enumerate(d.nam):
                d.aik[i][eidx] = _input_float(f"Atoms of {ename} in {nm} [{d.aik[i][eidx]:.11E}]: ")
            return
        if 1 <= k <= d.nt:
            i = k - 1
            d.aik[i][eidx] = _input_float(f"Atoms of {ename} in {d.nam[i]} [{d.aik[i][eidx]:.11E}]: ")
            return
        print("Invalid choice.")

    def _edit_element_moles() -> None:
        print("1) Everything")
        for i, nm in enumerate(d.name, start=2):
            print(f"{i:2d}) {nm} [{d.elem[i-2]:.11E}]")
        k = _input_int_in_range("Choice: ", 1, d.m + 1) - 1
        if k == 0:
            for i, nm in enumerate(d.name):
                d.elem[i] = _input_float(f"Moles of {nm} [{d.elem[i]:.11E}]: ")
            return
        if 1 <= k <= d.m:
            i = k - 1
            d.elem[i] = _input_float(f"Moles of {d.name[i]} [{d.elem[i]:.11E}]: ")
            return
        print("Invalid choice.")

    def _edit_species_guess() -> None:
        print("1) Everything")
        for i, nm in enumerate(d.nam, start=2):
            print(f"{i:2d}) {nm} [{d.x[i-2]:.11E}]")
        k = _input_int_in_range("Choice: ", 1, d.nt + 1) - 1
        if k == 0:
            for i, nm in enumerate(d.nam):
                d.x[i] = _input_float(f"Moles guess for {nm} [{d.x[i]:.11E}]: ")
            return
        if 1 <= k <= d.nt:
            i = k - 1
            d.x[i] = _input_float(f"Moles guess for {d.nam[i]} [{d.x[i]:.11E}]: ")
            return
        print("Invalid choice.")

    def _edit_second_name_twin() -> None:
        if d.nsf <= 0:
            print("No solid species in current BKWDATA.")
            return
        while True:
            sname = input("Solid species name in nam (e.g. sol c): ").strip().lower()
            if sname:
                break
            print("Invalid choice.")
        idx = None
        for i in range(d.n, d.nt):
            if d.nam[i].strip().lower() == sname:
                idx = i
                break
        if idx is None:
            print("That species is not in the product.")
            return
        sidx = idx - d.n
        cur = d.nams[sidx] if sidx < len(d.nams) else d.nam[idx]
        new_name = input(f"Second name [{cur}]: ").strip()
        if not new_name:
            return
        if sidx < len(d.nams):
            d.nams[sidx] = new_name[:6]
        else:
            d.nams.append(new_name[:6])

    while True:
        print("")
        print("Advanced page3b:")
        print("1) View composition table")
        print("2) Edit species THERC/SOLEQ")
        print("3) Edit element stoichiometry in species (aik)")
        print("4) Edit explosive element moles (amoles/elem)")
        print("5) Change species mole guesses")
        print("6) Change species second name (twin for solids)")
        print("(-) Back")
        print("(+) Apply and continue")
        choice = input("Choice: ").strip().lower()
        if choice == "-":
            return
        if choice == "+":
            return
        if choice == "1":
            _print_comp_table()
        elif choice == "2":
            _edit_species_therc_soleq()
        elif choice == "3":
            _edit_element_in_species_formula()
        elif choice == "4":
            _edit_element_moles()
        elif choice == "5":
            _edit_species_guess()
        elif choice == "6":
            _edit_second_name_twin()
        else:
            print("You must choose a number between 1 and 6.")


def interactive_cli(d: BKWData, db: Databases) -> BKWData:
    state = UIState()
    while True:
        print("")
        print("USERBKW (Python) menu")
        print("1. Summary")
        print("2. Edit flags (page 2 mode/settings)")
        print("3. Page 3: select components from ZZZCOMPS")
        print("4. Page 4: set composition and apply to BKWDATA")
        print("5. Page 5: add custom component")
        print("6. Page 6: extended species editor (THERC/SOLEQ)")
        print("7. Page 7: save and optional run")
        print("8. Edit basic data (manual label/BKW/rho/T/P)")
        print("9. Edit elemental composition (manual)")
        print("12. Legacy page1: modes/settings")
        print("13. Legacy page2: EOS presets")
        print("14. Legacy page3b: deep editor")
        print("10. Legacy page5: athrho/aispr")
        print("11. Legacy page6: 30 constants")
        print("0. Exit")
        choice = input("> ").strip()
        if choice == "1":
            print_summary(d)
        elif choice == "2":
            edit_flags(d)
        elif choice == "3":
            _select_components_page3(state, db)
        elif choice == "4":
            _apply_composition_page4(d, state, db)
        elif choice == "5":
            _add_custom_component_page5(state)
        elif choice == "6":
            _edit_species_page6(d, db)
        elif choice == "7":
            _save_run_page7(d)
        elif choice == "8":
            edit_basic(d)
        elif choice == "9":
            edit_elements(d)
        elif choice == "12":
            _legacy_page1_modes(d)
        elif choice == "13":
            _legacy_page2_eos(d)
        elif choice == "14":
            _legacy_page3b_editor(d)
        elif choice == "10":
            _legacy_page5_athrho_aispr(d)
        elif choice == "11":
            _legacy_page6_constants(d)
        elif choice == "0":
            return d


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="USERBKW preprocessor (Python)")
    ap.add_argument("--template", help="Template name from ./userbkw (e.g. CHNO)")
    ap.add_argument("--input", help="Input BKWDATA file path")
    ap.add_argument("--output", help="Output BKWDATA file path")
    ap.add_argument("--set-label")
    ap.add_argument("--set-ioeq", type=int)
    ap.add_argument("--set-icjc", type=int)
    ap.add_argument("--set-ihug", type=int)
    ap.add_argument("--set-ipvc", type=int)
    ap.add_argument("--set-igrp", type=int)
    ap.add_argument("--set-rho", type=float)
    ap.add_argument("--set-temp", type=float)
    ap.add_argument("--set-press", type=float)
    ap.add_argument("--legacy-eos-preset", choices=["default", "rdx", "tnt"], default="default")
    ap.add_argument("--legacy-athrho", help="Comma-separated extra densities (up to 4)")
    ap.add_argument("--legacy-aispr", type=float, help="Legacy page5 Hugoniot pressure input")
    ap.add_argument("--legacy-var", action="append", default=[], help="Legacy constant override no=val (1..30)")
    ap.add_argument("--legacy-solid-twin", action="append", default=[], help="Rename solid second name old=new")
    ap.add_argument("--mix", help="Mixture spec: name=value,name=value (page 3/4 non-interactive)")
    ap.add_argument("--mix-basis", choices=["wt", "mol"], default="wt")
    ap.add_argument("--strict-elements", action="store_true")
    ap.add_argument("--add-gas-db", action="append", default=[], help="Add gas species from ZZZTHERC (repeatable)")
    ap.add_argument("--add-solid-db", action="append", default=[], help="Add solid species from ZZZTHERC+ZZZSOLEQ (repeatable)")
    ap.add_argument(
        "--add-gas-custom",
        action="append",
        default=[],
        help="Custom gas: name|a,b,c,d,e,ic,hf,covol|el=val,el=val (repeatable)",
    )
    ap.add_argument(
        "--add-solid-custom",
        action="append",
        default=[],
        help="Custom solid: name|8therc|12soleq|el=val,el=val (repeatable)",
    )
    ap.add_argument("--run", choices=["none", "bkw", "isp"], default="none")
    ap.add_argument("--list-templates", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    return ap


def apply_noninteractive_overrides(d: BKWData, args: argparse.Namespace) -> None:
    mapping = {
        "set_label": "label",
        "set_ioeq": "ioeq",
        "set_icjc": "icjc",
        "set_ihug": "ihug",
        "set_ipvc": "ipvc",
        "set_igrp": "igrp",
        "set_rho": "rho",
        "set_temp": "temp",
        "set_press": "press",
    }
    vals = vars(args)
    for k, field in mapping.items():
        v = vals.get(k)
        if v is not None:
            setattr(d, field, v)
    _validate_flags(d)


def _apply_legacy_eos_preset(d: BKWData, preset: str) -> None:
    p = preset.strip().lower()
    if p == "default":
        return
    if p == "rdx":
        d.alpha = 0.5
        d.beta = 0.16
        d.theta = 400.0
        d.kappa = 10.9097784436
        return
    if p == "tnt":
        d.alpha = 0.5
        d.beta = 0.09585
        d.theta = 400.0
        d.kappa = 12.685
        return
    raise ValueError(f"unknown legacy EOS preset: {preset}")


def _apply_legacy_athrho(d: BKWData, spec: str | None) -> None:
    if spec is None:
        return
    vals = [float(x.strip()) for x in spec.split(",") if x.strip()]
    if len(vals) > 4:
        raise ValueError("legacy-athrho supports at most 4 values")
    d.athrho = vals
    d.irho = len(vals)


def _apply_legacy_constants(d: BKWData, overrides: list[str]) -> None:
    if not overrides:
        return
    current, original = _legacy_constants_current_original(d)
    for raw in overrides:
        if "=" not in raw:
            raise ValueError(f"legacy-var must be no=val, got: {raw}")
        no_s, val_s = raw.split("=", 1)
        no = int(no_s.strip())
        if no < 1 or no > 30:
            raise ValueError(f"legacy-var index out of range (1..30): {no}")
        val = float(val_s.strip())
        current[no] = original[no] if val == -1.0 else val
    _legacy_apply_constants_to_deck(d, current, original)


def _apply_legacy_solid_twins(d: BKWData, specs: list[str]) -> None:
    if not specs:
        return
    if d.nsf <= 0:
        raise ValueError("legacy-solid-twin requires at least one solid species")
    solid_map: dict[str, int] = {}
    for i in range(d.n, d.nt):
        solid_map[d.nam[i].strip().lower()] = i - d.n
    for raw in specs:
        if "=" not in raw:
            raise ValueError(f"legacy-solid-twin must be old=new, got: {raw}")
        old_s, new_s = raw.split("=", 1)
        old = old_s.strip().lower()
        new = new_s.strip()
        if not old or not new:
            raise ValueError(f"legacy-solid-twin must be old=new, got: {raw}")
        sidx = solid_map.get(old)
        if sidx is None:
            raise ValueError(f"legacy-solid-twin solid not found in nam: {old}")
        if sidx < len(d.nams):
            d.nams[sidx] = new[:6]
        else:
            d.nams.append(new[:6])


def _parse_custom_gas_spec(spec: str) -> tuple[str, list[float], dict[str, float]]:
    parts = [x.strip() for x in spec.split("|")]
    if len(parts) != 3:
        raise ValueError("gas custom spec must be: name|8therc|composition")
    name = parts[0]
    therc = [float(x.strip()) for x in parts[1].split(",") if x.strip()]
    comp = _parse_composition(parts[2])
    return name, therc, comp


def _parse_custom_solid_spec(spec: str) -> tuple[str, list[float], list[float], dict[str, float]]:
    parts = [x.strip() for x in spec.split("|")]
    if len(parts) != 4:
        raise ValueError("solid custom spec must be: name|8therc|12soleq|composition")
    name = parts[0]
    therc = [float(x.strip()) for x in parts[1].split(",") if x.strip()]
    soleq = [float(x.strip()) for x in parts[2].split(",") if x.strip()]
    comp = _parse_composition(parts[3])
    return name, therc, soleq, comp


def run_cli(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    db = load_databases(db_dir())

    if args.list_templates:
        for name in list_templates():
            print(name)
        return 0

    if args.input:
        d = load_case(args.input)
    elif args.template:
        d = load_case(args.template)
    else:
        d = load_case("CHNO")

    apply_noninteractive_overrides(d, args)
    _apply_legacy_eos_preset(d, args.legacy_eos_preset)
    _apply_legacy_athrho(d, args.legacy_athrho)
    if args.legacy_aispr is not None:
        d.aispr = float(args.legacy_aispr)
    _apply_legacy_constants(d, args.legacy_var)

    if args.mix:
        mix_entries = parse_mix_spec(args.mix)
        idx = component_index([*db.components])
        unknown = apply_mixture_to_bkwdata(
            d,
            mix_entries,
            idx,
            basis=args.mix_basis,
            strict_elements=args.strict_elements,
        )
        if unknown:
            print("Warning: elements not present in template deck:", ", ".join(unknown))

    for name in args.add_gas_db:
        key = name.strip().lower()
        if key not in db.therc:
            raise KeyError(f"gas species not found in ZZZTHERC: {name}")
        ts = db.therc[key]
        add_gas_species(
            d,
            name=ts.name,
            therc=list(float(v) for v in ts.therc[:8]),
            composition={_normalize_element(k): float(v) for k, v in ts.composition.items()},
        )

    for name in args.add_solid_db:
        key = name.strip().lower()
        if key not in db.therc or key not in db.soleqs:
            raise KeyError(f"solid species not found in ZZZTHERC/ZZZSOLEQ: {name}")
        ts = db.therc[key]
        sq = db.soleqs[key]
        add_solid_species(
            d,
            name=ts.name,
            therc=list(float(v) for v in ts.therc[:8]),
            soleq=list(float(v) for v in sq.soleqs[:12]),
            composition={_normalize_element(k): float(v) for k, v in ts.composition.items()},
        )

    for spec in args.add_gas_custom:
        name, therc, comp = _parse_custom_gas_spec(spec)
        add_gas_species(d, name=name, therc=therc, composition=comp)

    for spec in args.add_solid_custom:
        name, therc, soleq, comp = _parse_custom_solid_spec(spec)
        add_solid_species(d, name=name, therc=therc, soleq=soleq, composition=comp)

    # Apply twin remap after all solids (template + db + custom) are present.
    _apply_legacy_solid_twins(d, args.legacy_solid_twin)

    if args.interactive:
        d = interactive_cli(d, db)

    if args.output:
        save_bkwdata(d, args.output)
        print(f"Saved: {args.output}")
        if args.run != "none":
            from bkw_py import bkw as _bkw_engine, ispbkw as _isp_engine
            engine = _bkw_engine if args.run == "bkw" else _isp_engine
            out = "bkw.out" if args.run == "bkw" else "isp.out"
            engine.run(args.output, out)
            print(f"Ran {args.run}, output: {out}")

    return 0
