from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class RunSettings:
    mode: str = "bkw"  # bkw | isp
    run_in_background: bool = True


@dataclass
class MixItem:
    name: str
    value: float


@dataclass
class BkwProject:
    version: int = 1
    name: str = "new_project"
    source_mode: str = "import"  # template | import
    template: str = "CHNO"
    source_bkwdata: str = ""
    mix_basis: str = "wt"
    mix: list[MixItem] = field(default_factory=list)
    strict_elements: bool = False
    add_gas_db: list[str] = field(default_factory=list)
    add_solid_db: list[str] = field(default_factory=list)
    add_gas_custom: list[str] = field(default_factory=list)
    add_solid_custom: list[str] = field(default_factory=list)
    legacy_ioeq: int | None = None
    legacy_icjc: int | None = None
    legacy_ihug: int | None = None
    legacy_ipvc: int | None = None
    legacy_igrp: int | None = None
    legacy_eos_preset: str = "default"  # default | rdx | tnt
    legacy_athrho: str = ""  # comma-separated values
    legacy_aispr: str = ""
    legacy_constants: list[str] = field(default_factory=list)  # lines: no=val
    legacy_solid_twins: list[str] = field(default_factory=list)  # lines: old=new
    run_settings: RunSettings = field(default_factory=RunSettings)
    last_output_bkwdata: str = ""
    last_output_report: str = ""
    updated_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json_dict(self) -> dict:
        d = asdict(self)
        d["mix"] = [asdict(x) for x in self.mix]
        return d

    @staticmethod
    def from_json_dict(d: dict) -> "BkwProject":
        p = BkwProject()
        p.version = int(d.get("version", 1))
        p.name = str(d.get("name", p.name))
        p.source_mode = str(d.get("source_mode", "import"))
        p.template = str(d.get("template", p.template))
        p.source_bkwdata = str(d.get("source_bkwdata", ""))
        p.mix_basis = str(d.get("mix_basis", p.mix_basis))
        p.mix = [MixItem(name=str(x.get("name", "")), value=float(x.get("value", 0.0))) for x in d.get("mix", [])]
        p.strict_elements = bool(d.get("strict_elements", False))
        p.add_gas_db = [str(x) for x in d.get("add_gas_db", [])]
        p.add_solid_db = [str(x) for x in d.get("add_solid_db", [])]
        p.add_gas_custom = [str(x) for x in d.get("add_gas_custom", [])]
        p.add_solid_custom = [str(x) for x in d.get("add_solid_custom", [])]
        p.legacy_ioeq = int(d["legacy_ioeq"]) if d.get("legacy_ioeq") is not None else None
        p.legacy_icjc = int(d["legacy_icjc"]) if d.get("legacy_icjc") is not None else None
        p.legacy_ihug = int(d["legacy_ihug"]) if d.get("legacy_ihug") is not None else None
        p.legacy_ipvc = int(d["legacy_ipvc"]) if d.get("legacy_ipvc") is not None else None
        p.legacy_igrp = int(d["legacy_igrp"]) if d.get("legacy_igrp") is not None else None
        p.legacy_eos_preset = str(d.get("legacy_eos_preset", "default"))
        p.legacy_athrho = str(d.get("legacy_athrho", ""))
        p.legacy_aispr = str(d.get("legacy_aispr", ""))
        p.legacy_constants = [str(x) for x in d.get("legacy_constants", [])]
        p.legacy_solid_twins = [str(x) for x in d.get("legacy_solid_twins", [])]
        rs = d.get("run_settings", {}) if isinstance(d.get("run_settings", {}), dict) else {}
        p.run_settings = RunSettings(
            mode=str(rs.get("mode", "bkw")),
            run_in_background=bool(rs.get("run_in_background", True)),
        )
        p.last_output_bkwdata = str(d.get("last_output_bkwdata", ""))
        p.last_output_report = str(d.get("last_output_report", ""))
        p.updated_utc = str(d.get("updated_utc", p.updated_utc))
        return p
