"""Schema rules: no ki or opc anywhere, ever."""

from __future__ import annotations

import app.bss_lines.models.lines  # noqa: F401 -- registers the models
from app.db import Base


def test_no_ki_or_opc_columns_anywhere() -> None:
    forbidden = {"ki", "opc"}
    for table in Base.metadata.tables.values():
        for col in table.columns:
            assert col.name not in forbidden, (
                f"{table.name}.{col.name}: ki/opc must never appear in BSS tables"
            )
