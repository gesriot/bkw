from __future__ import annotations

import sys
from pathlib import Path

from bkw_py.ui.userbkw import run_cli


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
