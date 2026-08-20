"""Domain errors and the handlers that turn them into JSON responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or self.__doc__ or self.code)
        self.message = message or "Request could not be processed"
        self.details = details or {}


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class InsufficientFundsError(AppError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "insufficient_funds"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class BannedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "banned"


def _error(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.info("app_error", extra={"code": exc.code, "detail": exc.message})
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Request payload is invalid",
            {"errors": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # Constraint violations are how the database enforces invariants such as
        # "balance >= 0" or "one giveaway entry per user" under concurrency.
        logger.warning("integrity_error", exc_info=exc)
        return _error(status.HTTP_409_CONFLICT, "conflict", "Operation conflicts with current state")

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_error", exc_info=exc)
        # 42703/42P01: the query names a column or table the database does not
        # have, which in practice means the deployment is ahead of its schema.
        # That is worth naming, because "storage is unavailable" sends the
        # operator looking at the database instead of at the migrations.
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if code in {"42703", "42P01"}:
            return _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "schema_outdated",
                "Database schema is out of date — apply the migrations "
                "(GET /api/internal/setup?token=<CRON_SECRET>)",
            )
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "database_error", "Storage is unavailable")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", exc_info=exc)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal server error")
