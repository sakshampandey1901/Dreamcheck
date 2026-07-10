import json
import os
import uuid
from app.db import get_conn

_SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "seed_data.json")


def seed_if_empty() -> None:
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
        if count > 0:
            return

    with open(_SEED_FILE, encoding="utf-8") as f:
        entries = json.load(f)

    with get_conn() as conn:
        for entry in entries:
            conn.execute(
                """INSERT INTO generations
                   (id, prompt, model, prompt_pattern, state, failure_reason,
                    asset_type, asset_url, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry["id"],
                    entry["prompt"],
                    entry["model"],
                    entry["prompt_pattern"],
                    entry["state"],
                    entry["failure_reason"],
                    entry["asset_type"],
                    entry["asset_url"],
                    entry["created_at"],
                    entry["completed_at"],
                ),
            )
            review = entry.get("review")
            if review:
                conn.execute(
                    """INSERT INTO reviews (id, generation_id, decision, note, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        review["id"],
                        entry["id"],
                        review["decision"],
                        review.get("note"),
                        review["created_at"],
                    ),
                )
