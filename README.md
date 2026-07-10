# Dreamcheck — Luma Generation QA

A lightweight prompt-QA loop for product teams building on [Luma's API](https://docs.lumalabs.ai).

It is the layer between "we have API access" and "we know which prompt patterns reliably produce good outputs." You submit prompts, watch generations move through Luma's lifecycle (`queued → dreaming → completed | failed`), judge each output, and read rollup stats that show you which prompt patterns land and which don't.

**What it is NOT:** an internal tool for Luma's own eval process, a SaaS product, or an ML evaluation framework.

---

## How it works

```
Submit prompt → mock (or real) Luma client creates a generation
             → asyncio poller sweeps every 3 s, advances state in SQLite
             → completed generation appears in review queue
             → reviewer judges (accept / modify / reject) + optional note
             → /stats derives acceptance rates by prompt pattern and model
```

Three pages:
- **Submit** (`/`) — enter a prompt and model
- **Review queue** (`/queue`) — judge completed generations; keyboard shortcuts A / M / R
- **Stats** (`/stats`) — per-pattern and per-model acceptance rates, rejection themes, median time-to-review

Three API endpoints:
- `POST /generations` — create a generation
- `GET /generations` — list with optional `?state=` and `?unreviewed=true` filters
- `POST /generations/{id}/review` — record a decision
- `GET /stats` — SQL aggregates (JSON or HTML depending on Accept header)

---

## Mock-first approach

**Default mode is `LUMA_MODE=mock`.** No API key is required. The mock client simulates Luma's lifecycle deterministically (5–15 s per generation, ~10% failure rate) with state persisted in SQLite. This means you can demo and develop the full QA loop with zero spend.

**To switch to the real Luma API:** set two env vars and restart — no code changes.

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
| `LUMAAI_API_KEY` | *(your key)* | Only if `LUMA_MODE=real` |

### 4. Deploy

Click **Deploy**. First deploy installs deps and starts the server. The app seeds example data on boot so stats work immediately.

---

## Limitations (stated plainly)

- **Single reviewer, no auth.** Anyone with the URL can submit and review. Intended for a solo engineer or a small team who trusts each other.
- **Ephemeral disk on Render free tier.** SQLite is wiped on each restart. The seed-on-boot mechanism makes the app self-healing for demos, but real QA data from sessions is lost. Use a paid Render plan with a persistent disk if you need to keep data.
- **Free-tier cold start.** Render free services sleep after ~15 min of inactivity; first request after sleep takes ~30 s.
- **Mock generates placeholder SVGs, not real images.** Phase 4 (not yet done) swaps in real watermarked images from [dream-machine.lumalabs.ai](https://dream-machine.lumalabs.ai) (no card required). Until then, every generation shows the same gray placeholder.
- **~10% mock failure rate.** Deterministic per generation ID. The failure is realistic (same `failure_reason` strings as real API) but not random.

---

## What would come next (modestly)

- **Phase 4:** swap placeholder SVGs for real watermarked images from Luma's consumer tier; committed under `/static/seed/`
- **Persistent disk:** Render paid plan or replace SQLite with a small managed Postgres to survive restarts
- **Multi-reviewer:** add a `reviewer_id` column to reviews and a simple name field on submission — no full auth needed
- **CSV export:** one endpoint that dumps the reviews table so you can pull patterns into a spreadsheet

---

## Stack

- **Backend:** FastAPI + uvicorn
- **Frontend:** Jinja2 templates + vanilla JS `fetch()` polling (no separate frontend deployment)
- **DB:** SQLite with WAL mode, `CREATE TABLE IF NOT EXISTS` (no migrations)
- **Async work:** one asyncio task — no Celery, no Redis, no queue infrastructure
- **Deploy:** Render free tier, single service, one URL
