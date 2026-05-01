from __future__ import annotations

import re
from dataclasses import dataclass


_NUM = r"([+-]?(?:\d+\.\d+|\d+\.?|\.\d+)E[+-]\d+)"

RE_HUG_BLOCK = re.compile(
    rf"Pressure\s*=\s*{_NUM}\s+Volume\s*=\s*{_NUM}\s+"
    rf"Temperature\s*=\s*{_NUM}.*?"
    rf"Shock Velocity\s*=\s*{_NUM}\s+Particle Velocity\s*=\s*{_NUM}",
    re.S,
)

RE_6COL = re.compile(
    rf"^\s*{_NUM}\s+{_NUM}\s+{_NUM}\s+{_NUM}\s+{_NUM}\s+{_NUM}\s*$",
    re.M,
)

RE_ISP_BLOCK = re.compile(
    rf"THE CHAMBER OR EXHAUST PRESSURE IS\s*{_NUM}\s+BARS.*?"
    rf"THE ISP IS\s*{_NUM}\s+POUNDS THURST/POUND MASS/SEC.*?"
    rf"The Temperature is\s*{_NUM}\s+degrees Kelvin.*?"
    rf"The Computed\s+Volume\s*{_NUM}\s+cc/gm of propellant",
    re.S,
)


@dataclass
class BkwTables:
    hugoniot: list[tuple[float, float, float, float, float]]
    isentrope: list[tuple[float, float, float, float, float, float]]


@dataclass
class IspPoint:
    state: str
    pressure_bars: float
    isp: float
    temperature_k: float
    volume_cc_gm: float


def parse_bkw_tables(text: str) -> BkwTables:
    hug = [tuple(float(m.group(i)) for i in range(1, 6)) for m in RE_HUG_BLOCK.finditer(text)]

    hdr = "Pressure (mb) Volume (c/g) Temperature(k) Energy+c   Gamma      Part Vel"
    end = "The isentrope state variables as computed from the least squares fit"
    i0 = text.find(hdr)
    i1 = text.find(end)
    iso: list[tuple[float, float, float, float, float, float]] = []
    if i0 >= 0 and i1 > i0:
        block = text[i0:i1]
        iso = [tuple(float(m.group(i)) for i in range(1, 7)) for m in RE_6COL.finditer(block)]

    return BkwTables(hugoniot=hug, isentrope=iso)


def parse_isp_summary(text: str) -> list[IspPoint]:
    rows = [tuple(float(m.group(i)) for i in range(1, 5)) for m in RE_ISP_BLOCK.finditer(text)]
    points: list[IspPoint] = []
    for idx, (p, isp, t, v) in enumerate(rows):
        state = "Chamber" if idx == 0 else ("Exhaust" if idx == 1 else f"Point{idx+1}")
        points.append(IspPoint(state=state, pressure_bars=p, isp=isp, temperature_k=t, volume_cc_gm=v))
    return points

