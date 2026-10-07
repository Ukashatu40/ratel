import hashlib
import hmac
import json
import logging
import re
from datetime import timedelta
from typing import Any

import pytest

from ratel_link.auth import (
    ApiKeyError,
    ApiPrincipal,
    KeyPolicy,
    Rejected,
    RejectReason,
    authenticate,
    create_system,
    disable,
    find_expiring,
    generate_token,
    hash_secret,
    log_expiring,
    revoke,
    rotate,
)
from ratel_link.models import ApiKeyGeneration, ApiKeyRecord
from tests.ratel_link.fakes import FakeClock, InMemoryApiKeyRepository
from tests.synthetic import SENTINEL_API_KEY, SENTINEL_API_KEY_ID, SENTINEL_API_SECRET

POLICY = KeyPolicy()  # 90 days, 7 days overlap, 14 days warning


def _setup() -> tuple[InMemoryApiKeyRepository, FakeClock]:
    return InMemoryApiKeyRepository(), FakeClock()


def _system(repo: InMemoryApiKeyRepository, clock: FakeClock, api_key_id: str = "bss-app") -> str:
    return create_system(repo, api_key_id, "RatelBSS", clock(), POLICY)


def _check(token: str, repo: InMemoryApiKeyRepository, clock: FakeClock) -> Any:
    return authenticate(f"Bearer {token}", repo, clock())


# --- tokens and hashing -------------------------------------------------------------------------


def test_token_format_and_entropy() -> None:
    pattern = re.compile(r"^rlk_bss-app\.[A-Za-z0-9_-]{43}$")
    tokens = [generate_token("bss-app") for _ in range(2000)]
    assert all(pattern.match(t) for t, _ in tokens)
    assert len({t for t, _ in tokens}) == 2000  # no repeats
    assert len({t.split(".")[1] for t, _ in tokens}) == 2000
    # 43 url-safe characters is 256 bits. Every character class shows up, so it is not a stub.
    alphabet = set("".join(t.split(".")[1] for t, _ in tokens))
    assert len(alphabet) > 60


def test_hash_is_sha256_hex_of_the_secret_with_a_domain_prefix() -> None:
    h = hash_secret(SENTINEL_API_SECRET)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == hash_secret(SENTINEL_API_SECRET)
    assert h != hash_secret(SENTINEL_API_SECRET + "x")
    assert h != hashlib.sha256(SENTINEL_API_SECRET.encode()).hexdigest()  # domain separated


def test_only_the_hash_is_stored() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
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
    repo, clock = _setup()
    _system(repo, clock)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].secret_hash not in repr(record)


# --- verification -------------------------------------------------------------------------------


def test_correct_key_verifies() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
    assert _check(token, repo, clock) == ApiPrincipal("bss-app", 1)


def test_scheme_is_case_insensitive() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
    for scheme in ("Bearer", "bearer", "BEARER", "bEaReR"):
        assert authenticate(f"{scheme} {token}", repo, clock()) == ApiPrincipal("bss-app", 1)


def test_sentinel_key_can_be_made_valid_for_end_to_end_tests() -> None:
    repo, clock = _setup()
    repo.insert(
        ApiKeyRecord(
            SENTINEL_API_KEY_ID,
            "RatelBSS",
            "active",
            clock(),
            (
                ApiKeyGeneration(
                    1,
                    hash_secret(SENTINEL_API_SECRET),
                    clock(),
                    clock() + timedelta(days=90),
                ),
            ),
        )
    )
    assert _check(SENTINEL_API_KEY, repo, clock) == ApiPrincipal(SENTINEL_API_KEY_ID, 1)


