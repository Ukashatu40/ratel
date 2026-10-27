"""Staff accounts and their sign-in sessions.

`password_hash` is a salted scrypt hash, never the password. `staff_session.token_hash` is the
SHA-256 of the cookie's value, never the value, so a copy of this table cannot be used to sign in.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class StaffUser(Base, TimestampMixin):
    __tablename__ = "staff_user"
    __table_args__ = (CheckConstraint("role IN ('agent', 'admin')", name="role_valid"),)

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    failed_logins: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StaffSession(Base, TimestampMixin):
    __tablename__ = "staff_session"
    __table_args__ = (Index("ix_staff_session_staff_id", "staff_id"),)

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff_user.staff_id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
