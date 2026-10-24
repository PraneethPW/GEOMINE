import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from fastapi import HTTPException
from psycopg import sql

from app import db, identity
from app.config import settings
from app.security import digest, passwords


@pytest_asyncio.fixture
async def identity_database(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated test database.")
    schema = "test_identity_" + uuid4().hex
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
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
async def test_linking_requires_old_password_and_preserves_existing_owner(
    identity_database,
):
    owner, area = uuid4(), uuid4()
    old_password = "test-only-old-account-password"
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO users(id,email,name,password_hash) VALUES (%s,'owner@test.invalid','Owner',%s)",
            (owner, passwords.hash(old_password)),
        )
        await conn.execute(
            "INSERT INTO areas(id,user_id,name,geometry,area_km2) VALUES (%s,%s,'Existing area','{}',1)",
            (area, owner),
        )
        await conn.execute(
            "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s,now()+interval '1 hour')",
            (digest("old-test-session"), owner),
        )
    verified = {
        "uid": "test-provider-user",
        "email": "owner@test.invalid",
        "email_verified": True,
    }
    with pytest.raises(HTTPException) as missing:
        await identity.link_identity(verified)
    assert missing.value.status_code == 409
    with pytest.raises(HTTPException) as incorrect:
        await identity.link_identity(verified, "incorrect-old-test-password")
    assert incorrect.value.status_code == 401
    linked = await identity.link_identity(verified, old_password)
    assert linked["id"] == owner and linked["email_verified"] is True
    assert (await identity.linked_identity(verified))["id"] == owner
    async with db.connection() as conn:
        stored = await (
            await conn.execute("SELECT * FROM users WHERE id=%s", (owner,))
        ).fetchone()
        assert stored["password_hash"] is None
        assert not await (
            await conn.execute("SELECT 1 FROM sessions WHERE user_id=%s", (owner,))
        ).fetchone()
        assert (
            await (
                await conn.execute("SELECT user_id FROM areas WHERE id=%s", (area,))
            ).fetchone()
        )["user_id"] == owner
    assert (await identity.link_identity(verified))["id"] == owner
    with pytest.raises(HTTPException):
        await identity.link_identity(
            {**verified, "uid": "different-provider-user"}, old_password
        )


@pytest.mark.asyncio
async def test_managed_registration_can_be_closed_and_does_not_require_local_password(
    identity_database, monkeypatch
):
    verified = {
        "uid": "new-provider-user",
        "email": "new@test.invalid",
        "email_verified": True,
        "name": "New owner",
    }
    monkeypatch.setenv("ENABLE_REGISTRATION", "false")
    settings.cache_clear()
    with pytest.raises(HTTPException) as closed:
        await identity.link_identity(verified)
    assert closed.value.status_code == 403
    monkeypatch.setenv("ENABLE_REGISTRATION", "true")
    settings.cache_clear()
    row = await identity.link_identity(verified)
    assert row["email"] == verified["email"] and row["email_verified"]
    assert (await identity.link_identity(verified))["id"] == row["id"]


@pytest.mark.asyncio
async def test_provider_verification_requires_verified_email_and_revocation_check(
    monkeypatch,
):
    from firebase_admin import auth

    calls = []
    monkeypatch.setattr(identity, "firebase_app", lambda: object())

    def provider_verify(token, **kwargs):
        calls.append(kwargs)
        return {
            "uid": "test-subject",
            "email": "not-yet@test.invalid",
            "email_verified": False,
        }

    monkeypatch.setattr(auth, "verify_id_token", provider_verify)
    with pytest.raises(HTTPException) as unverified:
        await identity.verify_identity("test-only-token")
    assert unverified.value.status_code == 403 and calls[0]["check_revoked"] is True

    def rejected(*args, **kwargs):
        raise auth.InvalidIdTokenError("invalid test token")

    monkeypatch.setattr(auth, "verify_id_token", rejected)
    with pytest.raises(HTTPException) as invalid:
        await identity.verify_identity("invalid-test-token")
    assert invalid.value.status_code == 401
