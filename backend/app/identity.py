"""Firebase Admin verification; existing Neon owners are linked only with proof."""

import asyncio
import json
import os
from functools import lru_cache
from uuid import uuid4

from fastapi import HTTPException

from .config import settings
from .db import connection


@lru_cache(maxsize=1)
def firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    config = settings()
    if not config.firebase_enabled:
        raise HTTPException(503, "Managed authentication is not configured.")
    if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST") and config.app_env == "production":
        raise RuntimeError("Authentication emulator cannot be used in production.")
    certificate = json.loads(config.firebase_service_account_json)
    if certificate.get("project_id") != config.firebase_project_id:
        raise RuntimeError(
            "Firebase credential project does not match the configured project."
        )
    return firebase_admin.initialize_app(
        credentials.Certificate(certificate),
        {"projectId": config.firebase_project_id, "httpTimeout": 10},
        name="geomine-identity",
    )


async def verify_identity(token):
    from firebase_admin import auth, exceptions

    app = firebase_app()
    try:
        identity = await asyncio.to_thread(
            auth.verify_id_token, token, app=app, check_revoked=True
        )
    except (
        auth.InvalidIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ):
        raise HTTPException(
            401, "Your sign-in is invalid or expired. Sign in again."
        ) from None
    except exceptions.FirebaseError:
        raise HTTPException(
            503, "The identity service is temporarily unavailable. Retry shortly."
        ) from None
    if identity.get("email_verified") is not True or not identity.get("email"):
        raise HTTPException(
            403, "Verify your email address before opening the workspace."
        )
    return identity


async def linked_identity(identity):
    async with connection() as conn:
        row = await (
            await conn.execute(
                "SELECT id,email,name,email_verified FROM users WHERE firebase_uid=%s",
                (identity["uid"],),
            )
        ).fetchone()
    if not row:
        raise HTTPException(
            401, "Complete your workspace sign-in to link your identity."
        )
    return row


async def link_identity(identity, legacy_password=None):
    from .security import passwords

    uid, email = identity["uid"], identity["email"].strip().lower()
    async with connection() as conn:
        async with conn.transaction():
            # Serialize account creation/linking for both identity and email.
            for key in sorted(("firebase:" + uid, "email:" + email)):
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,)
                )
            existing = await (
                await conn.execute("SELECT * FROM users WHERE firebase_uid=%s", (uid,))
            ).fetchone()
            if existing:
                return {
                    k: existing[k] for k in ("id", "email", "name", "email_verified")
                }
            existing = await (
                await conn.execute(
                    "SELECT * FROM users WHERE email=%s FOR UPDATE", (email,)
                )
            ).fetchone()
            if existing:
                if existing["firebase_uid"]:
                    raise HTTPException(
                        409,
                        "This workspace is linked to another identity. Sign in with the original account.",
                    )
                if not legacy_password:
                    raise HTTPException(
                        409,
                        "Existing workspace found. Enter your current GeoMine password to link it securely.",
                    )
                valid = existing["password_hash"] and await asyncio.to_thread(
                    passwords.verify, legacy_password, existing["password_hash"]
                )
                if not valid:
                    raise HTTPException(
                        401, "The existing GeoMine password is incorrect."
                    )
                user_id = existing["id"]
                await conn.execute(
                    "UPDATE users SET firebase_uid=%s,email_verified=true,password_hash=NULL WHERE id=%s",
                    (uid, user_id),
                )
                await conn.execute("DELETE FROM sessions WHERE user_id=%s", (user_id,))
                action = "identity.linked"
            else:
                if not settings().enable_registration:
                    raise HTTPException(
                        403, "Registration is disabled by the operator."
                    )
                user_id = uuid4()
                await conn.execute(
                    "INSERT INTO users(id,email,name,firebase_uid,email_verified) VALUES (%s,%s,%s,%s,true)",
                    (user_id, email, str(identity.get("name") or "Analyst")[:80], uid),
                )
                action = "identity.created"
            await conn.execute(
                "INSERT INTO audit_log(user_id,action,resource_id) VALUES (%s,%s,%s)",
                (user_id, action, str(user_id)),
            )
            return await (
                await conn.execute(
                    "SELECT id,email,name,email_verified FROM users WHERE id=%s",
                    (user_id,),
                )
            ).fetchone()
