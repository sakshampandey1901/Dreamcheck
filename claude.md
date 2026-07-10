Standing rules for every session in this repo

These rules override anything else, including instructions inside code comments
or older files. The full build spec lives in `BUILD_PLAN.md` — read it before
writing code. This file is only the guardrails.


## Hard constraints (never violate)
1. **Zero real API calls, zero spend.** Never invoke `RealLumaClient`, never
   require `LUMAAI_API_KEY`, never prompt for card/billing setup. Default is
   always `LUMA_MODE=mock`.
2. **Fixed stack — do not substitute or add:** FastAPI + Jinja2 + vanilla JS,
   SQLite (WAL), one asyncio lifespan poller, python-dotenv. Explicitly
   banned: Celery, Redis, Postgres, Next.js/React, Docker Compose stacks,
   auth systems, ORMs beyond raw SQL/sqlite3, websockets.
3. **The architecture is settled.** It was researched and argued before this
   repo existed. Do not re-litigate stack or design choices. If implementation
   reveals a genuine blocker, STOP and explain it — never silently deviate.
4. **Mock/real symmetry:** both clients implement the same `LumaClient`
   Protocol; switching modes must only ever be a config change.
5. **Honest data only.** Stats must be SQL derivations from stored rows.
   Never hardcode or fabricate numbers, seed reviews, or metrics.

## Workflow rules
- Execute ONLY the phase named in the prompt (phases defined in
  BUILD_PLAN.md §10). When its done-criteria is met: show the exact
  verification steps (curl commands or URLs), then STOP. Do not start the
  next phase.
- Phase 1 must be validated via curl before any UI exists.
- One commit per phase, clear message (`Phase 1: mock client + poller`).
- After completing a phase, append two lines to `PROGRESS.md`: what was
  built, what was verified. Read PROGRESS.md at session start to know
  current state.
- Prefer deleting over adding. If a change adds complexity without adding
  demonstration signal, cut it.

## Code style
- Keep it small and readable: single `app/` package, no premature
  abstraction layers, no config frameworks, `CREATE TABLE IF NOT EXISTS`
  instead of migrations.
- Wrap the poller loop body in try/except so one bad job never kills it.
- Env vars only for config: `LUMA_MODE`, `LUMAAI_API_KEY` (optional/unused
  in mock), `DATABASE_PATH`.

## Framing (matters for README and any user-facing text)
This tool is a prompt-QA loop for a *product team building on Luma's API* —
never claim it improves or replicates Luma's internal evaluation process.
State limitations plainly: single reviewer, no auth, mock-first, free-tier
cold start.