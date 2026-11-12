import logging
from typing import Optional
from fastapi import Header, HTTPException, status
from .config import settings

logger = logging.getLogger("controller.security")


async def verify_admin_access(
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret"),
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
    authorization: Optional[str] = Header(None),
) -> None:
    """
    Enforces authentication for sensitive administrative operations
    (failover, failback, reset, policy mutation, chaos simulation).

    - In development / local testing (require_admin_auth=False): open by default.
    - In production (require_admin_auth=True): strictly requires X-Admin-Secret,
      X-Internal-Secret, or Authorization: Bearer <token> matching the configured secret.
    """
    if not settings.require_admin_auth:
        return

    token = x_admin_secret or x_internal_secret
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    expected = settings.admin_api_secret or settings.internal_api_secret
    if not token or token != expected:
        logger.warning("Rejected unauthorized request to administrative endpoint.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Admin-Secret or X-Internal-Secret header required for administrative operations.",
        )

