import enum


class ControllerState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    PRIMARY_SUSPECTED = "PRIMARY_SUSPECTED"
    QUORUM_CHECK = "QUORUM_CHECK"
    FENCING_PRIMARY = "FENCING_PRIMARY"
    PROMOTING_STANDBY = "PROMOTING_STANDBY"
    ROUTE_UPDATING = "ROUTE_UPDATING"
    VERIFYING_ROUTE = "VERIFYING_ROUTE"
    SECONDARY_ACTIVE = "SECONDARY_ACTIVE"
    FAILOVER_BLOCKED = "FAILOVER_BLOCKED"
    PRIMARY_RECOVERING = "PRIMARY_RECOVERING"
    FAILBACK_PENDING = "FAILBACK_PENDING"
    FAILBACK_IN_PROGRESS = "FAILBACK_IN_PROGRESS"


class RegionId(str, enum.Enum):
    REGION_A = "region-a"
    REGION_B = "region-b"


class RegionRole(str, enum.Enum):
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"


class HealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class ReplicationStatus(str, enum.Enum):
    STREAMING = "STREAMING"
    DEGRADED = "DEGRADED"
    SEVERED = "SEVERED"
    REVERSED = "REVERSED"
    SYNCED = "SYNCED"


class RouteVerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class EventSeverity(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"
    SUCCESS = "success"
    ACTION = "action"


class EventSubsystem(str, enum.Enum):
    DNS = "DNS"
    DATABASE = "DATABASE"
    QUORUM = "QUORUM"
    FENCING = "FENCING"
    CONTROLLER = "CONTROLLER"
    NETWORK = "NETWORK"
    CHAOS = "CHAOS"
    SAFETY_GATE = "SAFETY_GATE"


class TransitionStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class QuorumVote(str, enum.Enum):
    PRIMARY_OUTAGE = "PRIMARY_OUTAGE"
    PRIMARY_HEALTHY = "PRIMARY_HEALTHY"
    ABSTAIN = "ABSTAIN"

