# Production hardening — 25 October 2026

This is the current release record. Earlier records below are retained as dated history; their former limitations and deployment IDs are superseded where explicitly addressed here.

- Vercel frontend `dpl_6FC7Aomtvd21dLHim3bA5PhYiSLz` READY; canonical URL https://geomine-xnet.vercel.app. Existing Vercel protection remains enabled.
- Railway API `115ab066-1f28-45ab-8ccd-c17dad1b77f2` and private worker `1614c2bb-0c75-4de9-a662-17accd27bc9a` SUCCESS, one running replica each. Schema migration 4 is live. Readiness and worker-health endpoints return 200; anonymous workspace and operator requests return 401; operator token access returns 200.
- Existing Firebase project/web app reused; real admin API calls confirm Google/email providers, enforced 12-character password policy and improved email privacy. Dedicated verifier service account is limited to Firebase Auth Viewer. Private key is API-only. Public runtime configuration contains no server key.
- User confirmed reaching their real workspace through the deployed Google sign-in. Inbox delivery of verification/reset and a complete recovery roundtrip remain human acceptance items. Existing workspaces require old-password proof before same-email linking; unit tests do not substitute for real provider acceptance.
- 39 backend tests passed with real isolated PostgreSQL and optional ML dependencies. Ruff passed. Tests exercise identity-link ownership, verified-email requirements, tenant isolation, heartbeat recovery, bounded cleanup, queue fencing, deadline supervision, catalog/raster alignment, geographic label audit and previous geospatial/AI contracts. Firebase claim fixtures are isolated test contracts; the real project was not seeded with QA users.
- Frontend TypeScript production build, jsx-a11y lint, production dependency audit (zero vulnerabilities) and bundle gate passed. Initial static JS gzip 136,458 bytes and CSS gzip 20,807 bytes. Workspace/map/Three/Firebase code remains lazy. Large map/3D chunks still require representative-device profiling.
- Desktop browser checks confirmed initial modal focus, Shift-Tab wrapping, Escape dismissal and focus return, route-heading focus, motion pause state, real System metrics, actual source imagery/coverage warning, deployed Google/email controls and recovery page. This is not a full accessibility certification; physical mobile devices, screen readers, load and broad performance checks remain pending.
- Scheduled acceptance job `aea7935f-1612-4d93-8a86-b1bfdfd22488` was created by the actual scheduler and completed through the supervised worker against remote Sentinel COGs in a separate local database. The first incompatible-date attempt remains in history. Joint optical/radar selection now finds compatible alternatives. Six source records, 100% radar validity and 0% clear optical overlap were measured. Physical disturbance could not be assessed for these cloudy dates; the UI explicitly says zero candidates is not no disturbance. Monitoring was disabled after this local drill. No production monitoring preference or sample records were inserted.
- Real Neon schema backup encrypted using AES-256-GCM was restored into a fresh isolated database. Counts matched across all nine tables present before the migration. Source-target rejection and tamper detection passed; no production writes occurred. PostgreSQL 18 client installed alongside existing services to match Neon 18.6. Backup/key remain private and are excluded from all deliverables.
- Free Colab notebook, reviewed-data audit/import/preparation, AMP/gradient accumulation, per-epoch artifacts, explicit final-test gate and operator release-review gate are ready. No GPU training, trained weights, calibration or held-out model performance has been produced. Real public mining metadata was verified for annotation planning, not substituted as temporal fusion truth.

Remaining: real verification/reset inbox acceptance, external uptime alert delivery and scheduled off-machine backup retention, representative load/device/screen-reader tests, actual reviewed paired labels/compatible 10 m source access/GPU training and independent model evaluation. MFA and organization roles remain unimplemented. Git CI configuration exists but no Git repository/autodeploy is connected.

See OPERATIONS.md and TRAINING.md for concrete commands and prerequisites.

---

# Radar boundary fix — 25 October 2026

The user's real failed analysis crossed latitude 7° at a Digital Earth Africa tile boundary. Its 19.55km² study area was covered by adjacent tiles, but no single radar tile covered the whole polygon. Requiring one full-coverage tile incorrectly rejected both windows with a co-orbital-pair error.

The worker now groups adjacent public radar tiles only when platform, absolute orbit, relative orbit, and direction identify the same pass. It checks union coverage, reads each tile into the same bounded grid, keeps both polarizations together, applies each tile's validity mask, and records every original STAC source ID. It does not borrow pixels from other passes or relax the 12-day optical/radar limit. Single-scene behavior remains supported.

Twenty-six backend tests passed against isolated PostgreSQL, including ten new regression cases for boundary coverage, incompatible/unknown passes, gaps, missing polarization, deduplication, per-tile timing, and real temporary raster reads/masks. Ruff and changed-file formatting checks passed.

A direct calculation using the exact failed polygon and original July–August / September–October 2026 windows completed from actual remote COG pixels in 68.46 seconds. It used two optical records plus four radar tile records. Radar overlap was 100%; clear optical overlap was 12.382%, and zero candidates were extracted. The limited optical overlap restricts interpretation; zero candidates is not evidence of absence of mining.

Worker deployment: `a43ce48d-88b3-4915-930e-c565195f2660`. API/frontend routing and authentication are unchanged. Production retry `b78c5dde-d959-4652-9c02-a05d92dcb959` completed on the deployed Railway worker with results persisted to Neon. It used the user's existing area and exact original windows; the two failed attempts were preserved. Creation used the application's normal validated job-creation function, plus a retry audit entry linking the original job. No QA account or sample observation was created. The result again measured 100% valid radar overlap, 12.382% clear optical overlap, zero extracted candidates, and six original source records. Authenticated browser rendering of this production account was not exercised; source imagery/review/monitoring acceptance beyond this job remains pending.

