"""Which Idempotency-Key created which record, so a repeated create returns the first one.

Only the key and the id of what was created are stored. Never the request or the answer: a customer
record holds a name and a NIN, and a second copy of it in this table would be a second place to
protect. A repeat reads the real record back and compares the request with it, field by field.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class IdempotentCreate(Base, TimestampMixin):
    __tablename__ = "idempotent_create"

    # What was created ("customer", "line"): the same string on two operations is two keys.
    scope: Mapped[str] = mapped_column(String(20), primary_key=True)
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer)
