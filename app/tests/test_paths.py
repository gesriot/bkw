from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def test_frozen_macos_paths_are_writable_user_locations(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    paths_file = repo / "bkw_ui" / "bkw_ui_app" / "paths.py"
    home = tmp_path / "home"
    exe_dir = tmp_path / "BKW.app" / "Contents" / "MacOS"
    tdf_source = exe_dir / "tdf_engine"
    tdf_source.mkdir(parents=True)
    (tdf_source / "tdfdata").write_text("sample tdfdata", encoding="ascii")
    (tdf_source / "tdfdata.default").write_text("sample default", encoding="ascii")
    exe = exe_dir / "main"
    exe.write_text("", encoding="ascii")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "platform", "darwin")

    spec = importlib.util.spec_from_file_location("bkw_paths_frozen_test", paths_file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__compiled__ = True
    spec.loader.exec_module(module)

    assert module.RUNTIME_ROOT == home / "Library" / "Application Support" / "BKW"
    assert module.PROJECTS_DIR == home / "Documents" / "BKW"
    assert module.TDF_ENGINE_DIR == module.RUNTIME_ROOT / "tdf_engine"

    module.ensure_dirs()

    assert module.LOG_DIR.is_dir()
    assert module.PROJECTS_DIR.is_dir()
    assert (module.TDF_ENGINE_DIR / "tdfdata").read_text(encoding="ascii") == "sample tdfdata"
    assert (module.TDF_ENGINE_DIR / "tdfdata.default").read_text(encoding="ascii") == "sample default"


def test_engine_resolver_extracts_packaged_payload(monkeypatch, tmp_path):
    from bkw_py.engines.paths import resolve_engine

    payload_dir = tmp_path / "engine_payload"
    payload_dir.mkdir()
    (payload_dir / "payloadtest.bin").write_bytes(b"payload engine")
    runtime_root = tmp_path / "runtime"

    monkeypatch.setenv("BKW_ENGINE_PAYLOAD_DIR", str(payload_dir))
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(runtime_root))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(runtime_root))

    exe = resolve_engine("payloadtest")

    expected_name = "payloadtest.exe" if sys.platform == "win32" else "payloadtest"
    assert exe == runtime_root / "BKW" / "bin" / expected_name
    assert exe.read_bytes() == b"payload engine"
    assert os.access(exe, os.X_OK)
