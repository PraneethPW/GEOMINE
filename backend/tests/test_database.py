"""Integration tests against an explicitly isolated real Postgres database."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from app import db
from app.config import settings
from app.main import app
from app.worker import claim


@pytest.mark.asyncio
async def test_persistence_tenant_isolation_reviews_and_queue(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database.")
    schema = "test_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    test_url = psycopg.conninfo.make_conninfo(url, options=f"-csearch_path={schema}")
    monkeypatch.setenv("DATABASE_URL", test_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("PC_SUBSCRIPTION_KEY", "integration-test-gate-only")
    settings.cache_clear()
    try:
        await db.open_pool()
        async with db.connection() as conn:
            await conn.execute(
                Path(__file__).parents[1].joinpath("app/schema.sql").read_text(),
                prepare=False,
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def signup(name):
                response = await client.post(
                    "/api/auth/register",
                    json={
                        "name": name,
                        "email": name + "@integration.invalid",
                        "password": "Test-only-long-password-324!Z",
                    },
                )
                assert response.status_code == 201, response.text
                return {"Authorization": "Bearer " + response.json()["token"]}

            alice = await signup("alice")
            bob = await signup("bob")
            geom = {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-1.94, 6.04],
                        [-1.92, 6.04],
                        [-1.92, 6.06],
                        [-1.94, 6.06],
                        [-1.94, 6.04],
                    ]
                ],
            }
            response = await client.post(
                "/api/areas",
                headers=alice,
                json={"name": "Integration area", "geometry": geom},
            )
            assert response.status_code == 201, response.text
            area = response.json()
            assert (await client.get("/api/areas", headers=bob)).json() == []
            assert len((await client.get("/api/areas", headers=alice)).json()) == 1
            payload = {
                "area_id": area["id"],
                "engine": "physical",
                "before_start": "2025-01-01",
                "before_end": "2025-01-30",
                "after_start": "2025-02-01",
                "after_end": "2025-02-28",
            }
            assert (
                await client.post("/api/jobs", headers=bob, json=payload)
            ).status_code == 404
            response = await client.post("/api/jobs", headers=alice, json=payload)
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            assert (
                await client.post("/api/jobs", headers=alice, json=payload)
            ).status_code == 409
            one, two = await asyncio.gather(claim(), claim())
            assert len([j for j in (one, two) if j]) == 1
            assert str((one or two)["id"]) == job_id
            assert (
                await client.post(f"/api/jobs/{job_id}/cancel", headers=bob)
            ).status_code == 409
            assert (
                await client.post(f"/api/jobs/{job_id}/cancel", headers=alice)
            ).status_code == 200
            async with db.connection() as conn:
                row = await (
                    await conn.execute(
                        "UPDATE jobs SET status='completed' WHERE id=%s AND status='running' AND lease_token=%s RETURNING id",
                        (job_id, (one or two)["lease_token"]),
                    )
                ).fetchone()
                assert row is None
            assert (
                await client.get(f"/api/jobs/{job_id}/export", headers=bob)
            ).status_code == 404
            assert (
                await client.get(f"/api/jobs/{job_id}/export", headers=alice)
            ).json()["features"] == []
            candidate_id = uuid4()
            async with db.connection() as conn:
                # Fixture exists only in this isolated test schema.
                owner = await (
                    await conn.execute(
                        "SELECT user_id FROM areas WHERE id=%s", (area["id"],)
                    )
                ).fetchone()
                await conn.execute(
                    """INSERT INTO alerts(id,user_id,job_id,area_id,geometry,area_ha,score,legal_context)
                       VALUES (%s,%s,%s,%s,%s,.1,.5,'unknown')""",
                    (candidate_id, owner["user_id"], job_id, area["id"], Jsonb(geom)),
                )
            decision = {"status": "investigating", "note": "Test-only review decision"}
            assert (
                await client.patch(
                    f"/api/alerts/{candidate_id}", headers=bob, json=decision
                )
            ).status_code == 404
            reviewed = await client.patch(
                f"/api/alerts/{candidate_id}", headers=alice, json=decision
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["status"] == "investigating"
            assert (await client.get("/api/alerts", headers=bob)).json() == []
            assert (
                len(
                    (
                        await client.get(f"/api/jobs/{job_id}/export", headers=alice)
                    ).json()["features"]
                )
                == 1
            )
            rows = (await client.get("/api/audit", headers=alice)).json()
            assert {
                "area.created",
                "job.created",
                "job.cancelled",
                "alert.reviewed",
            }.issubset({r["action"] for r in rows})
            assert (
                await client.post("/api/auth/logout", headers=alice)
            ).status_code == 204
            assert (await client.get("/api/areas", headers=alice)).status_code == 401
            assert (await client.get("/api/areas")).status_code == 401
    finally:
        await db.close_pool()
        db.pool = None
        settings.cache_clear()
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
