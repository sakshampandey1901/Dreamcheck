import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable


@dataclass
class Generation:
    id: str
    state: str                        # queued | dreaming | completed | failed
    failure_reason: Optional[str] = None
    asset_url: Optional[str] = None


@runtime_checkable
class LumaClient(Protocol):
    def create_generation(self, prompt: str, model: str) -> Generation: ...
    def get_generation(self, gen_id: str) -> Generation: ...


# ---------------------------------------------------------------------------
# Mock client — state persists in SQLite; no in-memory state
# ---------------------------------------------------------------------------

_FAILURE_REASONS = [
    "Generation timed out after maximum retries",
    "Server error: upstream model temporarily unavailable",
    "Invalid prompt: conflicting style descriptors cannot be resolved",
    "Content moderation flag: prompt contains restricted terms",
]

_PLACEHOLDER_URL = "/static/placeholder.svg"


def _completion_seconds(gen_id: str) -> float:
    """Deterministic completion time 5–15 s based on generation id."""
    digest = int(hashlib.md5(gen_id.encode()).hexdigest(), 16)
    return 5.0 + (digest % 101) / 10.0   # 5.0 → 15.0


def _should_fail(gen_id: str) -> bool:
    """~10% failure rate, deterministic per id."""
    digest = int(hashlib.sha256(gen_id.encode()).hexdigest(), 16)
    return (digest % 10) == 0


def _failure_reason(gen_id: str) -> str:
    digest = int(hashlib.md5(gen_id.encode()).hexdigest(), 16)
    return _FAILURE_REASONS[digest % len(_FAILURE_REASONS)]


class MockLumaClient:
    def create_generation(self, prompt: str, model: str) -> Generation:
        return Generation(id=str(uuid.uuid4()), state="queued")

    def get_generation(self, gen_id: str) -> Generation:
        from app.db import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT state, created_at FROM generations WHERE id = ?", (gen_id,)
            ).fetchone()

        if not row:
            raise ValueError(f"Generation {gen_id!r} not found")

        state = row["state"]
        if state in ("completed", "failed"):
            return Generation(id=gen_id, state=state)

        created = datetime.fromisoformat(row["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()

        if state == "queued" and elapsed >= 2:
            return Generation(id=gen_id, state="dreaming")

        completion = _completion_seconds(gen_id)
        if state == "dreaming" and elapsed >= completion:
            if _should_fail(gen_id):
                return Generation(id=gen_id, state="failed",
                                  failure_reason=_failure_reason(gen_id))
            return Generation(id=gen_id, state="completed",
                              asset_url=_PLACEHOLDER_URL)

        return Generation(id=gen_id, state=state)


# ---------------------------------------------------------------------------
# Real client — written but never invoked during dev (LUMA_MODE=mock default)
# ---------------------------------------------------------------------------

class RealLumaClient:
    def __init__(self):
        import lumaai  # type: ignore
        self._client = lumaai.LumaAI(auth_token=os.environ["LUMAAI_API_KEY"])

    def create_generation(self, prompt: str, model: str) -> Generation:
        result = self._client.generations.image.create(prompt=prompt, model=model)
        return Generation(id=result.id, state=result.state)

    def get_generation(self, gen_id: str) -> Generation:
        result = self._client.generations.get(gen_id)
        asset_url = None
        if result.assets and result.assets.image:
            asset_url = result.assets.image
        return Generation(
            id=result.id,
            state=result.state,
            failure_reason=getattr(result, "failure_reason", None),
            asset_url=asset_url,
        )


# ---------------------------------------------------------------------------
# Factory — mode switch is config only
# ---------------------------------------------------------------------------

def get_luma_client() -> LumaClient:
    mode = os.getenv("LUMA_MODE", "mock").lower()
    if mode == "real":
        return RealLumaClient()
    return MockLumaClient()
