"""Expire only operational credentials/counters; never delete observation or audit history."""

from .db import connection


async def cleanup():
    async with connection() as conn:
        # All workers may call this; serialize a bounded cleanup transaction.
        lock = await (
            await conn.execute("SELECT pg_try_advisory_xact_lock(71824002) AS acquired")
        ).fetchone()
        if not lock["acquired"]:
            return
        await conn.execute(
            "DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE expires_at<now() LIMIT 1000)"
        )
        await conn.execute(
            "DELETE FROM rate_limits WHERE (key,bucket) IN (SELECT key,bucket FROM rate_limits WHERE expires_at<now() LIMIT 1000)"
        )
        await conn.execute(
            "DELETE FROM worker_heartbeats WHERE id IN (SELECT id FROM worker_heartbeats WHERE last_seen_at<now()-interval '7 days' LIMIT 1000)"
        )
