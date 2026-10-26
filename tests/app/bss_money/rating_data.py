"""Synthetic lines, allowances and usage for the rating job's tests. Nothing here is real data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_money.models.allowance import AllowanceBucket
from app.meter_api.models import UsageRecordModel

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)  # the "now" of most tests
DAY = timedelta(days=1)


@dataclass(frozen=True)
class SeededLine:
    line_id: int
    imsi: str
    plan_id: int


def seed_line(
    session: Session, n: int = 1, *, state: str = "active", on_exhaustion: str = "slow"
) -> SeededLine:
    """A customer, SIM, number, plan and line, all synthetic, numbered by `n`."""
    imsi = f"62100000000{n:04d}"
    session.add(
        Customer(
            name=f"Test Customer {n}",
            phone=f"0800000{n:04d}",
            email=f"test{n}@example.invalid",
            id_type="NIN",
            id_number=f"{n:011d}",
            address="unknown",
            kyc_status="verified",
        )
    )
    session.add(Sim(iccid=f"89000000000000{n:05d}", imsi=imsi, batch="test", state="in_use"))
    session.add(Number(msisdn=f"23480000{n:05d}", state="in_use"))
    plan = Plan(
        name=f"Test plan {n}",
        price_kobo=100_000,
        validity_days=30,
        data_bytes=1_000,
        speed_ul_mbps=5.0,
        speed_dl_mbps=10.0,
        slow_ul_mbps=0.5 if on_exhaustion == "slow" else None,
        slow_dl_mbps=1.0 if on_exhaustion == "slow" else None,
        channels="data",
        on_exhaustion=on_exhaustion,
        state="on_sale",
    )
    session.add(plan)
    session.flush()
    customer_id = (
        session.query(Customer.customer_id).filter(Customer.name == f"Test Customer {n}").scalar()
    )
    line = Line(
        customer_id=customer_id,
        iccid=f"89000000000000{n:05d}",
        imsi=imsi,
        msisdn=f"23480000{n:05d}",
        plan_id=plan.plan_id,
        state=state,
    )
    session.add(line)
    session.flush()
    return SeededLine(line.line_id, imsi, plan.plan_id)


def add_bucket(
    session: Session,
    line: SeededLine,
    total: int,
    *,
    starts: datetime = T0 - DAY,
    expires: datetime = T0 + 29 * DAY,
    used: int = 0,
) -> int:
    bucket = AllowanceBucket(
        line_id=line.line_id,
        source_kind="plan",
        source_id=line.plan_id,
        data_bytes_total=total,
        data_bytes_used=used,
        valid_from=starts,
        valid_to=expires,
    )
    session.add(bucket)
    session.flush()
    return bucket.bucket_id


def add_usage(
    session: Session, line: SeededLine, up: int, down: int, *, minutes_ago: int = 10
) -> int:
    start = T0 - timedelta(minutes=minutes_ago)
    record = UsageRecordModel(
        imsi=line.imsi,
        period_start=start,
        period_end=start + timedelta(seconds=300),
        bytes_up=up,
        bytes_down=down,
    )
    session.add(record)
    session.flush()
    return record.id
