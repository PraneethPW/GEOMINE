CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS users (
 id uuid PRIMARY KEY, email text UNIQUE NOT NULL, name text NOT NULL,
 password_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS rate_limits (
 key text NOT NULL, bucket bigint NOT NULL, count integer NOT NULL,
 PRIMARY KEY(key, bucket)
);
CREATE TABLE IF NOT EXISTS areas (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name text NOT NULL, geometry jsonb NOT NULL, area_km2 double precision NOT NULL,
 monitoring boolean NOT NULL DEFAULT false, interval_hours integer NOT NULL DEFAULT 24,
 next_run_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS areas_owner ON areas(user_id);
CREATE TABLE IF NOT EXISTS concessions (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name text NOT NULL, authority text NOT NULL, source_url text NOT NULL,
 valid_from date NOT NULL, valid_to date NOT NULL, geometry jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS concessions_owner ON concessions(user_id);
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 area_id uuid NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed','cancelled')),
 stage text NOT NULL DEFAULT 'Awaiting worker', progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
 engine text NOT NULL CHECK(engine IN ('physical','geomine')),
 before_start date NOT NULL, before_end date NOT NULL, after_start date NOT NULL, after_end date NOT NULL,
 result jsonb, error text, attempts integer NOT NULL DEFAULT 0,
 lease_token uuid, lease_until timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz, finished_at timestamptz,
 CHECK(before_start <= before_end AND before_end < after_start AND after_start <= after_end)
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS alerts (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 area_id uuid NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
 geometry jsonb NOT NULL, area_ha double precision NOT NULL,
 score double precision NOT NULL CHECK(score BETWEEN 0 AND 1),
 legal_context text NOT NULL CHECK(legal_context IN ('unknown','outside_supplied_concessions','inside_supplied_concession')),
 status text NOT NULL DEFAULT 'new' CHECK(status IN ('new','investigating','dismissed','confirmed')),
 note text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_owner ON alerts(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS events (
 id bigserial PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_owner ON events(user_id,id);
CREATE TABLE IF NOT EXISTS audit_log (
 id bigserial PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 action text NOT NULL, resource_id text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS briefs (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, model text NOT NULL,
 content text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS worker_heartbeats (
 id uuid PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL CHECK(state IN ('idle','running','stopped')),
 job_id uuid REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS worker_heartbeat_recent ON worker_heartbeats(last_seen_at DESC);
INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT DO NOTHING;

ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_firebase_identity ON users(firebase_uid) WHERE firebase_uid IS NOT NULL;
INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT DO NOTHING;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id uuid REFERENCES worker_heartbeats(id) ON DELETE SET NULL;
ALTER TABLE rate_limits ADD COLUMN IF NOT EXISTS expires_at timestamptz NOT NULL DEFAULT now()+interval '2 days';
CREATE INDEX IF NOT EXISTS rate_limit_expiry ON rate_limits(expires_at);
INSERT INTO schema_migrations(version) VALUES (4) ON CONFLICT DO NOTHING;
