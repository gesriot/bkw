# BKW calculation package

Python package providing four calculation entrypoints:

- `BKW` – detonation parameters
- `ISPBKW` – specific impulse
- `USERBKW` – `BKWDATA` preprocessor
- `TDF` – thermodynamic functions of ideal gases and solids

## Installation

```bash
pip install -e .
```

This exposes the calculation commands `bkw`, `ispbkw`, `userbkw`, `tdf`, and equivalent `python -m bkw_py.<name>` invocations. Installing from the repository root also exposes the desktop UI command `bkw-ui`.

## Package layout

```
bkw_py/
├── bkw.py        – BKW entrypoint
├── ispbkw.py     – ISPBKW entrypoint
├── userbkw.py    – USERBKW entrypoint
├── tdf.py        – TDF entrypoint
├── core/         – algorithms (EOS, equilibrium, detonation, ISP)
├── io/           – BKWDATA and database I/O
├── ui/           – USERBKW CLI menu
└── data/
    ├── ZZZCOMPS      – components library
    ├── ZZZSOLEQ      – solid-phase EOS coefficients
    ├── ZZZTHERC      – thermochemical coefficients
    └── templates/    – BKWDATA templates (CHNO, CHNF, ...)
```

## Quick start

The `bkw` and `ispbkw` commands keep historical default input paths (`bkw/BKWDATA` and `ispbkw/bkwdata`). For a fresh checkout, generate a local `BKWDATA` first or pass your own `--input` path.

### BKW

```bash
python -m bkw_py.userbkw --template CHNO --mix "rdx=100" --output BKWDATA
python -m bkw_py.bkw --input BKWDATA --output bkw.out
```

Arguments:

- `--input PATH` – path to `BKWDATA` (default `bkw/BKWDATA`)
- `--output PATH` – path for `bkw.out` (default `bkw.out`)

### ISPBKW

```bash
python -m bkw_py.userbkw --template CHNO --mix "rdx=100" --set-ioeq 2 --output BKWDATA
python -m bkw_py.ispbkw --input BKWDATA --output isp.out
```

Arguments:

- `--input PATH` – path to `BKWDATA` for ISPBKW (default `ispbkw/bkwdata`)
- `--output PATH` – path for `isp.out` (default `isp.out`)

### USERBKW (non-interactive)

```bash
python -m bkw_py.userbkw --template CHNO --mix "rdx=60,tnt=40" --mix-basis wt --output BKWDATA
```

### USERBKW (interactive)

```bash
python -m bkw_py.userbkw --interactive
```

### TDF

Run from a directory containing `tdfdata` (and produces `tdf.out`, `scoef`, and `plots/*.png` when Matplotlib is available). The repository ships a working dataset at `bkw_ui/tdf_engine/`:

```bash
cd bkw_ui/tdf_engine
python -m bkw_py.tdf
```

In the packaged GUI app TDF input lives at `<user-data>/BKW/tdf_engine/` (e.g. `%LOCALAPPDATA%\BKW\tdf_engine` on Windows, `~/Library/Application Support/BKW/tdf_engine` on macOS).

## USERBKW reference

### Data source

- `--template NAME` – load template from `bkw_py/data/templates/`
- `--input PATH` – load existing BKWDATA
- `--output PATH` – output BKWDATA path
- `--list-templates` – print available template names

### Top-level settings

- `--set-label TEXT`
- `--set-ioeq INT`, `--set-icjc INT`, `--set-ihug INT`, `--set-ipvc INT`, `--set-igrp INT` – page-1 mode flags
- `--set-rho FLOAT`, `--set-temp FLOAT`, `--set-press FLOAT`

### Mixture composition

- `--mix "name=value,name=value,..."` – components and amounts
- `--mix-basis wt|mol` – mass or molar fractions (default `wt`)
- `--strict-elements` – abort on unknown elements

### Extra species

- `--add-gas-db NAME` (repeatable) – add gas species from `ZZZTHERC`
- `--add-solid-db NAME` (repeatable) – add solid species from `ZZZTHERC` + `ZZZSOLEQ`
- `--add-gas-custom "name|a,b,c,d,e,ic,hf,covol|el=val,el=val"` (repeatable) – custom gas with the 8 THERC numbers and element composition
- `--add-solid-custom "name|8therc|12soleq|el=val,el=val"` (repeatable) – custom solid: 8 THERC numbers, 12 SOLEQ numbers, element composition

### Legacy options (rarely needed)

- `--legacy-eos-preset default|rdx|tnt` – page-2 EOS preset
- `--legacy-athrho "rho1,rho2,..."` – extra densities (up to 4) for page 5
- `--legacy-aispr FLOAT` – Hugoniot pressure input on page 5
- `--legacy-var "no=val"` (repeatable) – override constant 1..30 on page 6
- `--legacy-solid-twin "old=new"` (repeatable) – rename a solid's second name

### Run after save

- `--run none|bkw|isp` – optionally invoke BKW or ISPBKW immediately after writing BKWDATA (default `none`)

### Interactive menu

`--interactive` opens the menu below. Items 1–9 are the modern Python flow; items 10–14 expose the legacy Fortran-style pages for fine-grained edits.

| # | Action |
| --- | --- |
| 1 | Summary |
| 2 | Edit flags (page-2 mode/settings) |
| 3 | Page 3 – select components from `ZZZCOMPS` |
| 4 | Page 4 – set composition and apply to BKWDATA |
| 5 | Page 5 – add custom component |
| 6 | Page 6 – extended species editor (`THERC`/`SOLEQ`) |
| 7 | Page 7 – save and optional run |
| 8 | Edit basic data (label, BKW preset, rho, T, P) |
| 9 | Edit elemental composition manually |
| 12 | Legacy page 1 – modes/settings (`ioeq`/`icjc`/`ihug`/`ipvc`/`igrp`) |
| 13 | Legacy page 2 – EOS presets (`RDX`/`TNT`/`input`/`default`) |
| 14 | Legacy page 3b – deep editor for `THERC`/`SOLEQ`, `aik`, mole fractions |
| 10 | Legacy page 5 – `athrho` / `aispr` |
| 11 | Legacy page 6 – 30 constants (`novar`/`var`, `-1` resets) |
| 0 | Exit |

## End-to-end examples

### USERBKW → BKW

```bash
python -m bkw_py.userbkw --template CHNO --mix "rdx=60,tnt=40" --output BKWDATA
python -m bkw_py.bkw --input BKWDATA --output bkw.out
```

### USERBKW → ISPBKW

```bash
python -m bkw_py.userbkw --template CHNO --mix "rdx=100" --set-ioeq 2 --output BKWDATA
python -m bkw_py.ispbkw --input BKWDATA --output isp.out
```

## Notes

- Output formatting preserves the legacy `bkw.out` / `isp.out` structure.
- Small numerical differences are possible due to iterative solver behavior.
