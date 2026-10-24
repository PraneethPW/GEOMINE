import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from .briefs import ANALYST_INSTRUCTIONS, analyst_narrative, brief_evidence
from .catalog import public_scene, radar_provider, search_scenes
from .config import settings
from .db import close_pool, connection, open_pool
from .geo import normalize_geojson
from .operations import operational_status, require_operator, worker_health
from .security import (
    DUMMY_HASH,
    current_user,
    digest,
    issue_session,
    passwords,
    rate_limit,
)
from .worker import emit

log = logging.getLogger("geomine.api")


@asynccontextmanager
async def lifespan(app):
    await open_pool()
    yield
    await close_pool()


app = FastAPI(title="GeoMine-XNet API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings().frontend_origin.split(",")],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    expose_headers=["X-Request-ID"],
)
User = Annotated[dict, Depends(current_user)]


@app.middleware("http")
async def safety(request: Request, call_next):
    request_id = str(uuid4())
    # Bound request bodies even when Content-Length is absent (chunked uploads).
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2_000_000:
            return Response("Request exceeds 2 MB", status_code=413)
    request._body = bytes(body)
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        log.error("Request %s failed (%s)", request_id, type(exc).__name__)
        from fastapi.responses import JSONResponse

        response = JSONResponse(
            {
                "detail": "An internal error occurred. Use the request ID when reporting this issue."
            },
            status_code=500,
        )
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }
    )
    log.info(
        "%s %s %s %.3fs",
        request_id,
        request.method,
        response.status_code,
        time.monotonic() - started,
    )
    return response


async def audit(conn, user, action, resource, details=None):
    await conn.execute(
        "INSERT INTO audit_log(user_id,action,resource_id,details) VALUES (%s,%s,%s,%s)",
        (user["id"], action, str(resource), Jsonb(details or {})),
    )


@app.get("/api/health")
async def health():
    return {
        "status": "alive",
        "service": "geomine-api",
        "time": datetime.now(timezone.utc),
    }


@app.get("/api/ready")
async def ready():
    async with connection() as conn:
        row = await (
            await conn.execute("SELECT version FROM schema_migrations WHERE version=4")
        ).fetchone()
    if not row:
        raise HTTPException(503, "Database migration is required.")
    return {"status": "ready"}


@app.get("/api/health/worker")
async def worker_readiness():
    state = await worker_health()
    if state["status"] != "healthy":
        raise HTTPException(503, "Analysis worker is unavailable.")
    return {"status": "healthy"}


@app.get("/api/workspace/operations")
async def workspace_operations(user: User):
    return await operational_status(user["id"])


@app.get("/api/ops/status", dependencies=[Depends(require_operator)])
async def operator_status():
    return await operational_status()


@app.get("/api/system")
async def system():
    database = "unconfigured"
    try:
        async with connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT version FROM schema_migrations WHERE version=1"
                )
            ).fetchone()
        database = "connected" if row else "migration_required"
    except Exception:
        if settings().database_url:
            database = "unavailable"
    return {
        "database": database,
        "catalog": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "radar_access": True,
        "radar_provider": radar_provider(),
        "radar_coverage": "Africa"
        if radar_provider() == "digital-earth-africa"
        else "provider catalog coverage",
        "analysis_resolution_m": 30
        if radar_provider() == "digital-earth-africa"
        else 10,
        "ai": bool(settings().openrouter_api_key),
        "model_available": settings().model_available,
        "registration": settings().enable_registration,
        "authentication": "firebase" if settings().firebase_enabled else "legacy",
        "max_aoi_km2": settings().max_aoi_km2,
        "realtime": "durable event stream",
    }


class AuthInput(BaseModel):
    email: str = Field(
        min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="Analyst", min_length=1, max_length=80)


@app.get("/api/auth/config")
async def identity_config():
    config = settings()
    return {
        "provider": "firebase" if config.firebase_enabled else "legacy",
        "firebase": {
            "projectId": config.firebase_project_id,
            "apiKey": config.firebase_web_api_key,
            "appId": config.firebase_app_id,
            "authDomain": f"{config.firebase_project_id}.firebaseapp.com",
        }
        if config.firebase_enabled
        else None,
    }


class FirebaseInput(BaseModel):
    id_token: str = Field(min_length=100, max_length=8000)
    legacy_password: str | None = Field(default=None, min_length=12, max_length=128)


