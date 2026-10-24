"""Durable Postgres queue; lease tokens fence concurrent and restarted workers."""

import asyncio
import logging
import signal
import sys
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg import connect, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .catalog import search_scenes, select_observations
from .config import settings
from .db import close_pool, connection, open_pool
from .processing import analyze

log = logging.getLogger("geomine.worker")
stop = asyncio.Event()


async def fail_job(job, message):
    async with connection() as conn:
        async with conn.transaction():
            updated = await (
                await conn.execute(
                    """UPDATE jobs SET status='failed',stage='Analysis failed',error=%s,
                    finished_at=now() WHERE id=%s AND lease_token=%s AND status='running'
                    RETURNING id""",
                    (message, job["id"], job["lease_token"]),
                )
            ).fetchone()
            if updated:
                await emit(
                    conn,
                    job["user_id"],
                    "job.failed",
                    {"id": str(job["id"]), "error": message},
                )


async def heartbeat(worker_id, state, job_id=None):
    async with connection() as conn:
        await conn.execute(
            """INSERT INTO worker_heartbeats(id,state,job_id) VALUES (%s,%s,%s)
            ON CONFLICT(id) DO UPDATE SET last_seen_at=now(),state=excluded.state,job_id=excluded.job_id""",
            (worker_id, state, job_id),
        )


async def heartbeat_loop(worker_id, runtime):
    while not stop.is_set():
        try:
            await heartbeat(worker_id, runtime["state"], runtime["job_id"])
        except Exception as exc:
            log.error("Worker heartbeat failed (%s)", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), settings().worker_heartbeat_seconds)
        except TimeoutError:
            pass


async def supervise_process(child, shutdown, timeout):
    """Wait for completion, or terminate and reap an actual child at its deadline."""
    finished = asyncio.create_task(child.wait())
    stopping = asyncio.create_task(shutdown.wait())
    try:
        done, _ = await asyncio.wait(
            {finished, stopping}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if finished in done:
            return (
                None
                if child.returncode == 0
                else "The analysis process stopped unexpectedly. Retry this analysis."
            )
        reason = (
            "Worker restarted during analysis. Retry this analysis."
            if stopping in done
            else "Analysis exceeded its processing time limit. Use a smaller area or retry."
        )
        if child.returncode is None:
            with suppress(ProcessLookupError):
                child.terminate()
            try:
                await asyncio.wait_for(asyncio.shield(finished), 10)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    child.kill()
                await finished
        return reason
    finally:
        stopping.cancel()
        with suppress(asyncio.CancelledError):
            await stopping


async def run_claimed(job):
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.runner", str(job["id"]), str(job["lease_token"])
    )
    error = await supervise_process(child, stop, settings().job_timeout_seconds)
    if error:
        await fail_job(job, error)


async def emit(conn, user_id, type_, payload):
    await conn.execute(
        "INSERT INTO events(user_id,type,payload) VALUES (%s,%s,%s)",
        (user_id, type_, Jsonb(payload)),
    )


async def schedule():
    today = datetime.now(timezone.utc).date()
    async with connection() as conn:
        async with conn.transaction():
            areas = await (
                await conn.execute("""SELECT * FROM areas WHERE monitoring AND (next_run_at IS NULL OR next_run_at <= now())
                FOR UPDATE SKIP LOCKED LIMIT 10""")
            ).fetchall()
            for area in areas:
                active = await (
                    await conn.execute(
                        "SELECT id FROM jobs WHERE area_id=%s AND status IN ('queued','running')",
                        (area["id"],),
                    )
                ).fetchone()
                if not active:
                    job_id = uuid4()
                    await conn.execute(
                        """INSERT INTO jobs(id,user_id,area_id,engine,before_start,before_end,after_start,after_end)
                        VALUES (%s,%s,%s,'physical',%s,%s,%s,%s)""",
                        (
                            job_id,
                            area["user_id"],
                            area["id"],
                            today - timedelta(days=75),
                            today - timedelta(days=46),
                            today - timedelta(days=30),
                            today,
                        ),
                    )
                    await emit(
                        conn,
                        area["user_id"],
                        "job.queued",
                        {"id": str(job_id), "scheduled": True},
                    )
                await conn.execute(
                    "UPDATE areas SET next_run_at=now()+(interval_hours*interval '1 hour') WHERE id=%s",
                    (area["id"],),
                )


async def claim(worker_id=None):
    async with connection() as conn:
        async with conn.transaction():
            # A worker exceeding the configured hard timeout loses its right to commit.
            expired = await (
                await conn.execute(
                    """UPDATE jobs SET status='failed',stage='Worker unavailable',
                error='Worker stopped, lost its heartbeat, or exceeded the time limit. Retry this analysis.',finished_at=now()
                WHERE status='running' AND (lease_until < now() OR EXISTS (
                    SELECT 1 FROM worker_heartbeats w WHERE w.id=jobs.worker_id AND
                    (w.state='stopped' OR w.last_seen_at<now()-(%s*interval '1 second'))
                )) RETURNING id,user_id""",
                    (settings().worker_stale_seconds,),
                )
            ).fetchall()
            for row in expired:
                await emit(conn, row["user_id"], "job.failed", {"id": str(row["id"])})
            job = await (
                await conn.execute(
                    "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
                )
            ).fetchone()
            if not job:
                return None
            token = uuid4()
            await conn.execute(
                """UPDATE jobs SET status='running',stage='Searching satellite catalog',progress=5,
                attempts=attempts+1,started_at=now(),lease_token=%s,worker_id=%s,lease_until=now()+(%s*interval '1 second') WHERE id=%s""",
                (token, worker_id, settings().job_timeout_seconds, job["id"]),
            )
            job["lease_token"] = token
            await emit(conn, job["user_id"], "job.running", {"id": str(job["id"])})
            return job


