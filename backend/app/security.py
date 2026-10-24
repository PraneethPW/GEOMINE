import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from pwdlib import PasswordHash

from .config import settings
from .db import connection

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("constant-time-unmatched-password")


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


async def rate_limit(key: str, limit: int, seconds: int):
    window = int(datetime.now(timezone.utc).timestamp()) // seconds
    async with connection() as conn:
        row = await (
            await conn.execute(
                """INSERT INTO rate_limits(key,bucket,count,expires_at) VALUES (%s,%s,1,now()+(%s*interval '1 second'))
            ON CONFLICT (key,bucket) DO UPDATE SET count=rate_limits.count+1 RETURNING count""",
                (key, window, seconds * 2),
            )
        ).fetchone()
    if row["count"] > limit:
        raise HTTPException(
            429,
            "Request limit reached. Please try again later.",
            headers={"Retry-After": str(seconds)},
        )


async def current_user(request: Request):
    value = request.headers.get("authorization", "")
    token = value[7:] if value.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Sign in to your observatory.")
    if token.count(".") == 2:
        from .identity import linked_identity, verify_identity

        row = await linked_identity(await verify_identity(token))
        request.state.user_id = str(row["id"])
        return row
    async with connection() as conn:
        row = await (
            await conn.execute(
                """SELECT u.id,u.email,u.name,u.email_verified FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=%s AND s.expires_at > now() AND u.firebase_uid IS NULL""",
                (digest(token),),
            )
        ).fetchone()
    if not row:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    request.state.user_id = str(row["id"])
    return row


async def issue_session(conn, user_id):
    token = secrets.token_urlsafe(48)
    await conn.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)",
        (
            digest(token),
            user_id,
            datetime.now(timezone.utc) + timedelta(hours=settings().session_hours),
        ),
    )
    return token
