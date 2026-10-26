"""Code organisation inside each component (docs/adr/0008): layers, import direction, no cycles.

A component is a folder of layers (api, services, domain, ...). Each layer may import only the
layers listed for it, so the code stays easy to read, test and change. These tests read the source
with `ast`, so they need no running service. Each rule is proven able to fail on a small fake tree.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[2] / "services"


@dataclass(frozen=True)
class Layering:
    # The dotted package name: "ratel_link", or "app.bss_money" for a module inside the app.
    package: str
    # Modules at the package root: entry points and settings. Nothing else may live there.
    root_modules: frozenset[str]
    # Entry points may import any layer. Everything else is limited by `allowed`.
    entry_points: frozenset[str]
    # layer -> internal layers it may import. A layer may always import itself, and `config`
    # (when listed in `config_users`).
    allowed: dict[str, frozenset[str]]
    # layer -> third-party/top-level modules it must not import.
    banned_external: dict[str, frozenset[str]] = field(default_factory=dict)
    config_users: frozenset[str] = frozenset()
    # Files in `repositories/` that are separate layers: services may use the ports only.
    repository_modules: frozenset[str] = frozenset({"ports", "mongo", "voice_template"})

    @property
    def path(self) -> str:
        return self.package.replace(".", "/")


RATEL_LINK = Layering(
    package="ratel_link",
    root_modules=frozenset({"__init__", "main", "admin_cli", "config"}),
    entry_points=frozenset({"main", "admin_cli"}),
    allowed={
        "domain": frozenset(),
        "security": frozenset({"domain"}),
        "repositories.ports": frozenset({"domain"}),
        "repositories.mongo": frozenset({"domain", "repositories.ports"}),
        "repositories.voice_template": frozenset({"domain"}),
        "services": frozenset({"domain", "security", "repositories.ports"}),
        "api": frozenset({"services", "domain"}),
    },
    banned_external={
        "domain": frozenset(
            {"fastapi", "starlette", "pymongo", "bson", "cryptography", "sqlalchemy"}
        ),
        "security": frozenset({"fastapi", "starlette", "pymongo", "bson"}),
        "repositories.ports": frozenset(
            {"fastapi", "starlette", "pymongo", "bson", "cryptography"}
        ),
        "repositories.mongo": frozenset({"fastapi", "starlette", "cryptography"}),
        "repositories.voice_template": frozenset({"fastapi", "starlette", "cryptography"}),
        "services": frozenset({"fastapi", "starlette", "pymongo", "bson"}),
        "api": frozenset({"pymongo", "bson"}),
    },
    config_users=frozenset({"security", "repositories.mongo", "services"}),
)

# RatelBSS: money (docs/adr/0008, 0009). `api` joins the rules when the module gets routes.
BSS_MONEY = Layering(
    package="app.bss_money",
    root_modules=frozenset({"__init__", "check_cli", "voucher_cli"}),
    entry_points=frozenset({"check_cli", "voucher_cli"}),
    allowed={
        "domain": frozenset(),
        "models": frozenset(),
        "repositories.ports": frozenset({"domain"}),
        "repositories.sql": frozenset({"domain", "repositories.ports", "models"}),
        "services": frozenset({"domain", "repositories.ports"}),
    },
    banned_external={
        "domain": frozenset({"fastapi", "starlette", "sqlalchemy", "psycopg", "pymongo"}),
        "models": frozenset({"fastapi", "starlette", "pymongo"}),
        "repositories.ports": frozenset({"fastapi", "starlette", "sqlalchemy", "psycopg"}),
        "repositories.sql": frozenset({"fastapi", "starlette", "pymongo"}),
        "services": frozenset({"fastapi", "starlette", "sqlalchemy", "psycopg", "pymongo"}),
    },
    repository_modules=frozenset({"ports", "sql"}),
)

# Add a Layering here when another component gets layers (the other app modules, meter_agent).
LAYERINGS = [RATEL_LINK, BSS_MONEY]


def _module_name(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _layer_of(module: str, rules: Layering) -> str:
    """The layer a module belongs to: 'ratel_link.services.sim_keys' is 'services'.

    Modules at the package root are 'root' (entry points) or 'config'. In `repositories`, the ports
    and each implementation are separate layers, because services may use only the ports.
    """
    inside = module.removeprefix(rules.package).lstrip(".")
    parts = inside.split(".") if inside else []
    if len(parts) <= 1:
        return "config" if parts == ["config"] else "root"
    if parts[0] == "repositories" and parts[1] in rules.repository_modules:
        return f"repositories.{parts[1]}"
    return parts[0]


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found += [f"{node.module}.{a.name}" for a in node.names]
    return found


def layer_violations(root: Path, rules: Layering) -> list[str]:
    problems: list[str] = []
    for py in sorted((root / rules.path).rglob("*.py")):
        module = _module_name(py, root)
        layer = _layer_of(module, rules)
        if layer in ("root", "config"):
            continue  # entry points and settings may import any layer
        for imported in _imports(py):
            top = imported.split(".")[0]
            if top in rules.banned_external.get(layer, frozenset()):
                problems.append(f"{module} ({layer}) must not import {top}")
            if imported != rules.package and not imported.startswith(rules.package + "."):
                continue
            target = _layer_of(imported, rules)
            if target == layer:
                continue
            if target == "root":
                entry = imported.removeprefix(rules.package).lstrip(".").split(".")[0]
                if entry in rules.entry_points:
                    problems.append(f"{module} ({layer}) must not import the entry point {entry}")
            elif target == "config":
                if layer not in rules.config_users:
                    problems.append(f"{module} ({layer}) must not import config")
            elif target not in rules.allowed.get(layer, frozenset()):
                problems.append(f"{module} ({layer}) must not import {target} ({imported})")
    return problems


def root_violations(root: Path, rules: Layering) -> list[str]:
    """Only entry points and settings may sit at the package root."""
    names = {p.stem for p in (root / rules.path).glob("*.py")}
    return sorted(
        f"{rules.path}/{n}.py does not belong at the package root"
        for n in names - rules.root_modules
    )


def undocumented_packages(root: Path, rules: Layering) -> list[str]:
    problems = []
    for directory in sorted((root / rules.path).rglob("*")):
        if (
            not directory.is_dir()
            or directory.name == "__pycache__"
            or not list(directory.glob("*.py"))
        ):
            continue
        init = directory / "__init__.py"
        if not init.exists():
            problems.append(f"{directory.relative_to(root)} has no __init__.py")
        elif not ast.get_docstring(ast.parse(init.read_text())):
            where = directory.relative_to(root)
            problems.append(f"{where}/__init__.py has no docstring (say what the layer is for)")
    return problems


def import_cycles(root: Path, package: str) -> list[list[str]]:
    modules = {_module_name(p, root): p for p in (root / package.replace(".", "/")).rglob("*.py")}
    graph: dict[str, set[str]] = {m: set() for m in modules}
    for module, path in modules.items():
        for imported in _imports(path):
            if imported in modules and imported != module:
                graph[module].add(imported)
    cycles: list[list[str]] = []
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        for nxt in sorted(graph[node]):
            if state.get(nxt) == 1:
                cycles.append([*stack[stack.index(nxt) :], nxt] if nxt in stack else [node, nxt])
            elif nxt not in state:
                visit(nxt, [*stack, nxt])
        state[node] = 2

    for m in sorted(graph):
        if m not in state:
            visit(m, [m])
    return cycles


@pytest.mark.parametrize("rules", LAYERINGS, ids=lambda r: r.package)
def test_layers_only_import_what_they_are_allowed_to(rules: Layering) -> None:
    assert layer_violations(SERVICES, rules) == []


@pytest.mark.parametrize("rules", LAYERINGS, ids=lambda r: r.package)
def test_only_entry_points_and_settings_sit_at_the_package_root(rules: Layering) -> None:
    assert root_violations(SERVICES, rules) == []


@pytest.mark.parametrize("rules", LAYERINGS, ids=lambda r: r.package)
def test_every_layer_says_what_it_is_for(rules: Layering) -> None:
    assert undocumented_packages(SERVICES, rules) == []


@pytest.mark.parametrize("package", ["ratel_link", "app", "common", "meter_agent"])
def test_no_import_cycles(package: str) -> None:
    assert import_cycles(SERVICES, package) == []


# --- each rule can fail -------------------------------------------------------------------------


def _fake_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / "ratel_link" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_the_checker_flags_an_inward_layer_importing_outward(tmp_path: Path) -> None:
    root = _fake_tree(
        tmp_path,
        {
            "domain/x.py": "from ratel_link.services import y\n",
            "services/y.py": "",
            "services/__init__.py": "",
        },
    )
    assert any("domain" in p and "services" in p for p in layer_violations(root, RATEL_LINK))


def test_the_checker_flags_a_service_using_the_database_directly(tmp_path: Path) -> None:
    root = _fake_tree(
        tmp_path,
        {
            "services/y.py": "from ratel_link.repositories.mongo import open_database\n",
            "repositories/mongo.py": "",
        },
    )
    assert any(
        "services" in p and "repositories.mongo" in p for p in layer_violations(root, RATEL_LINK)
    )


def test_the_checker_flags_a_framework_in_the_domain(tmp_path: Path) -> None:
    root = _fake_tree(tmp_path, {"domain/x.py": "import fastapi\n"})
    assert any("must not import fastapi" in p for p in layer_violations(root, RATEL_LINK))


def test_the_checker_flags_the_domain_reading_settings(tmp_path: Path) -> None:
    root = _fake_tree(
        tmp_path, {"domain/x.py": "from ratel_link.config import Settings\n", "config.py": ""}
    )
    assert any("must not import config" in p for p in layer_violations(root, RATEL_LINK))


def test_the_checker_flags_a_layer_importing_an_entry_point(tmp_path: Path) -> None:
    root = _fake_tree(
        tmp_path, {"api/x.py": "from ratel_link.main import create_app\n", "main.py": ""}
    )
    assert layer_violations(root, RATEL_LINK)


def test_the_checker_flags_a_file_dumped_at_the_root(tmp_path: Path) -> None:
    root = _fake_tree(tmp_path, {"main.py": "", "helpers.py": ""})
    assert root_violations(root, RATEL_LINK) == [
        "ratel_link/helpers.py does not belong at the package root"
    ]


def test_the_checker_flags_a_package_with_no_explanation(tmp_path: Path) -> None:
    root = _fake_tree(tmp_path, {"api/x.py": "", "api/__init__.py": "", "domain/y.py": ""})
    problems = undocumented_packages(root, RATEL_LINK)
    assert any("api" in p and "docstring" in p for p in problems)
    assert any("domain" in p and "no __init__" in p for p in problems)


def test_the_checker_flags_an_import_cycle(tmp_path: Path) -> None:
    root = _fake_tree(
        tmp_path,
        {
            "domain/a.py": "from ratel_link.domain import b\n",
            "domain/b.py": "from ratel_link.domain import a\n",
        },
    )
    assert import_cycles(root, "ratel_link")


# --- the same rules for an app module (RatelBSS: money) can fail too ---------------------------


def _fake_money_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / "app" / "bss_money" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_money_flags_a_service_importing_sqlalchemy(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path, {"services/ledger.py": "from sqlalchemy.orm import Session\n"}
    )
    assert any("must not import sqlalchemy" in p for p in layer_violations(root, BSS_MONEY))


def test_money_flags_a_service_using_the_sql_repository_directly(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path,
        {
            "services/ledger.py": (
                "from app.bss_money.repositories.sql import SqlLedgerRepository\n"
            ),
            "repositories/sql.py": "",
        },
    )
    assert any(
        "services" in p and "repositories.sql" in p for p in layer_violations(root, BSS_MONEY)
    )


def test_money_flags_a_service_importing_the_tables(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path,
        {
            "services/ledger.py": "from app.bss_money.models.ledger import Wallet\n",
            "models/ledger.py": "",
        },
    )
    assert any("services" in p and "models" in p for p in layer_violations(root, BSS_MONEY))


def test_money_flags_the_domain_importing_outward(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path,
        {
            "domain/entries.py": "from app.bss_money.repositories import ports\n",
            "repositories/ports.py": "",
        },
    )
    assert any(
        "domain" in p and "repositories.ports" in p for p in layer_violations(root, BSS_MONEY)
    )


def test_money_flags_a_layer_importing_the_entry_point(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path,
        {"services/ledger.py": "from app.bss_money.check_cli import main\n", "check_cli.py": ""},
    )
    assert any("entry point" in p for p in layer_violations(root, BSS_MONEY))


def test_money_flags_a_file_dumped_at_the_root(tmp_path: Path) -> None:
    root = _fake_money_tree(tmp_path, {"__init__.py": "", "check_cli.py": "", "helpers.py": ""})
    assert root_violations(root, BSS_MONEY) == [
        "app/bss_money/helpers.py does not belong at the package root"
    ]


def test_money_flags_a_layer_with_no_explanation(tmp_path: Path) -> None:
    root = _fake_money_tree(tmp_path, {"services/ledger.py": "", "services/__init__.py": ""})
    assert any("services" in p and "docstring" in p for p in undocumented_packages(root, BSS_MONEY))


def test_money_allows_what_the_rules_permit(tmp_path: Path) -> None:
    root = _fake_money_tree(
        tmp_path,
        {
            "services/ledger.py": "from app.bss_money.repositories.ports import LedgerRepository\n"
            "from app.bss_money.domain.entries import Posting\n",
            "repositories/ports.py": "from app.bss_money.domain.entries import Posting\n",
            "repositories/sql.py": "from app.bss_money.models.ledger import Wallet\n"
            "from sqlalchemy import select\n",
            "domain/entries.py": "",
            "models/ledger.py": "",
        },
    )
    assert layer_violations(root, BSS_MONEY) == []
