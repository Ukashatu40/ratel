"""A line's state changes only through the state machine (Build Plan, RatelBSS: lines; M-14).

Every place in `app/bss_lines` that writes a **line's** state must first ask `validate_transition`
whether the move is allowed, in the same function. Four ways of writing a line's state are
recognised: assigning `line.state`, `setattr(line, "state", ...)`, `.values(state=...)`, and a
bulk `update(Line)` or a raw `UPDATE line` statement (those two can never be checked, so they are
always refused).

Assignments to `.state` on any other object (a SIM's `.state`, a Number's `.state`) are not the
line state machine's business and are not flagged. See `_state_writes` for the receiver check.

The test reads the source with `ast`, so it needs no running service, and each rule is proven able
to fail on a small fake tree.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2] / "services"
PACKAGE = "app/bss_lines"
GUARD = "validate_transition"
RAW_UPDATE = re.compile(r"\bupdate\s+\"?line\"?\b", re.IGNORECASE)


def _calls(node: ast.AST, name: str) -> list[int]:
    """Line numbers of calls to `name` anywhere under `node`."""
    found = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if called == name:
                found.append(child.lineno)
    return found


def _state_writes(node: ast.AST) -> list[tuple[int, str]]:
    """(line, how) for every way `node` writes a **line's** state.

    Only attributes on an object named `line` count. A SIM's or a Number's `.state` is a
    different field on a different table, and is not the line state machine's business.
    `.values(state=...)` is flagged regardless of receiver, because it is the shape SQLAlchemy
    uses for a bulk update and the checker cannot tell which table it targets.
    """
    writes: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "state"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "line"
                ):
                    writes.append((child.lineno, "assigns line.state"))
        elif isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id == "setattr" and len(child.args) >= 2:
                obj = child.args[0]
                key = child.args[1]
                if (
                    isinstance(obj, ast.Name)
                    and obj.id == "line"
                    and isinstance(key, ast.Constant)
                    and key.value == "state"
                ):
                    writes.append((child.lineno, "calls setattr(line, 'state', ...)"))
            if isinstance(func, ast.Attribute) and func.attr == "values":
                names = {kw.arg for kw in child.keywords}
                keys = {
                    k.value
                    for arg in child.args
                    if isinstance(arg, ast.Dict)
                    for k in arg.keys
                    if isinstance(k, ast.Constant)
                }
                if "state" in names or "state" in keys:
                    writes.append((child.lineno, "sets state with .values(...)"))
    return writes


def _never_allowed(tree: ast.AST) -> list[tuple[int, str]]:
    """Writes the guard cannot vouch for: a bulk update of Line, or a raw UPDATE of `line`."""
    found: list[tuple[int, str]] = []
    for child in ast.walk(tree):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id == "update" and child.args:
                first = child.args[0]
                if isinstance(first, ast.Name) and first.id == "Line":
                    found.append((child.lineno, "bulk update(Line)"))
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if RAW_UPDATE.search(child.value):
                found.append((child.lineno, "raw UPDATE of the line table"))
    return found


def line_state_violations(root: Path, package: str = PACKAGE) -> list[str]:
    problems: list[str] = []
    for path in sorted((root / package).rglob("*.py")):
        tree = ast.parse(path.read_text())
        where = path.relative_to(root)
        for lineno, how in _never_allowed(tree):
            problems.append(
                f"{where}:{lineno} {how}: change a line's state through the state machine"
            )
        functions = [
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        inside: set[int] = set()
        for function in functions:
            guards = _calls(function, GUARD)
            for lineno, how in _state_writes(function):
                inside.add(lineno)
                if not any(g < lineno for g in guards):
                    problems.append(f"{where}:{lineno} {how} without calling {GUARD} first")
        for lineno, how in _state_writes(tree):
            if lineno not in inside:
                problems.append(
                    f"{where}:{lineno} {how} outside any function, so it cannot be guarded"
                )
    return problems


def test_a_lines_state_changes_only_after_the_state_machine_allows_it() -> None:
    assert line_state_violations(SERVICES) == []


# --- each rule can fail ---------------------------------------------------------------------------


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / "app" / "bss_lines" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_a_write_after_the_guard_is_allowed(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "services/ok.py": (
                "def go(line):\n    t = validate_transition(a, b)\n    line.state = t\n"
            ),
        },
    )
    assert line_state_violations(root) == []


def test_a_write_with_no_guard_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"services/bad.py": "def go(line):\n    line.state = 'active'\n"})
    assert any(
        "assigns line.state without calling validate_transition" in p
        for p in line_state_violations(root)
    )


def test_a_write_before_the_guard_is_flagged(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {"services/bad.py": "def go(line):\n    line.state = 'x'\n    validate_transition(a, b)\n"},
    )
    assert line_state_violations(root)


def test_the_guard_in_another_function_does_not_count(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "services/bad.py": "def check():\n    validate_transition(a, b)\n\n"
            "def go(line):\n    line.state = 'x'\n"
        },
    )
    assert line_state_violations(root)


def test_setattr_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"services/bad.py": "def go(line):\n    setattr(line, 'state', 'x')\n"})
    assert any("setattr" in p for p in line_state_violations(root))


def test_values_with_a_state_is_flagged(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "repositories/bad.py": "def go(s):\n    s.execute(stmt.values(state='x'))\n",
            "repositories/bad2.py": "def go(s):\n    s.execute(stmt.values({'state': 'x'}))\n",
        },
    )
    assert len(line_state_violations(root)) == 2


def test_a_bulk_update_of_line_is_always_refused(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "repositories/bad.py": (
                "def go(s):\n    validate_transition(a, b)\n    s.execute(update(Line))\n"
            )
        },
    )
    assert any("bulk update(Line)" in p for p in line_state_violations(root))


def test_a_raw_update_of_the_line_table_is_always_refused(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "repositories/bad.py": (
                "def go(s):\n    validate_transition(a, b)\n"
                "    s.execute(text('UPDATE line SET x = 1'))\n"
            )
        },
    )
    assert any("raw UPDATE" in p for p in line_state_violations(root))


def test_a_write_outside_any_function_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"services/bad.py": "line.state = 'x'\n"})
    assert any("outside any function" in p for p in line_state_violations(root))


def test_other_tables_state_columns_are_not_mistaken_for_a_write(tmp_path: Path) -> None:
    # A column declaration is not an assignment to an attribute.
    root = _tree(
        tmp_path, {"models/ok.py": "class Sim:\n    state: str = mapped_column(String(20))\n"}
    )
    assert line_state_violations(root) == []


def test_a_sims_state_assignment_is_not_a_line_write(tmp_path: Path) -> None:
    # The checker flags line.state, not any .state. Setting a SIM's state is a different
    # field on a different table, and is not the line state machine's business.
    root = _tree(
        tmp_path,
        {"repositories/ok.py": ("def retire(sim):\n    sim.state = 'retired'\n")},
    )
    assert line_state_violations(root) == []
