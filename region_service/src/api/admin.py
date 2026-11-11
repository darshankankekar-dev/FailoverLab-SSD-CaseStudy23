from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db_session
from ..schemas import (
    RegionalStatusResponse,
    EpochStatusResponse,
    FenceRequest,
    PromoteRequest,
    DemoteRequest,
)
from ..services.admin_service import (
    get_regional_status,
    fence_region,
    promote_region,
    demote_region,
)

admin_router = APIRouter(tags=["Regional Admin"])


@admin_router.get("/api/status", response_model=RegionalStatusResponse)
async def regional_status(session: AsyncSession = Depends(get_db_session)) -> RegionalStatusResponse:
    """Returns regional operational status, active role, epoch, and record counts."""
    return await get_regional_status(session)


@admin_router.post("/admin/fence", response_model=EpochStatusResponse)
@admin_router.post("/internal/admin/fence", response_model=EpochStatusResponse)
async def admin_fence(
    payload: FenceRequest,
    session: AsyncSession = Depends(get_db_session),
) -> EpochStatusResponse:
    """Invoked by the Controller to revoke write leases and establish a storage fence."""
    return await fence_region(
        session,
        epoch=payload.fencing_epoch,
        revoke_write_lease=payload.revoke_write_lease,
    )


@admin_router.post("/admin/promote", response_model=EpochStatusResponse)
@admin_router.post("/internal/admin/promote", response_model=EpochStatusResponse)
async def admin_promote(
    payload: PromoteRequest,
    session: AsyncSession = Depends(get_db_session),
) -> EpochStatusResponse:
    """Invoked by the Controller to promote standby to ACTIVE writer with a new generation epoch."""
    return await promote_region(
        session,
        epoch=payload.fencing_epoch,
        grant_write_authority=payload.grant_write_authority,
    )


@admin_router.post("/admin/demote", response_model=EpochStatusResponse)
@admin_router.post("/internal/admin/demote", response_model=EpochStatusResponse)
async def admin_demote(
    payload: DemoteRequest,
    session: AsyncSession = Depends(get_db_session),
) -> EpochStatusResponse:
    """Invoked by the Controller during guarded failback to demote active region back to STANDBY."""
    return await demote_region(session, epoch=payload.fencing_epoch)


@admin_router.get("/admin/epoch", response_model=EpochStatusResponse)
@admin_router.get("/internal/admin/epoch", response_model=EpochStatusResponse)
async def admin_epoch(session: AsyncSession = Depends(get_db_session)) -> EpochStatusResponse:
    """Returns the current fencing epoch, role, and write authority."""
    status_resp = await get_regional_status(session)
    return EpochStatusResponse(
        region_id=status_resp.region_id,
        role=status_resp.role,
        fencing_epoch=status_resp.fencing_epoch,
        accepts_writes=status_resp.accepts_writes,
        is_fenced=status_resp.is_fenced,
    )

