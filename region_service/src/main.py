import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .logging_config import setup_structured_logging, StructuredLoggingMiddleware, region_id_ctx, fencing_epoch_ctx
from .database import init_db
from .api.health import router as health_router
from .api.records import router as records_router
from .api.replication import router as replication_router
from .api.admin import admin_router

setup_structured_logging(service_name=f"region-{settings.region_id}", log_level=settings.log_level)
logger = logging.getLogger("region.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    region_id_ctx.set(settings.region_id)
    fencing_epoch_ctx.set(settings.initial_epoch)
    logger.info(f"Starting {settings.app_name} for Region '{settings.region_id}' ({settings.region_name})")
    logger.info(f"Database: {settings.sanitized_database_url}")
    await init_db()
    yield
    logger.info(f"Shutting down {settings.app_name} for Region '{settings.region_id}'")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} - {settings.region_name}",
        version=settings.app_version,
        description=f"Regional Data Service for {settings.region_name} ({settings.region_id}, {settings.cloud_zone})",
        lifespan=lifespan,
    )

    app.add_middleware(StructuredLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error handling {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal regional error occurred."},
        )

    app.include_router(health_router)
    app.include_router(records_router)
    app.include_router(replication_router)
    app.include_router(admin_router)

    return app


app = create_app()
