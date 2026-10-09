"""The Week 2 issue files become GitHub issues (scripts/github/create_issues.sh). They must follow
the label rules in docs/WORKFLOW.md, or the board and the review rules stop meaning anything."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ISSUES = sorted((ROOT / "docs" / "issues-week2").glob("W2-*.md"))
LABELS = {entry["name"] for entry in yaml.safe_load((ROOT / ".github" / "labels.yml").read_text())}
LOGIN = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def _labels(text: str) -> list[str]:
    line = next(ln for ln in text.splitlines() if ln.startswith("Labels:"))
    return [x.strip() for x in line.removeprefix("Labels:").split(",")]


def _field(text: str, name: str) -> str:
    match = re.search(rf"\*\*{name}:\*\* ([^|\n]*)", text)
    assert match, f"no **{name}:** field"
    return match.group(1).strip()


def test_there_are_issue_files() -> None:
    assert len(ISSUES) >= 17


@pytest.mark.parametrize("path", ISSUES, ids=lambda p: p.name[:5])
def test_header_is_what_the_seed_script_expects(path: Path) -> None:
    lines = path.read_text().splitlines()
    assert lines[0].startswith("# ") and len(lines[0]) > 10  # the title
    assert lines[1].startswith("Labels:")  # second line, read by create_issues.sh


@pytest.mark.parametrize("path", ISSUES, ids=lambda p: p.name[:5])
def test_labels_exist_and_follow_one_per_family(path: Path) -> None:
    labels = _labels(path.read_text())
    unknown = [x for x in labels if x not in LABELS]
    assert not unknown, f"labels not defined in .github/labels.yml: {unknown}"
    for family in ("type:", "priority:", "risk:"):
        assert len([x for x in labels if x.startswith(family)]) == 1, f"need exactly one {family}"
    assert any(x.startswith("area:") for x in labels), "need at least one area:"


@pytest.mark.parametrize("path", ISSUES, ids=lambda p: p.name[:5])
def test_owner_is_a_login_or_todo(path: Path) -> None:
    owner = _field(path.read_text(), "Owner")
    first = owner.split(" (")[0].split(" with ")[0].strip()
    assert first == "TODO" or LOGIN.match(first), f"owner {owner!r}"


@pytest.mark.parametrize("path", ISSUES, ids=lambda p: p.name[:5])
def test_critical_issues_name_two_reviewers(path: Path) -> None:
    text = path.read_text()
    if "risk:critical" not in _labels(text):
        return
    reviewers = re.search(r"\*\*Reviewers?:\*\* ([^\n]*)", text)
    assert reviewers, "no reviewer field"
    assert len(re.findall(r"@[A-Za-z0-9-]+", reviewers.group(1))) >= 2, (
        "critical needs two reviewers"
    )


@pytest.mark.parametrize("path", ISSUES, ids=lambda p: p.name[:5])
def test_the_author_of_an_issue_is_not_its_only_reviewer(path: Path) -> None:
    text = path.read_text()
    owner = re.findall(r"@[A-Za-z0-9-]+", _field(text, "Owner"))[:1]
    reviewers = re.search(r"\*\*Reviewers?:\*\* ([^\n]*)", text)
    assert reviewers
    others = [r for r in re.findall(r"@[A-Za-z0-9-]+", reviewers.group(1)) if r not in owner]
    assert others or not owner, "nobody but the owner is named as reviewer"
