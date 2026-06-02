from __future__ import annotations

from pathlib import Path

from bkw_ui_app.app import _find_icon_path


def test_app_icon_path_is_available_in_source_layout():
    repo = Path(__file__).resolve().parents[1]

    assert _find_icon_path() == repo / "icon.png"
