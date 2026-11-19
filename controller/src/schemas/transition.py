from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from .common import ControllerState, TransitionStatus, RegionId


class FailoverRequest(BaseModel):
    force: bool = Field(default=False, description="Manual override bypass for drill execution")
    target_region: Optional[Union[RegionId, Literal["auto"], str]] = Field(
        default="auto", description="Desired destination region, or 'auto' for dynamic candidate selection"
    )
    reason: Optional[str] = Field(default="Manual operator drill or failover trigger")


class FailbackRequest(BaseModel):
    operator_id: str = Field(..., description="Operator identifier authorizing guarded failback")
    confirmation: bool = Field(..., description="Explicit confirmation of deliberate failback")
    target_region: Optional[Union[RegionId, str]] = Field(default=RegionId.REGION_A, description="Original primary region")
    reason: Optional[str] = Field(default="Guarded failback after data reconciliation")


class ResetRequest(BaseModel):
    preserve_policy: bool = Field(default=False, description="Whether to retain customized policy thresholds on reset")


class GateEvaluationResult(BaseModel):
    gate_name: str
    passed: bool
    reason: str
    details: Optional[Dict[str, Any]] = None


class TransitionResponse(BaseModel):
    status: TransitionStatus
    previous_state: ControllerState
    current_state: ControllerState
    fencing_epoch: int
    message: str
    blocked_reason: Optional[str] = None
    gate_results: List[GateEvaluationResult] = Field(default_factory=list)

