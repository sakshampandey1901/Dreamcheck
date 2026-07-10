# Dreamcheck - Prompt QA for Luma API Workflows

Dreamcheck is a small product-engineering tool for teams building features on top of [Luma's public API](https://docs.lumalabs.ai). It sits after "we can call the generation API" and before "we know which prompt patterns produce outputs worth shipping."

The app lets a reviewer submit prompts, watch each generation move through Luma's public lifecycle (`queued -> dreaming -> completed | failed`), judge the completed output, and use stored review data to compare prompt patterns and models. The point is not to build an ML benchmark. The point is to make the product feedback loop visible, repeatable, and cheap to run.

**What it is not:** an internal Luma evaluation tool, a claim about Luma's production systems, a SaaS product, or a replacement for formal model evaluation.

---

## Why this exists

Generative API integrations usually fail in the gap between a successful API call and a reliable product experience. A product team needs to know which prompt structures work, where outputs need revision, and whether model choices are changing the acceptance rate.

Dreamcheck demonstrates that loop with a deliberately small stack:

- a mock-first Luma client that follows the public API lifecycle without spend
- persisted generation state so polling survives app restarts
- a review queue that captures human accept / modify / reject decisions
- SQL-derived rollups instead of hardcoded demo metrics
- one deployable FastAPI service with server-rendered pages

---

## How it works

```
Submit prompt -> mock Luma client creates a generation through the same interface
              -> asyncio poller sweeps every 3 s and advances state in SQLite
              -> completed generation appears in the review queue
              -> reviewer records accept / modify / reject plus an optional note
              -> /stats derives acceptance rates by prompt pattern and model
```

Three pages:
- **Submit** (`/`) - enter a prompt and model
- **Review queue** (`/queue`) - judge completed generations; keyboard shortcuts A / M / R
- **Stats** (`/stats`) - per-pattern and per-model acceptance rates, rejection themes, median time-to-review

API endpoints:
- `POST /generations` - create a generation
- `GET /generations` - list with optional `?state=` and `?unreviewed=true` filters
- `POST /generations/{id}/review` - record a decision
- `GET /stats` - SQL aggregates (JSON or HTML depending on Accept header)

---

## Mock-first API approach

**Default mode is `LUMA_MODE=mock`.** No API key is required. The mock client simulates Luma's lifecycle deterministically (5–15 s per generation, ~10% failure rate) with state persisted in SQLite. This means you can demo and develop the full QA loop with zero spend.

The real API adapter is intentionally thin and config-gated. It exists to show that the app is built around the public Luma client contract, but the demo path should stay in mock mode unless you are intentionally testing with a real key.

To enable the real adapter locally, set two env vars and restart:

```bash
LUMA_MODE=real
LUMAAI_API_KEY=your_key_here
```

Both clients implement the same `LumaClient` Protocol (`create_generation` + `get_generation`).

---

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit if needed; defaults work out of the box
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. The app seeds 18 example generations with reviews on first boot so stats are immediately meaningful.

---

## Deploy to Render (single service, free tier)

The recommended public demo deployment uses mock mode. That keeps the app cost-safe and avoids putting a paid API key into the deployed environment.

### 1. Push to GitHub

Make sure your repo is on GitHub and the working tree is clean.

### 2. Create a new Web Service on Render

- **Repository:** your GitHub repo
- **Branch:** `main`
- **Runtime:** Python 3
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 3. Set environment variables in Render dashboard

| Variable | Value | Required |
|---|---|---|
| `LUMA_MODE` | `mock` | Yes (set explicitly; default is mock) |
| `DATABASE_PATH` | `/opt/render/project/src/dreamcheck.db` | Recommended (keeps DB in project dir) |

### 4. Deploy

Click **Deploy**. First deploy installs deps and starts the server. The app seeds example data on boot so stats work immediately.

---

## Security and deployment notes

- Keep `LUMA_MODE=mock` for public demos unless you intentionally want to spend real API credits.
- Do not commit `.env` or real API keys. Use `.env.example` for documented defaults and keep secrets in local or hosted environment settings.
- This app intentionally has no authentication. Share deployed URLs with trusted reviewers or add an access layer before using it with real team data.

---

## Limitations (stated plainly)

- **Single reviewer, no auth.** Anyone with the URL can submit and review. Intended for a solo engineer or a small team who trusts each other.
- **Ephemeral disk on Render free tier.** SQLite is wiped on each restart. The seed-on-boot mechanism makes the app self-healing for demos, but real QA data from sessions is lost. Use a paid Render plan with a persistent disk if you need to keep data.
- **Free-tier cold start.** Render free services sleep after ~15 min of inactivity; first request after sleep takes ~30 s.
- **Mock generates placeholder SVGs, not real images.** Phase 4 (not yet done) swaps in real watermarked images from [dream-machine.lumalabs.ai](https://dream-machine.lumalabs.ai) (no card required). Until then, every generation shows the same gray placeholder.
- **~10% mock failure rate.** Deterministic per generation ID. Failure reasons are realistic enough for the workflow, but they are simulated.
- **Real adapter is opt-in.** The project is designed to exercise the public API shape without making paid API calls during normal development or demos.

---

## What would come next (modestly)

- **Phase 4:** swap placeholder SVGs for real watermarked images from Luma's consumer tier; committed under `/static/seed/`
- **Persistent disk:** use Render persistent storage or another hosted volume if session data needs to survive restarts
- **Multi-reviewer:** add a `reviewer_id` column to reviews and a simple name field on submission - no full auth needed
- **CSV export:** one endpoint that dumps the reviews table so you can pull patterns into a spreadsheet

---

## Stack

- **Backend:** FastAPI + uvicorn
- **Frontend:** Jinja2 templates + vanilla JS `fetch()` polling (no separate frontend deployment)
- **DB:** SQLite with WAL mode, `CREATE TABLE IF NOT EXISTS` (no migrations)
- **Async work:** one asyncio task - no Celery, no Redis, no queue infrastructure
- **Deploy:** Render free tier, single service, one URL
