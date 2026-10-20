import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.db.init_db import ROOT, SCHEMA_PATH

ESCALATE_HIGH_SEVERITY = "high_severity"
ESCALATE_LOW_CONFIDENCE = "low_confidence"


def _default_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", ROOT / "data" / "tickets.db"))


def _resolution_source(result: dict) -> str:
    if result["escalated"]:
        return "none"
    if result["kb_snippets"]:
        return "RAG"
    if (result["customer_context"] or {}).get("found"):
        return "SQL"
    return "none"


def _escalation_reason(result: dict) -> str | None:
    if not result["escalated"]:
        return None
    return ESCALATE_HIGH_SEVERITY if result["severity"] == "high" else ESCALATE_LOW_CONFIDENCE


def log_triage(
    result: dict,
    latency_ms: float,
    created_at: datetime | None = None,
    db_path: Path | None = None,
) -> None:
    created_at = created_at or datetime.now(timezone.utc)
    conn = sqlite3.connect(db_path or _default_db_path())
    try:
        # Idempotent, so a database seeded before triage_log existed still works.
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute(
            "INSERT INTO triage_log (ticket_id, created_at, category, severity, confidence, "
            "decision, escalation_reason, resolution_source, latency_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result["ticket_id"],
                created_at.astimezone(timezone.utc).isoformat(),
                result["category"],
                result["severity"],
                result["confidence"],
                "escalated" if result["escalated"] else "auto_resolved",
                _escalation_reason(result),
                _resolution_source(result),
                round(latency_ms, 1),
            ),
        )
        conn.commit()
    finally:
        conn.close()
