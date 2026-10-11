"""Fixed addresses for lines: unique, held for 24 hours after release, never shared."""

import logging
from datetime import datetime

import pytest

from ratel_link.domain.ip_pool import IpAllocation, IpPool, PoolExhaustedError
from ratel_link.services.ip_allocation import AllocationContentionError, IpAllocator
from tests.ratel_link.fakes import FakeClock, InMemoryIpAllocationRepository

A, B, C = "621000000000001", "621000000000002", "621000000000003"
EXTRA = "621000000009999"  # a line that is not one of the numbered ones


def _setup(
    cidr: str = "10.45.0.0/16",
) -> tuple[IpAllocator, InMemoryIpAllocationRepository, FakeClock]:
    repo, clock = InMemoryIpAllocationRepository(), FakeClock()
    return IpAllocator(repo, IpPool.from_cidr(cidr), clock), repo, clock


def test_the_first_line_gets_the_lowest_usable_address() -> None:
    allocator, _, _ = _setup()
    assert allocator.allocate(A) == "10.45.0.2"  # .0 is the network, .1 is reserved
    assert allocator.allocate(B) == "10.45.0.3"


def test_allocating_again_returns_the_same_address() -> None:
    allocator, repo, _ = _setup()
    first = allocator.allocate(A)
    assert allocator.allocate(A) == first
    assert len(repo.by_ip) == 1


def test_two_lines_never_share_an_address() -> None:
    allocator, repo, _ = _setup()
    addresses = [allocator.allocate(f"6210000000{n:05d}") for n in range(300)]
    assert len(set(addresses)) == 300
    assert len({a.imsi for a in repo.by_ip.values()}) == 300


def test_a_released_address_is_held_for_24_hours() -> None:
    allocator, _, clock = _setup()
    first = allocator.allocate(A)
    assert allocator.release(A) is True
    assert allocator.allocate(B) != first  # B must not get A's address yet
    clock.advance(seconds=24 * 3600 - 1)
    assert allocator.allocate(C) != first  # one second short of 24 hours
    # the held address was skipped each time, so it is still the lowest free one after the hold
    clock.advance(seconds=1)
    assert allocator.allocate("621000000000004") == first


def test_the_hold_is_exactly_24_hours() -> None:
    allocator, _, clock = _setup()
    first = allocator.allocate(A)
    allocator.release(A)
    clock.advance(days=1)
    assert allocator.allocate(B) == first


def test_a_line_can_take_its_own_released_address_back_during_the_hold() -> None:
    allocator, _, clock = _setup()
    first = allocator.allocate(A)
    allocator.release(A)
    clock.advance(seconds=60)
    assert allocator.allocate(A) == first


def test_a_line_that_lost_its_address_after_the_hold_gets_a_different_one() -> None:
    allocator, _, clock = _setup()
    first = allocator.allocate(A)
    allocator.release(A)
    clock.advance(days=2)
    assert allocator.allocate(B) == first  # someone else takes it after the hold
    again = allocator.allocate(A)
    assert again != first


def test_releasing_twice_or_for_an_unknown_line_is_harmless() -> None:
    allocator, _, _ = _setup()
    allocator.allocate(A)
    assert allocator.release(A) is True
    assert allocator.release(A) is False
    assert allocator.release(B) is False


def test_a_full_pool_raises_and_gives_nothing() -> None:
    allocator, repo, _ = _setup("10.45.0.0/29")  # five usable addresses
    for n in range(5):
        allocator.allocate(f"6210000000{n:05d}")
    with pytest.raises(PoolExhaustedError):
        allocator.allocate(EXTRA)
    assert len(repo.by_ip) == 5


def test_a_freed_address_is_not_available_in_a_full_pool_until_the_hold_ends() -> None:
    allocator, _, clock = _setup("10.45.0.0/29")
    for n in range(5):
        allocator.allocate(f"6210000000{n:05d}")
    allocator.release("621000000000000")
    with pytest.raises(PoolExhaustedError):
        allocator.allocate(EXTRA)
    clock.advance(days=1)
    assert allocator.allocate(EXTRA)


def test_losing_a_race_for_an_address_moves_on_to_the_next() -> None:
    class Racy(InMemoryIpAllocationRepository):
        def claim_free(self, ue_ip: str, imsi: str, now: datetime, hold_cutoff: datetime) -> bool:
            if self.claim_attempts == 0:  # another activation takes this address first
                self.claim_attempts += 1
                self.by_ip[ue_ip] = IpAllocation(ue_ip, EXTRA, "active", now)
                return False
            return super().claim_free(ue_ip, imsi, now, hold_cutoff)

    allocator = IpAllocator(Racy(), IpPool.from_cidr("10.45.0.0/16"), FakeClock())
    assert allocator.allocate(A) == "10.45.0.3"  # .2 was taken in the race


def test_endless_contention_gives_up_instead_of_looping() -> None:
    class Never(InMemoryIpAllocationRepository):
        def claim_free(self, ue_ip: str, imsi: str, now: datetime, hold_cutoff: datetime) -> bool:
            return False

    allocator = IpAllocator(Never(), IpPool.from_cidr("10.45.0.0/16"), FakeClock())
    with pytest.raises(AllocationContentionError):
        allocator.allocate(A)


@pytest.mark.parametrize("bad", ["", "123", "62100000000000a", "6210000000000012"])
def test_an_invalid_imsi_is_refused(bad: str) -> None:
    allocator, repo, _ = _setup()
    with pytest.raises(ValueError, match="invalid IMSI"):
        allocator.allocate(bad)
    with pytest.raises(ValueError, match="invalid IMSI"):
        allocator.release(bad)
    assert repo.by_ip == {}


def test_logs_never_carry_the_imsi(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    allocator, _, _ = _setup()
    allocator.allocate(A)
    allocator.release(A)
    allocator.allocate(A)
    assert [r.__dict__.get("event") for r in caplog.records] == [
        "ip.allocated",
        "ip.released",
        "ip.reclaimed",
    ]
    assert A not in caplog.text and A not in str([r.__dict__ for r in caplog.records])
