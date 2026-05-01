"""Handlers globais de exceção para FastAPI."""
from __future__ import annotations
import structlog

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import GCAException

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globais. Chamar uma vez em main.py após criar o app."""

    @app.exception_handler(GCAException)
    async def gca_exception_handler(
        request: Request, exc: GCAException
    ) -> JSONResponse:
        logger.error(
            "gca_exception",
            exc_info=exc,
            code=exc.code,
            context=exc.context,
            path=str(request.url.path),
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.to_dict()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            exc_info=exc,
            path=str(request.url.path),
            method=request.method,
            exception_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "GCA_UNHANDLED",
                    "message": "Internal server error",
                    "context": {},
                }
            },
        )
