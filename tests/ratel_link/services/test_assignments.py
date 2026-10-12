"""The address list RatelMeter uses: active addresses plus those still on hold, in order."""

from ipaddress import ip_address

from ratel_link.domain.ip_pool import Assignment, IpPool
from ratel_link.services.assignments import AssignmentService
from ratel_link.services.ip_allocation import IpAllocator
from tests.ratel_link.fakes import FakeClock, InMemoryIpAllocationRepository

A, B, C = "621000000000001", "621000000000002", "621000000000003"


def _env() -> tuple[AssignmentService, IpAllocator, FakeClock]:
    repo, clock = InMemoryIpAllocationRepository(), FakeClock()
    return (
        AssignmentService(repo, clock),
        IpAllocator(repo, IpPool.from_cidr("10.45.0.0/16"), clock),
        clock,
    )


def test_nothing_allocated_is_an_empty_list() -> None:
    service, _, _ = _env()
    assert service.list_current() == []


def test_active_addresses_are_listed_with_their_lines() -> None:
    service, allocator, _ = _env()
    allocator.allocate(A)
    allocator.allocate(B)
    assert service.list_current() == [
        Assignment("10.45.0.2", A),
        Assignment("10.45.0.3", B),
    ]


def test_the_order_is_numeric_not_alphabetical() -> None:
    service, allocator, _ = _env()
    for n in range(10, 0, -1):  # 10 lines, so addresses run past .9 into .10 and .11
        allocator.allocate(f"6210000000{n:05d}")
    listed = [a.ue_ip for a in service.list_current()]
    assert listed == sorted(listed, key=ip_address)
    assert "10.45.0.11" in listed and listed.index("10.45.0.11") > listed.index("10.45.0.9")


def test_a_released_address_stays_with_its_line_for_the_whole_hold() -> None:
    service, allocator, clock = _env()
    allocator.allocate(A)
    allocator.release(A)
    clock.advance(seconds=24 * 3600 - 1)
    assert service.list_current() == [Assignment("10.45.0.2", A)]


def test_a_released_address_is_dropped_once_the_hold_ends() -> None:
    service, allocator, clock = _env()
    allocator.allocate(A)
    allocator.release(A)
    clock.advance(seconds=24 * 3600 + 1)
    assert service.list_current() == []


def test_after_the_hold_the_address_is_listed_against_its_new_line() -> None:
    service, allocator, clock = _env()
    allocator.allocate(A)
    allocator.release(A)
    clock.advance(seconds=24 * 3600 + 1)
    assert allocator.allocate(B) == "10.45.0.2"
    assert service.list_current() == [Assignment("10.45.0.2", B)]


def test_one_address_is_never_listed_twice() -> None:
    service, allocator, clock = _env()
    allocator.allocate(A)
    allocator.release(A)
    clock.advance(seconds=24 * 3600 + 1)
    allocator.allocate(B)
    allocator.release(B)
    clock.advance(seconds=3600)
    listed = [a.ue_ip for a in service.list_current()]
    assert len(listed) == len(set(listed)) == 1
