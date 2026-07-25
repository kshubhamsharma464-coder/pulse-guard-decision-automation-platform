"""Permission -- catalog entry for a single grantable capability, e.g.
"incidents:evaluate" or "rules:manage". Roles reference these by code
(see role.py's docstring for why roles don't use a join table)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Permission:
    code: str
    description: str = ""
    created_at: Optional[datetime] = None
