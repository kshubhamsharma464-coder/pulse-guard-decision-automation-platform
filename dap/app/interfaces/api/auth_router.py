"""Registration, login, token refresh, and "who am I". All additive --
nothing here is on the request path of any pre-existing endpoint unless a
caller opts in by presenting credentials."""

import jwt
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.settings import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.interfaces.api.schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse,
)
from app.interfaces.api.security import Principal, get_current_principal, require_permission
from app.interfaces.api.dependencies import (
    register_user_use_case, authenticate_user_use_case, user_repository,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def _issue_tokens(user_id: str, roles) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        accessToken=create_access_token(
            subject=user_id, roles=roles, secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm, expires_minutes=settings.jwt_access_token_minutes,
        ),
        refreshToken=create_refresh_token(
            subject=user_id, secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm, expires_days=settings.jwt_refresh_token_days,
        ),
        tokenType="bearer",
        expiresInMinutes=settings.jwt_access_token_minutes,
    )


@router.post("/register", response_model=UserResponse, summary="Register a new user")
def register(body: RegisterRequest):
    try:
        user = register_user_use_case.execute(
            email=body.email, password=body.password, full_name=body.fullName, roles=body.roles,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserResponse(id=user.id, email=user.email, fullName=user.full_name, roles=user.roles, isActive=user.is_active)


@router.post("/login", response_model=TokenResponse, summary="Exchange email/password for an access + refresh token pair")
def login(body: LoginRequest):
    try:
        user = authenticate_user_use_case.execute(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return _issue_tokens(user.id, user.roles)


@router.post("/refresh", response_model=TokenResponse, summary="Exchange a refresh token for a new access + refresh token pair")
def refresh(body: RefreshRequest):
    settings = get_settings()
    try:
        payload = decode_token(
            body.refreshToken, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm, expected_type="refresh",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired refresh token: {exc}")

    user = user_repository.get_by_id(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists or is inactive")
    return _issue_tokens(user.id, user.roles)


@router.get("/me", response_model=UserResponse, summary="Current authenticated user")
def me(principal: Principal = Depends(get_current_principal)):
    if not principal.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No credentials presented")
    user = user_repository.get_by_id(principal.subject)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(id=user.id, email=user.email, fullName=user.full_name, roles=user.roles, isActive=user.is_active)
