"""Role -- a named bundle of permission codes. Deliberately modeled as a
JSON array of permission codes on the role itself rather than a full
role_permissions join table: with a handful of roles and a few dozen
permission codes, a join table buys referential integrity at the cost of
real complexity (join queries, migration churn every time a permission is
added to a role) for a benefit this project doesn't need yet. The
Permission catalog (app/domain/entities/permission.py) still exists as the
source of truth for which codes are valid -- RoleRepository
implementations validate against it on save."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Role:
    code: str
    name: str
    permissions: List[str] = field(default_factory=list)
    description: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
