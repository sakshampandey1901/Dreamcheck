# DreamCheck — Frontend Build Plan

> **Audience:** this document is written for an LLM coding agent (Claude Code or similar) to read and execute against. If you are that agent: read this whole file before writing any code. Do not skip Section 1.

---

## 0. What this document is, and isn't

This is a **frontend-only** build plan. It assumes the backend (FastAPI routes, SQLite schema, async poller, mock/real Luma client) already exists and works. Your job is to add templates, static assets, and the minimum route wiring needed to render them — nothing else.

If at any point a step in this plan seems to require changing `db.py`, `poller.py`, `clients.py`, or `seed.py`, **stop and flag it instead of doing it.** That is very likely a sign the plan or your interpretation of it has drifted, not a sign those files need to change.

---

## 1. Hard constraints (read before touching anything)

1. **Stack is locked.** FastAPI + Jinja2 + server-rendered HTML. No Next.js, no React, no separate frontend service, no build pipeline (no webpack/vite/npm build step). Plain CSS and vanilla JS only.
2. **Deployment target is locked.** Render free tier, single web service, single dyno. No new services, no background workers beyond the existing asyncio poller, no external font/CDN fetches at request time (self-host fonts).
3. **Files you may create or edit:**
   - `templates/*.html` (new)
   - `static/css/*.css` (new)
   - `static/js/*.js` (new, minimal — one small file for the state-ticker animation only)
   - `static/fonts/*.woff2` (new)
   - `static/placeholder.svg` (new — this is a known gap, see Section 7)
   - The **return statements** of existing routes in `main.py` — swapping a bare dict/JSON return for a `TemplateResponse`, or adding a new GET route that renders a template. You may add routes. You may not change the behavior of existing routes that anything already depends on (see rule 4).
4. **Files you may NOT edit:** `db.py`, `poller.py`, `clients.py`, `seed.py`. Schema, poller cadence, and the mock/real client interface are out of scope for a frontend pass. If a template needs data shaped differently than the DB currently returns it, add a small transformation in the route handler in `main.py` — do not reshape the schema.
5. **Do not change existing route paths, methods, or request/response contracts for endpoints that are already in use.** Adding a new template-rendering route alongside an existing JSON route is fine. Replacing one is not, unless this plan explicitly says so.
6. **No new Python dependencies beyond what's already installed**, except `jinja2` itself if not already present (it should be, given the locked stack). Do not add a CSS framework, icon library, or JS framework as a package — hand-roll or self-host everything.

---

## 2. Current codebase state (as of last review)

Confirm this against the actual repo before starting — this is what was true as of the last check-in, not a guarantee of the present state:

- Five core files reviewed and structurally sound: `app/main.py`, `app/clients.py`, `app/db.py`, `app/poller.py`, `app/seed.py`
- **Templates exist from the backend phase** (`base.html`, `submit.html`, `queue.html`, `stats.html`) using a GitHub-dark design system. This frontend pass replaces their styling with the design system in Section 3 — keep the existing route wiring and filenames exactly as-is.
- `seed_data.json` exists with 18 entries and pre-written reviews — Section 6 gap is already closed.
- `static/placeholder.svg` exists — Section 6 gap is already closed.
- `render.yaml` and `requirements.txt` exist — deployment config already present, no action needed.
- Route-to-template mapping (do not change these): `/` → `submit.html`, `/queue` → `queue.html`, `/stats` → `stats.html`.
- Known bug, **not in scope for this plan**: `RealLumaClient` uses video model names (`ray-2`, `ray-flash-2`) instead of image model names (`photon-1`, `photon-flash-1`). Do not fix this as part of a frontend pass — it's a client-layer bug, mention it in a final summary if you notice it, but leave `clients.py` untouched per Section 1.

Run a quick `view` of `templates/` and `static/` at the start of your session to confirm this is still accurate before proceeding.

---

## 3. Design system (tokens — implement exactly, don't reinterpret)

### Color
```css
:root {
  --ink: #0E0E11;           /* background */
  --paper: #EDEAE2;         /* primary text */
  --paper-dim: #A6A39B;     /* secondary text, captions */
  --dreaming: #E8A33D;      /* state: queued / dreaming (in progress) */
  --verdict-accept: #4FA57A;/* state: accepted */
  --verdict-reject: #C1554B;/* state: rejected */
  --verdict-modify: #7E7BC4;/* state: modified */
  --failed: #8A5A52;        /* state: generation failed (distinct from reject — this is a system failure, not a human judgment) */
  --line: #232228;          /* hairline borders, dividers */
}
```

### Type
- Display (`h1`, `h2`, page titles): `Fraunces` — self-host the variable woff2, weight range ~400–600.
- Body / UI (everything else): `Inter` — self-host, weights 400/500/600.
- Data / state labels (timestamps, generation IDs, the words `queued`/`dreaming`/`completed`/`failed`): `JetBrains Mono`, weight 400/500. Always monospace, always uppercase or lowercase consistently (pick one, apply everywhere) — this is a learned visual convention across the whole app: **mono = system state, never human-written content.**

### Signature element: the Verdict Ledger
A colored left-border strip on every review card, using the four state colors above. The same visual device reappears in the rollup view as a stacked horizontal bar (accept/modify/reject proportions of total reviewed). This is one component reused in two contexts, not two separate chart components — implement it as a single reusable partial (`templates/partials/verdict_strip.html` or equivalent) parameterized by state/proportions.

### Motion
One deliberate animation only: a small looping state-ticker on the landing/submission view cycling `queued → dreaming → completed` in the mono type, using the state colors. Pure CSS `@keyframes`, no JS animation library. Respect `prefers-reduced-motion` — freeze on `completed` if the user has that setting on.

