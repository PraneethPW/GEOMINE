"""One leased analysis per process, so deadlines and shutdown release native memory."""

import asyncio
import logging
import sys
from uuid import UUID

from .db import close_pool, connection, open_pool
from .worker import fail_job, process


async def run(job_id, lease_token):
    await open_pool()
    try:
        async with connection() as conn:
            job = await (
                await conn.execute(
                    """SELECT * FROM jobs WHERE id=%s AND lease_token=%s
                    AND status='running' AND lease_until>now()""",
                    (job_id, lease_token),
                )
            ).fetchone()
        if not job:
            return
        try:
            await process(job)
        except Exception as exc:
            message = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "Processing failed. Check worker configuration and logs, then retry."
            )
            logging.getLogger("geomine.runner").error(
                "Analysis %s failed (%s)", job_id, type(exc).__name__
            )
            await fail_job(job, message)
    finally:
        await close_pool()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run(UUID(sys.argv[1]), UUID(sys.argv[2])))
