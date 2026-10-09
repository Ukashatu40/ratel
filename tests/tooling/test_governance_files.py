"""CODEOWNERS and the critical-review lists must agree, and must not make a PR unmergeable.

GitHub counts one approval from any listed owner per changed file and never counts the author's
own. A path with a single owner therefore blocks every PR that owner writes, and the main ruleset
has no bypass actors. These tests keep that, and the link to the two-reviewer gate, checkable.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITHUB = ROOT / ".github"
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def _lines(path: Path) -> list[str]:
    text = path.read_text().splitlines()
    return [ln.strip() for ln in text if ln.strip() and not ln.strip().startswith("#")]


def _rules() -> list[tuple[str, list[str]]]:
    rules = []
    for ln in _lines(GITHUB / "CODEOWNERS"):
        pattern, *owners = ln.split()
        rules.append((pattern, [o.removeprefix("@") for o in owners]))
    return rules


def _owners_of(path: str) -> list[str]:
    """Owners of a repository path: the last matching rule wins (prefix rules are enough here)."""
    found: list[str] = []
    for pattern, owners in _rules():
        if pattern == "*" or path.startswith(pattern.lstrip("/")):
            found = owners
    return found


def test_codeowners_has_rules_with_real_usernames() -> None:
    rules = _rules()
    assert rules, "CODEOWNERS has no active rules"
    for pattern, owners in rules:
        assert owners, f"{pattern} has no owner"
        for owner in owners:
            assert LOGIN.match(owner), f"{pattern}: {owner!r} is not a GitHub username"
            assert "TODO" not in owner.upper()


def test_every_rule_has_two_distinct_owners_so_the_author_can_always_be_replaced() -> None:
    single = [f"{p}: {o}" for p, o in _rules() if len(set(o)) < 2]
    assert not single, "paths whose only owner cannot approve their own PR: " + "; ".join(single)


def test_critical_reviewers_are_real_and_are_code_owners_of_every_critical_path() -> None:
    reviewers = _lines(GITHUB / "critical-reviewers.txt")
    assert len(reviewers) >= 2, "name the project lead and the independent reviewer"
    assert all(LOGIN.match(r) for r in reviewers)
    for prefix in _lines(GITHUB / "critical-paths.txt"):
        owners = _owners_of(prefix + "x")
        missing = [r for r in reviewers if r not in owners]
        assert not missing, f"{prefix}: required reviewers {missing} are not code owners there"


def test_the_governance_files_are_reviewed_by_the_independent_reviewer() -> None:
    reviewers = _lines(GITHUB / "critical-reviewers.txt")
    for guarded in (
        ".github/critical-paths.txt",
        ".github/critical-reviewers.txt",
        ".github/workflows/critical-review-gate.yml",
        "scripts/ci/critical_review_gate.py",
    ):
        assert set(reviewers) <= set(_owners_of(guarded)), guarded


def test_the_owner_lookup_follows_last_match_wins() -> None:
    assert _owners_of("README.md") == _owners_of("anything/else.txt")
    assert _owners_of("services/ratel_link/auth.py") != _owners_of("README.md")
    # The more specific rule for the gate files overrides the general /.github/ rule.
    assert _owners_of(".github/workflows/ci.yml") != _owners_of(".github/critical-reviewers.txt")
