import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts/ci/critical_review_gate.py")
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

HEAD = "sha-new"
CRIT = ["services/ratel_link/main.py"]
PREFIXES = ["services/ratel_link/", "services/app/bss_money/"]


def review(
    user: str, state: str = "APPROVED", sha: str = HEAD, at: str = "2026-10-06T10:00:00Z"
) -> dict[str, Any]:
    return {"user": {"login": user}, "state": state, "commit_id": sha, "submitted_at": at}


def run(
    files: list[str],
    reviews: list[dict[str, Any]],
    required: list[str] | None = None,
    author: str = "dev",
) -> tuple[bool, str]:
    return gate.evaluate(files, reviews, HEAD, author, PREFIXES, required or [])


def test_non_critical_change_passes_without_reviews() -> None:
    assert run(["docs/x.md"], [])[0]


def test_critical_change_needs_two_approvals() -> None:
    assert not run(CRIT, [])[0]
    assert not run(CRIT, [review("a")])[0]
    assert run(CRIT, [review("a"), review("b")])[0]


def test_same_person_twice_counts_once() -> None:
    assert not run(CRIT, [review("a", at="1"), review("a", at="2")])[0]


def test_author_cannot_approve_own_change() -> None:
    assert not run(CRIT, [review("dev"), review("a")])[0]


def test_stale_approval_on_old_commit_does_not_count() -> None:
    assert not run(CRIT, [review("a", sha="sha-old"), review("b")])[0]


def test_later_changes_requested_cancels_earlier_approval() -> None:
    reviews = [review("a", at="1"), review("a", "CHANGES_REQUESTED", at="2"), review("b")]
    assert not run(CRIT, reviews)[0]


def test_comment_does_not_cancel_approval() -> None:
    reviews = [review("a", at="1"), review("a", "COMMENTED", at="2"), review("b")]
    assert run(CRIT, reviews)[0]


def test_named_required_reviewer_must_approve() -> None:
    reviews = [review("a"), review("b")]
    ok, msg = run(CRIT, reviews, required=["lead"])
    assert not ok and "lead" in msg
    assert run(CRIT, [*reviews, review("lead")], required=["lead"])[0]


def test_author_on_required_list_is_skipped() -> None:
    assert run(CRIT, [review("a"), review("b")], required=["dev"], author="dev")[0]


def test_money_module_is_critical() -> None:
    assert not run(["services/app/bss_money/rating.py"], [review("a")])[0]


def test_main_wires_api_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Independent of the repository's real reviewer list, which names real people.
    lists = {"critical-paths.txt": ["services/ratel_link/"], "critical-reviewers.txt": []}
    monkeypatch.setattr(gate, "read_list", lambda path: lists[path.name])
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7}}))

    def fake(url: str) -> Any:
        if url.endswith("/pulls/7"):
            return {"head": {"sha": HEAD}, "user": {"login": "dev"}}
        if "/files" in url:
            return [{"filename": "services/ratel_link/main.py"}]
        return [review("a"), review("b")]

    assert gate.main(fake, str(event)) == 0

    def fake_one(url: str) -> Any:
        return fake(url) if "/reviews" not in url else [review("a")]

    assert gate.main(fake_one, str(event)) == 1


def test_non_pr_event_passes(tmp_path: Path) -> None:
    event = tmp_path / "e.json"
    event.write_text("{}")
    assert gate.main(lambda _u: [], str(event)) == 0
