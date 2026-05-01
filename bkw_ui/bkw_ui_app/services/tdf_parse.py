from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


RE_FLOAT = re.compile(r"^[\s+\-0-9.E]+$")
RE_NUM = re.compile(r"[+\-]?\d+\.\d+E[+\-]\d+")


@dataclass
class TdfCurve:
    title: str
    xlabel: str
    ylabel: str
    x: list[float]
    y: list[float]


def _line_material(line: str) -> str | None:
    if not line.startswith("1"):
        return None
    s = line[1:].strip()
    if not s:
        return None
    if "entropy fit" in s.lower():
        return None
    return s


def _parse_table(lines: list[str], i: int) -> tuple[int, list[list[float]]]:
    rows: list[list[float]] = []
    while i < len(lines):
        ln = lines[i].rstrip("\n")
        if not ln.strip():
            i += 1
            continue
        if not RE_FLOAT.match(ln):
            break
        nums = [float(x) for x in RE_NUM.findall(ln)]
        if len(nums) in {5, 6}:
            rows.append(nums)
            i += 1
            continue
        break
    return i, rows


def parse_tdf_out(path: str | Path) -> list[TdfCurve]:
    p = Path(path)
    lines = p.read_text(encoding="ascii", errors="replace").splitlines()
    curves: list[TdfCurve] = []
    cur_material = "material"
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _line_material(line)
        if m:
            cur_material = m
            i += 1
            continue

        if "Temp (deg k)" in line and "Fo-Ho" in line and "So" in line:
            i += 1
            i, rows = _parse_table(lines, i)
            if not rows:
                continue

            # row shapes:
            # 5 cols: temp, fo, ho, so, ic
            # 6 cols: temp, fo, ho, so, cv, ic
            x = [r[0] for r in rows]
            fo = [r[1] for r in rows]
            ho = [r[2] for r in rows]
            so = [r[3] for r in rows]
            has_cv = len(rows[0]) == 6
            cv = [r[4] for r in rows] if has_cv else []

            base = cur_material.strip()
            curves.append(TdfCurve(f"{base} | Free energy", "Temperature (K)", "Fo-Ho/T", x, fo))
            curves.append(TdfCurve(f"{base} | Enthalpy", "Temperature (K)", "Ho", x, ho))
            curves.append(TdfCurve(f"{base} | Entropy", "Temperature (K)", "So", x, so))
            if has_cv:
                curves.append(TdfCurve(f"{base} | Heat capacity", "Temperature (K)", "Cv", x, cv))
            continue

        i += 1

    return curves
