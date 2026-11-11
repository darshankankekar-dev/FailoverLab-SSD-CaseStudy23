import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from gateway.src.main import app, route_table


@pytest.fixture(autouse=True)
def reset_route_table():
    """Resets route table to known default state before each test."""
    route_table.set_target("region-a", dns_ttl_seconds=2, propagation_percent=100)
    route_table.route_epoch = 1
    yield


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

