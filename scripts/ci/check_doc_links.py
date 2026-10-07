#!/usr/bin/env python3
"""Fail on broken relative links in Markdown files. External URLs are not fetched."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def main() -> int:
    broken: list[str] = []
    checked = 0
    for md in sorted(ROOT.rglob("*.md")):
        if set(md.relative_to(ROOT).parts) & SKIP:
            continue
        text = FENCE.sub("", md.read_text())
        for target in LINK.findall(text):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            checked += 1
            resolved = (ROOT / path.lstrip("/")) if path.startswith("/") else (md.parent / path)
            if not resolved.exists():
                broken.append(f"{md.relative_to(ROOT)}: {target}")
    for b in broken:
        sys.stderr.write(f"BROKEN LINK {b}\n")
    sys.stdout.write(f"Checked {checked} relative links, {len(broken)} broken.\n")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
