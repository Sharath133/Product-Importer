from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Product, WebhookEventType
from ..schemas import Pagination, ProductCreate, ProductListResponse, ProductRead, ProductUpdate
from ..services.webhook_service import enqueue_webhook_events


router = APIRouter(prefix="/api/products", tags=["products"])

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def _apply_filters(
    query,
    sku: Optional[str],
    name: Optional[str],
    description: Optional[str],
    active: Optional[bool],
):
    if sku:
        query = query.where(Product.sku_normalized == Product.normalize_sku(sku))
    if name:
        query = query.where(Product.name.ilike(f"%{name}%"))
    if description:
        query = query.where(Product.description.ilike(f"%{description}%"))
    if active is not None:
        query = query.where(Product.active.is_(active))
    return query


@router.get("", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    sku: Optional[str] = Query(default=None, description="Filter by SKU (case-insensitive exact match)"),
    name: Optional[str] = Query(default=None, description="Filter by name (case-insensitive contains)"),
    description: Optional[str] = Query(default=None, description="Filter by description (case-insensitive contains)"),
    active: Optional[bool] = Query(default=None, description="Filter by active status"),
    session: AsyncSession = Depends(get_session),
) -> ProductListResponse:
    base_query = select(Product)
    base_query = _apply_filters(base_query, sku, name, description, active)

    count_query = select(func.count()).select_from(Product)
    count_query = _apply_filters(count_query, sku, name, description, active)

    total = (await session.execute(count_query)).scalar_one()

    offset = (page - 1) * size
    items_result = await session.execute(
        base_query.order_by(Product.created_at.desc()).offset(offset).limit(size)
    )
    items = items_result.scalars().all()

    return ProductListResponse(
        items=items,
        pagination=Pagination(total=total, page=page, size=size),
    )


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)) -> ProductRead:
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, session: AsyncSession = Depends(get_session)) -> ProductRead:
    normalized_sku = Product.normalize_sku(payload.sku)
    existing_result = await session.execute(select(Product).where(Product.sku_normalized == normalized_sku))
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.name = payload.name
        existing.sku = payload.sku  # triggers normalization validator
        existing.description = payload.description
        existing.active = payload.active
        product = existing
        event_type = WebhookEventType.PRODUCT_UPDATED
    else:
        product = Product(**payload.model_dump())
        session.add(product)
        event_type = WebhookEventType.PRODUCT_CREATED

    await session.commit()
    await session.refresh(product)

    await enqueue_webhook_events(
        session,
        event_type,
        ProductRead.model_validate(product, from_attributes=True).model_dump(),
    )
    return product


@router.put("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "sku" in update_data:
        new_sku = update_data["sku"]
        normalized_sku = Product.normalize_sku(new_sku)
        existing_result = await session.execute(
            select(Product).where(Product.sku_normalized == normalized_sku, Product.id != product_id)
        )
        conflict = existing_result.scalar_one_or_none()
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists")
        product.sku = new_sku  # validator updates normalized sku

    if "name" in update_data:
        product.name = update_data["name"]
    if "description" in update_data:
        product.description = update_data["description"]
    if "active" in update_data:
        product.active = update_data["active"]

    await session.commit()
    await session.refresh(product)

    await enqueue_webhook_events(
        session,
        WebhookEventType.PRODUCT_UPDATED,
        ProductRead.model_validate(product, from_attributes=True).model_dump(),
    )
    return product


@router.delete("/bulk", response_model=dict)
async def bulk_delete_products(session: AsyncSession = Depends(get_session)) -> dict:
    total_query = await session.execute(select(func.count()).select_from(Product))
    total_products = total_query.scalar_one()

    if total_products == 0:
        return {"deleted": 0}

    await session.execute(delete(Product))
    await session.commit()

    await enqueue_webhook_events(
        session,
        WebhookEventType.BULK_DELETE_COMPLETED,
        {"deleted": total_products},
    )

    return {"deleted": total_products}


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    payload = ProductRead.model_validate(product, from_attributes=True).model_dump()
    await session.delete(product)
    await session.commit()

    await enqueue_webhook_events(session, WebhookEventType.PRODUCT_DELETED, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

