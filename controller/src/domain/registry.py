"""
FailoverLab Regional Registry
Centralized, authoritative definition of all logical application regions.
Decouples regional configuration from hardcoded conditionals across the control plane.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RegionDefinition:
    id: str
    name: str
    cloud_zone: str
    default_role: str
    app_port: int
    db_port: int
    default_iops: int
    nominal_latency_ms: int = 20
    app_servers_healthy: int = 12
    app_servers_total: int = 12

    @property
    def region_id(self) -> str:
        return self.id

    @property
    def initial_role(self) -> str:
        return self.default_role

    @property
    def baseline_iops(self) -> int:
        return self.default_iops


# Definitive 5-region cluster registry
REGION_REGISTRY: Dict[str, RegionDefinition] = {
    "region-a": RegionDefinition(
        id="region-a",
        name="Mumbai",
        cloud_zone="ap-south-1",
        default_role="ACTIVE",
        app_port=8001,
        db_port=5432,
        default_iops=4800,
        nominal_latency_ms=18,
    ),
    "region-b": RegionDefinition(
        id="region-b",
        name="Singapore",
        cloud_zone="ap-southeast-1",
        default_role="STANDBY",
        app_port=8002,
        db_port=5433,
        default_iops=120,
        nominal_latency_ms=34,
    ),
    "region-c": RegionDefinition(
        id="region-c",
        name="Frankfurt",
        cloud_zone="eu-central-1",
        default_role="STANDBY",
        app_port=8004,
        db_port=5435,
        default_iops=120,
        nominal_latency_ms=115,
    ),
    "region-d": RegionDefinition(
        id="region-d",
        name="Virginia",
        cloud_zone="us-east-1",
        default_role="STANDBY",
        app_port=8005,
        db_port=5436,
        default_iops=120,
        nominal_latency_ms=175,
    ),
    "region-e": RegionDefinition(
        id="region-e",
        name="São Paulo",
        cloud_zone="sa-east-1",
        default_role="STANDBY",
        app_port=8006,
        db_port=5437,
        default_iops=120,
        nominal_latency_ms=240,
    ),
}


def get_region_definition(region_id: str) -> Optional[RegionDefinition]:
    """Retrieves metadata definition for a region ID."""
    return REGION_REGISTRY.get(region_id.lower().strip())


def get_all_region_definitions() -> List[RegionDefinition]:
    """Returns definitions of all registered regions in order."""
    return list(REGION_REGISTRY.values())


def get_all_region_ids() -> List[str]:
    """Returns list of all registered region identifiers."""
    return list(REGION_REGISTRY.keys())


def is_valid_region(region_id: str) -> bool:
    """Validates whether a region ID is registered in the cluster."""
    return region_id.lower().strip() in REGION_REGISTRY


def get_default_active_region() -> str:
    """Returns the default active primary region identifier."""
    return "region-a"


def get_default_standby_regions() -> List[str]:
    """Returns the list of standby region identifiers."""
    return [r_id for r_id, reg in REGION_REGISTRY.items() if reg.default_role == "STANDBY"]
