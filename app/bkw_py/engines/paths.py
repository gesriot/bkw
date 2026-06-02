"""Locate bundled native engine executables.

Search order:
1. ``$BKW_ENGINE_DIR`` (explicit override).
2. ``<app>/bin/`` for source-tree runs.
3. ``bin/`` next to the frozen executable.
4. ``PATH`` (``shutil.which``).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ENGINE_NAMES = ("abbkw", "abispbkw", "abtdf")


class EngineNotFoundError(RuntimeError):
    """Raised when a required native executable cannot be located."""


def _exe_name(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("BKW_ENGINE_DIR")
    if env:
        dirs.append(Path(env))
    pkg = Path(__file__).resolve().parent          # bkw_py/engines
    repo_root = pkg.parents[1]                      # bkw_py/engines -> bkw_py -> <repo>
    dirs.append(repo_root / "bin")
    exe_dir = Path(sys.executable).resolve().parent
    dirs.append(exe_dir / "bin")
    bundle_root = Path(getattr(sys, "_MEIPASS", exe_dir))
    dirs.append(bundle_root / "bin")
    return dirs


def resolve_engine(name: str) -> Path:
    """Return the path to engine executable ``name`` (e.g. ``"abbkw"``)."""
    exe = _exe_name(name)
    searched = _candidate_dirs()
    for d in searched:
        p = d / exe
        if p.is_file() and os.access(p, os.X_OK):
            return p
    found = shutil.which(exe)
    if found:
        return Path(found)
    raise EngineNotFoundError(
        f"Engine '{exe}' not found. Set BKW_ENGINE_DIR or place it in bin/. "
        f"Searched: " + ", ".join(str(d) for d in searched) + ", PATH."
    )
