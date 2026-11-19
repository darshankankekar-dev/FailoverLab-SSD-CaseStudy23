import pytest
from httpx import AsyncClient
from src.domain.registry import (
    REGION_REGISTRY,
    get_all_region_definitions,
    get_all_region_ids,
    get_region_definition,
    is_valid_region,
)


@pytest.mark.asyncio
async def test_region_registry_definitions():
    """Confirms all 5 regions are correctly registered in the authoritative domain registry."""
    all_ids = get_all_region_ids()
    assert len(all_ids) == 5
    assert all_ids == ["region-a", "region-b", "region-c", "region-d", "region-e"]

    expected_metadata = {
        "region-a": {"name": "Mumbai", "cloud_zone": "ap-south-1", "initial_role": "ACTIVE"},
        "region-b": {"name": "Singapore", "cloud_zone": "ap-southeast-1", "initial_role": "STANDBY"},
        "region-c": {"name": "Frankfurt", "cloud_zone": "eu-central-1", "initial_role": "STANDBY"},
        "region-d": {"name": "Virginia", "cloud_zone": "us-east-1", "initial_role": "STANDBY"},
        "region-e": {"name": "São Paulo", "cloud_zone": "sa-east-1", "initial_role": "STANDBY"},
    }

    for rid, expected in expected_metadata.items():
        assert is_valid_region(rid)
        r_def = get_region_definition(rid)
        assert r_def is not None
        assert r_def.name == expected["name"]
        assert r_def.cloud_zone == expected["cloud_zone"]
        assert r_def.initial_role == expected["initial_role"]


@pytest.mark.asyncio
async def test_controller_lists_all_five_regions(client: AsyncClient):
    """Confirms GET /api/v1/regions returns all five configured regions with correct roles and metadata."""
    resp = await client.get("/api/v1/regions")
    assert resp.status_code == 200
    regions = resp.json()
    assert len(regions) == 5

    by_id = {r["id"]: r for r in regions}
    assert set(by_id.keys()) == {"region-a", "region-b", "region-c", "region-d", "region-e"}

    # Region A (Mumbai) - ACTIVE
    assert by_id["region-a"]["name"] == "Mumbai"
    assert by_id["region-a"]["role"] == "ACTIVE"
    assert by_id["region-a"]["accepts_writes"] is True

    # Regions B, C, D, E - STANDBY
    assert by_id["region-b"]["name"] == "Singapore"
    assert by_id["region-b"]["role"] == "STANDBY"
    assert by_id["region-b"]["accepts_writes"] is False

    assert by_id["region-c"]["name"] == "Frankfurt"
    assert by_id["region-c"]["role"] == "STANDBY"
    assert by_id["region-c"]["accepts_writes"] is False

    assert by_id["region-d"]["name"] == "Virginia"
    assert by_id["region-d"]["role"] == "STANDBY"
    assert by_id["region-d"]["accepts_writes"] is False

    assert by_id["region-e"]["name"] == "São Paulo"
    assert by_id["region-e"]["role"] == "STANDBY"
    assert by_id["region-e"]["accepts_writes"] is False


@pytest.mark.asyncio
async def test_controller_inspect_individual_regions(client: AsyncClient):
    """Confirms GET /api/v1/regions/{region_id} inspects each of the 5 regions individually."""
    expected_locations = {
        "region-a": "Mumbai",
        "region-b": "Singapore",
        "region-c": "Frankfurt",
        "region-d": "Virginia",
        "region-e": "São Paulo",
    }

    for region_id, name in expected_locations.items():
        resp = await client.get(f"/api/v1/regions/{region_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == region_id
        assert data["name"] == name
        assert data["health"] == "HEALTHY"


@pytest.mark.asyncio
async def test_controller_state_contains_all_five_regions(client: AsyncClient):
    """Confirms GET /api/v1/state returns all 5 regions in structured state response."""
    resp = await client.get("/api/v1/state")
    assert resp.status_code == 200
    state = resp.json()

    # Named accessors
    assert state["region_a"]["id"] == "region-a"
    assert state["region_b"]["id"] == "region-b"
    assert state["region_c"]["id"] == "region-c"
    assert state["region_d"]["id"] == "region-d"
    assert state["region_e"]["id"] == "region-e"

    # Dynamic list
    assert "regions" in state
    assert len(state["regions"]) == 5
    region_ids = [r["id"] for r in state["regions"]]
    assert set(region_ids) == {"region-a", "region-b", "region-c", "region-d", "region-e"}


@pytest.mark.asyncio
async def test_writer_safety_policy_enforcement(client: AsyncClient):
    """Confirms only region-a initially accepts writes, and all 4 standbys reject writes."""
    resp = await client.get("/api/v1/regions")
    regions = resp.json()

    writers = [r for r in regions if r["accepts_writes"]]
    standbys = [r for r in regions if not r["accepts_writes"]]

    assert len(writers) == 1, "There must be exactly ONE active writer globally"
    assert writers[0]["id"] == "region-a"

    assert len(standbys) == 4, "All other 4 regions must be standbys"
    standby_ids = {r["id"] for r in standbys}
    assert standby_ids == {"region-b", "region-c", "region-d", "region-e"}


@pytest.mark.asyncio
async def test_prometheus_metrics_export_five_regions(client: AsyncClient):
    """Confirms Prometheus metrics report failoverlab_active_region for all 5 regions."""
    resp = await client.get("/api/v1/metrics/prometheus")
    assert resp.status_code == 200
    text = resp.text

    assert 'failoverlab_active_region{region="region-a"} 1' in text
    assert 'failoverlab_active_region{region="region-b"} 0' in text
    assert 'failoverlab_active_region{region="region-c"} 0' in text
    assert 'failoverlab_active_region{region="region-d"} 0' in text
    assert 'failoverlab_active_region{region="region-e"} 0' in text
    assert 'failoverlab_healthy_regions 5' in text
