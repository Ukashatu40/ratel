import pytest
from pydantic import BaseModel, ValidationError

from common.money import Kobo, NonNegativeKobo, kobo


class Entry(BaseModel):
    amount_kobo: Kobo
    price_kobo: NonNegativeKobo = 0


def test_integer_kobo_accepted() -> None:
    assert Entry(amount_kobo=-500).amount_kobo == -500


@pytest.mark.parametrize("bad", [1.5, 1.0, "100", None, True])
def test_non_integer_kobo_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        Entry(amount_kobo=bad)  # type: ignore[arg-type]


def test_negative_price_rejected() -> None:
    with pytest.raises(ValidationError):
        Entry(amount_kobo=1, price_kobo=-1)


def test_kobo_boundary_helper() -> None:
    assert kobo(100) == 100
    for bad in (1.0, "1", True):
        with pytest.raises(TypeError):
            kobo(bad)  # type: ignore[arg-type]
