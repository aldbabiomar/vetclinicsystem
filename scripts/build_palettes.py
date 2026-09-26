#!/usr/bin/env python3
"""
Write vcs/static/palettes.css from vcs/web/palettes.py.

    /tmp/vcs_test_venv_jo/bin/python scripts/build_palettes.py          # write
    /tmp/vcs_test_venv_jo/bin/python scripts/build_palettes.py --check  # differ? exit 1

tests/test_palettes.py fails while the file and the registry disagree, so a
palette is changed in the registry and this is run -- never the CSS by hand.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vcs.web import palettes  # noqa: E402

TARGET = ROOT / "vcs" / "static" / "palettes.css"


def main():
    css = palettes.css()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != css:
            print(f"{TARGET.relative_to(ROOT)} is out of date: run scripts/build_palettes.py")
            return 1
        print("palettes.css is up to date")
        return 0
    TARGET.write_text(css, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(palettes.PALETTES)} palettes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
