"""Shared fixtures for the tests of the RatelMeter API."""

from tests.app.bss_money.postgres import (
    db,  # noqa: F401  (a real PostgreSQL, built by the migrations)
)
