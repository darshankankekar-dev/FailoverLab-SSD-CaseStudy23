from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db_session
from ..schemas import RecordCreateRequest, RecordUpdateRequest, RecordResponse
from ..services.record_service import (
    write_record,
    get_record,
    list_records,
    delete_record,
)

router = APIRouter(prefix="/api/records", tags=["Records"])


@router.get("", response_model=List[RecordResponse])
async def get_all_records(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> List[RecordResponse]:
    """Reads all committed application records (permitted on ACTIVE and STANDBY)."""
    records = await list_records(session, limit=limit, offset=offset)
    return [RecordResponse.model_validate(r) for r in records]


@router.get("/{key}", response_model=RecordResponse)
async def get_single_record(
    key: str,
    session: AsyncSession = Depends(get_db_session),
) -> RecordResponse:
    """Reads a single record by key (permitted on ACTIVE and STANDBY)."""
    rec = await get_record(session, key)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record '{key}' not found.",
        )
    return RecordResponse.model_validate(rec)


@router.post("", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    payload: RecordCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RecordResponse:
    """
    Creates an application record.
    Strictly verifies writer authority:
    - STANDBY regions reject writes with HTTP 403.
    - Fenced regions reject writes with HTTP 403.
    - Stale fencing epochs are rejected with HTTP 409.
    Creates an ordered outbox replication event transactionally.
    """
    rec = await write_record(
        session,
        key=payload.key,
        value=payload.value,
        caller_epoch=payload.fencing_epoch,
    )
    return RecordResponse.model_validate(rec)


@router.put("/{key}", response_model=RecordResponse)
async def update_record(
    key: str,
    payload: RecordUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RecordResponse:
    """Updates an application record with writer safety validation."""
    rec = await write_record(
        session,
        key=key,
        value=payload.value,
        caller_epoch=payload.fencing_epoch,
    )
    return RecordResponse.model_validate(rec)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_record(
    key: str,
    fencing_epoch: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_db_session),
):
    """Deletes an application record with writer safety validation."""
    await delete_record(session, key=key, caller_epoch=fencing_epoch)
    return None

