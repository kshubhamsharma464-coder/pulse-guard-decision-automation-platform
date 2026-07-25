"""APIKey -- an alternative credential to a JWT, for machine-to-machine
callers. The raw key is shown to the caller exactly once at creation time
and never stored; only `hashed_key` (same PBKDF2 scheme as user passwords,
see app/core/security.py) is persisted, plus `key_prefix` (the first 8
chars of the raw key, stored in plaintext) so lookups don't require
hashing every stored key against every incoming request -- the prefix
narrows to (in practice) a single candidate row, then the hash is verified
against just that one."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class APIKey:
    id: str
    key_prefix: str
    hashed_key: str
    owner_user_id: Optional[str] = None
    name: str = ""
    roles: List[str] = field(default_factory=lambda: ["viewer"])
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
