import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from fastapi import FastAPI, Query, status
from pydantic import BaseModel, Field

from .config import settings
from .lag_tracker import lag_tracker
from .replicator import engine
from .logging_config import setup_structured_logging

setup_structured_logging(service_name="replication-worker", log_level=settings.log_level)
logger = logging.getLogger("replication.main")

worker_task: Optional[asyncio.Task] = None
is_running: bool = True


async def run_worker_loop():
    logger.info("Replication worker loop started.")
    while is_running:
        try:
            await engine.sync_iteration()
        except Exception as e:
            logger.error(f"Error in replication iteration: {e}", exc_info=False)
        await asyncio.sleep(settings.poll_interval_sec)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task, is_running
    is_running = True
    worker_task = asyncio.create_task(run_worker_loop())
    yield
    is_running = False
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    logger.info("Replication worker stopped.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Application-Level Asynchronous Record Replication Worker",
    lifespan=lifespan,
)


class DelayRequest(BaseModel):
    delay_seconds: float = Field(..., ge=0.0, le=60.0, description="Artificial injected latency in seconds")


@app.get("/health")
async def health():
    return {
        "status": "alive",
        "service": "failoverlab-replication-worker",
        "is_paused": engine.is_paused,
        "source_region": engine.source_region,
        "target_region": engine.target_region,
    }


@app.get("/status")
@app.get("/metrics")
async def status_and_metrics():
    """Returns replication operational telemetry, directional topology, and measured lag."""
    return {
        "source_region": engine.source_region,
        "target_region": engine.target_region,
        "reversal_count": engine.reversal_count,
        "is_paused": engine.is_paused,
        "injected_delay_sec": engine.injected_delay_sec,
        "last_replicated_sequence_id": engine.last_replicated_seq,
        "total_applied_events": engine.total_applied_events,
        "consecutive_errors": engine.consecutive_errors,
        "lag_metrics": lag_tracker.to_dict(),
    }


@app.post("/controls/pause")
async def pause_replication():
    """Pauses replication to simulate cross-region WAN partition or fiber cut."""
    engine.is_paused = True
    logger.info("Replication worker PAUSED.")
    return {"is_paused": True, "message": "Replication successfully paused."}


@app.post("/controls/resume")
async def resume_replication():
    """Resumes replication after partition resolution."""
    engine.is_paused = False
    logger.info("Replication worker RESUMED.")
    return {"is_paused": False, "message": "Replication successfully resumed."}


@app.post("/controls/delay")
async def set_delay(payload: DelayRequest):
    """Sets artificial replication throttling delay (e.g. 8.4s for Scenario F)."""
    engine.injected_delay_sec = payload.delay_seconds
    lag_tracker.injected_delay_sec = payload.delay_seconds
    logger.info(f"Replication injected delay set to {payload.delay_seconds:.1f}s.")
    return {"injected_delay_sec": payload.delay_seconds, "message": f"Delay updated to {payload.delay_seconds:.1f}s."}


@app.post("/sync-once")
async def trigger_sync_once():
    """Triggers an immediate, deterministic replication pass (ideal for tests and drills)."""
    result = await engine.sync_iteration()
    return result

