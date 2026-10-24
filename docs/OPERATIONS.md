# Operations and recovery

Use existing resources listed in deployment-state.json. No external uptime service, alert destination, or automatic off-machine backup schedule is configured by this release.

## Health and failure response

- `/api/health`: API liveness.
- `/api/ready`: Neon connection and schema migration 4 readiness.
- `/api/health/worker`: minimal public heartbeat health, HTTP 503 when no fresh worker is available.
- `/api/workspace/operations`: authenticated owner-scoped queue, completed/failed 24-hour counts, p95 runtime, monitored/overdue areas.
- `/api/ops/status`: global operator data, requires `Authorization: Bearer OPERATIONS_TOKEN`. Keep this token out of browsers, URLs, screenshots and logs.

The System page polls real workspace metrics every 30 seconds while visible. A healthy heartbeat does not guarantee provider availability or analysis accuracy. Review failures and queue age, plus Railway CPU/RAM and service logs. Connect an external checker to readiness and worker health, with an operator-selected alert destination; only then is unattended alert delivery active.

The worker supervisor maintains heartbeats while analysis runs in a child process. Hard deadlines and shutdown terminate/reap the child. Lease tokens fence stale results; a stale/stopped worker permits reclamation. Inspect a failed job's original source/coverage error before retrying. Failed history is preserved; no infinite retry loop hides provider failures. Optical/radar selection tries compatible alternative dates while retaining orbit, coverage, and 12-day constraints.

Do not interpret zero candidates as no disturbance. In particular, a completed run with zero clear optical overlap reports coverage but cannot assess physical disturbance. Select another window. Public Africa RTC uses 30 m; current neural mode requires reviewed artifacts and compatible 10 m input.

## Data maintenance

Hourly bounded, locked batches remove expired opaque sessions, expired rate-limit buckets, and week-old stale worker heartbeats. Observation records, source provenance, candidates, decisions, events and audit history are not deleted by maintenance. Monitor storage and establish a deliberate retention policy before broad public use.

## Encrypted backups

Run backups from a trusted operator machine with the backend environment. Store BACKUP_ENCRYPTION_KEY (base64 random 32 bytes) separately from encrypted archives; losing it prevents recovery. The tool uses schema-scoped custom pg_dump with AES-256-GCM authentication, private temporary files and no-overwrite publication. It does not copy other projects' schemas.

Use a PostgreSQL client at least as new as the source server. Neon was PostgreSQL 18.6 during verification; pg_dump 17 fails against it. On this machine libpq 18 is installed at `/opt/homebrew/opt/libpq/bin` without changing existing PostgreSQL services.

```bash
cd backend
export PG_DUMP_BIN=/opt/homebrew/opt/libpq/bin/pg_dump
python -m app.backup create --output /private/backup-location/geomine-DATE.backup
```

Copy encrypted archives to independently controlled off-machine storage and maintain the encryption key in a separate secret store. Choose retention and schedule explicitly; the application does not currently perform this transfer or scheduling. Back up before schema changes and test restores regularly.

## Restore drill

Provision a separate **empty** database and set RESTORE_DATABASE_URL privately. Never point it at the application database. The tool rejects the configured source database and nonempty targets, authenticates the entire archive before database writes, and restores transactionally. It never runs a destructive clean/replace.

```bash
export PG_RESTORE_BIN=/opt/homebrew/opt/libpq/bin/pg_restore
python -m app.backup restore-drill --archive /private/backup-location/geomine-DATE.backup
```

Compare table counts and representative source/audit records, then exercise a separate application instance against the restore. A real Neon-to-isolated-Postgres drill passed on 25 October 2026, along with tamper detection and source-target rejection. Evidence contains counts only, not credentials or backup contents.

## Identity lifecycle

Firebase project geomine-ff45c enables email/password and Google sign-in using default Firebase email delivery; a custom domain is not needed. Production frontend domains are authorized. Password policy enforces 12–128 characters and improved email privacy is enabled. The API uses a dedicated Firebase Auth Viewer service account for revoked/disabled-user checks; its private key belongs only in API variables.

Google sign-in supplies a verified identity; email/password users must complete email verification. Password reset uses Firebase's hosted action flow. Existing same-email GeoMine workspaces require the old GeoMine password once before UID linking; all workspace ownership remains on the existing Neon UUID. Legacy login is available for unlinked accounts. If the old password is lost before linking, do not bypass ownership checks; handle a manual, documented recovery review. A Firebase reset alone does not prove ownership of a previously unverified legacy account.

Real user Google/login/link, inbox verification, reset delivery and refreshed-session acceptance must be completed by the account owner. Administrative configuration and unit tests do not establish email delivery or human account acceptance. MFA and organization roles remain future requirements.
