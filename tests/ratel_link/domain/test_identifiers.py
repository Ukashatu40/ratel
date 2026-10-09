"""Identifier rules."""

from ratel_link.domain.identifiers import is_imsi
from tests.synthetic import (
    SYNTHETIC_IMSI,
)


def test_is_imsi() -> None:
    assert is_imsi(SYNTHETIC_IMSI)
    assert not is_imsi(SYNTHETIC_IMSI + "\n")
    assert not is_imsi({"$ne": ""})
    assert not is_imsi(None)
