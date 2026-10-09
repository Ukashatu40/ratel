"""Authentication: every way a key can be accepted or rejected."""

import hmac
from datetime import timedelta
from typing import Any

import pytest

from ratel_link.domain.api_keys import ApiKeyGeneration, ApiKeyRecord
from ratel_link.security.api_key_tokens import hash_secret
from ratel_link.services.api_key_admin import (
    disable,
    revoke,
    rotate,
)
from ratel_link.services.authentication import ApiPrincipal, Rejected, RejectReason, authenticate
from tests.ratel_link.helpers import POLICY, authenticate_with, register_system, setup_repo
from tests.synthetic import SENTINEL_API_KEY, SENTINEL_API_KEY_ID, SENTINEL_API_SECRET


def test_correct_key_verifies() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    assert authenticate_with(token, repo, clock) == ApiPrincipal("bss-app", 1)


def test_scheme_is_case_insensitive() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    for scheme in ("Bearer", "bearer", "BEARER", "bEaReR"):
        assert authenticate(f"{scheme} {token}", repo, clock()) == ApiPrincipal("bss-app", 1)


def test_sentinel_key_can_be_made_valid_for_end_to_end_tests() -> None:
    repo, clock = setup_repo()
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
    assert authenticate_with(SENTINEL_API_KEY, repo, clock) == ApiPrincipal(SENTINEL_API_KEY_ID, 1)


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
    repo, clock = setup_repo()
    register_system(repo, clock)
    header, reason = _rejection_cases()[name]
    result = authenticate(header, repo, clock())
    assert isinstance(result, Rejected)
    assert result.reason is reason


def test_rejection_names_the_system_only_when_the_token_parsed() -> None:
    repo, clock = setup_repo()
    register_system(repo, clock)
    assert authenticate("Bearer junk", repo, clock()) == Rejected(RejectReason.MALFORMED_TOKEN)
    wrong = authenticate("Bearer rlk_bss-app." + "A" * 43, repo, clock())
    assert wrong == Rejected(RejectReason.BAD_SECRET, "bss-app")


def test_revoked_key_is_rejected() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    revoke(repo, "bss-app", 1, clock())
    assert authenticate_with(token, repo, clock) == Rejected(RejectReason.REVOKED, "bss-app")


def test_expired_key_is_rejected_at_exactly_ninety_days() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    clock.advance(days=90, seconds=-1)
    assert isinstance(authenticate_with(token, repo, clock), ApiPrincipal)
    clock.advance(seconds=1)
    assert authenticate_with(token, repo, clock) == Rejected(RejectReason.EXPIRED, "bss-app")


def test_disabled_system_is_rejected_even_with_a_valid_key() -> None:
    repo, clock = setup_repo()
    token = register_system(repo, clock)
    disable(repo, "bss-app")
    assert authenticate_with(token, repo, clock) == Rejected(RejectReason.DISABLED, "bss-app")


def test_a_key_of_one_system_does_not_work_for_another() -> None:
    repo, clock = setup_repo()
    bss = register_system(repo, clock, "bss-app")
    register_system(repo, clock, "meter-agent")
    stolen_secret = bss.split(".", 1)[1]
    result = authenticate_with(f"rlk_meter-agent.{stolen_secret}", repo, clock)
    assert result == Rejected(RejectReason.BAD_SECRET, "meter-agent")


def test_comparison_uses_hmac_compare_digest_on_every_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, clock = setup_repo()
    old = register_system(repo, clock)
    rotate(repo, "bss-app", clock(), POLICY)  # two valid generations
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    # The OLD key matches the first generation. The second must still be compared.
    assert isinstance(authenticate_with(old, repo, clock), ApiPrincipal)
    assert len(calls) == 2
    assert all(isinstance(a, bytes) and isinstance(b, bytes) for a, b in calls)


def test_unknown_id_still_runs_a_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, clock = setup_repo()
    calls: list[Any] = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    result = authenticate("Bearer rlk_nobody-here." + "A" * 43, repo, clock())
    assert result == Rejected(RejectReason.UNKNOWN_ID, "nobody-here")
    assert len(calls) == 1


def test_a_system_with_no_generations_still_runs_a_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, clock = setup_repo()
    repo.insert(ApiKeyRecord("empty-sys", "x", "active", clock(), ()))
    calls: list[Any] = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert authenticate("Bearer rlk_empty-sys." + "A" * 43, repo, clock()) == Rejected(
        RejectReason.BAD_SECRET, "empty-sys"
    )
    assert len(calls) == 1
