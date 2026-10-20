"""Plans and bundles: valid ones are accepted as they are, and every bad field is refused.

The plans used here are synthetic. The real plans, prices and speeds are TODO(PRD).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.bss_money.domain.plans import Bundle, OnExhaustion, Plan


def _plan(**overrides: Any) -> Plan:
    values: dict[str, Any] = {
        "plan_id": 1,
        "name": "Synthetic Basic",
        "price_kobo": 150_000,
        "validity_days": 30,
        "data_bytes": 5 * 1024**3,
        "speed_ul_mbps": 5,
        "speed_dl_mbps": 10.5,
        "channels": ("ussd", "app"),
        "on_exhaustion": OnExhaustion.SLOW,
        "slow_ul_mbps": 0.25,
        "slow_dl_mbps": 0.5,
    }
    values.update(overrides)
    return Plan(**values)


def _bundle(**overrides: Any) -> Bundle:
    values: dict[str, Any] = {
        "bundle_id": 1,
        "name": "Synthetic Top-up",
        "price_kobo": 50_000,
        "validity_days": 7,
        "data_bytes": 1024**3,
        "channels": ("app",),
    }
    values.update(overrides)
    return Bundle(**values)


def test_a_valid_plan_is_kept_exactly_as_given() -> None:
    plan = _plan()
    assert (plan.price_kobo, plan.data_bytes, plan.on_exhaustion) == (
        150_000,
        5 * 1024**3,
        OnExhaustion.SLOW,
    )
    assert isinstance(plan.price_kobo, int) and isinstance(plan.data_bytes, int)


def test_a_plan_that_stops_needs_no_slow_speeds() -> None:
    plan = _plan(on_exhaustion="stop", slow_ul_mbps=None, slow_dl_mbps=None)
    assert plan.on_exhaustion is OnExhaustion.STOP


def test_a_free_plan_is_allowed() -> None:
    assert _plan(price_kobo=0).price_kobo == 0


def test_the_exhaustion_rule_may_be_given_as_text() -> None:
    assert _plan(on_exhaustion="slow").on_exhaustion is OnExhaustion.SLOW


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"plan_id": 0}, "id"),
        ({"plan_id": True}, "id"),
        ({"name": "  "}, "name"),
        ({"price_kobo": 1500.5}, "price_kobo"),
        ({"price_kobo": -1}, "price_kobo"),
        ({"price_kobo": True}, "price_kobo"),
        ({"validity_days": 0}, "validity_days"),
        ({"validity_days": 30.0}, "validity_days"),
        ({"data_bytes": 0}, "data_bytes"),
        ({"data_bytes": 1e9}, "data_bytes"),
        ({"speed_ul_mbps": 0}, "speed_ul_mbps"),
        ({"speed_dl_mbps": -1}, "speed_dl_mbps"),
        ({"speed_dl_mbps": float("nan")}, "speed_dl_mbps"),
        ({"speed_ul_mbps": float("inf")}, "speed_ul_mbps"),
        ({"speed_ul_mbps": True}, "speed_ul_mbps"),
        ({"on_exhaustion": "throttle"}, "on_exhaustion"),
        ({"slow_ul_mbps": None}, "slow_ul_mbps"),
        ({"slow_dl_mbps": None}, "slow_dl_mbps"),
        ({"slow_ul_mbps": 0}, "slow_ul_mbps"),
        ({"channels": ["ussd"]}, "channels"),
        ({"channels": ("ussd", "")}, "channels"),
    ],
)
def test_a_plan_with_a_bad_field_is_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _plan(**overrides)


def test_a_plan_that_stops_cannot_also_carry_slow_speeds() -> None:
    with pytest.raises(ValueError, match="no slow speeds"):
        _plan(on_exhaustion="stop")  # the default slow speeds are still set


def test_a_valid_bundle_is_kept_exactly_as_given() -> None:
    bundle = _bundle()
    assert (bundle.price_kobo, bundle.validity_days, bundle.data_bytes) == (50_000, 7, 1024**3)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bundle_id": -3}, "id"),
        ({"name": ""}, "name"),
        ({"price_kobo": 99.99}, "price_kobo"),
        ({"validity_days": 0}, "validity_days"),
        ({"data_bytes": -1}, "data_bytes"),
        ({"channels": "app"}, "channels"),
    ],
)
def test_a_bundle_with_a_bad_field_is_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _bundle(**overrides)


def test_plans_and_bundles_cannot_be_changed_after_they_are_built() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _plan().price_kobo = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _bundle().data_bytes = 1  # type: ignore[misc]
