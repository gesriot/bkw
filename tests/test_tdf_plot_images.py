from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bkw_ui"))

from bkw_ui_app.services.tdf_parse import TdfCurve, tdf_plot_image_paths


def test_tdf_plot_image_paths_match_curve_order(tmp_path):
    out = tmp_path / "tdf.out"
    out.write_text("", encoding="ascii")
    plots = tmp_path / "plots"
    plots.mkdir()

    curves = [
        TdfCurve("Ammonium nitrate | Free energy", "T", "F", [], []),
        TdfCurve("Ammonium nitrate | Enthalpy", "T", "H", [], []),
        TdfCurve("Ammonium nitrate | Entropy", "T", "S", [], []),
        TdfCurve("Ammonium nitrate | Heat capacity", "T", "Cv", [], []),
    ]
    for name in (
        "001_Ammonium_nitrate_free_energy.png",
        "001_Ammonium_nitrate_enthalpy.png",
        "001_Ammonium_nitrate_entropy.png",
        "001_Ammonium_nitrate_heat_capacity.png",
    ):
        (plots / name).write_bytes(b"png")

    paths = tdf_plot_image_paths(out, curves)

    assert [p.name if p else None for p in paths] == [
        "001_Ammonium_nitrate_free_energy.png",
        "001_Ammonium_nitrate_enthalpy.png",
        "001_Ammonium_nitrate_entropy.png",
        "001_Ammonium_nitrate_heat_capacity.png",
    ]


def test_tdf_plot_image_paths_handle_repeated_material_names(tmp_path):
    out = tmp_path / "tdf.out"
    out.write_text("", encoding="ascii")
    plots = tmp_path / "plots"
    plots.mkdir()

    curves = [
        TdfCurve("Same material | Free energy", "T", "F", [], []),
        TdfCurve("Same material | Enthalpy", "T", "H", [], []),
        TdfCurve("Same material | Free energy", "T", "F", [], []),
    ]
    (plots / "001_Same_material_free_energy.png").write_bytes(b"png")
    (plots / "001_Same_material_enthalpy.png").write_bytes(b"png")
    (plots / "002_Same_material_free_energy.png").write_bytes(b"png")

    paths = tdf_plot_image_paths(out, curves)

    assert [p.name if p else None for p in paths] == [
        "001_Same_material_free_energy.png",
        "001_Same_material_enthalpy.png",
        "002_Same_material_free_energy.png",
    ]
