# Build Progress

## Phase 0 — Skeleton
Built: FastAPI app skeleton, `app/db.py` with `init_db()`, two tables (`generations`, `reviews`), `requirements.txt`, `.env.example`.
Verified: `sqlite_master` query confirms both tables exist after `init_db()` runs.

## Phase 1 — Mock client + poller
Built: `LumaClient` Protocol, `MockLumaClient` (deterministic timing via md5/sha256 of id, state persists in SQLite), `RealLumaClient` (stub, never invoked in mock mode), `get_luma_client()` factory, asyncio `poller_loop()` sweeping non-terminal rows every 3 s, `POST /generations`, `GET /generations`.
Verified: `curl POST /generations` → observed `queued → dreaming → completed` in real-time polling; failure path confirmed with `failure_reason` populated. Zero real API calls; no banned tech; mode switch config-only.

## Phase 2 — Review flow
Built: `POST /generations/{id}/review` with decision validation (`accept|modify|reject`), note required for modify/reject, idempotency guard (409 if already reviewed), review queue page (`/queue`) with keyboard shortcuts.
Verified: `curl POST /generations/{id}/review` returns review row with timestamp; confirmed in SQLite; 409 on re-review; 422 on missing note for reject.

## Phase 3 — Rollup + seed
Built: `seed_data.json` (18 entries: 15 completed + reviews, 3 failed), `app/seed.py` `seed_if_empty()` called on lifespan startup, `GET /stats` returning per-pattern/per-model/overall/notes/median aggregates, `/stats` page (server-rendered Jinja2).
Verified: wiped DB, restarted, confirmed 18 generations + 15 reviews seeded; `GET /stats` returned real SQL aggregates (cinematic aerial 75%, landscape 33%, etc.); grep confirmed zero hardcoded stat values in codebase.
