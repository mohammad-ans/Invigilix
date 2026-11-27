"""Enter expiry_worker in the FastAPI application's lifespan."""
import asyncio
import logging
from contextlib import asynccontextmanager

from .service import expire_due

logger = logging.getLogger(__name__)


@asynccontextmanager
async def expiry_worker(connect, score_objective, interval_seconds=5):
    stopped = asyncio.Event()

    async def run():
        while not stopped.is_set():
            try:
                count = await asyncio.to_thread(expire_due, connect, score_objective)
                if count == 64:
                    continue
            except Exception:
                logger.exception("Could not finalize due attempts")
            try:
                await asyncio.wait_for(stopped.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(run())
    try:
        yield
    finally:
        stopped.set()
        await task
