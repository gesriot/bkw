# BKW UI

Desktop application for preparing `BKWDATA`, running `BKW`/`ISPBKW` calculations and working with `TDF` from a single window.

The current UI labels are Russian. This README uses English section names, and shows the exact Russian labels where that helps match the window.

## Quick start

### Scenario A – calculate from an existing `BKWDATA`

1. Tab `1. Проект`:
   - `Источник входа = import`
   - point `Входной BKWDATA` to your file
2. Tab `4. Расчет`:
   - choose `Режим` (`bkw` or `isp`)
   - press `Запустить расчет`
3. Tab `5. Результаты` – review report text and graphs
4. Tab `6. Экспорт` – `Экспорт CSV` and/or `Экспорт PNG`

### Scenario B – calculate from a template

1. Tab `1. Проект`:
   - `Источник входа = template`
   - pick `Шаблон BKWDATA`
2. Tab `2. Смесь`:
   - add components (name + value > 0)
   - press `Применить в проект`
3. Tab `3. Species` (optional): add `gas/solid db`, custom species, legacy
   fields
4. Tab `4. Расчет`:
   - `Сгенерировать BKWDATA`
   - `Запустить расчет`

For an `isp` run generated from a template, set `Legacy page1: ioeq` to `2` before generating `BKWDATA`; `ispbkw` accepts only ISP-mode decks.

### Scenario C – TDF

1. Tab `7. TDF`:
   - edit `tdfdata` (as text or via the structured form)
   - `Применить в tdf_engine`
2. Press `Запустить TDF`
3. Browse the curves (`Prev`/`Next` or the dropdown)

## 1. Purpose

The application solves three tasks:

1. Preparing `BKWDATA` (mixture, species and USERBKW legacy settings).
2. Running calculations:
   - `bkw` → `bkw.out`-compatible report
   - `ispbkw` → `isp.out`-compatible report
3. Working with `TDF`:
   - editing the input deck
   - running TDF
   - browsing curves

## 2. Requirements and installation

- Python 3.11+ (the packaging scripts default to Python 3.14)
- `PySide6 >= 6.7`
- `pyqtgraph >= 0.13`
- `matplotlib >= 3.10`

Install from the repository root:

```bash
pip install -e .
```

Or using `uv`:

```bash
uv sync
```

Run:

```bash
python bkw_ui/main.py
```

Or via the installed entry point:

```bash
bkw-ui
```

If you already have a packaged build, just launch `BKW.exe` (Windows), `BKW.app` (macOS) or `BKW.dist/BKW` (Linux) directly.

## 3. Data layout

The UI uses resources from `bkw_py/` (calculation engine) and per-user files. The exact location depends on whether you run from source or from a packaged build.

| Path (dev) | Path (packaged app) | Contents |
|------|------|-----------|
| `bkw_py/data/templates/` | inside the bundle | `BKWDATA` templates (CHNO, CHNF, ...) |
| `bkw_py/data/` | inside the bundle | Databases `ZZZCOMPS`, `ZZZSOLEQ`, `ZZZTHERC` |
| `bkw_ui/tdf_engine/` | `<user-data>/BKW/tdf_engine/` | TDF working files (`tdfdata`, `scoef`, `tdf.out`, `plots/*.png`) |
| `bkw_ui/projects/` | `~/Documents/BKW/` | Saved projects `.bkwproj.json` |
| `bkw_ui/logs/` | `<user-data>/BKW/logs/` | Run logs |

`<user-data>` resolves per OS:

- Windows – `%LOCALAPPDATA%\BKW` (typically `C:\Users\<user>\AppData\Local\BKW`)
- macOS – `~/Library/Application Support/BKW`
- Linux – `$XDG_DATA_HOME/BKW` (defaults to `~/.local/share/BKW`)

On the first launch of the packaged app the `bkw_ui/tdf_engine/` contents are copied into `<user-data>/BKW/tdf_engine/`; afterwards everything runs from the user-writable directory (files inside the bundle are read-only).

Calculations run in-process via `bkw_py` library functions:

- `bkw_py.bkw.run(...)`
- `bkw_py.ispbkw.run(...)`
- `bkw_py.tdf.run(...)`

