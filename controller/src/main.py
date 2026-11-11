import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .logging_config import setup_structured_logging, StructuredLoggingMiddleware
from .database import init_db
from .api.health import router as health_router
from .api.v1.router import v1_router
from .api.internal.router import internal_router
from .api.prometheus import router as prometheus_router

# Configure structured contextual logging
setup_structured_logging(
    service_name="controller",
    log_level=settings.log_level,
    json_format=getattr(settings, "log_format", "console").lower() == "json",
)
logger = logging.getLogger("controller.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Database URL: {settings.sanitized_database_url}")
    # Initialize DB schema & seeds
    await init_db()
    yield
    logger.info(f"Shutting down {settings.app_name}")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multi-Region Active-Passive Failover Controller Plane (System Design Case Study 23)",
        lifespan=lifespan,
    )

    # Correlation ID & Context Logging Middleware
    app.add_middleware(StructuredLoggingMiddleware)

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error handling {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal controller error occurred. Sensitive details suppressed for security."},
        )

    # Mount Route Trees
    app.include_router(health_router)
    app.include_router(v1_router)
    app.include_router(internal_router)
    app.include_router(prometheus_router)

    return app


app = create_app()
