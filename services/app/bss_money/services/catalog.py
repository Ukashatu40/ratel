"""What RatelPay may show: the bundles on sale."""

from __future__ import annotations

from app.bss_money.domain.plans import Bundle
from app.bss_money.repositories.ports import CatalogScope


def bundles_on_sale(scope: CatalogScope) -> list[Bundle]:
    """Every bundle that can be bought now. Retired bundles are never listed."""
    with scope() as catalog:
        return catalog.bundles_on_sale()
