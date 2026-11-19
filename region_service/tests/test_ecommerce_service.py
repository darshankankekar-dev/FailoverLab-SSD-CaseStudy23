import pytest
from httpx import AsyncClient
from sqlalchemy import select
from region_service.src.models import RecordEntity, OutboxEventEntity, RegionalMetadataEntity


@pytest.mark.asyncio
async def test_ecommerce_catalog_and_inventory(client: AsyncClient, db_session):
    # 1. Product catalog is accessible
    res_cat = await client.get("/api/ecommerce/products")
    assert res_cat.status_code == 200
    products = res_cat.json()
    assert len(products) >= 5
    laptop = next((p for p in products if p["id"] == "prod-laptop-01"), None)
    assert laptop is not None
    assert laptop["price"] == 1299.0

    # 2. Product details
    res_detail = await client.get("/api/ecommerce/products/prod-laptop-01")
    assert res_detail.status_code == 200
    assert res_detail.json()["name"] == "ThinkStation Ultra 16"

    # 3. Product inventory
    res_inv = await client.get("/api/ecommerce/inventory/prod-laptop-01")
    assert res_inv.status_code == 200
    assert res_inv.json()["stock"] >= 1


@pytest.mark.asyncio
async def test_order_creation_on_active_writer_and_outbox_emission(client: AsyncClient, db_session):
    # Set region to ACTIVE
    res_m = await db_session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res_m.scalar_one()
    meta.role = "ACTIVE"
    meta.accepts_writes = True
    meta.is_fenced = False
    await db_session.commit()

    # Get initial stock
    res_inv_before = await client.get("/api/ecommerce/inventory/prod-phone-02")
    stock_before = res_inv_before.json()["stock"]

    # Place order
    res_order = await client.post(
        "/api/ecommerce/orders",
        json={
            "product_id": "prod-phone-02",
            "quantity": 2,
            "customer_email": "buyer@example.com",
            "client_region": "ap-south-1",
        },
    )
    assert res_order.status_code == 201
    order_data = res_order.json()
    assert order_data["status"] == "CONFIRMED"
    assert order_data["quantity"] == 2
    order_id = order_data["order_id"]

    # Verify inventory was deducted atomically
    res_inv_after = await client.get("/api/ecommerce/inventory/prod-phone-02")
    assert res_inv_after.json()["stock"] == stock_before - 2

    # Verify outbox events were transactionally created for replication
    res_outbox = await db_session.execute(
        select(OutboxEventEntity).where(OutboxEventEntity.record_key.in_([f"order:{order_id}", "inventory:prod-phone-02"]))
    )
    events = res_outbox.scalars().all()
    assert len(events) >= 1

    # Verify order lookup
    res_lookup = await client.get(f"/api/ecommerce/orders/{order_id}")
    assert res_lookup.status_code == 200
    assert res_lookup.json()["order_id"] == order_id


@pytest.mark.asyncio
async def test_order_creation_strictly_rejected_on_standby_region(client: AsyncClient, db_session):
    # Demote region to STANDBY
    res_m = await db_session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res_m.scalar_one()
    meta.role = "STANDBY"
    meta.accepts_writes = False
    await db_session.commit()

    # Attempt to place order
    res_order = await client.post(
        "/api/ecommerce/orders",
        json={
            "product_id": "prod-laptop-01",
            "quantity": 1,
        },
    )
    assert res_order.status_code == 403
    assert "STANDBY_READ_ONLY" in str(res_order.json()["detail"])
