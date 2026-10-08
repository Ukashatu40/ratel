"""Key administration: create, rotate, revoke, disable, expiry warnings."""

import json
import logging
from datetime import timedelta

import pytest

from ratel_link.security.api_key_tokens import hash_secret
from ratel_link.services.api_key_admin import (
    ApiKeyError,
    KeyPolicy,
    create_system,
    disable,
    find_expiring,
    log_expiring,
    revoke,
    rotate,
)
from ratel_link.services.authentication import ApiPrincipal, Rejected, RejectReason
from tests.ratel_link.helpers import POLICY, authenticate_with, register_system, setup_repo


def test_only_the_hash_is_stored() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    secret = token.split(".", 1)[1]
    stored = json.dumps(repo.documents, default=str)
    assert token not in stored
    assert secret not in stored
    gen = repo.documents["bss-app"]["generations"][0]
    assert gen["secret_hash"] == hash_secret(secret)
    assert set(repo.documents["bss-app"]) == {
        "api_key_id",
        "system_name",
        "status",
        "generations",
        "created_at",
    }
    assert set(gen) == {"generation", "secret_hash", "created_at", "expires_at", "revoked_at"}


def test_records_do_not_show_their_hash_in_repr() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].secret_hash not in repr(record)


def test_first_key_expires_in_ninety_days() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    record = repo.get("bss-app")
    assert record is not None
    gen = record.generations[0]
    assert gen.expires_at == clock() + timedelta(days=90)
    assert gen.created_at == clock()
    assert record.status == "active"


@pytest.mark.parametrize("days", [91, 365, 0, -1])
def test_creation_beyond_the_cap_is_refused(days: int) -> None:
    repo, clock = setup_repo()
    with pytest.raises(ApiKeyError, match="90 days"):
        create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy(max_age_days=days))
    assert repo.documents == {}


def test_a_shorter_lifetime_is_allowed() -> None:
    repo, clock = setup_repo()
    create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy(max_age_days=30))
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].expires_at == clock() + timedelta(days=30)


@pytest.mark.parametrize(
    "bad", ["", "ab", "Bss-app", "1bss", "bss_app", "bss app", "a" * 33, "bss.app"]
)
def test_bad_api_key_id_is_refused(bad: str) -> None:
    repo, clock = setup_repo()
    with pytest.raises(ApiKeyError, match="api_key_id must be"):
        create_system(repo, bad, "RatelBSS", clock(), POLICY)


@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_bad_system_name_is_refused(name: str) -> None:
    repo, clock = setup_repo()
    with pytest.raises(ApiKeyError, match="system name"):
        create_system(repo, "bss-app", name, clock(), POLICY)


def test_duplicate_system_is_refused_and_changes_nothing() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    before = json.dumps(repo.documents, default=str)
    with pytest.raises(ApiKeyError, match="already exists"):
        register_system(repo, clock)
    assert json.dumps(repo.documents, default=str) == before


def test_both_keys_work_during_the_overlap_then_the_old_one_stops() -> None:
    repo, clock = setup_repo()
    old = register_system(repo, clock)
    clock.advance(days=60)
    new = rotate(repo, "bss-app", clock(), POLICY)
    assert authenticate_with(old, repo, clock) == ApiPrincipal("bss-app", 1)
    assert authenticate_with(new, repo, clock) == ApiPrincipal("bss-app", 2)
    clock.advance(days=6, seconds=86399)  # still inside the 7-day overlap
    assert isinstance(authenticate_with(old, repo, clock), ApiPrincipal)
    clock.advance(seconds=1)
    assert authenticate_with(old, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")
    assert authenticate_with(new, repo, clock) == ApiPrincipal("bss-app", 2)


def test_rotation_never_extends_the_old_key() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    clock.advance(days=88)  # the old key has 2 days left, less than the 7-day overlap
    rotate(repo, "bss-app", clock(), POLICY)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].expires_at == clock() - timedelta(days=88) + timedelta(days=90)


def test_new_key_gets_a_full_ninety_days() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    clock.advance(days=80)
    rotate(repo, "bss-app", clock(), POLICY)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[1].expires_at == clock() + timedelta(days=90)


def test_revoking_the_old_key_ends_the_overlap_at_once() -> None:
    repo, clock = setup_repo()
    old = register_system(repo, clock)
    new = rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    assert authenticate_with(old, repo, clock) == Rejected(RejectReason.REVOKED, "bss-app")
    assert isinstance(authenticate_with(new, repo, clock), ApiPrincipal)


