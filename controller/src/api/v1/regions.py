from typing import List
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db_session
from ...schemas import RegionResponse, RegionId
from ...models import RegionEntity

router = APIRouter(tags=["Regions"])


@router.get("/regions", response_model=List[RegionResponse])
async def list_regions(session: AsyncSession = Depends(get_db_session)) -> List[RegionResponse]:
    """Lists all configured regions and their active operational statuses."""
    res = await session.execute(select(RegionEntity).order_by(RegionEntity.id))
    regions = res.scalars().all()
    return [
        RegionResponse(
            id=RegionId(r.id),
            name=r.name,
            cloud_zone=r.cloud_zone,
            role=r.role,
            health=r.health,
            status=r.status,
            accepts_writes=r.accepts_writes,
            ingress_traffic_percent=r.ingress_traffic_percent,
            ingress_rps=r.ingress_rps,
            app_servers_healthy=r.app_servers_healthy,
            app_servers_total=r.app_servers_total,
            active_connections=r.active_connections,
            iops=r.iops,
            fencing_epoch=r.fencing_epoch,
            is_fenced=r.is_fenced,
        )
        for r in regions
    ]


@router.get("/regions/{region_id}", response_model=RegionResponse)
async def get_region(
    region_id: str = Path(..., description="Region identifier (e.g. region-a, region-b)"),
    session: AsyncSession = Depends(get_db_session),
) -> RegionResponse:
    """Gets details for a specific region."""
    res = await session.execute(select(RegionEntity).where(RegionEntity.id == region_id))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail=f"Region '{region_id}' not found.")
    return RegionResponse(
        id=RegionId(r.id),
        name=r.name,
        cloud_zone=r.cloud_zone,
        role=r.role,
        health=r.health,
        status=r.status,
        accepts_writes=r.accepts_writes,
        ingress_traffic_percent=r.ingress_traffic_percent,
        ingress_rps=r.ingress_rps,
        app_servers_healthy=r.app_servers_healthy,
        app_servers_total=r.app_servers_total,
        active_connections=r.active_connections,
        iops=r.iops,
        fencing_epoch=r.fencing_epoch,
        is_fenced=r.is_fenced,
    )

