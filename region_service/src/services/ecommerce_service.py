import uuid
import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import RecordEntity, RegionalMetadataEntity, utc_now
from .record_service import write_record, get_record, validate_writer_authority

logger = logging.getLogger("region.services.ecommerce")

INITIAL_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "prod-laptop-01",
        "name": "ThinkStation Ultra 16",
        "category": "Laptops",
        "price": 1299.00,
        "description": "High-performance enterprise laptop with 32GB RAM, 1TB NVMe, and 16-inch OLED display.",
        "stock": 50,
        "rating": 4.8,
        "image_url": "/images/laptop.png",
    },
    {
        "id": "prod-phone-02",
        "name": "AuraPhone Pro 5G",
        "category": "Smartphones",
        "price": 799.00,
        "description": "Flagship 5G smartphone with 120Hz LTPO AMOLED, triple 50MP cameras, and 5000mAh battery.",
        "stock": 100,
        "rating": 4.7,
        "image_url": "/images/phone.png",
    },
    {
        "id": "prod-headset-03",
        "name": "NoiseCancel Elite X",
        "category": "Audio",
        "price": 199.00,
        "description": "Wireless over-ear noise-canceling headphones with LDAC audio and 40-hour battery life.",
        "stock": 80,
        "rating": 4.9,
        "image_url": "/images/headphones.png",
    },
    {
        "id": "prod-watch-04",
        "name": "PulseTracker BioSmart",
        "category": "Wearables",
        "price": 249.00,
        "description": "Smart health watch with ECG, continuous SpO2, sleep scoring, and 7-day battery life.",
        "stock": 65,
        "rating": 4.6,
        "image_url": "/images/watch.png",
    },
    {
        "id": "prod-monitor-05",
        "name": "ViewMaster 4K 144Hz",
        "category": "Displays",
        "price": 499.00,
        "description": "32-inch 4K UHD IPS gaming and productivity monitor with 1ms response and 98% DCI-P3.",
        "stock": 35,
        "rating": 4.8,
        "image_url": "/images/monitor.png",
    },
]


async def seed_initial_catalog_if_empty(session: AsyncSession) -> None:
    """Pre-seeds the catalog into the records table if not present."""
    res = await session.execute(
        select(RecordEntity).where(RecordEntity.key.like("catalog:%")).limit(1)
    )
    if res.scalar_one_or_none() is not None:
        return

    # Fetch region metadata to assign source region
    res_m = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res_m.scalar_one_or_none()
    src_reg = meta.region_id if meta else "region-a"

    for item in INITIAL_CATALOG:
        cat_key = f"catalog:{item['id']}"
        inv_key = f"inventory:{item['id']}"

        cat_rec = RecordEntity(
            key=cat_key,
            value=item,
            version=1,
            fencing_epoch=meta.fencing_epoch if meta else 101,
            source_region=src_reg,
        )
        inv_rec = RecordEntity(
            key=inv_key,
            value={"product_id": item["id"], "stock": item["stock"], "reserved": 0},
            version=1,
            fencing_epoch=meta.fencing_epoch if meta else 101,
            source_region=src_reg,
        )
        session.add(cat_rec)
        session.add(inv_rec)

    await session.commit()
    logger.info("Pre-seeded default e-commerce catalog and inventory.")


async def list_products(session: AsyncSession) -> List[Dict[str, Any]]:
    await seed_initial_catalog_if_empty(session)
    res = await session.execute(
        select(RecordEntity).where(RecordEntity.key.like("catalog:%"))
    )
    records = res.scalars().all()
    return [r.value for r in records]


async def get_product_details(session: AsyncSession, product_id: str) -> Optional[Dict[str, Any]]:
    await seed_initial_catalog_if_empty(session)
    key = f"catalog:{product_id}"
    rec = await get_record(session, key)
    if not rec:
        return None
    return rec.value


async def get_product_inventory(session: AsyncSession, product_id: str) -> Dict[str, Any]:
    await seed_initial_catalog_if_empty(session)
    key = f"inventory:{product_id}"
    rec = await get_record(session, key)
    if not rec:
        # Fall back to checking catalog record
        cat_rec = await get_record(session, f"catalog:{product_id}")
        if not cat_rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{product_id}' not found.",
            )
        return {"product_id": product_id, "stock": cat_rec.value.get("stock", 0), "reserved": 0}
    return rec.value