@app.post("/api/auth/firebase")
async def firebase_signin(data: FirebaseInput):
    from .identity import link_identity, verify_identity

    identity = await verify_identity(data.id_token)
    await rate_limit("identity:" + digest(identity["uid"]), 15, 900)
    return {"user": await link_identity(identity, data.legacy_password)}


@app.post("/api/auth/register", status_code=201)
async def register(data: AuthInput):
    if settings().firebase_enabled:
        raise HTTPException(409, "Create your account using managed sign-up.")
    if not settings().enable_registration:
        raise HTTPException(403, "Registration is disabled by the operator.")
    email = data.email.strip().lower()
    await rate_limit("register:" + digest(email), 5, 3600)
    user_id = uuid4()
    hashed = await asyncio.to_thread(passwords.hash, data.password)
    try:
        async with connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)",
                    (user_id, email, data.name.strip(), hashed),
                )
                token = await issue_session(conn, user_id)
    except UniqueViolation:
        raise HTTPException(409, "An account with this email already exists.")
    return {
        "token": token,
        "user": {"id": str(user_id), "email": email, "name": data.name.strip()},
    }


@app.post("/api/auth/login")
async def login(data: AuthInput):
    email = data.email.strip().lower()
    await rate_limit("login:" + digest(email), 10, 900)
    async with connection() as conn:
        user = await (
            await conn.execute("SELECT * FROM users WHERE email=%s", (email,))
        ).fetchone()
        valid = await asyncio.to_thread(
            passwords.verify,
            data.password,
            user["password_hash"] if user and user["password_hash"] else DUMMY_HASH,
        )
        if not user or not user["password_hash"] or not valid:
            raise HTTPException(401, "Email or password is incorrect.")
        token = await issue_session(conn, user["id"])
    return {"token": token, "user": {k: user[k] for k in ("id", "email", "name")}}


@app.get("/api/auth/me")
async def me(user: User):
    return user


@app.post("/api/auth/logout", status_code=204)
async def logout(request: Request, user: User):
    async with connection() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE token_hash=%s",
            (digest(request.headers["authorization"][7:]),),
        )


class AreaInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    geometry: dict


@app.get("/api/areas")
async def areas(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT * FROM areas WHERE user_id=%s ORDER BY created_at DESC",
                (user["id"],),
            )
        ).fetchall()


@app.post("/api/areas", status_code=201)
async def add_area(data: AreaInput, user: User):
    geometry, km2 = normalize_geojson(data.geometry, settings().max_aoi_km2)
    area_id = uuid4()
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "INSERT INTO areas(id,user_id,name,geometry,area_km2) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                    (area_id, user["id"], data.name.strip(), Jsonb(geometry), km2),
                )
            ).fetchone()
            await audit(conn, user, "area.created", area_id)
            await emit(conn, user["id"], "area.created", {"id": str(area_id)})
    return row


class MonitorInput(BaseModel):
    monitoring: bool
    interval_hours: int = Field(default=24, ge=6, le=168)


@app.patch("/api/areas/{area_id}")
async def monitor(area_id: UUID, data: MonitorInput, user: User):
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE areas SET monitoring=%s,interval_hours=%s,next_run_at=now() WHERE id=%s AND user_id=%s RETURNING *",
                    (data.monitoring, data.interval_hours, area_id, user["id"]),
                )
            ).fetchone()
            if not row:
                raise HTTPException(404, "Area not found.")
            await audit(conn, user, "area.monitoring", area_id, data.model_dump())
    return row


@app.delete("/api/areas/{area_id}", status_code=204)
async def delete_area(area_id: UUID, user: User):
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "DELETE FROM areas WHERE id=%s AND user_id=%s RETURNING id",
                    (area_id, user["id"]),
                )
            ).fetchone()
            if not row:
                raise HTTPException(404, "Area not found.")
            await audit(conn, user, "area.deleted", area_id)
            await emit(conn, user["id"], "area.deleted", {"id": str(area_id)})


class ConcessionInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    authority: str = Field(min_length=2, max_length=200)
    source_url: str = Field(min_length=8, max_length=1000, pattern=r"^https?://")
    valid_from: date
    valid_to: date
    geojson: dict

    @model_validator(mode="after")
    def dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError("Validity end precedes start.")
        return self


