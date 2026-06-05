"""Locate bundled native engine executables.

Search order:
1. ``$BKW_ENGINE_DIR`` (explicit override).
2. caller-provided directories.
3. ``<app>/bin/`` for source-tree runs.
4. ``bin/`` next to the frozen executable.
5. extracted onefile payload.
6. ``PATH`` (``shutil.which``).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

ENGINE_NAMES = ("abbkw", "abispbkw", "abtdf")
PAYLOAD_DIR_NAME = "engine_payload"
APP_NAME = "BKW"


class EngineNotFoundError(RuntimeError):
    """Raised when a required native executable cannot be located."""


def _exe_name(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _candidate_dirs(extra_dirs: Iterable[str | Path] | None = None) -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("BKW_ENGINE_DIR")
    if env:
        dirs.append(Path(env))
    if extra_dirs:
        dirs.extend(Path(d) for d in extra_dirs)
    pkg = Path(__file__).resolve().parent          # bkw_py/engines
    repo_root = pkg.parents[1]                      # bkw_py/engines -> bkw_py -> <repo>
    dirs.append(repo_root / "bin")
    exe_dir = Path(sys.executable).resolve().parent
    dirs.append(exe_dir / "bin")
    bundle_root = Path(getattr(sys, "_MEIPASS", exe_dir))
    dirs.append(bundle_root / "bin")
    return dirs


def _payload_dirs(extra_dirs: Iterable[str | Path] | None = None) -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("BKW_ENGINE_PAYLOAD_DIR")
    if env:
        dirs.append(Path(env))
    if extra_dirs:
        dirs.extend(Path(d) / PAYLOAD_DIR_NAME for d in extra_dirs)
    pkg = Path(__file__).resolve().parent
    repo_root = pkg.parents[1]
    exe_dir = Path(sys.executable).resolve().parent
    bundle_root = Path(getattr(sys, "_MEIPASS", exe_dir))
    dirs.extend([
        repo_root / PAYLOAD_DIR_NAME,
        exe_dir / PAYLOAD_DIR_NAME,
        bundle_root / PAYLOAD_DIR_NAME,
    ])
    return dirs


def _runtime_bin_dir() -> Path:
    if sys.platform == "win32":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or Path.home() / "AppData" / "Local"
        )
        return base / APP_NAME / "bin"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "bin"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME / "bin"


def _extract_payload(name: str, exe: str, extra_dirs: Iterable[str | Path] | None) -> Path | None:
    payload_name = f"{name}.bin"
    for d in _payload_dirs(extra_dirs):
        payload = d / payload_name
        if not payload.is_file():
            continue
        target_dir = _runtime_bin_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / exe
        if not target.exists() or target.stat().st_size != payload.stat().st_size:
            shutil.copy2(payload, target)
        try:
            target.chmod(target.stat().st_mode | 0o755)
        except OSError:
            pass
        return target
    return None


def resolve_engine(name: str, *, extra_dirs: Iterable[str | Path] | None = None) -> Path:
    """Return the path to engine executable ``name`` (e.g. ``"abbkw"``)."""
    exe = _exe_name(name)
    searched = _candidate_dirs(extra_dirs)
    for d in searched:
        p = d / exe
        if p.is_file() and os.access(p, os.X_OK):
            return p
    extracted = _extract_payload(name, exe, extra_dirs)
    if extracted is not None and extracted.is_file() and os.access(extracted, os.X_OK):
        return extracted
    found = shutil.which(exe)
    if found:
        return Path(found)
    raise EngineNotFoundError(
        f"Engine '{exe}' not found. Set BKW_ENGINE_DIR or place it in bin/. "
        f"Searched: "
        + ", ".join(str(d) for d in [*searched, *_payload_dirs(extra_dirs)])
        + ", PATH."
    )