async def create_ecommerce_order(
    session: AsyncSession,
    product_id: Optional[str] = None,
    quantity: int = 1,
    items: Optional[List[Dict[str, Any]]] = None,
    customer_name: str = "Demo Customer",
    customer_email: str = "customer@example.com",
    shipping_address: str = "123 Tech Park, Gateway City",
    client_region: str = "ap-south-1",
    caller_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Creates an e-commerce order.
    Enforces Writer Safety:
    - Only ACTIVE writer can accept orders.
    - Atomically updates inventory and order records with outbox events.
    Supports single-product orders and multi-item cart orders.
    """
    # 1. Authoritative writer validation
    meta = await validate_writer_authority(session, caller_epoch)

    # Normalize items
    order_items: List[Dict[str, Any]] = []
    if items and len(items) > 0:
        for it in items:
            p_id = it.get("product_id") if isinstance(it, dict) else getattr(it, "product_id", None)
            qty = it.get("quantity", 1) if isinstance(it, dict) else getattr(it, "quantity", 1)
            if p_id:
                order_items.append({"product_id": p_id, "quantity": int(qty)})
    elif product_id:
        order_items.append({"product_id": product_id, "quantity": int(quantity)})
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must specify either 'product_id' or 'items'.",
        )

    # 2. Check and deduct inventory for each item
    processed_items = []
    total_amount = 0.0

    for item in order_items:
        p_id = item["product_id"]
        qty = item["quantity"]

        inv_key = f"inventory:{p_id}"
        inv_rec = await get_record(session, inv_key)
        current_stock = inv_rec.value.get("stock", 0) if inv_rec else 50
        if current_stock < qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient inventory for product '{p_id}'. Available: {current_stock}, Requested: {qty}",
            )

        new_stock = current_stock - qty
        await write_record(
            session,
            key=inv_key,
            value={"product_id": p_id, "stock": new_stock, "reserved": 0},
            caller_epoch=caller_epoch,
        )

        cat_rec = await get_record(session, f"catalog:{p_id}")
        price = cat_rec.value.get("price", 99.0) if cat_rec else 99.0
        p_name = cat_rec.value.get("name", p_id) if cat_rec else p_id
        if cat_rec:
            updated_cat = dict(cat_rec.value)
            updated_cat["stock"] = new_stock
            await write_record(session, key=f"catalog:{p_id}", value=updated_cat, caller_epoch=caller_epoch)

        item_total = round(price * qty, 2)
        total_amount += item_total
        processed_items.append({
            "product_id": p_id,
            "product_name": p_name,
            "quantity": qty,
            "unit_price": price,
            "total_price": item_total,
        })

    primary_product = processed_items[0]
    total_quantity = sum(i["quantity"] for i in processed_items)
    order_id = f"ord-{uuid.uuid4().hex[:10]}"

    order_data = {
        "order_id": order_id,
        "product_id": primary_product["product_id"],
        "product_name": primary_product["product_name"] if len(processed_items) == 1 else f"{primary_product['product_name']} (+{len(processed_items) - 1} more)",
        "quantity": total_quantity,
        "unit_price": primary_product["unit_price"],
        "items": processed_items,
        "total_amount": round(total_amount, 2),
        "status": "CONFIRMED",
        "customer_name": customer_name,
        "customer_email": customer_email,
        "shipping_address": shipping_address,
        "client_region": client_region,
        "created_in_region": meta.region_id,
        "fencing_epoch": meta.fencing_epoch,
        "created_at": utc_now().isoformat(),
    }

    await write_record(
        session,
        key=f"order:{order_id}",
        value=order_data,
        caller_epoch=caller_epoch,
    )

    logger.info(
        f"[ORDER_CREATED] Order '{order_id}' placed on {meta.region_name} ({meta.region_id}) [Epoch #{meta.fencing_epoch}]: "
        f"{len(processed_items)} item(s), total={total_amount}"
    )
    return order_data


async def get_order_status(session: AsyncSession, order_id: str) -> Dict[str, Any]:
    key = f"order:{order_id}"
    rec = await get_record(session, key)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )
    return rec.value


async def list_ecommerce_orders(session: AsyncSession, limit: int = 50) -> List[Dict[str, Any]]:
    res = await session.execute(
        select(RecordEntity).where(RecordEntity.key.like("order:%")).limit(limit)
    )
    records = res.scalars().all()
    return [r.value for r in records]
