"""Exercise the real HTTP event stream against an isolated real Postgres schema."""

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql


@pytest.mark.asyncio
async def test_authenticated_http_events_are_replayable():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set an isolated TEST_DATABASE_URL for HTTP event integration.")
    schema = "events_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(
        database_url, autocommit=True
    ) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        await conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        await conn.execute(
            Path(__file__).parents[1].joinpath("app/schema.sql").read_text(),
            prepare=False,
        )
    url = psycopg.conninfo.make_conninfo(
        database_url, options=f"-csearch_path={schema}"
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "DATABASE_URL": url, "DATABASE_SCHEMA": schema},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", timeout=10
        ) as client:
            for _ in range(50):
                try:
                    if (await client.get("/api/ready")).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                pytest.fail("Isolated HTTP test server did not start.")
            assert (await client.get("/api/events")).status_code == 401
            account = await client.post(
                "/api/auth/register",
                json={
                    "email": "events@integration.invalid",
                    "password": "Test-only-long-password-324!Z",
                },
            )
            assert account.status_code == 201, account.text
            headers = {"Authorization": "Bearer " + account.json()["token"]}
            geometry = {
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
            created = await client.post(
                "/api/areas",
                headers=headers,
                json={"name": "Event test area", "geometry": geometry},
            )
            assert created.status_code == 201
            first_id = None
            async with client.stream("GET", "/api/events", headers=headers) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                async for line in response.aiter_lines():
                    if line.startswith("id: "):
                        first_id = line[4:]
                    if line.startswith("data: "):
                        assert "area.created" in line
                        assert created.json()["id"] in line
                        break
            assert first_id
            second = await client.post(
                "/api/areas",
                headers=headers,
                json={"name": "Event replay area", "geometry": geometry},
            )
            async with client.stream(
                "GET", "/api/events", headers={**headers, "Last-Event-ID": first_id}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        assert second.json()["id"] in line
                        assert created.json()["id"] not in line
                        break
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        async with await psycopg.AsyncConnection.connect(
            database_url, autocommit=True
        ) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
