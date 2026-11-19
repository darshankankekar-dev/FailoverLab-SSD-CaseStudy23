import logging
from typing import Optional
from fastapi import Header, HTTPException, status
from .config import settings

logger = logging.getLogger("controller.security")


async def verify_admin_access(
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
    authorization: Optional[str] = Header(None),
) -> None:
    """
    Enforces authentication for sensitive administrative operations:
    - Failover, failback, reset
    - Policy mutations
    - Chaos injections and simulation triggers

    Rules:
    1. In production (environment in 'production', 'prod'):
       Administrative authentication is MANDATORY. It cannot be silently disabled.
    2. In non-production environments (e.g. development):
       Administrative authentication is required if settings.require_admin_auth is True;
       if False, operations are allowed without auth for frictionless local testing.
    3. Secret matching:
       - Uses settings.admin_api_secret when configured.
       - If settings.admin_api_secret is not configured and not in production,
         falls back to settings.internal_api_secret for developer convenience.
       - In production, a dedicated administrative secret MUST be set.
       - Accepts X-Admin-Secret header or Authorization: Bearer <secret>.
       - Does NOT accept X-Internal-Secret (keeping Gateway internal secrets strictly separated).
    """
    is_prod = settings.environment.lower() in ("production", "prod")
    auth_required = settings.require_admin_auth or is_prod

    if not auth_required:
        return

    token = x_admin_secret
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    expected = settings.admin_api_secret or (settings.internal_api_secret if not is_prod else None)
    if not expected:
        logger.error("Administrative operation rejected: no admin_api_secret configured in production.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Administrative authentication required, but no admin secret is configured.",
        )

    if not token or token != expected:
        logger.warning("Rejected unauthorized request to administrative endpoint.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Admin-Secret or Bearer token required for administrative operations.",
        )


async def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
    authorization: Optional[str] = Header(None),
) -> None:
    """
    Strictly verifies service-to-service internal authentication (X-Internal-Secret).
    Always enforced for internal ingestion pipelines (e.g. Gateway -> Controller telemetry)
    regardless of environment mode. Kept strictly separate from operator administrative auth.
    """
    token = x_internal_secret
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    expected = settings.internal_api_secret
    if not token or token != expected:
        logger.warning("Rejected unauthorized request to internal telemetry ingestion endpoint.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Internal-Secret header required for internal telemetry ingestion.",
        )

