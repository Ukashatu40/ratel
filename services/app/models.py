"""Import every model module here so Alembic autogenerate sees the full metadata.

Tables arrive with their issues (docs/issues-modules/). Add each module's models package below.
"""

from app.bss_money import models as bss_money_models
from app.db import Base

__all__ = ["Base", "bss_money_models"]
