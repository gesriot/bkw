# BKW 0.9.0

Thermochemical toolkit covering detonation parameters (Becker–Kistiakowsky–Wilson), specific impulse, ideal-gas / solid thermodynamic functions, and a `BKWDATA` preprocessor – Python engine plus a desktop GUI.

## Downloads

- **macOS (Apple Silicon):** `BKW-0.9.0-macos-arm64.dmg`
- **Windows (x64):** `BKW-0.9.0-windows-x64.exe`
- **Linux (x64):** `BKW-0.9.0-linux-x64.tar.gz` (standalone bundle)

## Highlights

### Engines

- **BKW** – detonation parameters from a `BKWDATA` deck → `bkw.out` (Hugoniot, isentrope, CJ point).
- **ISPBKW** – specific impulse for ISP-mode decks (`ioeq=2`) → `isp.out`.
- **USERBKW** – `BKWDATA` preprocessor with chemistry templates (CHNO, CHNF, ...), mixture editor, custom species, and full access to legacy USERBKW knobs (`page1` modes, `page2` EOS preset, `page5` `athrho`/`aispr`, `page6` 30 constants, `page3b` solid-twin renames).
- **TDF** – thermodynamic functions of ideal gases and solids: structured deck editor, validation, in-process solver, curve viewer, PNG export.

### Desktop UI

- Single window with a step-by-step tab flow:
  Project → Mixture → Species → Calc → Results → Export, plus a separate TDF tab.
- Project save/load via `.bkwproj.json` (input source, mixture, species, legacy options, calc mode, recent output paths) – fully reproducible scenarios.
- Result graphs: Hugoniot `P-V`/`P-T`, isentrope `P-V`/`P-T`/`P-u`, ISP summary (chamber/exhaust pressure, isp, temperature, volume).
- Export: `hugoniot.csv` / `isentrope.csv` / `isp_summary.csv`, PNG of the current graph or all graphs.
- TDF tab: text + structured material editor, deck validation, native curve view via `pyqtgraph` with PNG fallback when `pyqtgraph` is unavailable.

### Architecture & runtime

- All four engines run **in-process** through `bkw_py.{bkw,ispbkw,tdf}.run(...)` – no subprocess fan-out, works inside Nuitka onefile/standalone bundles.
- Cooperative cancellation via `cancel_event`; configurable timeouts (`BKW_UI_CALC_TIMEOUT_SEC`, `BKW_UI_TDF_TIMEOUT_SEC`, default 1800s).
- Per-OS user data layout for the packaged app:
  - Windows – `%LOCALAPPDATA%\BKW`
  - macOS – `~/Library/Application Support/BKW`
  - Linux – `$XDG_DATA_HOME/BKW` (defaults to `~/.local/share/BKW`)
- Built-in component and thermodynamic databases (`ZZZCOMPS`, `ZZZTHERC`, `ZZZSOLEQ`) plus `BKWDATA` templates shipped inside the bundle.

### Packaging

- Nuitka builds for macOS (app-dist + DMG), Windows (onefile / standalone), and Linux (standalone tar.gz). Build args already include `pyqtgraph`, `numpy`, and the Qt OpenGL modules so graphs work out of the box.
- Packaging scripts default to Python 3.14.

## CLI entrypoints

Available after `pip install -e .` (or `uv sync`):

- `bkw`, `ispbkw`, `userbkw`, `tdf` – calculation CLIs
- `bkw-ui` – desktop application

## Requirements

- Python 3.11+ (packaging scripts default to 3.14)
- `PySide6 >= 6.7`, `pyqtgraph >= 0.13`, `matplotlib >= 3.10`
