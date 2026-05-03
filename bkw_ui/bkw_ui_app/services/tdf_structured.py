from __future__ import annotations

from dataclasses import dataclass, field
import re

from ..i18n import t


@dataclass
class TdfMaterial:
    marker: str  # e.g. "***" or "O2"
    code: str
    name: str
    comment: str
    nline: str
    body_lines: list[str] = field(default_factory=list)


@dataclass
class TdfDeck:
    prelude: list[str] = field(default_factory=list)
    materials: list[TdfMaterial] = field(default_factory=list)
    epilogue: list[str] = field(default_factory=list)


def _is_material_start(line: str) -> bool:
    s = line.rstrip("\n")
    if not s.strip():
        return False
    if s.startswith(" ***"):
        return True
    # Known special legacy record in tdfdata.
    if s.startswith(" O2  Diatomic"):
        return True
    return False


def _parse_header(line: str) -> tuple[str, str, str, str]:
    s = line.rstrip("\n")
    if s.startswith(" ***"):
        payload = s[4:].rstrip()
        parts = payload.split()
        code = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        comment = payload[len(code) + len(name) :].strip() if (code or name) else payload
        return "***", code, name, comment
    if s.startswith(" O2  Diatomic"):
        return "O2", "O2", "Diatomic", ""
    return "", "", "", s.strip()


def parse_tdfdata_text(text: str) -> TdfDeck:
    lines = text.splitlines()
    deck = TdfDeck()
    i = 0

    # Prelude lines before first material.
    while i < len(lines) and not _is_material_start(lines[i]):
        deck.prelude.append(lines[i])
        i += 1

    while i < len(lines):
        if not _is_material_start(lines[i]):
            deck.epilogue.extend(lines[i:])
            break

        marker, code, name, comment = _parse_header(lines[i])
        i += 1
        nline = lines[i] if i < len(lines) else ""
        if i < len(lines):
            i += 1

        body: list[str] = []
        while i < len(lines) and not _is_material_start(lines[i]):
            body.append(lines[i])
            i += 1

        deck.materials.append(
            TdfMaterial(marker=marker, code=code, name=name, comment=comment, nline=nline, body_lines=body)
        )

    return deck


def render_tdfdata_text(deck: TdfDeck) -> str:
    out: list[str] = []
    out.extend(deck.prelude)
    if deck.prelude and deck.prelude[-1].strip():
        out.append("")

    for m in deck.materials:
        if m.marker == "***":
            hdr = f" ***     {m.code:<8}  {m.name:<24} {m.comment}".rstrip()
        elif m.marker == "O2":
            hdr = " O2  Diatomic"
        else:
            hdr = f" ***     {m.code:<8}  {m.name:<24} {m.comment}".rstrip()
        out.append(hdr)
        out.append(m.nline)
        out.extend(m.body_lines)
        if not m.body_lines or m.body_lines[-1].strip():
            out.append("")

    if deck.epilogue:
        out.extend(deck.epilogue)

    # Keep file ending newline and avoid extra trailing blank rows.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def _parse_nline(nline: str) -> int | None:
    s = nline.strip()
    if not s:
        return None
    if not re.fullmatch(r"[0-9]+", s):
        return None
    try:
        return int(s)
    except Exception:
        return None


def validate_tdf_deck(deck: TdfDeck) -> list[str]:
    errors: list[str] = []
    min_nonempty_by_nline = {
        1: 4,
        2: 5,
        3: 6,
        4: 3,
        5: 3,
    }

    for i, m in enumerate(deck.materials, start=1):
        tag = t("tdf.validate.tag", i=i, code=m.code or "?", name=m.name or "").strip()
        if m.marker not in {"***", "O2"}:
            errors.append(t("tdf.validate.bad_marker", tag=tag, marker=m.marker))
        if m.marker == "***" and not m.code.strip():
            errors.append(t("tdf.validate.empty_code", tag=tag))
        if not m.nline.strip():
            errors.append(t("tdf.validate.empty_nline", tag=tag))
            continue

        nline = _parse_nline(m.nline)
        if nline is None:
            errors.append(t("tdf.validate.nline_not_int", tag=tag, nline=m.nline))
            continue
        if nline not in min_nonempty_by_nline:
            errors.append(t("tdf.validate.nline_unsupported", tag=tag, nline=nline))
            continue

        body_nonempty = [ln for ln in m.body_lines if ln.strip()]
        if len(body_nonempty) < min_nonempty_by_nline[nline]:
            errors.append(
                t(
                    "tdf.validate.body_too_short",
                    tag=tag,
                    nline=nline,
                    needed=min_nonempty_by_nline[nline],
                    got=len(body_nonempty),
                )
            )
            continue

        # Mandatory base rows for main material forms:
        # 1) composition/mass-like row
        # 2) temperature range row
        if not re.search(r"\d", body_nonempty[0]):
            errors.append(t("tdf.validate.body_row1_no_numbers", tag=tag))
        if not re.search(r"\d", body_nonempty[1]):
            errors.append(t("tdf.validate.body_row2_no_temp", tag=tag))

        # For nline 2/3 main gas forms, require an order/config row in body.
        if nline in {2, 3}:
            has_order_row = any(
                re.fullmatch(r"\s*[+-]?\d+(?:\.\d*)?\s+[+-]?\d+\s*(?:[+-]?\d+\s*)*$", ln) for ln in body_nonempty
            )
            if not has_order_row:
                errors.append(t("tdf.validate.no_order_row", tag=tag, nline=nline))

    return errors
