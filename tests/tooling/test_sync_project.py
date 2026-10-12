"""scripts/github/sync_project.py turns labels and the first issue line into project fields."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sync", ROOT / "scripts/github/sync_project.py")
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

BODY = (
    "**Week:** 2 | **Target date:** 2026-10-14 | **Owner:** @someone | **Reviewers:** @a + @b\n"
    "**Source:** Build Plan\n\n## Objective\n**Week:** 9 appears again later and must be ignored."
)


def test_labels_and_header_line_become_fields() -> None:
    labels = ["type:feature", "area:ratel-link", "priority:p0", "risk:critical"]
    assert sync.fields_from_issue(labels, BODY) == {
        "Priority": "P0",
        "Risk": "Critical",
        "Workstream": "RatelLink",
        "Week": "Week 2",
        "Target Date": "2026-10-14",
    }


def test_issue_bodies_start_with_a_blank_line_on_github() -> None:
    assert sync.fields_from_issue([], "\n" + BODY)["Target Date"] == "2026-10-14"


def test_only_the_first_line_is_read_for_week_and_date() -> None:
    fields = sync.fields_from_issue([], BODY)
    assert fields["Week"] == "Week 2"


def test_missing_information_gives_no_field() -> None:
    assert sync.fields_from_issue(["type:bug"], "No header here") == {}
    assert sync.fields_from_issue([], "") == {}


def test_every_area_label_maps_to_a_workstream_the_project_has() -> None:
    project_script = (ROOT / "scripts/github/create_project.sh").read_text()
    for workstream in set(sync.WORKSTREAM.values()):
        assert workstream in project_script, workstream


def test_every_priority_and_risk_option_exists_in_the_project_script() -> None:
    project_script = (ROOT / "scripts/github/create_project.sh").read_text()
    for value in [*sync.PRIORITY.values(), *sync.RISK.values()]:
        assert value in project_script, value


def test_label_names_match_the_label_file() -> None:
    labels = (ROOT / ".github/labels.yml").read_text()
    for name in [*sync.PRIORITY, *sync.RISK, *sync.WORKSTREAM]:
        assert name in labels, name
