from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db_session
from ...schemas import StateResponse
from ...services import get_full_state

router = APIRouter(tags=["State"])


@router.get("/state", response_model=StateResponse)
async def get_state(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Returns the comprehensive live state of the multi-region topology and controller."""
    return await get_full_state(session)