def _rejection_cases() -> dict[str, tuple[str | None, RejectReason]]:
    good_secret = "A" * 43
    return {
        "no_header": (None, RejectReason.MISSING_HEADER),
        "empty_header": ("", RejectReason.MISSING_HEADER),
        "basic_scheme": ("Basic dXNlcjpwdw==", RejectReason.WRONG_SCHEME),
        "raw_key_no_scheme": (f"rlk_bss-app.{good_secret}", RejectReason.WRONG_SCHEME),
        "scheme_only": ("Bearer", RejectReason.MALFORMED_TOKEN),
        "empty_token": ("Bearer ", RejectReason.MALFORMED_TOKEN),
        "garbage": ("Bearer not-a-key", RejectReason.MALFORMED_TOKEN),
        "wrong_prefix": (f"Bearer rlx_bss-app.{good_secret}", RejectReason.MALFORMED_TOKEN),
        "short_secret": ("Bearer rlk_bss-app." + "A" * 42, RejectReason.MALFORMED_TOKEN),
        "long_secret": ("Bearer rlk_bss-app." + "A" * 44, RejectReason.MALFORMED_TOKEN),
        "bad_secret_chars": ("Bearer rlk_bss-app." + "A" * 42 + "!", RejectReason.MALFORMED_TOKEN),
        "uppercase_id": (f"Bearer rlk_BSS-app.{good_secret}", RejectReason.MALFORMED_TOKEN),
        "two_spaces": (f"Bearer  rlk_bss-app.{good_secret}", RejectReason.MALFORMED_TOKEN),
        "trailing_newline": (f"Bearer rlk_bss-app.{good_secret}\n", RejectReason.MALFORMED_TOKEN),
        "unknown_id": (f"Bearer rlk_nobody-here.{good_secret}", RejectReason.UNKNOWN_ID),
        "wrong_secret": (f"Bearer rlk_bss-app.{good_secret}", RejectReason.BAD_SECRET),
    }


@pytest.mark.parametrize("name", sorted(_rejection_cases()))
def test_every_bad_request_is_rejected_with_its_reason(name: str) -> None:
    repo, clock = _setup()
    _system(repo, clock)
    header, reason = _rejection_cases()[name]
    result = authenticate(header, repo, clock())
    assert isinstance(result, Rejected)
    assert result.reason is reason


def test_rejection_names_the_system_only_when_the_token_parsed() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    assert authenticate("Bearer junk", repo, clock()) == Rejected(RejectReason.MALFORMED_TOKEN)
    wrong = authenticate("Bearer rlk_bss-app." + "A" * 43, repo, clock())
    assert wrong == Rejected(RejectReason.BAD_SECRET, "bss-app")


def test_revoked_key_is_rejected() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
    revoke(repo, "bss-app", 1, clock())
    assert _check(token, repo, clock) == Rejected(RejectReason.REVOKED, "bss-app")


def test_expired_key_is_rejected_at_exactly_ninety_days() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
    clock.advance(days=90, seconds=-1)
    assert isinstance(_check(token, repo, clock), ApiPrincipal)
    clock.advance(seconds=1)
    assert _check(token, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")


def test_disabled_system_is_rejected_even_with_a_valid_key() -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
    disable(repo, "bss-app")
    assert _check(token, repo, clock) == Rejected(RejectReason.DISABLED, "bss-app")


def test_a_key_of_one_system_does_not_work_for_another() -> None:
    repo, clock = _setup()
    bss = _system(repo, clock, "bss-app")
    _system(repo, clock, "meter-agent")
    stolen_secret = bss.split(".", 1)[1]
    result = _check(f"rlk_meter-agent.{stolen_secret}", repo, clock)
    assert result == Rejected(RejectReason.BAD_SECRET, "meter-agent")


def test_comparison_uses_hmac_compare_digest_on_every_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, clock = _setup()
    old = _system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)  # two valid generations
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    # The OLD key matches the first generation. The second must still be compared.
    assert isinstance(_check(old, repo, clock), ApiPrincipal)
    assert len(calls) == 2
    assert all(isinstance(a, bytes) and isinstance(b, bytes) for a, b in calls)


def test_unknown_id_still_runs_a_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, clock = _setup()
    calls: list[Any] = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    result = authenticate("Bearer rlk_nobody-here." + "A" * 43, repo, clock())
    assert result == Rejected(RejectReason.UNKNOWN_ID, "nobody-here")
    assert len(calls) == 1


