from datetime import UTC, datetime, timedelta

import pytest

from ratel_link.domain.ip_pool import (
    RELEASE_HOLD,
    IpAllocation,
    IpPool,
    PoolExhaustedError,
    hold_cutoff,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_the_hold_is_24_hours() -> None:
    assert RELEASE_HOLD == timedelta(hours=24)
    assert hold_cutoff(NOW) == NOW - timedelta(hours=24)


def test_network_and_broadcast_addresses_are_never_usable() -> None:
    usable = list(IpPool("10.45.0.0/16").usable())
    assert "10.45.0.0" not in usable and "10.45.255.255" not in usable
    assert usable[0] == "10.45.0.1" and usable[-1] == "10.45.255.254"
    assert len(usable) == 65534


def test_from_cidr_reserves_the_first_host_for_the_gateway() -> None:
    usable = list(IpPool.from_cidr("10.45.0.0/16").usable())
    assert "10.45.0.1" not in usable
    assert usable[0] == "10.45.0.2" and len(usable) == 65533


def test_first_free_is_the_lowest_address_not_in_use() -> None:
    pool = IpPool.from_cidr("10.45.0.0/16")
    assert pool.first_free(set()) == "10.45.0.2"
    assert pool.first_free({"10.45.0.2", "10.45.0.3"}) == "10.45.0.4"
    assert pool.first_free({"10.45.0.3"}) == "10.45.0.2"


def test_an_exhausted_pool_says_so() -> None:
    pool = IpPool.from_cidr("10.45.0.0/29")  # hosts .1 to .6, the first reserved: five usable
    taken = {f"10.45.0.{n}" for n in range(2, 7)}
    assert pool.first_free(taken - {"10.45.0.6"}) == "10.45.0.6"
    with pytest.raises(PoolExhaustedError):
        pool.first_free(taken)


@pytest.mark.parametrize("bad", ["10.45.0.0/31", "10.45.0.5/24", "not-a-network", "fd00::/64"])
def test_a_bad_pool_is_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        IpPool(bad)


def test_allocation_round_trips_through_its_document() -> None:
    a = IpAllocation("10.45.0.2", "621000000000001", "released", NOW, NOW + timedelta(hours=1))
    assert IpAllocation.from_document(a.to_document()) == a
    naive = {**a.to_document(), "allocated_at": NOW.replace(tzinfo=None)}
    assert IpAllocation.from_document(naive).allocated_at.tzinfo is not None
