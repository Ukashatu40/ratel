"""The line lifecycle routes end to end on SQLite, with the fake RatelLink client."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from app.bss_lines.api.lines import get_client
from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_lines.services.ratel_link_client import RatelLinkError
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in
from tests.app.bss_lines.fakes import FakeRatelLinkClient


def _bucket(line_id: int, **changes: object) -> AllowanceBucket:
    """A paid-for allowance: 1 GB, none used, valid for the next 30 days."""
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "line_id": line_id,
        "source_kind": "plan",
        "source_id": 1,
        "data_bytes_total": 1_000_000_000,
        "data_bytes_used": 0,
        "valid_from": now - timedelta(days=1),
        "valid_to": now + timedelta(days=30),
    }
    return AllowanceBucket(**{**values, **changes})


@pytest.fixture
def fake_client() -> FakeRatelLinkClient:
    return FakeRatelLinkClient()


@pytest.fixture
def client_with_seeded_line(tmp_path, fake_client: FakeRatelLinkClient) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory() as s:
        customer = Customer(
            name="Alice",
            phone="2348000000001",
            email="alice@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="addr",
            kyc_status="verified",
        )
        sim = Sim(
            iccid="8923400000000000001",
            imsi="621000000000001",
            batch="batch-1",
            state="in_use",
        )
        number = Number(msisdn="2348000000001", state="in_use")
        plan = Plan(
            name="Basic",
            price_kobo=500,
            validity_days=30,
            data_bytes=1_000_000,
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            slow_ul_mbps=1,
            slow_dl_mbps=1,
            channels="data",
            on_exhaustion="slow",
            state="on_sale",
        )
        s.add_all([customer, sim, number, plan])
        s.flush()
        line = Line(
            customer_id=customer.customer_id,
            iccid=sim.iccid,
            imsi=sim.imsi,
            msisdn=number.msisdn,
            plan_id=plan.plan_id,
            state="awaiting_activation",
        )
        s.add(line)
        s.flush()
        s.add(_bucket(line.line_id))
        s.commit()
        line_id = line.line_id

    app = make_app(factory)
    app.dependency_overrides[get_client] = lambda: fake_client
    email = add_staff(factory, "agent")

    with signed_in(app, email) as client:
        client.seeded_line_id = line_id  # type: ignore[attr-defined]
        client.staff_email = email  # type: ignore[attr-defined]
        yield client


def _activate(client, line_id: int, key: str | None = "key-1", body: dict | None = None):  # type: ignore[no-untyped-def]
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(f"/v1/lines/{line_id}/activate", json=body or {}, headers=headers)


def _care(client, action: str, line_id: int, key: str = "k", reason: str = "fraud", **extra):  # type: ignore[no-untyped-def]
    return client.post(
        f"/v1/lines/{line_id}/{action}",
        json={"reason": reason, **extra},
        headers={"Idempotency-Key": key},
    )


def _line_state(client, line_id: int) -> str:  # type: ignore[no-untyped-def]
    with client.app.state.session_factory() as session:
        return session.get(Line, line_id).state


def test_activate_answers_with_the_line_as_the_contract_describes_it(
    client_with_seeded_line,
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    response = _activate(client_with_seeded_line, line_id)
    assert response.status_code == 200
    assert set(response.json()) == {
        "line_id",
        "customer_id",
        "iccid",
        "imsi",
        "msisdn",
        "plan_id",
        "state",
        "state_before_suspension",
        "expires_at",
    }
    assert response.json()["state"] == "active"
    assert response.json()["line_id"] == line_id


def test_the_audit_actor_is_the_signed_in_member(client_with_seeded_line) -> None:
    from sqlalchemy import select

    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    factory = client_with_seeded_line.app.state.session_factory
    with factory() as session:
        actors = session.scalars(select(LineAudit.actor).where(LineAudit.line_id == line_id)).all()
    assert actors == ["staff:1"]


def test_a_body_that_names_an_actor_is_refused(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    response = _activate(client_with_seeded_line, line_id, body={"actor": "staff:999"})
    assert response.status_code == 422
    assert _line_state(client_with_seeded_line, line_id) == "awaiting_activation"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/lines/1/activate"),
        ("post", "/v1/lines/1/suspend"),
        ("post", "/v1/lines/1/reinstate"),
        ("post", "/v1/lines/1/terminate"),
        ("get", "/v1/lines/lookup?msisdn=2348000000001"),
        ("get", "/v1/lines/lookup/1"),
    ],
)
def test_the_line_routes_refuse_a_caller_who_is_not_signed_in(
    client_with_seeded_line, fake_client: FakeRatelLinkClient, method: str, path: str
) -> None:
    anonymous = TestClient(client_with_seeded_line.app)
    response = getattr(anonymous, method)(
        path, **({"json": {"reason": "fraud"}} if method == "post" else {})
    )
    assert response.status_code == 401
    assert fake_client.calls == []  # RatelLink was not called


@pytest.mark.parametrize("action", ["activate", "suspend", "reinstate", "terminate"])
def test_a_missing_sign_in_is_401_before_the_body_is_read(
    client_with_seeded_line, action: str
) -> None:
    anonymous = TestClient(client_with_seeded_line.app)
    response = anonymous.post(f"/v1/lines/1/{action}", json={"reason": "not-on-the-list"})
    assert response.status_code == 401


def _replace_allowance(client, **changes: object) -> None:  # type: ignore[no-untyped-def]
    """Swap the seeded line's allowance for one with `changes`; none at all if changes is None."""
    with client.app.state.session_factory() as session, session.begin():
        for bucket in session.query(AllowanceBucket).all():
            session.delete(bucket)
        if changes != {"none": True}:
            session.add(_bucket(client.seeded_line_id, **changes))


