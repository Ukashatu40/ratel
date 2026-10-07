"""Enforce the Build Plan's boundaries in code, not just in documents.

- RatelBSS (app) never touches the network or MongoDB. Only RatelLink uses the MongoDB driver.
- ratel_link and app never import each other. They meet only through the OpenAPI contract.
- common is a leaf: it imports nothing from the deployables.
- Money fields are never annotated float.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[2] / "services"

# deployable -> top-level modules it must not import
FORBIDDEN: dict[str, set[str]] = {
    "app": {"ratel_link", "meter_agent", "pymongo", "motor", "mongoengine"},
    "ratel_link": {"app", "meter_agent", "sqlalchemy", "alembic", "psycopg", "redis"},
    "meter_agent": {"app", "ratel_link", "pymongo", "motor", "sqlalchemy", "alembic"},
    "common": {"app", "ratel_link", "meter_agent", "pymongo", "sqlalchemy"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("deployable", sorted(FORBIDDEN))
def test_forbidden_imports(deployable: str) -> None:
    violations: list[str] = []
    for py in (SERVICES / deployable).rglob("*.py"):
        bad = _imports(py) & FORBIDDEN[deployable]
        if bad:
            violations.append(f"{py.relative_to(SERVICES)} imports {sorted(bad)}")
    assert not violations, "\n".join(violations)


def _annotation_mentions_float(node: ast.AST | None) -> bool:
    return node is not None and any(
        isinstance(n, ast.Name) and n.id == "float" for n in ast.walk(node)
    )


def test_no_float_money() -> None:
    violations: list[str] = []
    for py in SERVICES.rglob("*.py"):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id.endswith("_kobo")
                and _annotation_mentions_float(node.annotation)
            ):
                violations.append(f"{py.relative_to(SERVICES)}:{node.lineno} {node.target.id}")
            if isinstance(node, ast.arg) and node.arg.endswith("_kobo"):
                if _annotation_mentions_float(node.annotation):
                    violations.append(f"{py.relative_to(SERVICES)}:{node.lineno} arg {node.arg}")
    assert not violations, "money must be whole kobo (int): " + "; ".join(violations)


def test_boundary_checker_detects_a_violation(tmp_path: Path) -> None:
    bad = tmp_path / "x.py"
    bad.write_text("import pymongo\nfrom ratel_link import main\n")
    assert _imports(bad) == {"pymongo", "ratel_link"}


# Inside the single `app` process the modules still have a direction (docs/DEPENDENCIES.md):
# bss_money -> bss_lines and meter_api; bss_lines and meter_api import neither money nor each other.
APP_MODULE_FORBIDDEN: dict[str, set[str]] = {
    "bss_lines": {"app.bss_money", "app.meter_api"},
    "meter_api": {"app.bss_lines", "app.bss_money"},
}


def _dotted_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def _violates(imports: set[str], forbidden: set[str]) -> set[str]:
    return {i for i in imports for f in forbidden if i == f or i.startswith(f + ".")}


@pytest.mark.parametrize("module", sorted(APP_MODULE_FORBIDDEN))
def test_app_module_direction(module: str) -> None:
    violations: list[str] = []
    for py in (SERVICES / "app" / module).rglob("*.py"):
        bad = _violates(_dotted_imports(py), APP_MODULE_FORBIDDEN[module])
        if bad:
            violations.append(f"{py.relative_to(SERVICES)} imports {sorted(bad)}")
    assert not violations, "\n".join(violations)


def test_app_module_checker_detects_a_violation(tmp_path: Path) -> None:
    bad = tmp_path / "x.py"
    bad.write_text("from app.bss_money import rating\n")
    assert _violates(_dotted_imports(bad), APP_MODULE_FORBIDDEN["bss_lines"])


# Production code must not depend on test helpers or fakes (tests/ratel_link/fakes.py and friends).
def _imports_test_code(path: Path) -> bool:
    return "tests" in _imports(path)


def test_production_code_does_not_import_test_code() -> None:
    violations = [
        str(py.relative_to(SERVICES)) for py in SERVICES.rglob("*.py") if _imports_test_code(py)
    ]
    assert not violations, "services/ imports tests/: " + ", ".join(violations)


def test_test_code_import_checker_detects_a_violation(tmp_path: Path) -> None:
    bad = tmp_path / "x.py"
    bad.write_text("from tests.ratel_link.fakes import InMemorySimKeyRepository\n")
    assert _imports_test_code(bad)
    ok = tmp_path / "y.py"
    ok.write_text("from ratel_link.sim_keys import SimKeyStore\n")
    assert not _imports_test_code(ok)
