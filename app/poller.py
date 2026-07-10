import asyncio
import logging
from datetime import datetime, timezone

from app.clients import get_luma_client
from app.db import get_conn

logger = logging.getLogger(__name__)


async def poller_loop() -> None:
    client = get_luma_client()
    while True:
        try:
            await _sweep(client)
        except Exception as exc:
            logger.error("Poller sweep failed: %s", exc)
        await asyncio.sleep(3)


async def _sweep(client) -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, state FROM generations WHERE state IN ('queued', 'dreaming')"
        ).fetchall()

    for row in rows:
        try:
            gen = client.get_generation(row["id"])
            if gen.state != row["state"]:
                completed_at = None
                if gen.state in ("completed", "failed"):
                    completed_at = datetime.now(timezone.utc).isoformat()
                with get_conn() as conn:
                    conn.execute(
                        """UPDATE generations
                           SET state = ?, failure_reason = ?, asset_url = ?,
                               completed_at = ?
                           WHERE id = ?""",
                        (gen.state, gen.failure_reason, gen.asset_url,
                         completed_at, row["id"]),
                    )
        except Exception as exc:
            logger.error("Error polling generation %s: %s", row["id"], exc)
