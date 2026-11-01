"""The example bodies RatelDesk's tests use are valid against the contract.

web/desk/tests/fixtures/contract/<Schema>.<label>.json is a response body of the contract's
schema <Schema>. The Desk's adapters (web/desk/src/screens/*/contract.ts) are tested against
these files, so a fixture that drifts from the contract would let a wrong adapter pass.
Synthetic data only: no real person, number or card.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from tests.contract.helpers import ROOT, load_contract

FIXTURES = ROOT / "web/desk/tests/fixtures/contract"
PATHS = sorted(FIXTURES.glob("*.json"))


def _validator(schema_name: str) -> Draft202012Validator:
    spec = load_contract()
    assert schema_name in spec["components"]["schemas"], f"{schema_name} is not in the contract"
    # The whole components section travels with the reference, so nested refs resolve.
    ref = {"$ref": f"#/components/schemas/{schema_name}", "components": spec["components"]}
    return Draft202012Validator(ref)


def test_there_are_fixtures() -> None:
    assert PATHS, "web/desk/tests/fixtures/contract is empty"


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.name)
def test_a_fixture_is_valid_against_its_schema(path: Path) -> None:
    body: Any = json.loads(path.read_text())
    _validator(path.name.split(".")[0]).validate(body)


def test_the_check_can_fail() -> None:
    """A field the contract does not have, or a missing required one, is refused."""
    validator = _validator("Line")
    body = json.loads((FIXTURES / "Line.created.json").read_text())
    with pytest.raises(ValidationError):
        validator.validate({**body, "customerId": 1})  # camelCase is not the contract's shape
    del body["line_id"]
    with pytest.raises(ValidationError):
        validator.validate(body)