@app.get("/api/concessions")
async def concessions(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT * FROM concessions WHERE user_id=%s ORDER BY created_at DESC",
                (user["id"],),
            )
        ).fetchall()


@app.post("/api/concessions", status_code=201)
async def upload_concessions(data: ConcessionInput, user: User):
    raw = data.geojson
    features = (
        raw.get("features", []) if raw.get("type") == "FeatureCollection" else [raw]
    )
    if not 1 <= len(features) <= 500:
        raise HTTPException(
            422, "Upload between 1 and 500 concession features at a time."
        )
    geometries = [normalize_geojson(feature)[0] for feature in features]
    async with connection() as conn:
        async with conn.transaction():
            ids = []
            for geometry in geometries:
                cid = uuid4()
                await conn.execute(
                    """INSERT INTO concessions(id,user_id,name,authority,source_url,valid_from,valid_to,geometry)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        cid,
                        user["id"],
                        data.name,
                        data.authority,
                        data.source_url,
                        data.valid_from,
                        data.valid_to,
                        Jsonb(geometry),
                    ),
                )
                ids.append(str(cid))
            await audit(
                conn,
                user,
                "concessions.imported",
                ",".join(ids),
                {"count": len(ids), "authority": data.authority},
            )
    return {"ids": ids, "count": len(ids)}


@app.delete("/api/concessions/{concession_id}", status_code=204)
async def delete_concession(concession_id: UUID, user: User):
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "DELETE FROM concessions WHERE id=%s AND user_id=%s RETURNING id",
                    (concession_id, user["id"]),
                )
            ).fetchone()
            if not row:
                raise HTTPException(404, "Concession not found.")
            await audit(conn, user, "concession.deleted", concession_id)


class CatalogInput(BaseModel):
    geometry: dict
    start: date
    end: date
    sensor: Literal["optical", "radar"] = "optical"


@app.post("/api/catalog/search")
async def catalog(data: CatalogInput):
    geometry, _ = normalize_geojson(data.geometry, settings().max_aoi_km2)
    if data.start > data.end or (data.end - data.start).days > 120:
        raise HTTPException(422, "Choose a date range of up to 120 days.")
    items = await search_scenes(geometry, data.start, data.end, data.sensor)
    return {
        "items": [public_scene(i) for i in items],
        "source": "Digital Earth Africa STAC"
        if data.sensor == "radar" and radar_provider() == "digital-earth-africa"
        else "Microsoft Planetary Computer STAC",
        "returned": len(items),
        "limit": 30,
        "searched_at": datetime.now(timezone.utc),
    }


class JobInput(BaseModel):
    area_id: UUID
    engine: Literal["physical", "geomine"] = "physical"
    before_start: date
    before_end: date
    after_start: date
    after_end: date

    @model_validator(mode="after")
    def dates(self):
        if (
            not self.before_start
            <= self.before_end
            < self.after_start
            <= self.after_end
        ):
            raise ValueError(
                "Before and after windows must be ordered and must not overlap."
            )
        if self.after_end > date.today():
            raise ValueError("Future acquisitions cannot be analyzed.")
        if (
            max(
                (self.before_end - self.before_start).days,
                (self.after_end - self.after_start).days,
            )
            > 90
        ):
            raise ValueError("Each acquisition window must be at most 90 days.")
        return self


@app.get("/api/jobs")
async def jobs(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT j.*,a.name AS area_name FROM jobs j JOIN areas a ON a.id=j.area_id WHERE j.user_id=%s ORDER BY j.created_at DESC LIMIT 100",
                (user["id"],),
            )
        ).fetchall()


@app.post("/api/jobs", status_code=202)
async def start_job(data: JobInput, user: User):
    await rate_limit("jobs:" + str(user["id"]), 20, 3600)
    if data.engine == "geomine" and not settings().model_available:
        raise HTTPException(
            409,
            "Train and configure a validated GeoMine-XNet checkpoint before selecting neural inference.",
        )
    if data.engine == "geomine" and radar_provider() == "digital-earth-africa":
        raise HTTPException(
            409,
            "The configured neural checkpoint expects 10m inputs. Select physical analysis for public Africa RTC, or configure the 10m provider.",
        )
    job_id = uuid4()
    async with connection() as conn:
        async with conn.transaction():
            area = await (
                await conn.execute(
                    "SELECT id FROM areas WHERE id=%s AND user_id=%s FOR UPDATE",
                    (data.area_id, user["id"]),
                )
            ).fetchone()
            if not area:
                raise HTTPException(404, "Area not found.")
            active = await (
                await conn.execute(
                    "SELECT id FROM jobs WHERE area_id=%s AND status IN ('queued','running')",
                    (data.area_id,),
                )
            ).fetchone()
            if active:
                raise HTTPException(
                    409, "An analysis for this area is already queued or running."
                )
            row = await (
                await conn.execute(
                    """INSERT INTO jobs(id,user_id,area_id,engine,before_start,before_end,after_start,after_end)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (
                        job_id,
                        user["id"],
                        data.area_id,
                        data.engine,
                        data.before_start,
                        data.before_end,
                        data.after_start,
                        data.after_end,
                    ),
                )
            ).fetchone()
            await audit(conn, user, "job.created", job_id, {"engine": data.engine})
            await emit(conn, user["id"], "job.queued", {"id": str(job_id)})
    return row


