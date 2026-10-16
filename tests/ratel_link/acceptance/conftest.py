from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def quiet_driver() -> Iterator[None]:
    """These tests read and write the core's collection themselves, and it holds the keys by
    design. At DEBUG the MongoDB driver would copy those documents into the pytest log, where the
    key search (tests/conftest.py) would rightly object. RatelLink pins the driver quiet in its
    own process (test_no_key_in_any_log.py proves it); the test process has to do the same."""
    pymongo_log = logging.getLogger("pymongo")
    before = pymongo_log.level
    pymongo_log.setLevel(logging.WARNING)
    yield
    pymongo_log.setLevel(before)