---

# Verification record — 24 October 2026

## Deployed release

- Frontend: https://geomine-xnet.vercel.app — Vercel `dpl_8EEGp8MXv1yrTmy9UN9U9Se3L6Ym`, READY. Existing deployment protection was preserved.
- API: https://geomine-api-production.up.railway.app — Railway `dd090dfa-42de-4317-9f82-194cfdbc2033`, SUCCESS; one healthy API replica.
- Private worker: `1deb6bc4-ba06-4d18-a9e9-1b161b1ad2f6`, SUCCESS; one replica, no public domain.
- Neon uses the dedicated `geomine` schema. No test users, areas, jobs, concessions, or candidates were inserted into production for acceptance.
- Secrets are in service variables and ignored `backend/.env` (0600). Source packages exclude environment secrets. No database or AI credential is bundled in the frontend.
- Public radar is actual Digital Earth Africa RTC, Africa coverage, analyzed at 30m. Production AOIs are limited to 25km².

## Live checks

- New public page displays the retained hero and full-width story, approach, provenance, and signup sections. No workspace tools or testimonial/card grid appear on it.
- Direct `/app/overview` navigation redirects to `/login?next=%2Fapp%2Foverview`. Signup has its own form and preserves the intended destination.
- A deep analysis route returns the SPA HTML (200); a nonexistent asset returns 404. No broad catch-all rewrite masks missing assets.
- Latest API readiness returned HTTP 200 with the exact canonical frontend CORS origin.
- Previous cloud checks verified anonymous workspace/SSE denial (401), invalid registration rejection (422), Neon/provider readiness, and real optical/radar catalog searches. Previous browser checks verified the API connection and dated radar records. The redesign did not seed cloud data to populate charts.
- Railway built the Linux raster image with libgomp1/libexpat1 and import checks. `python -m app.server` reads PORT directly; the worker uses `python -m app.worker`.

## Isolated authenticated end-to-end checks

A separate local PostgreSQL database, not Neon production, held the acceptance account and observations. These checks used the real API, durable worker, public catalog, raster assets, and OpenRouter service.

- Logged in through the actual UI; protected routes and an empty dashboard behaved correctly.
- Saved a real Ghana polygon (4.897km²); compared January and February 2025. Job `01eb4c1a-734b-41ab-8594-3f18b55a6e2d` streamed queued/running/completed progress without manual refresh.
- Worker read actual Sentinel-2 and matching-orbit Sentinel-1 RTC COG pixels, applied masks and change extraction. Result: zero extracted candidates, 100% clear optical overlap, 100% valid radar overlap, 30m grid. Zero is a measured result, not an invented detection.
- Overview rendered a genuine zero-area timeline point, actual processing totals and area metrics. Selecting the point opened its dedicated analysis URL.
- The detail page displayed January 5 / February 4 optical imagery and quality charts. The comparison slider responded to keyboard input.
- Catalog UI queried six real January Sentinel-2 scenes and rendered acquisition counts and their actual cloud-cover values (5.95, 36.80, 34.79, 38.83, 48.58, 18.56%).
- Reports ran a real free OpenRouter inference against the completed result and returned a 296-word narrative. The previous generic free router could select a moderation classifier; the release pins a general-purpose free model, rejects moderation/incomplete outputs, and supplies explicit AOI/candidate/source context. Human review remains required because model prose can still be imprecise.
- Stopped the local API during session verification. The app preserved the session and displayed a retry screen; restarting the API and retrying restored the existing workspace.
- No demo series, random points, sample candidates, or fabricated source images were introduced.

## Automated and scientific checks

- React/TypeScript production build passed. Production dependency audit reported zero vulnerabilities. Edited source formatting checks passed.
- Sixteen backend tests passed against an isolated real PostgreSQL 17 instance. Coverage includes tenant isolation, persistence/review/export, queue claims and cancellation fencing, SSE replay, geometry/area/grid limits, cloud/stable-radar rejection, orbit/date pairing, model gradients/concession masking, and AI narrative/evidence contracts. Ruff passed.
- A separate 512×512 neural forward check verified shapes/finite outputs, not trained accuracy.
- An earlier direct physical pipeline check also read actual Ghana raster data and measured zero candidates. Neither acceptance run inserted production data.
- Public entry avoids preloading the map, Three.js workspace bundle, and private page code. Large lazy 3D/map chunks still need real-device performance measurement.

## Remaining acceptance and operational work

- No labeled training data, trained weights, or authoritative concession boundaries were supplied. Preparation/upload/training/evaluation/install workflows exist; no paper accuracy, calibrated mining probability, or legal determination is claimed. Neural mode expects 10m imagery; the keyless 30m Africa source cannot activate it.
- Authenticated production acceptance in a real user workspace, candidate review when a real candidate exists, daily monitoring acceptance, load/physical-device/accessibility testing, backup restore drills, monitoring/retention, and identity lifecycle requirements remain before broad public release. Current auth lacks recovery, email verification, MFA, and organization sharing.
- Free OpenRouter quotas/outages remain visible; no paid fallback was enabled. AI narratives require source checking and human review.
- OpenWeather returned HTTP 401 for the supplied key and was not integrated.
- No Git repository or automatic deployment pipeline is connected. This release uses sanitized source uploads.

## Local environment

Source remains in `/Users/praneethreddy/Freelance Projects /GEOMINE-XNET` with `frontend/` and `backend/`. The parent folder has a trailing space. Output links refer to this same project. Acceptance used only this chat's owned local PostgreSQL cluster and temporary servers; these were stopped after verification. This record distinguishes deployed behavior, isolated acceptance evidence, and remaining operational work. It does not certify a trained mining detector.
