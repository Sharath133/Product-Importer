from __future__ import annotations

from typing import Any, Dict

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from .config import get_settings

settings = get_settings()

PROGRESS_NAMESPACE = "product-import:progress"
PROGRESS_TTL_SECONDS = 60 * 60  # 1 hour


def _progress_key(job_id: str) -> str:
    return f"{PROGRESS_NAMESPACE}:{job_id}"


def _sync_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _async_client() -> AsyncRedis:
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


def update_progress(job_id: str, **fields: Any) -> None:
    client = _sync_client()
    try:
        if fields:
            client.hset(_progress_key(job_id), mapping=fields)
            client.expire(_progress_key(job_id), PROGRESS_TTL_SECONDS)
    finally:
        client.close()


def clear_progress(job_id: str) -> None:
    client = _sync_client()
    try:
        client.delete(_progress_key(job_id))
    finally:
        client.close()


async def get_progress(job_id: str) -> Dict[str, Any]:
    client = _async_client()
    try:
        data = await client.hgetall(_progress_key(job_id))
        return data or {}
    finally:
        await client.close()

