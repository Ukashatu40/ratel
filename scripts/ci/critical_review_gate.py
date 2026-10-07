#!/usr/bin/env python3
"""Require two distinct approvals on pull requests that touch critical paths.

Why this exists: GitHub branch rules can require N approvals on the whole branch, but not "2 for
these paths, 1 for the rest", and CODEOWNERS accepts ANY ONE listed owner. The Build Plan wants
two reviewers for RatelLink and RatelBSS: money only.

Counted approvals: latest review per person, state APPROVED, made on the current head commit,
author excluded. Anything that is not a pull request event passes trivially.
No third-party dependencies, so it runs on a bare runner.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_APPROVALS = 2


def read_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = (ln.strip() for ln in path.read_text().splitlines())
    return [ln for ln in lines if ln and not ln.startswith("#")]


def touches_critical(changed_files: list[str], prefixes: list[str]) -> list[str]:
    return sorted(f for f in changed_files if any(f.startswith(p) for p in prefixes))


def current_approvers(reviews: list[dict[str, Any]], head_sha: str, author: str) -> set[str]:
    latest: dict[str, dict[str, Any]] = {}
    for r in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        user = (r.get("user") or {}).get("login")
        if not user or r.get("state") == "COMMENTED":
            continue  # a comment never changes someone's approve/request-changes standing
        latest[user] = r
    return {
        u
        for u, r in latest.items()
        if r.get("state") == "APPROVED" and r.get("commit_id") == head_sha and u != author
    }


def evaluate(
    changed_files: list[str],
    reviews: list[dict[str, Any]],
    head_sha: str,
    author: str,
    prefixes: list[str],
    required_reviewers: list[str],
) -> tuple[bool, str]:
    critical = touches_critical(changed_files, prefixes)
    if not critical:
        return True, "No critical paths touched. One reviewer rule applies (branch rules)."
    approvers = current_approvers(reviews, head_sha, author)
    problems = []
    if len(approvers) < REQUIRED_APPROVALS:
        problems.append(
            f"needs {REQUIRED_APPROVALS} distinct approvals on the latest commit, "
            f"has {len(approvers)}"
        )
    missing = sorted(r for r in required_reviewers if r != author and r not in approvers)
    if missing:
        problems.append("still needs approval from: " + ", ".join(missing))
    shown = ", ".join(critical[:5]) + (" ..." if len(critical) > 5 else "")
    if problems:
        return False, f"Critical change ({shown}): " + "; ".join(problems)
    return True, f"Critical change ({shown}): approved by {', '.join(sorted(approvers))}"


Fetch = Callable[[str], Any]


def _github_fetch(url: str) -> Any:
    req = urllib.request.Request(  # noqa: S310 (fixed https GitHub API host)
        url,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.load(resp)


def _paged(fetch: Fetch, url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = fetch(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        items += batch
        if len(batch) < 100:
            return items
        page += 1


def main(fetch: Fetch = _github_fetch, event_path: str | None = None) -> int:
    event_file = event_path or os.environ.get("GITHUB_EVENT_PATH", "")
    event = json.loads(Path(event_file).read_text()) if event_file else {}
    pr = event.get("pull_request")
    if not pr:
        sys.stdout.write("Not a pull request event: nothing to gate.\n")
        return 0
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    base = f"https://api.github.com/repos/{repo}/pulls/{pr['number']}"
    current = fetch(base)  # fresh head sha and author, not the possibly stale event payload
    files = [f["filename"] for f in _paged(fetch, f"{base}/files")]
    reviews = _paged(fetch, f"{base}/reviews")
    ok, message = evaluate(
        files,
        reviews,
        current["head"]["sha"],
        current["user"]["login"],
        read_list(ROOT / ".github" / "critical-paths.txt"),
        read_list(ROOT / ".github" / "critical-reviewers.txt"),
    )
    sys.stdout.write(message + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
