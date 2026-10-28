"""What can be sold: the plans on sale and the free SIMs and numbers (M-26).

A SIM's keys are never here: RatelBSS keeps ICCID, IMSI and batch only (PRODUCT_RULES.md, SIMs).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.bss_lines.repositories.desk_ports import CatalogRepository, PlanRecord, SimRecord


def plans_on_sale(catalog: CatalogRepository) -> Sequence[PlanRecord]:
    return catalog.plans_on_sale()


def free_sims(catalog: CatalogRepository, limit: int) -> Sequence[SimRecord]:
    return catalog.free_sims(limit)


def free_numbers(catalog: CatalogRepository, limit: int) -> Sequence[str]:
    return catalog.free_numbers(limit)
