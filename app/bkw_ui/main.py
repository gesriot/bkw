from __future__ import annotations

import sys

from bkw_ui_app.app import run


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"--userbkw", "userbkw"}:
        from bkw_py.userbkw import main as userbkw_main

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return userbkw_main()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
