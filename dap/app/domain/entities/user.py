"""User -- authenticates via email/password (JWT). `roles` holds role
codes, not embedded
Role objects, so a role's permission set can be changed centrally without
rewriting every user -- resolved to actual permissions at check time by
whatever holds a RoleRepository (see app/core/security.py)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class User:
    id: str
    email: str
    hashed_password: str
    full_name: str = ""
    roles: List[str] = field(default_factory=lambda: ["viewer"])
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
