from __future__ import annotations

from pathlib import Path

from ..paths import TEMPLATES_DIR


SKIP = {"Makefile", "userbkw.f", "userbkw.exe", "USERBKW.txt", "ZZZCOMPS", "ZZZDECKS", "ZZZSOLEQ", "ZZZTHERC"}


def list_templates() -> list[str]:
    names: list[str] = []
    for p in TEMPLATES_DIR.iterdir():
        if not p.is_file():
            continue
        if p.name in SKIP:
            continue
        names.append(p.name)
    return sorted(names)


def template_path(name: str) -> Path:
    return TEMPLATES_DIR / name
