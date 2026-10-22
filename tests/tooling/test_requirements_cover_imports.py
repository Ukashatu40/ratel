"""Every third-party package a deployable imports is in its requirements file.

A missing line here only shows up when the service is installed on a clean host, which is the worst
moment to learn it (the meter agent could not be installed from requirements/agent.txt for exactly
this reason). Scans the service's own folder; the shared `common` package is covered by the
container install run described in deploy/*/README.md.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
# deployable folder -> its requirements file
DEPLOYABLES = {
    "meter_agent": "agent.txt",
    "ratel_link": "link.txt",
}
# import name -> package name, where they differ
PACKAGE_OF = {
    "pydantic_settings": "pydantic-settings",
    "bson": "pymongo",  # shipped inside pymongo
    "starlette": "fastapi",  # installed by, and versioned with, fastapi
}
OWN = {"meter_agent", "ratel_link", "common", "app", "services"}


def _requirements(name: str) -> set[str]:
    found: set[str] = set()
    for line in (ROOT / "requirements" / name).read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("-r"):
            found |= _requirements(line.removeprefix("-r").strip())
        else:
            found.add(re.split(r"[<>=!~\[ ;]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return found


def _imports(folder: Path) -> set[str]:
    names: set[str] = set()
    for path in folder.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(("folder", "requirements"), DEPLOYABLES.items())
def test_everything_the_service_imports_is_in_its_requirements(
    folder: str, requirements: str
) -> None:
    third_party = {n for n in _imports(SERVICES / folder) if n not in sys.stdlib_module_names}
    needed = {PACKAGE_OF.get(n, n).lower().replace("_", "-") for n in third_party - OWN}
    missing = needed - _requirements(requirements)
    assert missing == set(), f"add to requirements/{requirements}: {sorted(missing)}"