@pytest.mark.parametrize(
    "allowance",
    [
        {"none": True},
        {"data_bytes_used": 1_000_000_000},  # all of it used
        {
            "valid_from": datetime(2020, 1, 1, tzinfo=UTC),
            "valid_to": datetime(2020, 2, 1, tzinfo=UTC),
        },
    ],
    ids=["no allowance", "used up", "expired"],
)
def test_activate_is_refused_while_no_plan_is_paid_for(
    client_with_seeded_line, fake_client: FakeRatelLinkClient, allowance: dict
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _replace_allowance(client_with_seeded_line, **allowance)
    response = _activate(client_with_seeded_line, line_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "paid" in response.json()["error"]["message"]
    assert fake_client.calls == []
    assert _line_state(client_with_seeded_line, line_id) == "awaiting_activation"


def test_another_lines_allowance_does_not_count(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _replace_allowance(client_with_seeded_line, none=True)
    with client_with_seeded_line.app.state.session_factory() as session, session.begin():
        session.add(_bucket(line_id + 1000))
    assert _activate(client_with_seeded_line, line_id).status_code == 409
    assert fake_client.calls == []


def test_an_allowance_that_starts_later_counts_as_paid_for(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    soon = datetime.now(UTC) + timedelta(days=1)
    _replace_allowance(client_with_seeded_line, valid_from=soon, valid_to=soon + timedelta(days=7))
    assert _activate(client_with_seeded_line, line_id).status_code == 200


def test_paying_after_a_refusal_lets_the_same_key_through(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _replace_allowance(client_with_seeded_line, none=True)
    assert _activate(client_with_seeded_line, line_id, "same").status_code == 409
    _replace_allowance(client_with_seeded_line)
    assert _activate(client_with_seeded_line, line_id, "same").status_code == 200
    assert len(fake_client.calls) == 1


def test_the_whole_counter_journey_top_up_buy_the_plan_then_activate(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _replace_allowance(client_with_seeded_line, none=True)
    assert _activate(client_with_seeded_line, line_id, "a1").status_code == 409  # nothing paid

    with client_with_seeded_line.app.state.session_factory() as session, session.begin():
        session.add(Wallet(line_id=line_id, balance_kobo=1_000))
        session.flush()
        session.add(
            LedgerEntry(line_id=line_id, amount_kobo=1_000, kind="top_up", reference="pay-1")
        )
    bought = client_with_seeded_line.post(
        f"/v1/lines/{line_id}/purchases",
        json={"offer_kind": "plan", "offer_id": 1},
        headers={"Idempotency-Key": "buy-1"},
    )
    assert bought.status_code == 200, bought.text

    activated = _activate(client_with_seeded_line, line_id, "a2")
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"
    assert len(fake_client.calls) == 1


def test_activate_calls_ratellink_once(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    assert len(fake_client.calls) == 1


def test_a_repeat_with_the_same_key_returns_the_line_and_calls_ratellink_once(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    first = _activate(client_with_seeded_line, line_id, "same")
    second = _activate(client_with_seeded_line, line_id, "same")
    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == first.json()
    assert len(fake_client.calls) == 1


def test_the_same_key_for_another_line_is_409(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id, "same")
    response = _activate(client_with_seeded_line, line_id + 1, "same")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_a_call_without_a_key_works_and_each_one_is_a_new_operation(
    client_with_seeded_line,
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    assert _activate(client_with_seeded_line, line_id, None).status_code == 200
    # The line is active now, so a second keyless call is a refused transition, not a replay.
    assert _activate(client_with_seeded_line, line_id, None).status_code == 409


def test_an_empty_key_is_422(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    assert _activate(client_with_seeded_line, line_id, "").status_code == 422


def test_an_unknown_line_is_404_in_the_standard_error_shape(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    for response in (
        _activate(client_with_seeded_line, 99999),
        _care(client_with_seeded_line, "suspend", 99999),
        _care(client_with_seeded_line, "reinstate", 99999),
    ):
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "not_found", "message": "No such line."}}
    assert fake_client.calls == []


def test_activating_a_line_that_is_not_awaiting_activation_is_409(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id, "a")
    response = _activate(client_with_seeded_line, line_id, "b")
    assert response.status_code == 409
    assert len(fake_client.calls) == 1


def test_a_customer_who_is_not_verified_cannot_be_activated(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    with client_with_seeded_line.app.state.session_factory() as session, session.begin():
        session.get(Line, line_id).customer.kyc_status = "pending"
    response = _activate(client_with_seeded_line, line_id)
    assert response.status_code == 409
    assert fake_client.calls == []
    assert _line_state(client_with_seeded_line, line_id) == "awaiting_activation"


def test_overriding_the_plans_speeds_is_not_supported_yet(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    response = _activate(client_with_seeded_line, line_id, body={"speed_dl_mbps": 50})
    assert response.status_code == 422
    assert fake_client.calls == []


def test_when_ratellink_fails_the_answer_is_502_and_the_line_does_not_change(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    fake_client.fail_on_activate = RatelLinkError("secret detail 621000000000001", status=503)
    response = _activate(client_with_seeded_line, line_id)
    assert response.status_code == 502
    assert "621000000000001" not in response.text  # nothing from RatelLink is passed on
    assert _line_state(client_with_seeded_line, line_id) == "awaiting_activation"

    fake_client.fail_on_activate = None  # the retry, with the same key, goes through
    assert _activate(client_with_seeded_line, line_id).status_code == 200


def test_suspend_then_reinstate_walks_the_line_there_and_back(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)

    suspended = _care(client_with_seeded_line, "suspend", line_id, "s1", reason_text="seen")
    assert suspended.status_code == 200
    assert suspended.json()["state"] == "suspended"
    assert suspended.json()["state_before_suspension"] == "active"

    reinstated = _care(client_with_seeded_line, "reinstate", line_id, "r1", "customer_request")
    assert reinstated.status_code == 200
    assert reinstated.json()["state"] == "active"
    assert reinstated.json()["state_before_suspension"] is None


def test_the_audit_trail_keeps_the_reason_and_its_text(client_with_seeded_line) -> None:
    from sqlalchemy import select

    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    _care(client_with_seeded_line, "suspend", line_id, "s1", "lost_sim", reason_text="phone stolen")
    factory = client_with_seeded_line.app.state.session_factory
    with factory() as session:
        reasons = session.scalars(
            select(LineAudit.reason).where(LineAudit.line_id == line_id).order_by(LineAudit.id)
        ).all()
    assert reasons[-1] == "lost_sim: phone stolen"


def test_a_repeat_suspend_with_the_same_key_changes_nothing(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    first = _care(client_with_seeded_line, "suspend", line_id, "same")
    second = _care(client_with_seeded_line, "suspend", line_id, "same")
    assert (first.status_code, second.status_code) == (200, 200)
    assert len([c for c in fake_client.calls if c.endpoint == "/deactivate"]) == 1


def test_suspending_a_line_that_is_not_active_is_409_and_reinstating_one_that_is_not_suspended(
    client_with_seeded_line,
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    assert _care(client_with_seeded_line, "suspend", line_id, "a").status_code == 409
    assert _care(client_with_seeded_line, "reinstate", line_id, "b").status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reason": "because"},
        {"reason": "fraud", "reason_text": "x" * 201},
        {"reason": "fraud", "line_id": 1},
    ],
    ids=["no-reason", "reason-not-on-the-list", "text-too-long", "extra-field"],
)
def test_a_bad_care_action_body_is_422_and_changes_nothing(
    client_with_seeded_line, fake_client: FakeRatelLinkClient, body: dict
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    calls = len(fake_client.calls)
    response = client_with_seeded_line.post(f"/v1/lines/{line_id}/suspend", json=body)
    assert response.status_code == 422
    assert len(fake_client.calls) == calls


def test_reinstating_a_line_whose_stored_state_is_wrong_is_500_and_not_a_retry(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    with client_with_seeded_line.app.state.session_factory() as session, session.begin():
        line = session.get(Line, line_id)
        line.state = "suspended"
        line.state_before_suspension = None
    response = _care(client_with_seeded_line, "reinstate", line_id)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert fake_client.calls == []


def _admin(client):  # type: ignore[no-untyped-def]
    app = client.app
    return signed_in(app, add_staff(app.state.session_factory, "admin"))


def _sim_state(client, iccid: str = "8923400000000000001") -> str:  # type: ignore[no-untyped-def]
    with client.app.state.session_factory() as session:
        return session.get(Sim, iccid).state


def test_an_agent_may_suspend_and_reinstate_but_not_terminate(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    assert _care(client_with_seeded_line, "suspend", line_id, "s").status_code == 200
    assert _care(client_with_seeded_line, "reinstate", line_id, "r").status_code == 200
    calls_before = len(fake_client.calls)
    refused = _care(client_with_seeded_line, "terminate", line_id, "t")
    assert refused.status_code == 403
    assert len(fake_client.calls) == calls_before
    assert _line_state(client_with_seeded_line, line_id) == "active"
    assert _sim_state(client_with_seeded_line) == "in_use"


def test_an_admin_terminates_a_line_and_its_sim_is_retired(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    admin = _admin(client_with_seeded_line)
    response = _care(admin, "terminate", line_id, "t1", "lost_sim", reason_text="stolen")
    assert response.status_code == 200
    assert response.json()["state"] == "terminated"
    assert _line_state(client_with_seeded_line, line_id) == "terminated"
    assert _sim_state(client_with_seeded_line) == "retired"
    with client_with_seeded_line.app.state.session_factory() as session:
        last = session.query(LineAudit).order_by(LineAudit.id.desc()).first()
        assert (last.from_state, last.to_state) == ("active", "terminated")
        assert last.reason == "lost_sim: stolen"
        assert last.actor.startswith("staff:")


def test_terminating_twice_with_the_same_key_answers_the_first_result(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    admin = _admin(client_with_seeded_line)
    first = _care(admin, "terminate", line_id, "same")
    calls = len(fake_client.calls)
    second = _care(admin, "terminate", line_id, "same")
    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == first.json()
    assert len(fake_client.calls) == calls


def test_a_terminated_line_cannot_be_terminated_again(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    admin = _admin(client_with_seeded_line)
    assert _care(admin, "terminate", line_id, "t1").status_code == 200
    again = _care(admin, "terminate", line_id, "t2")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "conflict"


def test_terminating_an_unknown_line_is_404(client_with_seeded_line) -> None:
    admin = _admin(client_with_seeded_line)
    assert _care(admin, "terminate", 99999, "t").status_code == 404


def test_when_ratellink_fails_terminate_changes_nothing_and_the_retry_goes_through(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    _activate(client_with_seeded_line, line_id)
    admin = _admin(client_with_seeded_line)
    fake_client.fail_on_deactivate = RatelLinkError("secret detail 621000000000001", status=503)
    failed = _care(admin, "terminate", line_id, "t")
    assert failed.status_code == 502
    assert "621000000000001" not in failed.text
    assert _line_state(client_with_seeded_line, line_id) == "active"
    assert _sim_state(client_with_seeded_line) == "in_use"

    fake_client.fail_on_deactivate = None
    assert _care(admin, "terminate", line_id, "t").status_code == 200
    assert _sim_state(client_with_seeded_line) == "retired"


# --- M-26 line lookup ------------------------------------------------------------
#
# The 100,000-row database is seeded once per module (scope="module"), with bulk
# inserts rather than per-row ORM adds.


@pytest.fixture(scope="module")
def client_with_100k_lines(tmp_path_factory) -> Iterator[TestClient]:
    """100,000 lines in the table, so a lookup is a real index probe."""
    tmp = tmp_path_factory.mktemp("100k")
    engine = create_engine(f"sqlite:///{tmp / 'big.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory() as s:
        customer = Customer(
            name="Alice",
            phone="2348000000001",
            email="alice@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="addr",
            kyc_status="verified",
        )
        plan = Plan(
            name="Basic",
            price_kobo=500,
            validity_days=30,
            data_bytes=1_000_000,
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            slow_ul_mbps=1,
            slow_dl_mbps=1,
            channels="data",
            on_exhaustion="slow",
            state="on_sale",
        )
        s.add_all([customer, plan])
        s.flush()

        s.execute(
            insert(Sim),
            [
                {
                    "iccid": f"89{n:018d}",
                    "imsi": f"621{n:012d}",
                    "batch": "bulk",
                    "state": "in_use",
                }
                for n in range(100_000)
            ],
        )
        s.execute(
            insert(Number),
            [{"msisdn": f"234{n:010d}", "state": "in_use"} for n in range(100_000)],
        )
        s.execute(
            insert(Line),
            [
                {
                    "customer_id": customer.customer_id,
                    "iccid": f"89{n:018d}",
                    "imsi": f"621{n:012d}",
                    "msisdn": f"234{n:010d}",
                    "plan_id": plan.plan_id,
                    "state": "active",
                }
                for n in range(100_000)
            ],
        )
        s.commit()

    app = make_app(factory)
    email = add_staff(factory, "agent")

    with signed_in(app, email) as client:
        yield client


SEEDED_LINE_ID = 50001
SEEDED_MSISDN = "2340000050000"
SEEDED_ICCID = "89000000000000050000"
SEEDED_IMSI = "621000000050000"


def _timed_get(client: TestClient, url: str) -> tuple[int, float]:
    started = time.monotonic()
    response = client.get(url)
    elapsed = time.monotonic() - started
    return response.status_code, elapsed


def test_lookup_by_line_id_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup/{SEEDED_LINE_ID}")
    assert status == 200
    assert elapsed < 1.0, f"line_id lookup took {elapsed:.3f}s"


def test_lookup_by_msisdn_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}")
    assert status == 200
    assert elapsed < 1.0, f"msisdn lookup took {elapsed:.3f}s"
    body = client_with_100k_lines.get(f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}").json()
    assert body["line_id"] == SEEDED_LINE_ID


def test_lookup_by_iccid_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?iccid={SEEDED_ICCID}")
    assert status == 200
    assert elapsed < 1.0, f"iccid lookup took {elapsed:.3f}s"


def test_lookup_by_imsi_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?imsi={SEEDED_IMSI}")
    assert status == 200
    assert elapsed < 1.0, f"imsi lookup took {elapsed:.3f}s"


def test_lookup_with_no_identifier_is_422(client_with_100k_lines) -> None:
    assert client_with_100k_lines.get("/v1/lines/lookup").status_code == 422


def test_lookup_with_two_identifiers_is_422(client_with_100k_lines) -> None:
    response = client_with_100k_lines.get(
        f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}&imsi={SEEDED_IMSI}"
    )
    assert response.status_code == 422


def test_lookup_of_unknown_line_is_404(client_with_100k_lines) -> None:
    assert client_with_100k_lines.get("/v1/lines/lookup/99999999").status_code == 404
    assert client_with_100k_lines.get("/v1/lines/lookup?msisdn=2349999999999").status_code == 404
