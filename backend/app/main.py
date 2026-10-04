from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import auth_router, rentals_router, vehicles_router

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Proactive bucket creation so the first upload does not fail on a cold start.
    try:
        from app.services.storage import get_storage

        get_storage()
        logger.info("object storage ready")
    except Exception:
        logger.warning("object storage unavailable at boot; uploads will fail until it is up")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "Vehicle rental platform API. Authoritative validation is Pydantic "
            "(SPEC §3.6); business rules R1–R5 are enforced in the service layer."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Uniform envelope for Pydantic failures (SPEC §3.3)."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request payload failed validation.",
                    "errors": [
                        {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")}
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (auth_router, vehicles_router, rentals_router):
        app.include_router(router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
