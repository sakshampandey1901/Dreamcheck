import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Re-read DATABASE_PATH after load_dotenv so env file takes effect
import app.db as _db_module
_db_module.DATABASE_PATH = os.getenv("DATABASE_PATH", "dreamcheck.db")

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from app.clients import get_luma_client
from app.db import get_conn, init_db
from app.poller import poller_loop
from app.seed import seed_if_empty


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    task = asyncio.create_task(poller_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Dreamcheck", lifespan=lifespan)

_BASE = os.path.dirname(os.path.dirname(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE, "templates"))


# ---------------------------------------------------------------------------
# Prompt classifier
# ---------------------------------------------------------------------------

def _classify(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["aerial", "drone", "bird's eye", "overhead", "from above"]):
        return "cinematic aerial"
    if any(w in p for w in ["portrait", "headshot", "face of"]):
        return "portrait"
    if any(w in p for w in ["product", "flat lay", "commercial shoot", "studio shot"]):
        return "product shot"
    if any(w in p for w in ["abstract", "geometric", "fractal", "tessellation",
                             "fluid simulation", "ink in"]):
        return "abstract"
    if any(w in p for w in ["architectural", "architecture", "interior", "facade",
                             "brutalist", "library interior"]):
        return "architectural"
    if any(w in p for w in ["landscape", "mountain", "ocean", "forest", "valley",
                             "highland", "desert", "beach", "loch", "dunes"]):
        return "landscape"
    return "other"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GenerationRequest(BaseModel):
    prompt: str
    model: str = "ray-flash-2"

    @field_validator("model")
    @classmethod
    def _valid_model(cls, v: str) -> str:
        if v not in ("ray-flash-2", "ray-2"):
            raise ValueError("model must be ray-flash-2 or ray-2")
        return v


class ReviewRequest(BaseModel):
    decision: str
    note: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def _valid_decision(cls, v: str) -> str:
        if v not in ("accept", "modify", "reject"):
            raise ValueError("decision must be accept | modify | reject")
        return v


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/generations", status_code=201)
async def create_generation(body: GenerationRequest):
    client = get_luma_client()
    gen = client.create_generation(body.prompt, body.model)
    pattern = _classify(body.prompt)
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO generations
               (id, prompt, model, prompt_pattern, state, created_at)
               VALUES (?, ?, ?, ?, 'queued', ?)""",
            (gen.id, body.prompt, body.model, pattern, now),
        )
    return {"id": gen.id, "state": "queued", "prompt_pattern": pattern}


@app.get("/generations")
async def list_generations(state: Optional[str] = None, unreviewed: bool = False):
    query = """
        SELECT g.id, g.prompt, g.model, g.prompt_pattern, g.state,
               g.failure_reason, g.asset_url, g.created_at, g.completed_at,
               r.id as review_id, r.decision, r.note
        FROM generations g
        LEFT JOIN reviews r ON g.id = r.generation_id
    """
    params: list = []
    conditions = []
    if state:
        conditions.append("g.state = ?")
        params.append(state)
    if unreviewed:
        conditions.append("r.id IS NULL")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY g.created_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


@app.post("/generations/{gen_id}/review", status_code=201)
async def submit_review(gen_id: str, body: ReviewRequest):
    if body.decision in ("modify", "reject") and not body.note:
        raise HTTPException(
            status_code=422,
            detail="note is required for modify and reject decisions",
        )
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state FROM generations WHERE id = ?", (gen_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Generation not found")
        if row["state"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot review a generation in state '{row['state']}'",
            )
        existing = conn.execute(
            "SELECT id FROM reviews WHERE generation_id = ?", (gen_id,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Already reviewed")
        now = datetime.now(timezone.utc).isoformat()
        review_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO reviews (id, generation_id, decision, note, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (review_id, gen_id, body.decision, body.note, now),
        )
    return {"id": review_id, "generation_id": gen_id,
            "decision": body.decision, "created_at": now}


@app.get("/stats")
async def stats(request: Request):
    data = _compute_stats()
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return templates.TemplateResponse(
            "stats.html", {"request": request, "stats": data}
        )
    return JSONResponse(data)


def _compute_stats() -> dict:
    with get_conn() as conn:
        # Overall
        overall = conn.execute("""
            SELECT
                COUNT(r.id)                                                       AS total_reviewed,
                SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)           AS accepts,
                SUM(CASE WHEN r.decision = 'modify' THEN 1 ELSE 0 END)           AS modifies,
                SUM(CASE WHEN r.decision = 'reject' THEN 1 ELSE 0 END)           AS rejects,
                ROUND(100.0 * SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(r.id), 0), 1)                                AS acceptance_rate
            FROM reviews r
        """).fetchone()

        # Per prompt-pattern
        pattern_rows = conn.execute("""
            SELECT g.prompt_pattern                                                AS pattern,
                   COUNT(r.id)                                                     AS total,
                   SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)         AS accepts,
                   SUM(CASE WHEN r.decision = 'modify' THEN 1 ELSE 0 END)         AS modifies,
                   SUM(CASE WHEN r.decision = 'reject' THEN 1 ELSE 0 END)         AS rejects,
                   ROUND(100.0 * SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)
                         / NULLIF(COUNT(r.id), 0), 1)                             AS acceptance_rate
            FROM generations g
            JOIN reviews r ON g.id = r.generation_id
            GROUP BY g.prompt_pattern
            ORDER BY acceptance_rate DESC
        """).fetchall()

        # Per model
        model_rows = conn.execute("""
            SELECT g.model,
                   COUNT(r.id)                                                     AS total,
                   SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)         AS accepts,
                   SUM(CASE WHEN r.decision = 'modify' THEN 1 ELSE 0 END)         AS modifies,
                   SUM(CASE WHEN r.decision = 'reject' THEN 1 ELSE 0 END)         AS rejects,
                   ROUND(100.0 * SUM(CASE WHEN r.decision = 'accept' THEN 1 ELSE 0 END)
                         / NULLIF(COUNT(r.id), 0), 1)                             AS acceptance_rate
            FROM generations g
            JOIN reviews r ON g.id = r.generation_id
            GROUP BY g.model
            ORDER BY acceptance_rate DESC
        """).fetchall()

        # Rejection / modify notes (most recent 10)
        note_rows = conn.execute("""
            SELECT r.decision, r.note, g.prompt, g.prompt_pattern, r.created_at
            FROM reviews r
            JOIN generations g ON g.id = r.generation_id
            WHERE r.decision IN ('modify', 'reject') AND r.note IS NOT NULL
            ORDER BY r.created_at DESC
            LIMIT 10
        """).fetchall()

        # Time to review — compute median in Python
        times = conn.execute("""
            SELECT (julianday(r.created_at) - julianday(g.completed_at)) * 86400.0
                AS seconds_to_review
            FROM generations g
            JOIN reviews r ON g.id = r.generation_id
            WHERE g.completed_at IS NOT NULL
            ORDER BY seconds_to_review
        """).fetchall()

    seconds_list = [t["seconds_to_review"] for t in times if t["seconds_to_review"] is not None]
    median_s = _median(seconds_list)

    return {
        "overall": dict(overall),
        "per_pattern": [dict(r) for r in pattern_rows],
        "per_model": [dict(r) for r in model_rows],
        "rejection_notes": [dict(r) for r in note_rows],
        "median_seconds_to_review": round(median_s, 1) if median_s is not None else None,
    }


def _median(values: list) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def submit_page(request: Request):
    return templates.TemplateResponse("submit.html", {"request": request})


@app.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request):
    return templates.TemplateResponse("queue.html", {"request": request})
