from __future__ import annotations

import logging
import sys
import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AgeLimit, Prometheus, Retries
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend

from .app.config import get_settings

logger = logging.getLogger(__name__)

# Use a selector loop on Windows to avoid Proactor issues with async I/O libraries
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logger.info("Using WindowsSelectorEventLoopPolicy for Dramatiq worker.")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to set WindowsSelectorEventLoopPolicy")

settings = get_settings()

redis_broker = RedisBroker(url=settings.redis_url)
redis_results = RedisBackend(url=settings.redis_url, namespace="dramatiq-results")

redis_broker.add_middleware(AgeLimit(max_age=3600 * 1000))
redis_broker.add_middleware(Retries(max_retries=0))
redis_broker.add_middleware(Results(backend=redis_results))
# Prometheus exposition forks can be problematic on Windows; omit to simplify runtime
# redis_broker.add_middleware(Prometheus())

dramatiq.set_broker(redis_broker)

 