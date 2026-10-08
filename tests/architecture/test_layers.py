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


RATEL_LINK = Layering(
    package="ratel_link",
    root_modules=frozenset({"__init__", "main", "admin_cli", "config"}),
    entry_points=frozenset({"main", "admin_cli"}),
    allowed={
        "domain": frozenset(),
        "security": frozenset({"domain"}),
        "repositories.ports": frozenset({"domain"}),
        "repositories.mongo": frozenset({"domain", "repositories.ports"}),
        "services": frozenset({"domain", "security", "repositories.ports"}),
        "api": frozenset({"services", "domain"}),
    },
    banned_external={
        "domain": frozenset({"fastapi", "starlette", "pymongo", "cryptography", "sqlalchemy"}),
        "security": frozenset({"fastapi", "starlette", "pymongo"}),
        "repositories.ports": frozenset({"fastapi", "starlette", "pymongo", "cryptography"}),
        "repositories.mongo": frozenset({"fastapi", "starlette", "cryptography"}),
        "services": frozenset({"fastapi", "starlette", "pymongo"}),
        "api": frozenset({"pymongo"}),
    },
    config_users=frozenset({"security", "repositories.mongo", "services"}),
)

# Add a Layering here when another component gets layers (app modules, meter_agent).
LAYERINGS = [RATEL_LINK]


def _module_name(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _layer_of(module: str) -> str:
    """The layer a module belongs to: 'ratel_link.services.sim_keys' is 'services'.

    Modules at the package root are 'root' (entry points) or 'config'. In `repositories`, the ports
    and the MongoDB code are separate layers, because services may use only the ports.
    """
    parts = module.split(".")[1:]  # drop the package name
    if len(parts) <= 1:
        return "config" if parts == ["config"] else "root"
    if parts[0] == "repositories" and parts[1] in ("ports", "mongo"):
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
    for py in sorted((root / rules.package).rglob("*.py")):
        module = _module_name(py, root)
        layer = _layer_of(module)
        if layer in ("root", "config"):
            continue  # entry points and settings may import any layer
        for imported in _imports(py):
            top = imported.split(".")[0]
            if top in rules.banned_external.get(layer, frozenset()):
                problems.append(f"{module} ({layer}) must not import {top}")
            if top != rules.package:
                continue
            target = _layer_of(imported)
            if target == layer:
                continue
            if target == "root":
                entry = imported.split(".")[1] if "." in imported else ""
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
    names = {p.stem for p in (root / rules.package).glob("*.py")}
    return sorted(
        f"{rules.package}/{n}.py does not belong at the package root"
        for n in names - rules.root_modules
    )


def undocumented_packages(root: Path, rules: Layering) -> list[str]:
    problems = []
    for directory in sorted((root / rules.package).rglob("*")):
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
    modules = {_module_name(p, root): p for p in (root / package).rglob("*.py")}
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
