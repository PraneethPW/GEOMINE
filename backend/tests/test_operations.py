import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg import sql

from app import db
from app.config import settings
from app.main import app
from app.operations import job_statistics, worker_health
from app.worker import claim, fail_job, heartbeat, supervise_process


@pytest_asyncio.fixture
async def operational_database(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated test database.")
    schema = "test_ops_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("OPERATIONS_TOKEN", "test-only-operator-token-" + "x" * 32)
    settings.cache_clear()
    await db.open_pool()
    try:
        async with db.connection() as conn:
            await conn.execute(
                Path(__file__).parents[1].joinpath("app/schema.sql").read_text(),
                prepare=False,
            )
        yield
    finally:
        await db.close_pool()
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
        settings.cache_clear()


@pytest.mark.asyncio
async def test_worker_health_detects_stale_and_stopped_workers(operational_database):
    assert (await worker_health())["status"] == "unavailable"
    worker_id = uuid4()
    await heartbeat(worker_id, "idle")
    assert (await worker_health())["available_workers"] == 1
    async with db.connection() as conn:
        await conn.execute(
            "UPDATE worker_heartbeats SET last_seen_at=now()-interval '5 minutes'"
        )
    assert (await worker_health())["status"] == "unavailable"
    await heartbeat(worker_id, "running")
    assert (await worker_health())["status"] == "healthy"
    await heartbeat(worker_id, "stopped")
    assert (await worker_health())["status"] == "unavailable"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/health/worker")).status_code == 503
        assert (await client.get("/api/ops/status")).status_code == 401
        assert (await client.get("/api/workspace/operations")).status_code == 401
        response = await client.get(
            "/api/ops/status",
            headers={"Authorization": "Bearer " + settings().operations_token},
        )
        assert response.status_code == 200
        assert response.json()["scope"] == "operator"


@pytest.mark.asyncio
async def test_workspace_statistics_are_scoped_and_failures_remain_fenced(
    operational_database,
):
    owner, other, area, job_id, lease = [uuid4() for _ in range(5)]
    async with db.connection() as conn:
        for user in (owner, other):
            await conn.execute(
                "INSERT INTO users(id,email,name,password_hash) VALUES (%s,%s,'test','unusable')",
                (user, str(user) + "@test.invalid"),
            )
        await conn.execute(
            "INSERT INTO areas(id,user_id,name,geometry,area_km2) VALUES (%s,%s,'test','{}',1)",
            (area, owner),
        )
        await conn.execute(
            """INSERT INTO jobs(id,user_id,area_id,engine,before_start,before_end,after_start,after_end,status,lease_token)
            VALUES (%s,%s,%s,'physical','2025-01-01','2025-01-30','2025-02-01','2025-02-28','running',%s)""",
            (job_id, owner, area, lease),
        )
    assert (await job_statistics(owner))["jobs"]["running"] == 1
    assert (await job_statistics(other))["jobs"]["running"] == 0
    job = {"id": job_id, "user_id": owner, "lease_token": uuid4()}
    await fail_job(job, "stale worker")
    assert (await job_statistics(owner))["jobs"]["running"] == 1
    job["lease_token"] = lease
    await fail_job(job, "timeout")
    assert (await job_statistics(owner))["jobs"]["failed_24h"] == 1
    async with db.connection() as conn:
        row = await (
            await conn.execute("SELECT payload FROM events WHERE user_id=%s", (owner,))
        ).fetchone()
    assert row["payload"]["error"] == "timeout"


@pytest.mark.asyncio
async def test_supervisor_terminates_and_reaps_a_timed_out_native_process():
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)"
    )
    error = await supervise_process(child, asyncio.Event(), 0.05)
    assert "time limit" in error and child.returncode is not None


@pytest.mark.asyncio
async def test_supervisor_stops_for_shutdown_and_allows_normal_completion():
    shutdown = asyncio.Event()
    shutdown.set()
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)"
    )
    assert "restarted" in await supervise_process(child, shutdown, 60)
    assert child.returncode is not None
    done = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
    assert await supervise_process(done, asyncio.Event(), 5) is None


@pytest.mark.asyncio
async def test_a_crashed_workers_job_is_recovered_before_its_long_lease_expires(
    operational_database,
):
    owner, area, job, worker = [uuid4() for _ in range(4)]
    await heartbeat(worker, "running")
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO users(id,email,name) VALUES (%s,%s,'test')",
            (owner, str(owner) + "@test.invalid"),
        )
        await conn.execute(
            "INSERT INTO areas(id,user_id,name,geometry,area_km2) VALUES (%s,%s,'test','{}',1)",
            (area, owner),
        )
        await conn.execute(
            """INSERT INTO jobs(id,user_id,area_id,engine,before_start,before_end,after_start,after_end,status,worker_id,lease_until)
        VALUES (%s,%s,%s,'physical','2025-01-01','2025-01-30','2025-02-01','2025-02-28','running',%s,now()+interval '30 minutes')""",
            (job, owner, area, worker),
        )
        await conn.execute(
            "UPDATE worker_heartbeats SET last_seen_at=now()-interval '5 minutes' WHERE id=%s",
            (worker,),
        )
    assert await claim() is None
    async with db.connection() as conn:
        row = await (
            await conn.execute("SELECT status,error FROM jobs WHERE id=%s", (job,))
        ).fetchone()
    assert row["status"] == "failed" and "heartbeat" in row["error"]


@pytest.mark.asyncio
async def test_cleanup_expires_only_operational_records(operational_database):
    from app.maintenance import cleanup

    owner = uuid4()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO users(id,email,name) VALUES (%s,%s,'test')",
            (owner, str(owner) + "@test.invalid"),
        )
        await conn.execute(
            "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES ('expired',%s,now()-interval '1 hour'),('active',%s,now()+interval '1 hour')",
            (owner, owner),
        )
        await conn.execute(
            "INSERT INTO rate_limits(key,bucket,count,expires_at) VALUES ('expired',1,1,now()-interval '1 hour'),('active',1,1,now()+interval '1 hour')"
        )
        await conn.execute(
            "INSERT INTO audit_log(user_id,action,resource_id) VALUES (%s,'preserved','test')",
            (owner,),
        )
    await cleanup()
    async with db.connection() as conn:
        assert (
            await (await conn.execute("SELECT token_hash FROM sessions")).fetchone()
        )["token_hash"] == "active"
        assert (await (await conn.execute("SELECT key FROM rate_limits")).fetchone())[
            "key"
        ] == "active"
        assert (
            await (await conn.execute("SELECT count(*) AS n FROM audit_log")).fetchone()
        )["n"] == 1
