#!/usr/bin/env python3
"""Put the repository's open issues on the GitHub Project and fill in its fields.

For every open issue: adds it to the project, then sets Priority, Risk, Workstream and Week from
the issue's labels and its first line, and Target Date from that same line. It never creates or
deletes anything, never changes an issue, and setting a field twice is harmless, so it can be run
again whenever issues are added.

By default it only prints what it would do. Add --apply to do it.

Usage: sync_project.py <owner> <project-number> [--repo OWNER/REPO] [--apply]
Needs `gh` logged in with the `project` scope (gh auth refresh -s project).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

PRIORITY = {"priority:p0": "P0", "priority:p1": "P1", "priority:p2": "P2", "priority:p3": "P3"}
RISK = {
    "risk:critical": "Critical",
    "risk:high": "High",
    "risk:medium": "Medium",
    "risk:low": "Low",
}
WORKSTREAM = {
    "area:contracts": "Contracts",
    "area:ratel-link": "RatelLink",
    "area:ratel-meter": "RatelMeter",
    "area:bss-lines": "BSS Lines",
    "area:bss-money": "BSS Money",
    "area:ratel-desk": "RatelDesk",
    "area:ratel-pay": "RatelPay",
    "area:network": "Cross-cutting",
    "area:ops": "Cross-cutting",
    "area:deployment": "Cross-cutting",
    "area:repository": "Cross-cutting",
}
WEEK_LINE = re.compile(r"\*\*Week:\*\*\s*(\d+)")
DATE_LINE = re.compile(r"\*\*Target date:\*\*\s*(\d{4}-\d{2}-\d{2})")


def fields_from_issue(labels: list[str], body: str) -> dict[str, str]:
    """The project field values an issue implies. Only fields it actually says something about."""
    first_line = next((line for line in body.splitlines() if line.strip()), "")
    out: dict[str, str] = {}
    for field, mapping in (("Priority", PRIORITY), ("Risk", RISK), ("Workstream", WORKSTREAM)):
        for label in labels:
            if label in mapping:
                out[field] = mapping[label]
                break
    if week := WEEK_LINE.search(first_line):
        out["Week"] = f"Week {week.group(1)}"
    if date := DATE_LINE.search(first_line):
        out["Target Date"] = date.group(1)
    return out


def say(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def gh(*args: str) -> Any:
    # Fixed program name and an argument list, no shell: nothing is interpreted as a command.
    done = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        sys.exit(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return json.loads(done.stdout) if done.stdout.strip() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("owner")
    parser.add_argument("number")
    parser.add_argument("--repo", help="OWNER/REPO (default: the repository of the current folder)")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: preview)")
    args = parser.parse_args()

    repo = args.repo or gh("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]
    project = gh("project", "view", args.number, "--owner", args.owner, "--format", "json")
    fields = {
        f["name"]: f
        for f in gh(
            "project", "field-list", args.number, "--owner", args.owner, "--format", "json"
        )["fields"]
    }
    issues = gh(
        "issue", "list", "-R", repo, "--state", "open", "--limit", "200",
        "--json", "number,url,title,labels,body",
    )  # fmt: skip
    mode = "APPLY" if args.apply else "PREVIEW (nothing is changed; add --apply)"
    say(f"{mode}: project #{args.number} '{project['title']}', {len(issues)} open issues\n")

    problems = 0
    for issue in sorted(issues, key=lambda i: i["number"]):
        wanted = fields_from_issue([label["name"] for label in issue["labels"]], issue["body"])
        say(f"#{issue['number']} {issue['title'][:60]}")
        item_id = None
        if args.apply:
            item_id = gh(
                "project", "item-add", args.number, "--owner", args.owner,
                "--url", issue["url"], "--format", "json",
            )["id"]  # fmt: skip
        for name, value in wanted.items():
            field = fields.get(name)
            if field is None:
                say(f"    ! project has no field '{name}' (skipped)")
                problems += 1
                continue
            command = ["project", "item-edit", "--id", item_id or "ITEM", "--project-id"]
            command += [project["id"], "--field-id", field["id"]]
            if field["type"] == "ProjectV2SingleSelectField":
                option = next((o for o in field["options"] if o["name"] == value), None)
                if option is None:
                    say(f"    ! field '{name}' has no option '{value}' (skipped)")
                    problems += 1
                    continue
                command += ["--single-select-option-id", option["id"]]
            else:
                command += ["--date", value]
            if args.apply:
                gh(*command)
            say(f"    {name} = {value}")
    say(f"\n{'Done' if args.apply else 'Preview only'}. Problems: {problems}.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
