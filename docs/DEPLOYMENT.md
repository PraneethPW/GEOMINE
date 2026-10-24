# Deploy on your selected platforms

## Current release

Frontend: https://geomine-xnet.vercel.app  
API: https://geomine-api-production.up.railway.app

API and private worker are deployed to the existing `geomine-xnet` Railway project using CLI source uploads. The Vercel project is also linked and deployed. Resource IDs are in `deployment-state.json`; reuse these resources when updating. Initial production AOIs are limited to 25km². Registration is enabled for onboarding. Create your real account through **Enter workspace**; no accounts or observations are preloaded.

The Docker image includes the raster runtime's Linux libraries and checks imports during build. The API starts with `python -m app.server`, which reads PORT directly without relying on shell expansion. The worker's explicit Railway start command is `python -m app.worker`; it has no HTTP healthcheck/domain. Both services use `python -m app.db` before deployment. Live service commands/readiness were configured explicitly as well as retained in the local configuration files.

For subsequent CLI uploads, use only the backend source, requirements, Dockerfile, and intended Railway configuration. Exclude `.env`, `.venv`, caches, models, and datasets. Use `railway up <sanitized-backend-directory> --path-as-root --project <existing-project-id> --service <existing-service-id> --environment production`. Confirm the intended worker/API command remains configured. Transfer secrets through stdin or the service environment UI, never command-line values or frontend variables. The following sections document setup from scratch and operator acceptance.

## 1. Neon

Create a dedicated Neon project/database. Copy its pooled PostgreSQL connection string with TLS enabled into **Railway service variables**, never frontend variables. The code uses `psycopg` with prepared statements disabled for transaction-pool compatibility. `DATABASE_SCHEMA=geomine` selects a dedicated application schema; every connection sets a transaction-local search path so pooled transactions remain isolated from other application tables.

Run `python -m app.db` once against that database, or use the Railway pre-deploy command included in the service configuration. Migrations use a PostgreSQL transaction advisory lock so concurrent API/worker deployments serialize schema creation. No records are seeded.

Do not reuse a production application database for integration tests. Choose a separate test database/branch.

## 2. Railway API

Push this repository to your Git provider. Create a Railway service using **root directory `/backend`** and the Dockerfile. The configuration in `backend/railway.json` sets:

- Pre-deploy: `python -m app.db`
- Start: `python -m app.server`
- Readiness: `/api/ready`
- Restart on failure

Set these variables:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon pooled TLS connection string |
| `FRONTEND_ORIGIN` | Exact Vercel frontend origin; comma-separated origins if needed |
| `APP_ENV` | `production` |
| `PC_SUBSCRIPTION_KEY` | Optional key for the 10m Planetary Computer source; leave empty for public Africa RTC at 30m |
| `OPENROUTER_API_KEY` | Your private OpenRouter key |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-lightning:free` or an explicitly free `:free` route |
| `ENABLE_REGISTRATION` | `false` for an operator-controlled deployment after initial onboarding |
| `MAX_AOI_KM2` | `100` or a smaller operational limit |
| `JOB_TIMEOUT_SECONDS` | `1800` by default |

Expose only the API's generated HTTPS domain. Keep the worker private. Backend `/api/system` exposes readiness flags, not secret values. `/api/health` is liveness; `/api/ready` requires the database/migration.

## 3. Railway worker

Create a second service from the same repository with root `/backend`. Select the worker configuration path `railway.worker.json` in service settings (relative to that service's selected root), or set the commands explicitly:

- Pre-deploy: `python -m app.db`
- Start: `python -m app.worker`
- Remove the HTTP healthcheck; the worker has no public HTTP listener.
- Same Neon connection and optional provider key as API. Do not expose a domain.

Start with one worker and measure RAM/CPU on representative AOIs. The physical pipeline reads multiple float32 bands and vectorizes components; the maximum AOI is not a guarantee of a small memory footprint. Use a smaller AOI limit if resources are constrained.

For neural inference, build the worker with Docker build argument `INSTALL_ML=true`, provision adequate memory, and install a trained artifact version on an attached volume, then set `MODEL_PATH` and `MODEL_MANIFEST_PATH`. Configure artifact readiness on the API too. API and worker must agree on which model version is active. The worker reads the artifact during analysis, checks its manifest/checksum, and persists the model metadata in the result.

For GPU training, use a GPU host with `requirements-ml.txt` and the training commands in TRAINING.md. The included CPU worker image is an inference image, not a claim that a Railway CPU service can economically reproduce the paper's RTX 4090 training run.

## 4. Vercel frontend

Create a Vercel project from the same repository, selecting **root `frontend`** and framework **Vite**:

- Node.js 24
- Install: `npm ci`
- Build: `npm run build:vercel`
- Output: `dist`
- `VITE_API_URL=https://YOUR-API.up.railway.app`

