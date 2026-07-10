# Luma Generation QA & Feedback Tool — Build Architecture Plan
### Definitive handoff for the build agent. All decisions below are settled from prior research/argument passes — execute, don't re-litigate unless implementation reveals a genuine blocker.

---

## 1. Project identity (do not drift from this)

 It is a **prompt-QA loop for a product team building on Luma's API** — the layer between "we have API access" and "we know which prompt patterns reliably produce good outputs."

It is NOT: an internal tool for Luma's own eval team, a SaaS product, a scale demo, or an ML expertise demo. The bar is *correctly working and clearly explained*. Every implementation choice must pass the test: "does this add signal, or just complexity?"

---

## 2. Verified Luma API facts (already confirmed against docs.lumalabs.ai — the mock must mirror these exactly)

- SDK: `lumaai` on PyPI. Auth: Bearer token / `LUMAAI_API_KEY` env var.
- Lifecycle: create returns a UUID v4 generation id; client polls status until terminal. Polling is the standard retrieval pattern.
- States: `queued → dreaming → completed | failed`. Failed generations carry a `failure_reason` string.
- Asset location: `generation.assets.image` (or `.video`). This project models **image generations** (decided: easier free seed assets, instant display, no video hosting).
- Video models are `ray-flash-2` / `ray-2`; the mock may simulate two model names to enable per-model rollup comparison.
- API is pay-as-you-go (`/credits` endpoint, USD cents). **Never call the real API during the build. Zero spend is a hard constraint.**

---

## 3. Stack (final — argued and settled)

| Layer | Choice | Rejected alternative & why |
|---|---|---|
| Backend | FastAPI (single service) | — |
| Frontend | Jinja2 templates + vanilla JS `fetch()` polling | Next.js rejected: two deployments, CORS, build pipeline — no added signal for 3 views |
| DB | SQLite with WAL, `CREATE TABLE IF NOT EXISTS` (no migrations) | Postgres rejected: unjustified complexity |
| Async work | ONE asyncio background task started in FastAPI lifespan | Celery/Redis/queues rejected: massive overkill |
| Deploy | Render free tier, single service, one public URL | Vercel rejected: not needed without Next.js |
| Deps | fastapi, uvicorn, jinja2, sqlite3 (or aiosqlite), python-dotenv | Keep the list this short |

Cold-start note: Render free tier sleeps after ~15 min; README states this honestly in one line.

---

## 4. Client layer (the core abstraction)

Define a Python `Protocol` (or ABC) — `LumaClient` — with exactly two methods mirroring the SDK shape:

```python
create_generation(prompt: str, model: str) -> Generation   # returns id, state="queued"
get_generation(id: str) -> Generation                       # id, state, failure_reason, assets
```

- `get_luma_client()` factory reads `LUMA_MODE=mock|real` (default `mock`).
- `MockLumaClient`: **job state persists in SQLite, not in-memory** (poller/app restart must not orphan jobs). Simulates timed transitions queued→dreaming→completed over ~5–15s, with ~10% failures using realistic `failure_reason` strings. Completed mock jobs get placeholder image URLs (later swappable for real seed assets).
- `RealLumaClient`: thin wrapper on the `lumaai` SDK. Written but never invoked during dev. Switching modes must be a config change, never a code change.

---

## 5. Data model (two tables, intentionally minimal)

**generations**: id (UUID), prompt, model, state, failure_reason, asset_type, asset_url, created_at, completed_at
**reviews**: id, generation_id (FK), decision (`accept|modify|reject`), note (nullable — required for modify/reject to feed rollup themes), created_at

`asset_type` + `asset_url` kept generic so images and video both work without schema change.

---

## 6. HTTP surface

Endpoints:
- `POST /generations` — submit prompt (+model), creates row, calls client, returns id
- `GET /generations` — list with state filter (drives the review queue + polling)
- `POST /generations/{id}/review` — decision + optional note, timestamped
- `GET /stats` — SQL aggregates: overall acceptance rate, **per-prompt-pattern acceptance** (the 30-second-demo money shot, e.g. "cinematic aerial: 80% vs generic landscape: 40%"), per-model comparison, rejection-note themes, median time-to-review

Pages (Jinja): submit form · review queue (prompt + asset side-by-side, three buttons, keyboard-friendly) · rollup view. Frontend polls `GET /generations` with plain `fetch()` every few seconds — no websockets.

---

## 7. Background poller

One asyncio task, started on app lifespan startup:
- Every ~3s, sweep all rows in non-terminal states (`queued`, `dreaming`)
- Call `client.get_generation(id)` for each; write state changes (and asset URL / failure_reason on terminal) to SQLite
- Wrap the loop body in try/except so one bad job can't kill the poller
- This mirrors Luma's real polling contract — it is a genuine requirement, not decoration

---

## 8. Seed strategy (solves ephemeral disk + demo credibility together)

- Render free tier wipes SQLite on restart → **seed on boot if DB is empty**. The demo is self-healing; a recruiter always sees a populated tool.
- Seed source: a committed JSON file with 15–20 varied prompts spanning distinct patterns (cinematic aerial, portrait, abstract, generic landscape, etc.), each with an honest review decision + note authored by the user. Stats are then *real derivations from real judgments*, never hardcoded numbers.
- Phase 4 (optional): user manually generates a handful of real watermarked images via the free consumer web tier (dream-machine.lumalabs.ai, no card), committed under `/static/seed/`, and the JSON's placeholder URLs are swapped for those paths. No live API involved.

---

## 9. Config

Env vars only: `LUMA_MODE` (default `mock`), `LUMAAI_API_KEY` (optional, unused in mock), `DATABASE_PATH`. Loaded via python-dotenv. No config framework.

---

## 10. Build order & done-criteria

**Phase 0 — Skeleton (~½ day):** repo, deps file, config layer, DB schema. Done when app boots and tables exist.

**Phase 1 — Mock client + poller:** client Protocol, MockLumaClient, lifespan poller. Done when `curl POST /generations` produces a row that visibly transitions queued→dreaming→completed (and occasionally failed) with zero real API calls. **Validate via curl before touching any UI.**

**Phase 2 — Review flow:** review endpoint + queue page. Done when a completed generation can be judged and the decision is logged with timestamp.

**Phase 3 — Rollup + seed:** `/stats` endpoint, rollup page, seed-on-boot from the JSON file. Done when stats render real signal from the seeded batch, including the per-pattern breakdown.

**Phase 4 — Real seed assets (optional):** swap placeholder URLs for committed free-tier images.

**Phase 5 — Ship:**
 deploy to Render, write README.

At each phase boundary: stop, confirm the simplest version satisfies the phase's purpose, cut anything beyond it.

---

## 11. README r
equirements (framing is load-bearing)

- What it is: a lightweight prompt-QA loop for teams building on Luma's API — NOT a claim to improve Luma's internal eval process
- Why it was built (learning by building on the real API contract), live link, architecture summary, stack
- Explicit statement of the mock-first approach and the one-config-change path to real API mode
- Honest limitations: single reviewer, no auth, free-tier cold start, seed-on-boot
- What would come next — stated modestly, no overclaiming

---

## 12. Hard guardrails for the build agent

1. Zero real API calls, zero spend, no card — ever, in any phase.
2. No Celery, Redis, Postgres, Docker-compose stacks, auth systems, or multi-user anything.
3. No Next.js / separate frontend deployment.
4. Mock and real clients share one interface; mode switch = config only.
5. Stats must derive from stored data; never fabricate numbers.
6. If a choice adds complexity without proportional signal, cut it.