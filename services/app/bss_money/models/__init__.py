"""Models: the SQLAlchemy tables of RatelBSS: money. Used only by the repositories and by Alembic.

May import: SQLAlchemy and `app.db`. Must not import: any other bss_money layer, FastAPI. Importing
this package registers every table with `app.db.Base`, which is how `app/models.py` lets Alembic see
them. Money is BIGINT kobo.
"""

from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.models.rating import UsageRating
from app.bss_money.models.vouchers import Voucher, VoucherAttempt

__all__ = [
    "AllowanceBucket",
    "LedgerEntry",
    "UsageRating",
    "Voucher",
    "VoucherAttempt",
    "Wallet",
]