async def process(job):
    async with connection() as conn:
        area = await (
            await conn.execute(
                "SELECT * FROM areas WHERE id=%s AND user_id=%s",
                (job["area_id"], job["user_id"]),
            )
        ).fetchone()
        concessions = await (
            await conn.execute(
                """SELECT * FROM concessions WHERE user_id=%s AND valid_from<=%s AND valid_to>=%s""",
                (job["user_id"], job["after_start"], job["after_end"]),
            )
        ).fetchall()
    geometry = area["geometry"]
    s2b, s2a, s1b, s1a = await asyncio.gather(
        search_scenes(geometry, job["before_start"], job["before_end"], "optical", 100),
        search_scenes(geometry, job["after_start"], job["after_end"], "optical", 100),
        search_scenes(geometry, job["before_start"], job["before_end"], "radar", 100),
        search_scenes(geometry, job["after_start"], job["after_end"], "radar", 100),
    )
    if not s1b or not s1a:
        from .catalog import radar_provider

        if radar_provider() == "digital-earth-africa":
            raise ValueError(
                "No public Africa RTC acquisitions cover one or both windows. This source covers Africa only; adjust the area/dates or configure the 10m provider for other regions."
            )
    ob, oa, rb, ra = select_observations(s2b, s2a, s1b, s1a, geometry)

    def progress(stage, percent):
        with connect(
            settings().database_url, row_factory=dict_row, prepare_threshold=None
        ) as conn:
            conn.execute(
                sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(
                    sql.Identifier(settings().database_schema)
                )
            )
            updated = conn.execute(
                "UPDATE jobs SET stage=%s,progress=%s WHERE id=%s AND status='running' AND lease_token=%s AND lease_until>now() RETURNING id",
                (stage, percent, job["id"], job["lease_token"]),
            ).fetchone()
            if not updated:
                raise ValueError("Analysis was cancelled or its lease expired.")
            conn.execute(
                "INSERT INTO events(user_id,type,payload) VALUES (%s,%s,%s)",
                (
                    job["user_id"],
                    "job.progress",
                    Jsonb({"id": str(job["id"]), "stage": stage, "progress": percent}),
                ),
            )

    result, candidates = await asyncio.to_thread(
        analyze, geometry, ob, oa, rb, ra, concessions, job["engine"], progress
    )
    async with connection() as conn:
        async with conn.transaction():
            updated = await (
                await conn.execute(
                    """UPDATE jobs SET status='completed',progress=100,stage='Analysis complete',
                result=%s,finished_at=now() WHERE id=%s AND status='running' AND lease_token=%s AND lease_until>now() RETURNING id""",
                    (Jsonb(result), job["id"], job["lease_token"]),
                )
            ).fetchone()
            if not updated:
                return
            for candidate in candidates:
                await conn.execute(
                    """INSERT INTO alerts(id,user_id,job_id,area_id,geometry,area_ha,score,legal_context)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        uuid4(),
                        job["user_id"],
                        job["id"],
                        area["id"],
                        Jsonb(candidate["geometry"]),
                        candidate["area_ha"],
                        candidate["score"],
                        candidate["legal_context"],
                    ),
                )
            await emit(
                conn,
                job["user_id"],
                "job.completed",
                {"id": str(job["id"]), "candidates": len(candidates)},
            )


async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    await open_pool()
    worker_id = uuid4()
    runtime = {"state": "idle", "job_id": None}
    next_cleanup = 0.0
    await heartbeat(worker_id, "idle")
    beats = asyncio.create_task(heartbeat_loop(worker_id, runtime))
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        while not stop.is_set():
            try:
                if time.monotonic() >= next_cleanup:
                    from .maintenance import cleanup

                    next_cleanup = time.monotonic() + 3600
                    try:
                        await cleanup()
                    except Exception as exc:
                        log.warning(
                            "Operational cleanup deferred (%s)", type(exc).__name__
                        )
                await schedule()
                job = await claim(worker_id)
                if job:
                    runtime.update(state="running", job_id=job["id"])
                    try:
                        await run_claimed(job)
                    except Exception as exc:
                        log.error(
                            "Analysis %s failed (%s)", job["id"], type(exc).__name__
                        )
                        await fail_job(
                            job, "Unable to start the analysis process. Retry shortly."
                        )
                    finally:
                        runtime.update(state="idle", job_id=None)
                else:
                    try:
                        await asyncio.wait_for(
                            stop.wait(), timeout=settings().worker_poll_seconds
                        )
                    except TimeoutError:
                        pass
            except Exception as exc:
                log.error("Worker loop failed (%s)", type(exc).__name__)
                await asyncio.sleep(settings().worker_poll_seconds)
    finally:
        stop.set()
        await beats
        try:
            await heartbeat(worker_id, "stopped")
        except Exception:
            pass
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
