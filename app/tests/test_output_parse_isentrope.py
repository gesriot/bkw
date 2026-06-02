"""Regression: the BKW isentrope table must parse despite header spacing.

The legacy build emits the isentrope header with wider column padding than
the ABSOFT reference ("Energy+c       Gamma" vs "Energy+c   Gamma"). The parser
must be whitespace-tolerant; a literal substring match silently dropped the
whole isentrope table.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bkw_ui"))

from bkw_ui_app.services.output_parse import parse_bkw_tables

# legacy-style header (note the wide gap between "Energy+c" and "Gamma").
GFORTRAN_ISO = (
    "1 A BKW Isentrope thru BKW CJ Pressure for  \n"
    " Pressure (mb) Volume (c/g) Temperature(k) Energy+c       Gamma      Part Vel \n"
    " 3.467444E-01 4.159134E-01 2.587327E+03 1.242101E-01 2.940591E+00 2.200457E-01\n"
    " 1.733722E-01 5.262625E-01 2.295342E+03 9.697889E-02 2.853980E+00 3.555863E-01\n"
    " 8.668610E-02 6.719380E-01 2.012198E+03 7.906050E-02 2.748914E+00 4.664269E-01\n"
    "1 The isentrope state variables as computed from the least squares fit\n"
    " 9.999999E-09 9.999999E-09 9.999999E-09 9.999999E-09 9.999999E-09 9.999999E-09\n"
)


def test_isentrope_parses_with_wide_header_spacing():
    tables = parse_bkw_tables(GFORTRAN_ISO)
    assert len(tables.isentrope) == 3, tables.isentrope
    first = tables.isentrope[0]
    assert first[0] == 0.3467444
    assert first[5] == 0.2200457
    # The 6-col row after the end marker must NOT be captured.
    assert all(row[0] != 9.999999e-09 for row in tables.isentrope)


def test_no_isentrope_header_yields_empty():
    assert parse_bkw_tables("nothing to see here").isentrope == []
