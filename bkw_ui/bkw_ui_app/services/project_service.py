from __future__ import annotations

import json
from pathlib import Path

from ..models import BkwProject


def save_project(path: str | Path, project: BkwProject) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(project.to_json_dict(), f, ensure_ascii=False, indent=2)


def load_project(path: str | Path) -> BkwProject:
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return BkwProject.from_json_dict(data)