This matters for Nuitka builds: there is no separate Python interpreter inside the `.app`/standalone bundle to run scripts via subprocess.

## 4. Overall workflow

Tabs are organized as steps:

1. `Project` – input source (`import` or `template`), template/file.
2. `Mixture` – composition of the mixture (needed for `template`).
3. `Species` – DB and custom species + legacy parameters.
4. `Calc` – generate `BKWDATA`, run `bkw`/`isp`.
5. `Results` – report text and graphs.
6. `Export` – CSV/PNG.
7. `TDF` – separate flow for editing/running TDF.

Key principle:

- with `template` you typically configure the mixture and generate a fresh `BKWDATA`;
- with `import` you can use an existing `BKWDATA` and run the calculation directly.

## 5. Tab 1: Project

Fields:

- `Project name` – name in `.bkwproj.json`.
- `Input source`:
  - `import` (default) – use an existing `BKWDATA`;
  - `template` – assemble `BKWDATA` from a template + UI parameters.
- `BKWDATA template` – list of files in `bkw_py/data/templates/`.
- `Input BKWDATA` – path to the file in `import` mode.

Buttons:

- `New project`
- `Open .bkwproj.json`
- `Save .bkwproj.json`

Notes:

- editing `Input BKWDATA` manually syncs the path into the project;
- in `import` mode this path can be used to run a calculation immediately.

## 6. Tab 2: Mixture

Fields:

- `Basis`:
  - `wt` – mass fractions;
  - `mol` – molar fractions.
- `Strict elements` – disallow elements unknown to the template.
- `Component / Value` table.

Rules:

- the component name is required;
- the value is required and must be `> 0`;
- duplicates are not allowed.

The list of components comes from `ZZZCOMPS` (`bkw_py/data/ZZZCOMPS`).

## 7. Tab 3: Species

### 7.1 DB species

- `Add gas db` – comma-separated names (from `ZZZTHERC`)
- `Add solid db` – comma-separated names (from `ZZZTHERC + ZZZSOLEQ`)

Example:

```text
no,hcl,co2
```

### 7.2 Custom species

`Add gas custom` – one per line:

```text
name|a,b,c,d,e,ic,hf,covol|el=val,el=val
```

`Add solid custom` – one per line:

```text
name|8therc|12soleq|el=val,el=val
```

Examples:

```text
xg1|1,1,1,1,1,1,1,1|c=1,o=1
```

```text
xs1|1,1,1,1,1,1,1,1|1,1,1,1,1,1,1,1,1,1,1,1|c=1
```

### 7.3 USERBKW legacy parameters (via UI)

#### Legacy page1/page2

- `ioeq`, `icjc`, `ihug`, `ipvc`, `igrp` (`inherit` or explicit value)
- `EOS preset`: `default | rdx | tnt`

#### Legacy page5

- `athrho` – up to 4 comma-separated values
- `aispr` – single number

#### Legacy page6

- constants, one per line as `no=val`, with `no` in `1..30`
- `-1` as the value restores the original constant

#### Legacy page3b

- solid twin, one per line as `old=new`
- `old` – solid species name, `new` – second name (twin)

The UI normalizes formatting automatically (whitespace/case/separators).

## 8. Tab 4: Calc

Buttons:

- `Generate BKWDATA`
- `Run`
- `Cancel`

Mode:

- `bkw` or `isp`

Logic:

- `Generate BKWDATA` calls `bkw_py.ui.userbkw` functions directly with
  parameters collected from the UI.
- `Run` calls in-process functions:
  - `bkw_py.bkw.run(...)` for `bkw`
  - `bkw_py.ispbkw.run(...)` for `isp`

Progress:

- calculations run in a background worker (`QRunnable`/`QThreadPool`);
- status and progress are shown;
- `Cancel` sets a `cancel_event`; the solver exits cooperatively at the next checkpoint (no SIGKILL – the calculation terminates cleanly).

Timeouts (via env):

- `BKW_UI_CALC_TIMEOUT_SEC` (default `1800`)
- `BKW_UI_TDF_TIMEOUT_SEC` (default `1800`)