def test_a_system_with_no_generations_still_runs_a_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, clock = _setup()
    repo.insert(ApiKeyRecord("empty-sys", "x", "active", clock(), ()))
    calls: list[Any] = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert authenticate("Bearer rlk_empty-sys." + "A" * 43, repo, clock()) == Rejected(
        RejectReason.BAD_SECRET, "empty-sys"
    )
    assert len(calls) == 1


# --- creation and the 90-day rule ---------------------------------------------------------------


def test_first_key_expires_in_ninety_days() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    record = repo.get("bss-app")
    assert record is not None
    gen = record.generations[0]
    assert gen.expires_at == clock() + timedelta(days=90)
    assert gen.created_at == clock()
    assert record.status == "active"


@pytest.mark.parametrize("days", [91, 365, 0, -1])
def test_creation_beyond_the_cap_is_refused(days: int) -> None:
    repo, clock = _setup()
    with pytest.raises(ApiKeyError, match="90 days"):
        create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy(max_age_days=days))
    assert repo.documents == {}


def test_a_shorter_lifetime_is_allowed() -> None:
    repo, clock = _setup()
    create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy(max_age_days=30))
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].expires_at == clock() + timedelta(days=30)


@pytest.mark.parametrize(
    "bad", ["", "ab", "Bss-app", "1bss", "bss_app", "bss app", "a" * 33, "bss.app"]
)
def test_bad_api_key_id_is_refused(bad: str) -> None:
    repo, clock = _setup()
    with pytest.raises(ApiKeyError, match="api_key_id must be"):
        create_system(repo, bad, "RatelBSS", clock(), POLICY)


@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_bad_system_name_is_refused(name: str) -> None:
    repo, clock = _setup()
    with pytest.raises(ApiKeyError, match="system name"):
        create_system(repo, "bss-app", name, clock(), POLICY)


def test_duplicate_system_is_refused_and_changes_nothing() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    before = json.dumps(repo.documents, default=str)
    with pytest.raises(ApiKeyError, match="already exists"):
        _system(repo, clock)
    assert json.dumps(repo.documents, default=str) == before


# --- rotation -----------------------------------------------------------------------------------


def test_both_keys_work_during_the_overlap_then_the_old_one_stops() -> None:
    repo, clock = _setup()
    old = _system(repo, clock)
    clock.advance(days=60)
    new = rotate(repo, "bss-app", clock(), POLICY)
    assert _check(old, repo, clock) == ApiPrincipal("bss-app", 1)
    assert _check(new, repo, clock) == ApiPrincipal("bss-app", 2)
    clock.advance(days=6, seconds=86399)  # still inside the 7-day overlap
    assert isinstance(_check(old, repo, clock), ApiPrincipal)
    clock.advance(seconds=1)
    assert _check(old, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")
    assert _check(new, repo, clock) == ApiPrincipal("bss-app", 2)


def test_rotation_never_extends_the_old_key() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    clock.advance(days=88)  # the old key has 2 days left, less than the 7-day overlap
    rotate(repo, "bss-app", clock(), POLICY)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].expires_at == clock() - timedelta(days=88) + timedelta(days=90)


def test_new_key_gets_a_full_ninety_days() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    clock.advance(days=80)
    rotate(repo, "bss-app", clock(), POLICY)
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[1].expires_at == clock() + timedelta(days=90)


def test_revoking_the_old_key_ends_the_overlap_at_once() -> None:
    repo, clock = _setup()
    old = _system(repo, clock)
    new = rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    assert _check(old, repo, clock) == Rejected(RejectReason.REVOKED, "bss-app")
    assert isinstance(_check(new, repo, clock), ApiPrincipal)


def test_a_third_valid_key_is_refused() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    before = json.dumps(repo.documents, default=str)
    with pytest.raises(ApiKeyError, match="two valid keys"):
        rotate(repo, "bss-app", clock(), POLICY)
    assert json.dumps(repo.documents, default=str) == before


def test_rotation_works_again_once_the_overlap_is_over() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    clock.advance(days=8)
    third = rotate(repo, "bss-app", clock(), POLICY)
    assert _check(third, repo, clock) == ApiPrincipal("bss-app", 3)