def test_a_third_valid_key_is_refused() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    before = json.dumps(repo.documents, default=str)
    with pytest.raises(ApiKeyError, match="two valid keys"):
        rotate(repo, "bss-app", clock(), POLICY)
    assert json.dumps(repo.documents, default=str) == before


def test_rotation_works_again_once_the_overlap_is_over() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    clock.advance(days=8)
    third = rotate(repo, "bss-app", clock(), POLICY)
    assert authenticate_with(third, repo, clock) == ApiPrincipal("bss-app", 3)


def test_rotation_works_after_the_only_key_expired() -> None:
    repo, clock = setup_repo()
    old = register_system(repo, clock)
    clock.advance(days=100)
    new = rotate(repo, "bss-app", clock(), POLICY)
    assert isinstance(authenticate_with(new, repo, clock), ApiPrincipal)
    assert authenticate_with(old, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")


def test_rotation_of_unknown_or_disabled_systems_is_refused() -> None:
    repo, clock = setup_repo()
    with pytest.raises(ApiKeyError, match="no calling system"):
        rotate(repo, "bss-app", clock(), POLICY)
    register_system(repo, clock)
    disable(repo, "bss-app")
    with pytest.raises(ApiKeyError, match="disabled"):
        rotate(repo, "bss-app", clock(), POLICY)


def test_rotation_beyond_the_cap_is_refused() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    with pytest.raises(ApiKeyError, match="90 days"):
        rotate(repo, "bss-app", clock(), KeyPolicy(max_age_days=91))


def test_revoke_is_idempotent_and_keeps_the_first_revocation_time() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    first = clock()
    revoke(repo, "bss-app", 1, first)
    clock.advance(days=1)
    revoke(repo, "bss-app", 1, clock())
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].revoked_at == first


def test_revoke_unknown_generation_or_system_is_refused() -> None:
    repo, clock = setup_repo()
    with pytest.raises(ApiKeyError):
        revoke(repo, "bss-app", 1, clock())
    register_system(repo, clock)
    with pytest.raises(ApiKeyError, match="no generation 9"):
        revoke(repo, "bss-app", 9, clock())


def test_nothing_is_ever_deleted() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "bss-app")
    record = repo.get("bss-app")
    assert record is not None
    assert [g.generation for g in record.generations] == [1, 2]
    assert record.status == "disabled"


def test_keys_near_expiry_are_found() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock, "bss-app")
    clock.advance(days=70)
    register_system(repo, clock, "meter-agent")  # created 70 days later: nowhere near expiry
    clock.advance(days=6)  # bss-app now has 14 days left
    found = find_expiring(repo, clock(), POLICY)
    assert [(k.api_key_id, k.generation, k.days_left) for k in found] == [("bss-app", 1, 14)]


def test_expiry_warning_window_edges() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    clock.advance(days=76)  # 14 days left: inside
    assert len(find_expiring(repo, clock(), POLICY)) == 1
    clock.advance(days=-1)  # 15 days left: outside
    assert find_expiring(repo, clock(), POLICY) == []


def test_expired_revoked_and_disabled_keys_are_not_reported() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock, "bss-app")
    register_system(repo, clock, "meter-agent")
    register_system(repo, clock, "old-system")
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "meter-agent")
    clock.advance(days=80)
    assert [k.api_key_id for k in find_expiring(repo, clock(), POLICY)] == ["old-system"]
    clock.advance(days=11)  # now expired
    assert find_expiring(repo, clock(), POLICY) == []


def test_log_expiring_emits_events_without_secrets(caplog: pytest.LogCaptureFixture) -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    clock.advance(days=80)
    caplog.set_level(logging.INFO)
    log_expiring(repo, clock(), POLICY)
    rec = next(r for r in caplog.records if getattr(r, "event", "") == "api_key.expiring")
    assert (rec.api_key_id, rec.api_key_generation, rec.days_left) == ("bss-app", 1, 10)  # type: ignore[attr-defined]
    record = repo.get("bss-app")
    assert record is not None
    for secret in (token, token.split(".", 1)[1], record.generations[0].secret_hash):
        assert secret not in caplog.text


def test_admin_actions_log_no_secrets(caplog: pytest.LogCaptureFixture) -> None:
    repo, clock = setup_repo()
    caplog.set_level(logging.DEBUG)
    t1 = register_system(repo, clock)
    t2 = rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "bss-app")
    events = {getattr(r, "event", "") for r in caplog.records}
    assert {"api_key.created", "api_key.rotated", "api_key.revoked", "api_key.disabled"} <= events
    for token in (t1, t2):
        assert token not in caplog.text and token.split(".", 1)[1] not in caplog.text
    for g in repo.documents["bss-app"]["generations"]:
        assert g["secret_hash"] not in caplog.text
