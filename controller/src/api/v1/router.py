from fastapi import APIRouter
from .state import router as state_router
from .regions import router as regions_router
from .policy import router as policy_router
from .events import router as events_router
from .metrics import router as metrics_router
from .failover import router as failover_router
from .failback import router as failback_router
from .reset import router as reset_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(state_router)
v1_router.include_router(regions_router)
v1_router.include_router(policy_router)
v1_router.include_router(events_router)
v1_router.include_router(metrics_router)
v1_router.include_router(failover_router)
v1_router.include_router(failback_router)
v1_router.include_router(reset_router)

