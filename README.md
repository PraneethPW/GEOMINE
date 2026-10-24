# GeoMine-XNet Observatory

Live application: https://geomine-xnet.vercel.app · API readiness: https://geomine-api-production.up.railway.app/api/ready

React + TypeScript + Tailwind CSS + Three.js + Framer Motion frontend, FastAPI/PyTorch backend, Neon PostgreSQL persistence, Railway API/worker deployment, and Vercel frontend deployment.

This repository implements an environmental monitoring application based on the supplied GeoMine-XNet paper. **No demonstration records, invented detections, paper accuracy numbers, or synthetic scenes populate the application.** Empty workspaces stay empty. Missing credentials produce explicit setup errors.

## Project structure

```text
GEOMINE-XNET/
├── frontend/                 React application and Vercel configuration
│   ├── src/pages/            Public narrative, login, and signup pages
│   ├── src/components/       Globe, evidence comparison, map, and measured-data charts
│   ├── src/App.tsx           Public/private routing and lazy workspace loading
│   ├── src/Workspace.tsx     Authenticated pages, workflows, and live event subscriptions
│   └── .env.example
├── backend/                  FastAPI, Postgres queue, geospatial processing, and ML
│   ├── app/main.py           Authenticated HTTP API and event stream
│   ├── app/worker.py         Durable queue, scheduled monitoring, fenced leases
│   ├── app/processing.py     Real COG reading, registration, change evidence, vectorization
│   ├── app/ml/               Model, dataset preparation/import, training, model installation
│   ├── app/schema.sql        Idempotent schema migration
│   └── tests/                Unit and actual PostgreSQL integration tests
├── docs/                     Deployment, training, and verification notes
└── .github/workflows/ci.yml
```

## Run locally

Use Node.js 24 and Python 3.12+ (install Python 3.12 with your system package manager if it is not present). From this project directory:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `backend/.env` with your **real Neon DATABASE_URL**, with `sslmode=require`. Keep `DATABASE_SCHEMA=geomine` for the dedicated application schema. Optionally configure `PC_SUBSCRIPTION_KEY` for the 10m Planetary Computer radar source. Without it, physical analysis automatically uses public Digital Earth Africa RTC (Africa coverage, 30m analysis grid). Set `OPENROUTER_API_KEY` for AI briefs. Do not paste secrets into frontend files or commit `.env`.