@app.post("/api/jobs/{job_id}/cancel")
async def cancel(job_id: UUID, user: User):
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE jobs SET status='cancelled',stage='Cancelled',finished_at=now() WHERE id=%s AND user_id=%s AND status IN ('queued','running') RETURNING id",
                    (job_id, user["id"]),
                )
            ).fetchone()
            if not row:
                raise HTTPException(
                    409, "Analysis does not exist or has already finished."
                )
            await audit(conn, user, "job.cancelled", job_id)
            await emit(conn, user["id"], "job.cancelled", {"id": str(job_id)})
    return {"status": "cancelled"}


@app.get("/api/alerts")
async def alerts(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT al.*,a.name AS area_name FROM alerts al JOIN areas a ON a.id=al.area_id WHERE al.user_id=%s ORDER BY al.created_at DESC LIMIT 2000",
                (user["id"],),
            )
        ).fetchall()


class AlertInput(BaseModel):
    status: Literal["new", "investigating", "dismissed", "confirmed"]
    note: str = Field(default="", max_length=4000)


@app.patch("/api/alerts/{alert_id}")
async def review(alert_id: UUID, data: AlertInput, user: User):
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE alerts SET status=%s,note=%s WHERE id=%s AND user_id=%s RETURNING *",
                    (data.status, data.note, alert_id, user["id"]),
                )
            ).fetchone()
            if not row:
                raise HTTPException(404, "Candidate not found.")
            await audit(conn, user, "alert.reviewed", alert_id, data.model_dump())
            await emit(
                conn,
                user["id"],
                "alert.reviewed",
                {"id": str(alert_id), "status": data.status},
            )
    return row


@app.get("/api/jobs/{job_id}/export")
async def export(job_id: UUID, user: User):
    async with connection() as conn:
        job = await (
            await conn.execute(
                "SELECT * FROM jobs WHERE id=%s AND user_id=%s", (job_id, user["id"])
            )
        ).fetchone()
        if not job:
            raise HTTPException(404, "Analysis not found.")
        rows = await (
            await conn.execute(
                "SELECT * FROM alerts WHERE job_id=%s AND user_id=%s",
                (job_id, user["id"]),
            )
        ).fetchall()
    result = {
        "type": "FeatureCollection",
        "provenance": job["result"],
        "features": [
            {
                "type": "Feature",
                "id": str(r["id"]),
                "geometry": r["geometry"],
                "properties": {
                    k: jsonable_encoder(r[k])
                    for k in (
                        "area_ha",
                        "score",
                        "legal_context",
                        "status",
                        "note",
                        "created_at",
                    )
                },
            }
            for r in rows
        ],
    }
    return Response(
        json.dumps(result),
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="geomine-{job_id}.geojson"'
        },
    )


@app.get("/api/events")
async def events(request: Request, user: User, after: int = 0):
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(422, "Invalid event cursor.")

    async def stream():
        nonlocal cursor
        started = time.monotonic()
        while not await request.is_disconnected() and time.monotonic() - started < 300:
            async with connection() as conn:
                rows = await (
                    await conn.execute(
                        "SELECT id,type,payload FROM events WHERE user_id=%s AND id>%s ORDER BY id LIMIT 100",
                        (user["id"], cursor),
                    )
                ).fetchall()
            for row in rows:
                cursor = row["id"]
                yield f"id: {cursor}\nevent: update\ndata: {json.dumps(row)}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


