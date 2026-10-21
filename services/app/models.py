"""Import every model module here so Alembic autogenerate sees the full metadata.

Tables arrive with their issues (docs/issues-modules/). Add each module's models package below.
"""

from app.bss_lines import models as bss_lines_models
from app.bss_money import models as bss_money_models
from app.db import Base
from app.meter_api.models import UsageRecordModel

__all__ = ["Base", "bss_lines_models", "bss_money_models"]
