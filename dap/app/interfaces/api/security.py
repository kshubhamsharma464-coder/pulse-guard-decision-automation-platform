"""FastAPI-level authentication/authorization dependencies. Resolves a
request's credentials (JWT bearer token) into a Principal, then
require_permission(...) enforces RBAC against it.

Backward-compatibility contract: when Settings.auth_required is False
(the default), a request with NO credentials at all resolves to an
anonymous Principal that require_permission() lets through unchecked --
this is what keeps every existing unauthenticated endpoint working
unmodified. A request that DOES present credentials is always validated
for real, even when auth isn't required overall -- presenting a bad token
is never silently ignored, only its absence is tolerated.

Role -> permission resolution happens once per request against
RoleRepository, not baked permanently into the JWT, so a role's
permission set can change and take effect on every new request without
waiting for tokens to expire (only the token's *role codes* are cached in
the JWT itself, at issuance time -- see app/core/security.py)."""

from dataclasses import dataclass, field
from typing import List, Optional, Set

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.settings import get_settings
from app.core.security import decode_token


@dataclass
class Principal:
    subject: str
    roles: List[str] = field(default_factory=list)
    permissions: Set[str] = field(default_factory=set)
    auth_method: str = "anonymous"  # "anonymous" | "jwt"
    is_authenticated: bool = False


def _resolve_permissions(roles: List[str]) -> Set[str]:
    from app.interfaces.api.dependencies import role_repository
    permissions: Set[str] = set()
    for code in roles:
        role = role_repository.get_by_code(code)
        if role is not None:
            permissions.update(role.permissions)
    return permissions


def get_current_principal(
    authorization: Optional[str] = Header(None),
) -> Principal:
    settings = get_settings()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(
                token, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm, expected_type="access"
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired access token: {exc}")
        roles = payload.get("roles", [])
        return Principal(
            subject=payload["sub"], roles=roles, permissions=_resolve_permissions(roles),
            auth_method="jwt", is_authenticated=True,
        )

    if settings.auth_required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    return Principal(subject="anonymous", roles=[], permissions=set(), auth_method="anonymous", is_authenticated=False)


def require_permission(permission_code: str):
    """Dependency factory -- `Depends(require_permission("decisions:override"))`.
    Anonymous + auth not required => pass through unchanged (Phase-1 behavior).
    Anonymous + auth required => already rejected upstream by get_current_principal.
    Authenticated (JWT), regardless of auth_required => permission is always
    actually checked."""

    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        settings = get_settings()
        if not settings.auth_required and not principal.is_authenticated:
            return principal
        if permission_code not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: '{permission_code}'",
            )
        return principal
    return _dependency