`frontend/vercel.json` configures the deployment build, response headers, and targeted SPA rewrites for `/app/:path*`, `/login`, `/signup`, and `/forgot-password`. Direct private links load the router and then check authentication; missing assets retain real HTTP 404 responses. The Vercel build refuses an unset, malformed, or local/private `VITE_API_URL`. VITE variables are embedded at build time; changing the backend URL requires a new frontend deployment.

Set Railway `FRONTEND_ORIGIN` to the actual frontend origin. Avoid wildcard CORS. Preview deployments need explicitly allowed origins or a separate preview environment. Session bearer tokens are never placed in URL query strings.

## 5. Cloud acceptance

After service variables are configured:

1. Confirm API `/api/ready` returns 200 and `/api/system` reports the intended database/provider/model state.
2. Register a real workspace, save a small study area, reload, and confirm persistence.
3. Import actual concession data only when its source/validity is known.
4. Search both sensor catalogs. Run a small physical analysis with actual valid acquisitions. Confirm the worker receives it, progress streams, and source IDs match the result.
5. Review one actual candidate when present, export GeoJSON, and verify the audit decision. Zero candidates is a valid measured result; do not insert candidates to force an acceptance test.
6. Generate an AI brief with the real OpenRouter key and verify unavailable/rate-limit responses.
7. Enable monitoring and verify the private worker schedules the next comparison.
8. Test a service restart/cancellation during a job and confirm stale workers cannot commit.

## Operational work before broad public release

See OPERATIONS.md for verified encrypted backup/restore commands and the remaining external scheduling/alert setup; monitor worker failures, queue age, runtime/memory, SSE connections, and provider errors. Set an explicit account/registration policy, implement the identity lifecycle required by the deployment, and establish event/audit/rate-limit retention. Expired sessions/rate-limit buckets and stale worker heartbeats are pruned in bounded batches; observation and audit history are retained. Size Neon storage and compute accordingly.

The free OpenRouter route has provider quotas and no guaranteed availability. The application's measurement/review workflow remains independent of whether an AI brief is available.

## Keyless radar default

When PC_SUBSCRIPTION_KEY is empty, API and worker use Digital Earth Africa s1_rtc. This is actual radiometrically terrain-corrected gamma0 power, not uncalibrated GRD. It covers Africa; no-data/coverage errors are explicit. Native angular pixels are approximately 20m, and analysis uses 30m UTM cells. The current neural checkpoint contract expects 10m inputs, so neural mode is disabled for this source. Set the same optional provider configuration on both API and worker.

## Firebase identity configuration

Set FIREBASE_PROJECT_ID, FIREBASE_WEB_API_KEY, FIREBASE_APP_ID, FIREBASE_SERVICE_ACCOUNT_JSON and a random OPERATIONS_TOKEN (at least 32 characters) on the API. The service account has Firebase Auth Viewer only. Keep its JSON private, transfer through stdin/service UI, and never set it on Vercel or the worker. The frontend obtains public Firebase SDK config from `/api/auth/config`; it contains no private signing key. Backend auth is authoritative.

The existing Firebase project and web app are reused. `firebase.json` configures only authentication; no hosting, Firestore or application database is moved. Google/email providers, default verification/reset delivery, authorized production domains, 12-character policy and email privacy are configured. Use a separate Firebase project for staging. Refer to OPERATIONS.md for legacy-account linking and real-user acceptance.
