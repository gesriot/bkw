"""Binding layer to the bundled native compute engines.

This package locates bundled executables and runs them as headless
subprocesses, feeding BKWDATA in and reading the text report out.
"""
from __future__ import annotations

from .paths import EngineNotFoundError, resolve_engine
from .runner import run_fixed_io, run_in_dir

__all__ = ["EngineNotFoundError", "resolve_engine", "run_fixed_io", "run_in_dir"]
