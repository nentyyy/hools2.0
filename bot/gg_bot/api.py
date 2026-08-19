"""HTTP client for the backend's internal API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from gg_bot.config import settings

logger = logging.getLogger(__name__)


class BackendError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{settings.internal_base}{path}"
    headers = {"X-Internal-Token": settings.internal_api_token, **kwargs.pop("headers", {})}
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        logger.error("backend unreachable: %s", exc)
        raise BackendError("Backend is unreachable") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        logger.warning("backend error %s on %s: %s", response.status_code, path, detail)
        raise BackendError(detail, response.status_code)

    return response.json()


async def ensure_user(
    telegram_id: int,
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    language_code: str | None,
    start_param: str | None = None,
) -> dict:
    return await _request(
        "POST",
        "/internal/users/ensure",
        json={
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "language_code": language_code,
            "start_param": start_param,
        },
    )


async def get_user(telegram_id: int) -> dict:
    return await _request("GET", f"/internal/users/{telegram_id}")


async def active_giveaways(limit: int = 5) -> dict:
    return await _request("GET", "/internal/giveaways", params={"limit": limit})


async def get_config() -> dict:
    return await _request("GET", "/internal/config")


async def create_invoice(telegram_id: int, package: str) -> dict:
    return await _request(
        "POST", "/internal/payments/invoice", json={"telegram_id": telegram_id, "package": package}
    )


async def payment_history(telegram_id: int) -> dict:
    return await _request("GET", f"/internal/payments/{telegram_id}")


async def refund(admin_telegram_id: int, payment_id: int, reason: str | None = None, force: bool = False) -> dict:
    return await _request(
        "POST",
        "/internal/payments/refund",
        json={
            "admin_telegram_id": admin_telegram_id,
            "payment_id": payment_id,
            "reason": reason,
            "force": force,
        },
    )


async def precheckout(telegram_id: int, payload: str, total_amount: int, currency: str = "XTR") -> dict:
    return await _request(
        "POST",
        "/payments/stars/precheckout",
        json={
            "telegram_id": telegram_id,
            "payload": payload,
            "total_amount": total_amount,
            "currency": currency,
        },
    )


async def confirm_payment(
    *,
    telegram_id: int,
    payload: str,
    charge_id: str,
    total_amount: int,
    currency: str = "XTR",
    provider_charge_id: str | None = None,
    raw: dict | None = None,
) -> dict:
    return await _request(
        "POST",
        "/payments/stars/webhook",
        json={
            "telegram_id": telegram_id,
            "payload": payload,
            "telegram_payment_charge_id": charge_id,
            "provider_payment_charge_id": provider_charge_id,
            "total_amount": total_amount,
            "currency": currency,
            "raw": raw,
        },
    )
