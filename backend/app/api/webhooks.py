from __future__ import annotations

import time
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Webhook
from ..schemas import WebhookCreate, WebhookRead, WebhookUpdate

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("", response_model=List[WebhookRead])
async def list_webhooks(session: AsyncSession = Depends(get_session)) -> List[Webhook]:
    result = await session.execute(select(Webhook).order_by(Webhook.created_at))
    return result.scalars().all()


@router.post("", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookCreate, session: AsyncSession = Depends(get_session)) -> Webhook:
    data = payload.model_dump()
    data["url"] = str(payload.url)
    webhook = Webhook(**data)
    session.add(webhook)
    await session.commit()
    await session.refresh(webhook)
    return webhook


@router.put("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: int,
    payload: WebhookUpdate,
    session: AsyncSession = Depends(get_session),
) -> Webhook:
    webhook = await session.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"] is not None:
        data["url"] = str(data["url"])
    for key, value in data.items():
        setattr(webhook, key, value)

    await session.commit()
    await session.refresh(webhook)
    return webhook


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_webhook(webhook_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    webhook = await session.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    await session.delete(webhook)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    webhook = await session.get(Webhook, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    payload = {
        "event": "webhook.test",
        "data": {"message": "This is a test payload"},
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook.url, json=payload)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status_code": response.status_code,
            "response_time_ms": duration_ms,
            "body": response.text,
        }
    except httpx.RequestError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Request failed: {exc}",
        ) from exc

