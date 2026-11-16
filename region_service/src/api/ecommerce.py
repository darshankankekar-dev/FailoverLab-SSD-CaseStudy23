from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..services.ecommerce_service import (
    list_products,
    get_product_details,
    get_product_inventory,
    create_ecommerce_order,
    get_order_status,
    list_ecommerce_orders,
)

router = APIRouter(prefix="/api/ecommerce", tags=["Online Store"])


class OrderItemPayload(BaseModel):
    product_id: str = Field(..., description="Unique product ID")
    quantity: int = Field(default=1, ge=1, le=100, description="Order quantity")


class CreateOrderRequest(BaseModel):
    product_id: Optional[str] = Field(default=None, description="Unique product ID (for single product order)")
    quantity: int = Field(default=1, ge=1, le=100, description="Order quantity")
    items: Optional[List[OrderItemPayload]] = Field(default=None, description="Multi-item order payload")
    customer_name: Optional[str] = Field(default="Demo Customer")
    customer_email: Optional[str] = Field(default="shopper@example.com")
    shipping_address: Optional[str] = Field(default="123 Tech Park, Gateway City")
    client_region: Optional[str] = Field(default="ap-south-1")
    fencing_epoch: Optional[int] = Field(default=None)


@router.get("/products", response_model=List[Dict[str, Any]])
async def get_catalog(session: AsyncSession = Depends(get_db_session)):
    """
    Eventual-consistency read: Returns the online shopping product catalog.
    Served by the nearest healthy, fresh replica (or active writer).
    """
    return await list_products(session)


@router.get("/products/{product_id}", response_model=Dict[str, Any])
async def get_product(product_id: str, session: AsyncSession = Depends(get_db_session)):
    """
    Eventual-consistency read: Returns product specifications and details.
    """
    prod = await get_product_details(session, product_id)
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found.",
        )
    return prod


@router.get("/inventory/{product_id}", response_model=Dict[str, Any])
async def check_inventory(product_id: str, session: AsyncSession = Depends(get_db_session)):
    """
    Strong-consistency read: Fetches authoritative live stock from the active primary writer.
    """
    return await get_product_inventory(session, product_id)


@router.get("/orders", response_model=List[Dict[str, Any]])
async def get_orders(session: AsyncSession = Depends(get_db_session)):
    """
    Strong-consistency read: Returns list of placed orders from the authoritative writer.
    """
    return await list_ecommerce_orders(session)


@router.get("/orders/{order_id}", response_model=Dict[str, Any])
async def get_single_order(order_id: str, session: AsyncSession = Depends(get_db_session)):
    """
    Strong-consistency read: Reads order confirmation and fulfillment status.
    """
    return await get_order_status(session, order_id)


@router.post("/orders", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def submit_order(
    payload: CreateOrderRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Write: Submits a new shopping order.
    Strictly forwarded to the single active primary writer.
    Atomically updates stock and registers an outbox event.
    """
    return await create_ecommerce_order(
        session,
        product_id=payload.product_id,
        quantity=payload.quantity,
        items=[it.model_dump() for it in payload.items] if payload.items else None,
        customer_name=payload.customer_name or "Demo Customer",
        customer_email=payload.customer_email or "shopper@example.com",
        shipping_address=payload.shipping_address or "123 Tech Park, Gateway City",
        client_region=payload.client_region or "ap-south-1",
        caller_epoch=payload.fencing_epoch,
    )
