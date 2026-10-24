"""Database-backed worker health and tenant-scoped operational measurements."""

from datetime import datetime, timezone
from secrets import compare_digest

from fastapi import HTTPException, Request

from .config import settings
from .db import connection


async def require_operator(request: Request):
    expected = settings().operations_token
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    if len(expected) < 32 or not compare_digest(supplied, expected):
        raise HTTPException(401, "Operator authentication is required.")


async def worker_health():
    async with connection() as conn:
        row = await (
            await conn.execute(
                """SELECT count(*) FILTER (WHERE state<>'stopped' AND
                last_seen_at>now()-(%s*interval '1 second')) AS available,
                max(last_seen_at) FILTER (WHERE state<>'stopped') AS last_seen
                FROM worker_heartbeats""",
                (settings().worker_stale_seconds,),
            )
        ).fetchone()
    return {
        "status": "healthy" if row["available"] else "unavailable",
        "available_workers": row["available"],
        "last_seen_at": row["last_seen"],
        "stale_after_seconds": settings().worker_stale_seconds,
    }


async def job_statistics(user_id=None):
    async with connection() as conn:
        row = await (
            await conn.execute(
                """SELECT count(*) FILTER (WHERE status='queued') AS queued,
                count(*) FILTER (WHERE status='running') AS running,
                count(*) FILTER (WHERE status='running' AND lease_until<now()) AS expired_leases,
                count(*) FILTER (WHERE status='failed' AND finished_at>now()-interval '24 hours') AS failed_24h,
                count(*) FILTER (WHERE status='completed' AND finished_at>now()-interval '24 hours') AS completed_24h,
                min(created_at) FILTER (WHERE status='queued') AS oldest_queued_at,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM (finished_at-started_at)))
                FILTER (WHERE status='completed' AND finished_at>now()-interval '24 hours') AS duration_p95_seconds
                FROM jobs WHERE (%s::uuid IS NULL OR user_id=%s::uuid)""",
                (user_id, user_id),
            )
        ).fetchone()
        monitoring = await (
            await conn.execute(
                """SELECT count(*) AS enabled,
                count(*) FILTER (WHERE next_run_at<now()-interval '10 minutes') AS overdue
                FROM areas WHERE monitoring AND (%s::uuid IS NULL OR user_id=%s::uuid)""",
                (user_id, user_id),
            )
        ).fetchone()
    return {"jobs": row, "monitoring": monitoring}


async def operational_status(user_id=None):
    import asyncio

    worker, statistics = await asyncio.gather(worker_health(), job_statistics(user_id))
    return {
        "checked_at": datetime.now(timezone.utc),
        "worker": worker,
        **statistics,
        "scope": "workspace" if user_id is not None else "operator",
    }