@app.get("/api/audit")
async def audit_log(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT id,action,resource_id,details,created_at FROM audit_log WHERE user_id=%s ORDER BY id DESC LIMIT 100",
                (user["id"],),
            )
        ).fetchall()


@app.get("/api/briefs")
async def briefs(user: User):
    async with connection() as conn:
        return await (
            await conn.execute(
                "SELECT * FROM briefs WHERE user_id=%s ORDER BY created_at DESC LIMIT 50",
                (user["id"],),
            )
        ).fetchall()


@app.post("/api/jobs/{job_id}/brief")
async def brief(job_id: UUID, user: User):
    if not settings().openrouter_api_key:
        raise HTTPException(
            409, "Set OPENROUTER_API_KEY on the backend to enable analyst briefs."
        )
    await rate_limit("brief:" + str(user["id"]), 5, 3600)
    async with connection() as conn:
        job = await (
            await conn.execute(
                """SELECT j.id,j.result,j.before_start,j.before_end,j.after_start,j.after_end,
                a.name AS area_name,a.area_km2 FROM jobs j JOIN areas a ON a.id=j.area_id
                WHERE j.id=%s AND j.user_id=%s AND j.status='completed'""",
                (job_id, user["id"]),
            )
        ).fetchone()
    if not job:
        raise HTTPException(404, "A completed analysis is required.")
    model = settings().openrouter_model
    if model != "openrouter/free" and not model.endswith(":free"):
        raise HTTPException(409, "Only free OpenRouter model routes are enabled.")
    async with httpx.AsyncClient(timeout=90) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings().openrouter_api_key}",
                    "X-Title": "GeoMine Observatory",
                },
                json={
                    "model": model,
                    "max_tokens": 1600,
                    "reasoning": {"enabled": False},
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "system",
                            "content": ANALYST_INSTRUCTIONS,
                        },
                        {"role": "user", "content": json.dumps(brief_evidence(job))},
                    ],
                },
            )
            response.raise_for_status()
            body = response.json()
            actual_model = body.get("model", model)
            content = analyst_narrative(
                body["choices"][0]["message"]["content"], actual_model
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(
                502,
                "The free AI provider is unavailable or rate limited. Retry later; the analysis results are still available.",
            )
    async with connection() as conn:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "INSERT INTO briefs(id,user_id,job_id,model,content) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                    (uuid4(), user["id"], job_id, actual_model, content),
                )
            ).fetchone()
            await audit(
                conn,
                user,
                "brief.created",
                row["id"],
                {"job_id": str(job_id), "model": actual_model},
            )
    return row


@app.get("/api/jobs/{job_id}/imagery/{epoch}")
async def imagery(job_id: UUID, epoch: Literal["before", "after"], user: User):
    from .catalog import STAC
    from .processing import render_optical_preview

    await rate_limit("imagery:" + str(user["id"]), 60, 3600)
    async with connection() as conn:
        job = await (
            await conn.execute(
                """SELECT j.result,a.geometry FROM jobs j JOIN areas a ON a.id=j.area_id
            WHERE j.id=%s AND j.user_id=%s AND j.status='completed'""",
                (job_id, user["id"]),
            )
        ).fetchone()
    if not job or not job["result"]:
        raise HTTPException(404, "Completed analysis not found.")
    records = [
        s for s in job["result"]["scenes"] if s["collection"] == "sentinel-2-l2a"
    ]
    if len(records) != 2:
        raise HTTPException(
            409, "This analysis does not contain both optical acquisitions."
        )
    record = records[0 if epoch == "before" else 1]
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.get(
                f"{STAC}/collections/sentinel-2-l2a/items/{record['id']}"
            )
            response.raise_for_status()
            item = response.json()
        image = await asyncio.to_thread(
            render_optical_preview,
            job["geometry"],
            item,
            job["result"].get("resolution_m", 10),
        )
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502, "Unable to render dated optical evidence. Retry provider access."
        )
    return Response(
        image,
        media_type="image/png",
        headers={"X-Acquisition-Date": record["datetime"]},
    )