def test_rotation_works_after_the_only_key_expired() -> None:
    repo, clock = _setup()
    old = _system(repo, clock)
    clock.advance(days=100)
    new = rotate(repo, "bss-app", clock(), POLICY)
    assert isinstance(_check(new, repo, clock), ApiPrincipal)
    assert _check(old, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")


def test_rotation_of_unknown_or_disabled_systems_is_refused() -> None:
    repo, clock = _setup()
    with pytest.raises(ApiKeyError, match="no calling system"):
        rotate(repo, "bss-app", clock(), POLICY)
    _system(repo, clock)
    disable(repo, "bss-app")
    with pytest.raises(ApiKeyError, match="disabled"):
        rotate(repo, "bss-app", clock(), POLICY)


def test_rotation_beyond_the_cap_is_refused() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    with pytest.raises(ApiKeyError, match="90 days"):
        rotate(repo, "bss-app", clock(), KeyPolicy(max_age_days=91))


def test_revoke_is_idempotent_and_keeps_the_first_revocation_time() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    first = clock()
    revoke(repo, "bss-app", 1, first)
    clock.advance(days=1)
    revoke(repo, "bss-app", 1, clock())
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].revoked_at == first


def test_revoke_unknown_generation_or_system_is_refused() -> None:
    repo, clock = _setup()
    with pytest.raises(ApiKeyError):
        revoke(repo, "bss-app", 1, clock())
    _system(repo, clock)
    with pytest.raises(ApiKeyError, match="no generation 9"):
        revoke(repo, "bss-app", 9, clock())


def test_nothing_is_ever_deleted() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "bss-app")
    record = repo.get("bss-app")
    assert record is not None
    assert [g.generation for g in record.generations] == [1, 2]
    assert record.status == "disabled"


# --- expiry warnings ----------------------------------------------------------------------------


def test_keys_near_expiry_are_found() -> None:
    repo, clock = _setup()
    _system(repo, clock, "bss-app")
    clock.advance(days=70)
    _system(repo, clock, "meter-agent")  # created 70 days later: nowhere near expiry
    clock.advance(days=6)  # bss-app now has 14 days left
    found = find_expiring(repo, clock(), POLICY)
    assert [(k.api_key_id, k.generation, k.days_left) for k in found] == [("bss-app", 1, 14)]


def test_expiry_warning_window_edges() -> None:
    repo, clock = _setup()
    _system(repo, clock)
    clock.advance(days=76)  # 14 days left: inside
    assert len(find_expiring(repo, clock(), POLICY)) == 1
    clock.advance(days=-1)  # 15 days left: outside
    assert find_expiring(repo, clock(), POLICY) == []


def test_expired_revoked_and_disabled_keys_are_not_reported() -> None:
    repo, clock = _setup()
    _system(repo, clock, "bss-app")
    _system(repo, clock, "meter-agent")
    _system(repo, clock, "old-system")
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "meter-agent")
    clock.advance(days=80)
    assert [k.api_key_id for k in find_expiring(repo, clock(), POLICY)] == ["old-system"]
    clock.advance(days=11)  # now expired
    assert find_expiring(repo, clock(), POLICY) == []


def test_log_expiring_emits_events_without_secrets(caplog: pytest.LogCaptureFixture) -> None:
    repo, clock = _setup()
    token = _system(repo, clock)
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
    repo, clock = _setup()
    caplog.set_level(logging.DEBUG)
    t1 = _system(repo, clock)
    t2 = rotate(repo, "bss-app", clock(), POLICY)
    revoke(repo, "bss-app", 1, clock())
    disable(repo, "bss-app")
    events = {getattr(r, "event", "") for r in caplog.records}
    assert {"api_key.created", "api_key.rotated", "api_key.revoked", "api_key.disabled"} <= events
    for token in (t1, t2):
        assert token not in caplog.text and token.split(".", 1)[1] not in caplog.text
    for g in repo.documents["bss-app"]["generations"]:
        assert g["secret_hash"] not in caplog.text
