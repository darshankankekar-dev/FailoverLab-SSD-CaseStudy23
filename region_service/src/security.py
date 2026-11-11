from typing import Optional
from fastapi import Header, HTTPException, status
from .config import settings


async def verify_internal_access(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    """
    Validates internal authentication token if configured in settings.
    Protects administrative and replication endpoints against direct public requests.
    """
    if not settings.internal_api_secret:
        return  # No secret required in default/open development mode

    token = x_internal_secret or x_internal_token
    if not token or token != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid internal service credential required.",
        )

