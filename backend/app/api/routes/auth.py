"""Telegram Mini App authentication."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep, auth_limit, default_limit
from app.core.security import create_access_token, validate_init_data
from app.schemas.user import (
    AuthRequest,
    AuthResponse,
    BalanceResponse,
    GuestAuthRequest,
    UserPublic,
)
from app.services import users as users_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/auth/telegram", response_model=AuthResponse, dependencies=[Depends(auth_limit)])
async def authenticate(payload: AuthRequest, session: SessionDep) -> AuthResponse:
    """Exchange signed Telegram initData for a session token.

    The signature is checked against the bot token before anything is read out
    of the payload, so a client cannot claim to be another user.
    """
    tg_user = validate_init_data(payload.init_data)
    user, created = await users_service.get_or_create(
        session, tg_user, start_param=payload.start_param
    )
    users_service.ensure_active(user)
    await session.commit()
    await session.refresh(user)

    token, expires_in = create_access_token(user.id, user.telegram_id, is_admin=user.is_admin)
    logger.info("auth_ok", extra={"user_id": user.id, "is_new": created})
    return AuthResponse(
        token=token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
        is_new=created,
    )


@router.post("/auth/guest", response_model=AuthResponse, dependencies=[Depends(auth_limit)])
async def authenticate_guest(payload: GuestAuthRequest, session: SessionDep) -> AuthResponse:
    """Sign in without Telegram, for playing in a plain browser.

    Returns 403 unless ALLOW_BROWSER_LOGIN is enabled. Guest accounts are kept
    in a separate id range and can never be administrators; the Telegram path
    above is unaffected and still requires a valid signature.
    """
    user, created = await users_service.get_or_create_guest(
        session, payload.device_id, start_param=payload.start_param
    )
    users_service.ensure_active(user)
    await session.commit()
    await session.refresh(user)

    token, expires_in = create_access_token(user.id, user.telegram_id, is_admin=False)
    logger.info("guest_auth_ok", extra={"user_id": user.id, "is_new": created})
    return AuthResponse(
        token=token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
        is_new=created,
    )


@router.get("/auth/modes", dependencies=[Depends(auth_limit)])
async def auth_modes() -> dict:
    """Tells the client which sign-in paths this deployment accepts."""
    from app.services.runtime_flags import browser_login_enabled

    return {"telegram": True, "guest": await browser_login_enabled()}


@router.get("/me", response_model=UserPublic, dependencies=[Depends(default_limit)])
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.get("/balance", response_model=BalanceResponse, dependencies=[Depends(default_limit)])
async def balance(user: CurrentUser, session: SessionDep) -> BalanceResponse:
    # Always read the committed value rather than whatever the client cached.
    await session.refresh(user)
    return BalanceResponse(balance=int(user.balance))
