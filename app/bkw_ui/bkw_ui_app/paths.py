from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "BKW"


def _is_frozen() -> bool:
    # Nuitka exposes __compiled__; keep sys.frozen as a generic frozen-app fallback.
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def _home() -> Path:
    # On POSIX (incl. macOS) honor $HOME explicitly; Path.home() on Windows
    # ignores HOME and reads USERPROFILE, which breaks tests that simulate
    # darwin while running on Windows.
    if sys.platform != "win32":
        env_home = os.environ.get("HOME")
        if env_home:
            return Path(env_home)
    return Path.home()


def _user_data_root() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or Path.home() / "AppData" / "Local"
        )
        return base / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", _home() / ".local" / "share")) / APP_NAME


def _user_projects_dir() -> Path:
    return _home() / "Documents" / APP_NAME


if _is_frozen():
    exe = Path(sys.executable).resolve()
    # macOS .app bundle: <name>.app/Contents/MacOS/<binary>
    if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
        BUNDLE_ROOT = exe.parents[2]
    else:
        BUNDLE_ROOT = exe.parent
    RUNTIME_ROOT = _user_data_root()
    PROJECTS_DIR = _user_projects_dir()
    import bkw_py
    BKW_PY_DIR = Path(bkw_py.__file__).resolve().parent
    # Nuitka --include-data-dir places tdf_engine inside the app bundle next
    # to the executable; copy it to a writable runtime directory before use.
    TDF_ENGINE_SOURCE_DIR = exe.parent / "tdf_engine"
    if not TDF_ENGINE_SOURCE_DIR.exists():
        TDF_ENGINE_SOURCE_DIR = Path(getattr(sys, "_MEIPASS", exe.parent)) / "tdf_engine"
    TDF_ENGINE_DIR = RUNTIME_ROOT / "tdf_engine"
else:
    BKW_PY_DIR = Path(__file__).resolve().parents[2] / "bkw_py"
    BUNDLE_ROOT = Path(__file__).resolve().parents[1]   # BKW/bkw_ui/
    RUNTIME_ROOT = BUNDLE_ROOT
    PROJECTS_DIR = RUNTIME_ROOT / "projects"
    TDF_ENGINE_SOURCE_DIR = BUNDLE_ROOT / "tdf_engine"   # BKW/bkw_ui/tdf_engine/
    TDF_ENGINE_DIR = TDF_ENGINE_SOURCE_DIR

DATA_DIR = BKW_PY_DIR / "data"                          # bkw_py/data/
TEMPLATES_DIR = DATA_DIR / "templates"                  # bkw_py/data/templates/
LOG_DIR = RUNTIME_ROOT / "logs"


def _bootstrap_tdf_engine() -> None:
    if TDF_ENGINE_DIR == TDF_ENGINE_SOURCE_DIR:
        return
    TDF_ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    for item in TDF_ENGINE_SOURCE_DIR.iterdir():
        target = TDF_ENGINE_DIR / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    _bootstrap_tdf_engine()
