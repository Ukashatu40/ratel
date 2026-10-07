#!/usr/bin/env python3
"""Parse every YAML, TOML and JSON file in the repo so a typo fails CI, not a deploy."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def files(*suffixes: str) -> list[Path]:
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file() and p.suffix in suffixes and not (set(p.relative_to(ROOT).parts) & SKIP)
    )


def main() -> int:
    errors: list[str] = []
    count = 0
    for p in files(".yml", ".yaml"):
        count += 1
        try:
            list(yaml.safe_load_all(p.read_text()))
        except yaml.YAMLError as e:
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    for p in files(".toml"):
        count += 1
        try:
            tomllib.loads(p.read_text())
        except tomllib.TOMLDecodeError as e:
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    for p in files(".json"):
        count += 1
        try:
            json.loads(p.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    for e in errors:
        sys.stderr.write(f"INVALID {e}\n")
    sys.stdout.write(f"Parsed {count} config files, {len(errors)} invalid.\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
