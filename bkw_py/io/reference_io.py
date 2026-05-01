"""
Fixed-format I/O utilities.
Shared between all modules that read/write BKW-style fixed-format files.
"""
import math
import re


def parse_reference_float(s: str) -> float:
    """Parse a fixed-width floating-point field.

    Handles standard Python float strings and the BKW custom format
    where mantissa and exponent are separated by whitespace:
    e.g. '+3.0          +000' → 3.0
    """
    s = s.strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    # BKW custom: '+3.0          +000' → two tokens
    parts = s.split()
    if len(parts) == 2:
        try:
            return float(parts[0]) * (10.0 ** int(parts[1]))
        except ValueError:
            # Some decks split compact notation in the middle:
            # '+0.100 00000000+000' -> '+0.10000000000+000'
            s = parts[0] + parts[1]
    # Compact exponent format without explicit 'E':
    # '+1.60000000000-001' -> 0.16
    m = re.fullmatch(r"([+-]?\d*\.?\d+)([+-]\d+)", s)
    if m:
        return float(m.group(1)) * (10.0 ** int(m.group(2)))
    raise ValueError(f"Cannot parse reference float: '{s}'")


def read_e18(line: str, count: int) -> list:
    """Read `count` E18.11 floats from `line` (18 chars each)."""
    vals = []
    for i in range(count):
        start = i * 18
        end = start + 18
        field = line[start:end] if start < len(line) else ""
        vals.append(parse_reference_float(field))
    return vals


def read_i5(line: str, count: int) -> list:
    """Read `count` I5 integers from `line` (5 chars each)."""
    vals = []
    for i in range(count):
        start = i * 5
        end = start + 5
        field = line[start:end] if start < len(line) else ""
        field = field.strip()
        vals.append(int(field) if field else 0)
    return vals


def read_a6_records(lines_iter, count: int) -> list:
    """Read `count` A6 character fields from successive records.

    A6 records store 11 names per record; wraps to next record
    after 11. Returns a list of `count` stripped strings.
    """
    names = []
    per_line = 11
    remaining = count
    while remaining > 0:
        line = next(lines_iter).rstrip('\n')
        take = min(per_line, remaining)
        for i in range(take):
            start = i * 6
            end = start + 6
            field = line[start:end] if start < len(line) else ""
            names.append(field.strip())
        remaining -= take
    return names


def read_e18_records(lines_iter, count: int) -> list:
    """Read `count` E18.11 floats from successive records (4 per record)."""
    vals = []
    per_line = 4
    remaining = count
    while remaining > 0:
        line = next(lines_iter).rstrip('\n')
        take = min(per_line, remaining)
        vals.extend(read_e18(line, take))
        remaining -= take
    return vals


def fmt_e18_11(val: float) -> str:
    """Format a float in E18.11 style."""
    if val == 0.0:
        return f"{' 0.00000000000E+00':>18s}"
    sign = "-" if val < 0 else " "
    aval = abs(val)
    exp = int(math.floor(math.log10(aval))) + 1
    mant = aval / (10.0 ** exp)
    return f"{sign}{mant:.11f}E{'+' if exp >= 0 else '-'}{abs(exp):02d}"


def fmt_i5(val: int) -> str:
    """Format an integer in I5 style."""
    return f"{val:5d}"


def fmt_a6(s: str) -> str:
    """Format a string as A6 (left-justified, space-padded to 6)."""
    return f"{s:<6s}"