Exit codes:

- `0` – success
- `124` – cancelled or timed out

## 9. Tab 5: Results

### 9.1 `BKW` graphs

When data is available, the following are drawn:

- Hugoniot `P-V`
- Hugoniot `P-T`
- Isentrope `P-V`
- Isentrope `P-T`
- Isentrope `P-u`

### 9.2 `ISP` graph

For an `isp` report:

- summary graph: chamber/exhaust (pressure, isp, temperature, volume)

### 9.3 Navigation

- `Prev`/`Next` cycles through graphs
- empty graph sets are handled safely

### 9.4 Report text

The bottom panel shows the full text of `bkw.out`/`isp.out`.

## 10. Tab 6: Export

### CSV

The tables found in the report are exported:

- `hugoniot.csv`
- `isentrope.csv`
- `isp_summary.csv`

### PNG

- export the current graph or all graphs
- file name is derived from the graph title

## 11. Tab 7: TDF

The tab works with the TDF working directory:

- in dev – `bkw_ui/tdf_engine/`;
- in a packaged app – `<user-data>/BKW/tdf_engine/` (see section 3 for per-OS paths).

Calculation runs in-process via `bkw_py.tdf.run(...)`.

### Features

- editing `tdfdata` as text
- open/save/apply/reset
- structured material editor:
  - materials table
  - parameter form
  - generating `tdfdata` from the form
- structure validation before run
- background TDF run
- browsing curves from `tdf.out` via `pyqtgraph`, with a PNG fallback from `plots/*.png` if `pyqtgraph` is unavailable

### TDF logs

- `<logs>/tdf.log`, overwritten on each run. `<logs>` is `bkw_ui/logs/` in dev and `<user-data>/BKW/logs/` in a packaged app.

## 12. `.bkwproj.json` project format

Stores:

- input source
- template/path to `BKWDATA`
- mixture
- species and custom species
- USERBKW legacy settings
- calculation mode
- recent output paths

This makes the calculation scenario reproducible.

## 13. Logs and diagnostics

### Main calculation

- file: `<logs>/app.log` (dev – `bkw_ui/logs/app.log`, packaged – `<user-data>/BKW/logs/app.log`)
- overwritten on each run
- contains the launch line and `exit_code`

### What to check on problems

1. `app.log`: launch line and `exit_code`
2. `BKWDATA` and report paths in the UI
3. report file existence and size
4. `Results` tab: report text

If graphs are empty:

1. check `exit_code` in `app.log`
2. check the report path in the UI
3. open the report text on the `Results` tab

## 14. Current limitations

1. `TDF` does not yet have advanced curve filtering by type/substance.
2. Some rare historical dialog branches are not reproduced verbatim as UX strings.

## 15. Useful tips

- `Cancel` sets a cancel flag; the calculation terminates cleanly at the next checkpoint (no thread killing).
- Logs are overwritten on every new run.
- A project is saved as `.bkwproj.json` and restores the UI state.

## 16. CLI equivalents (for debugging)

Generate BKWDATA:

```bash
python -m bkw_py.userbkw --template CHNO --mix rdx=100 --output BKWDATA
```

For an ISP-compatible deck, add `--set-ioeq 2`.

BKW:

```bash
python -m bkw_py.bkw --input BKWDATA --output bkw.out
```

ISP:

```bash
python -m bkw_py.userbkw --template CHNO --mix rdx=100 --set-ioeq 2 --output BKWDATA
python -m bkw_py.ispbkw --input BKWDATA --output isp.out
```

TDF (run from the directory with `tdfdata`):

```bash
cd bkw_ui/tdf_engine
python -m bkw_py.tdf
```

## 17. Building the application

```bash
./scripts/package-macos.sh
pwsh ./scripts/package-windows.ps1 -Mode onefile -Lto yes
./scripts/package-linux.sh
```

The scripts use Nuitka and place artifacts under `dist/`. The build args already include `pyqtgraph`, `numpy` and `PySide6.QtOpenGL`/`QtOpenGLWidgets` via `--include-package`/`--include-module`, so graphs work out of the box in the packaged application.
