from contextlib import asynccontextmanager
from pathlib import Path

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import settings

pool: AsyncConnectionPool | None = None


async def open_pool():
    global pool
    if not settings().database_url:
        return
    pool = AsyncConnectionPool(
        settings().database_url,
        min_size=1,
        max_size=8,
        open=False,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
    )
    await pool.open()
    await pool.wait(timeout=20)


async def close_pool():
    if pool:
        await pool.close()


@asynccontextmanager
async def connection():
    if pool is None:
        from fastapi import HTTPException

        raise HTTPException(
            503, "Neon database is not configured. Set DATABASE_URL on the backend."
        )
    async with pool.connection() as conn:
        # SET LOCAL stays inside the transaction pinned by Neon's pooler.
        async with conn.transaction():
            await conn.execute(
                sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(
                    sql.Identifier(settings().database_schema)
                )
            )
            yield conn


async def migrate():
    await open_pool()
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(71824001)")
            await conn.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(settings().database_schema)
                )
            )
            await conn.execute(
                Path(__file__).with_name("schema.sql").read_text(), prepare=False
            )
    await close_pool()


if __name__ == "__main__":
    import asyncio

    asyncio.run(migrate())
