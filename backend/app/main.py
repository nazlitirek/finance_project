"""BIST Intelligence backend. Çalıştırma: uvicorn app.main:app --reload (backend klasöründen)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api import routes_data, routes_health, routes_stocks
from app.core.config import get_settings
from app.core.logging import setup_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    sched = None
    if get_settings().scheduler_enabled:
        from app.ingest import scheduler

        sched = scheduler.start()
    yield
    if sched is not None:
        sched.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.secret_values())

    app = FastAPI(title="BIST Intelligence API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": "http_error", "message": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request", "message": "İstek parametreleri geçersiz.", "details": exc.errors()},
        )

    @app.exception_handler(OperationalError)
    async def _db_error(_: Request, exc: OperationalError):
        log.error("Veritabanı hatası: %s", exc.__class__.__name__)
        return JSONResponse(
            status_code=503,
            content={"error": "database_unavailable", "message": "Veritabanına şu anda ulaşılamıyor."},
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("Beklenmeyen hata")
        return JSONResponse(status_code=500, content={"error": "internal_error", "message": "Beklenmeyen bir hata oluştu."})

    app.include_router(routes_health.router, prefix="/api")
    app.include_router(routes_stocks.router, prefix="/api")
    app.include_router(routes_data.router, prefix="/api")
    return app


app = create_app()