---

## 4. File structure to create

```
templates/
  base.html              # shared shell: <head>, font links, nav, footer
  submit.html            # submission form (extends base)
  queue.html             # review queue, one card per pending generation (extends base)
  stats.html             # aggregate stats view (extends base)
  partials/
    verdict_strip.html   # reusable colored strip / bar component
    state_pill.html      # small mono-type badge for queued/dreaming/completed/failed

static/
  css/
    tokens.css           # CSS custom properties from Section 3
    base.css             # resets, typography scale, layout primitives
    components.css        # cards, buttons, verdict strip, state pill
  js/
    ticker.js             # the one deliberate animation, vanilla JS/CSS only
  fonts/
    fraunces-*.woff2
    inter-*.woff2
    jetbrains-mono-*.woff2
  placeholder.svg          # fallback asset image (Section 7 gap)
```

---

## 5. Phased plan

Work in this order. **Do not start a phase until the previous one is verified working.** Each phase ends with a concrete check — don't just eyeball it, actually confirm it.

### Phase 0 — Fonts and tokens (no route changes)
- Add `static/fonts/*.woff2`, `static/css/tokens.css`, `static/css/base.css`.
- Confirm `main.py` already mounts `/static` via `StaticFiles` — if not, add that mount (this is the one infrastructure change this plan requires; it's additive and can't break an existing route since nothing currently serves static files).
- **Check:** hit `/static/css/tokens.css` directly in a browser/curl against the running app and confirm it returns the file with a 200. No template changes yet, so nothing else should be able to break.

### Phase 1 — Base shell
- Build `templates/base.html`: doctype, font `<link>`/`@font-face` includes, nav (Submit / Review / Rollup), a `{% block content %}`, footer.
- Add one throwaway route or reuse an existing root route to render `base.html` directly with no content, just to confirm the shell renders.
- **Check:** load the root route in a browser. Confirm fonts load (check network tab, not just visually — a fallback system font can look "close enough" and hide a broken font path).

### Phase 2 — Submission view
- Build `templates/submit.html`: form with a prompt input, submit button, and the state-ticker (`queued → dreaming → completed`) as ambient motion near the header.
- Wire it to the **existing** submission route. If that route currently returns JSON only, add a check on the `Accept` header or a separate GET route that renders the form, and keep the POST behavior (whatever currently consumes it) unchanged.
- **Check:** submit a real prompt through the UI. Confirm it creates a row in `generations` exactly as it did before this change (inspect the DB directly, don't infer from the UI alone).

### Phase 3 — Review queue
- Build `templates/queue.html` + `partials/verdict_strip.html` + `partials/state_pill.html`.
- List generations in a non-terminal or completed state; each card shows prompt, asset (or `placeholder.svg` if asset is missing — see Section 7), and accept/modify/reject controls.
- Wire accept/modify/reject to the existing review-submission route (or add one if it doesn't exist yet — a new route is fine, changing an existing one's contract is not).
- **Check:** submit a review decision through the UI, confirm a row lands in `reviews` with the correct decision value, and confirm the poller/generation state machine is completely unaffected (a review decision should never change a generation's `state` field — those are separate concerns).

### Phase 4 — Rollup
- Build `templates/stats.html` reusing the verdict-strip component as a stacked bar.
- Pull aggregate counts from the existing rollup/stats route (or add a read-only route if one doesn't exist — no write behavior here at all).
- **Check:** confirm the numbers shown match a manual count against the DB. This view should be trivially reproducible by hand — if it isn't, the query is wrong, not the frontend.

### Phase 5 — Polish pass
- `prefers-reduced-motion` support on the ticker.
- Keyboard focus states on all interactive elements (visible outline using `--dreaming` or `--verdict-modify`, not browser default, not `outline: none`).
- Mobile check down to ~375px width — review cards should stack, not overflow.
- Empty states: no generations yet, no reviews yet — write these in the interface's voice ("No generations yet — submit a prompt to get started"), not a blank page.

---

## 6. Known gap this plan intentionally does NOT close

- `seed_data.json` (15–20 varied prompts + pre-written reviews) is a data task, not a frontend task, but the review queue and rollup views are meaningless without it. If it doesn't exist by Phase 3, flag it and stop rather than building against an empty table and assuming it'll be fine later.
- `static/placeholder.svg` — the review card and submission-confirmation views should reference `/static/placeholder.svg` for any generation without a real asset URL. Create a simple, on-brand placeholder (use the token colors, not a generic gray box) as part of Phase 0 or 3, whichever comes first in practice.
- `RealLumaClient` model-name bug, `render.yaml`/`requirements.txt`, and the fragile DB-path-patching pattern are explicitly out of scope here. Do not fix them opportunistically mid-frontend-pass — note them in your final summary instead.

---

## 7. Definition of done (frontend scope only)

- All three views (submit, review queue, rollup) render server-side via Jinja2, no client-side framework.
- Verdict ledger component is implemented once and reused in both the review queue and rollup views.
- Fonts are self-hosted, no runtime external font fetch.
- No existing route's path, method, or payload contract changed without explicit note in this plan.
- `db.py`, `poller.py`, `clients.py`, `seed.py` are byte-for-byte unchanged from before this pass, unless a gap in Section 6 required a narrowly-scoped, explicitly-flagged exception.
- App still runs end-to-end on Render's free tier with no new services or build steps.

---

## 8. If you get stuck

If a requirement in this plan conflicts with what you find in the actual codebase (a route that doesn't exist, a schema field that isn't there, a naming mismatch), **stop and report the conflict rather than silently improvising a fix.** This plan was written from a snapshot of the codebase that may have drifted; a wrong guess here is worse than a paused build.