```bash
python -m app.db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the worker using the same backend environment:

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

In a third terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the printed localhost URL. The public landing narrative loads independently of a database. Accounts, catalog searches, and durable workflows are available through the authenticated workspace and require the backend configuration. Local development proxies `/api` to port 8000. Production **must** set `VITE_API_URL` to the Railway API HTTPS origin. Vercel runs `npm run build:vercel`, which rejects missing or local/private API origins before bundling.

The existing directory `Freelance Projects ` on this machine contains a trailing space. Quote its complete path in terminal commands.

## Navigation and charts

The public `/` page contains the hero, a visual story, the optical/radar approach, source provenance, and a signup invitation. It contains no analysis controls, catalog, dashboard, testimonial cards, or workspace data. `/login` and `/signup` are separate screens. All `/app/*` routes require a checked session.

| Route | Purpose |
| --- | --- |
| `/app/overview` | Measured change timeline, processing distribution, overlap quality, and recent activity |
| `/app/map` | Study areas and mapped evidence |
| `/app/catalog` | Live scene search, acquisition histogram, and optical cloud-cover curve |
| `/app/analyses` | Analysis history and new comparisons |
| `/app/analyses/:id` | Individual result, source imagery slider, and quality measurements |
| `/app/candidates` | Review evidence, status distribution, and evidence-index histogram |
| `/app/concessions` | Authoritative boundary import and provenance |
| `/app/reports` | Human-reviewed AI briefs linked to completed analyses |
| `/app/system` | Service/model configuration and monitoring controls |

Charts are derived from the authenticated API response, with honest empty states and displayed scope limits. Overview summaries cover the latest 100 analyses and up to 2,000 candidates; acquisition dates drive the timeline. Selecting a point opens the corresponding observation. Live events refresh the workspace across routes. A temporary authentication-service outage preserves the session and offers retry.

## Working flow

1. Sign in with Google, or register with email/password (at least 12 characters) and verify your email. Existing GeoMine accounts link once using their previous password; their workspace IDs and observations are preserved.
2. Place a study box on the map or import a WGS84 Polygon/MultiPolygon, up to the configured area limit (25 km² in the current deployment). The default Ghana map viewport is a navigation starting point, not a saved or claimed detection.
3. Search the live Microsoft Planetary Computer STAC catalog. Scene footprints, acquisition times, cloud metadata, and original record links come from the provider.
4. Optionally import authoritative concession GeoJSON, including its issuing authority, source URL, and validity dates.
5. Create an analysis with ordered, non-overlapping before/after windows. The worker reads actual Sentinel-2 RGB/NIR and co-orbital Sentinel-1 VV/VH pixels into a common UTM grid (30m for public Africa RTC; 10m for the configured Planetary Computer source).
6. Follow durable progress events. Inspect completed results and source acquisitions, review disturbance candidates, write investigation notes, export GeoJSON, or request an OpenRouter brief grounded in the computed result.
7. Enable daily monitoring in System to queue recurring comparisons while the worker runs.

## Two explicitly distinguished analysis modes

**Physical change detector:** an implemented, uncalibrated screening algorithm combining vegetation loss with median-filtered radar backscatter change. It rejects stable-radar seasonal-like changes, excludes cloudy optical observations, and emits disturbance candidates for review. It is not a trained mining classifier and does not claim the paper's accuracy or cloud resilience.

**GeoMine-XNet:** a paper-informed implementation of temporal weight-sharing optical/radar Swin encoders, windowed cross attention, cloud gating, a phenology consistency filter, multiscale difference decoding, and concession masking. No weights are bundled. Train on real aligned labeled data, measure held-out performance, install a checksum-verified safetensors checkpoint, and configure the artifact paths before activating it. The paper does not specify enough implementation detail for an exact reproduction; this implementation has approximately 58.6M parameters, not the paper's claimed 41.8M. See [training](docs/TRAINING.md).

Concession matching reports **inside/outside supplied concessions** or **unknown**. It never establishes illegality. The model's raw candidates remain reviewable, including those inside supplied concessions. A separate neural output implements the paper's multiplicative outside-concession mask.

## Deployment and status

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for Railway API/worker and Vercel setup. See [VERIFICATION.md](docs/VERIFICATION.md) for the checks actually performed and remaining external dependencies.

The frontend, API, and private worker are deployed on Vercel/Railway with Neon persistence. Authenticated workflows have been exercised against real satellite data in an isolated local workspace; authenticated cloud acceptance remains to be performed in a real user workspace. **The untrained neural model is not represented as a validated production mining detector.** Production readiness requires exercising the configured raster pipeline, trained checkpoint evaluation if enabled, infrastructure load testing, access policy review, operational monitoring, and field review of candidates.

## Data and operational limits

- “Realtime” means live catalog queries and streamed processing/review events. Satellite observations arrive on acquisition/revisit/provider schedules; this is not continuous video.
- The default keyless radar provider is Digital Earth Africa RTC, with Africa coverage and native 0.0002° cells (approximately 20m), analyzed conservatively on a 30m grid. For the broader 10m Planetary Computer radar source, configure PC_SUBSCRIPTION_KEY. There is no fake-data fallback.
- Each job needs full optical-scene coverage and a VV/VH radar pair with matching relative orbit/direction. Adjacent Digital Earth Africa radar tiles are combined only when platform, absolute orbit, relative orbit, and direction identify the same pass; all tile IDs remain in the result. Radar/optical dates must be within 12 days. Empty or incompatible coverage causes an actionable error.
- COG reads are bounded by AOI and raster grid size. Optical reflectance uses product XML quantification/offsets when explicit STAC scale/offset is absent. Signed asset URLs are not persisted or returned to the frontend.
- Scene search returns up to 30 catalog results; processing considers up to 100 per sensor/window. Wide windows may omit older scenes beyond that cap. Areas crossing optical source tiles should be divided into smaller study areas; adjacent same-pass public radar tiles are supported.
- OpenRouter defaults to `nvidia/nemotron-3.5-lightning:free`. The backend refuses paid model routes, limits requests, rejects moderation-only/incomplete narrative responses, and surfaces provider outages/rate limits. Briefs use explicit measured evidence and require human review; model text can still be imprecise. Free availability is not a production SLA.
- Firebase manages Google/email sign-in, email verification, and password recovery using its default sender, without a custom domain. The API verifies signed ID tokens, revocation, disabled-account status, and verified email. Existing Argon2 accounts require their previous password once to link; matching email alone never merges workspaces. Browser persistence is session-only. Legacy sessions remain available only for unlinked accounts. MFA and organization sharing are not implemented.
- Database events are replayable by cursor across API replicas without an in-memory broker. The client reconnects automatically. An individual stream rotates after five minutes for renewed auth checks.
- Queue claims use `FOR UPDATE SKIP LOCKED`; lease tokens and status predicates prevent a cancelled/timed-out worker from committing output. A parent supervisor terminates and reaps timed-out child processes. Independent heartbeats expose worker availability; stale/stopped-worker claims can be recovered without waiting for the full lease. Failed jobs can be re-created from the UI; there is no infinite retry loop.
- Firebase sends verification/reset emails. In-app events and audit history are durable; external operational alerts are not yet connected. The System page shows actual worker health and workspace metrics. Expired sessions/rate-limit buckets and old worker heartbeats are pruned; observation/audit history is retained. See docs/OPERATIONS.md for encrypted backups and recovery.

## Verification commands

```bash
cd frontend
npm run lint:a11y
npm run build
npm run check:bundle
npm audit --omit=dev

cd ../backend
pytest -q
# To include database integration tests, point ONLY to an isolated test database:
TEST_DATABASE_URL='postgresql://…/geomine_test' pytest -q
```

The database integration test creates a unique test schema and drops only that schema when done. The application database is not seeded. Numerical algorithm tests and test-only accounts do not enter the running application.

## References

- Supplied paper: GeoMine-XNet: A Multimodal SAR-Optical Cross-Attention Transformer for Cloud-Resilient and Phenology-Aware Illegal Mining Change Detection.
- [Microsoft Planetary Computer STAC](https://planetarycomputer.microsoft.com/docs/reference/stac/)
- [Sentinel-1 RTC access requirements](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc)
- [Sentinel-2 radiometric processing](https://sentiwiki.copernicus.eu/web/s2-processing)
- [OpenRouter model](https://openrouter.ai/nvidia/nemotron-3.5-lightning:free)
- [Vite deployment on Vercel](https://vercel.com/docs/frameworks/frontend/vite)

Earth texture is sourced from the Three.js examples repository. The decorative globe is not live satellite telemetry. Basemap attribution is shown on the map; dated Sentinel data is used for analysis. Fonts are bundled locally through Fontsource (SIL Open Font License).

## Public radar access

No Planetary Computer key is needed for the default Ghana/Africa physical workflow. The application uses [Digital Earth Africa terrain-corrected gamma0 backscatter](https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html), applies its valid-data/shadow mask, pairs matching radar orbits, and records provider/source links in the result. Public-source analysis runs at 30m. Nine connected analysis pixels correspond to a minimum candidate area of 0.81ha at that resolution. This does not provide 10m neural inference or radar coverage outside Africa. The UI and exports retain the actual grid and provider.
