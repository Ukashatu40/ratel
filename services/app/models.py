"""Import every model module here so Alembic autogenerate sees the full metadata.

Empty on purpose: tables arrive with their issues (see docs/issues-week2/).
"""

from app.db import Base
from app.meter_api.models import UsageRecordModel

__all__ = ["Base", "UsageRecordModel"]
