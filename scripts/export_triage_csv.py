#!/usr/bin/env python3
"""Export triage_log to a flat CSV for Tableau. Data is synthetic mock-mode output."""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.init_db import ROOT  # noqa: E402

DEFAULT_DB = ROOT / "data" / "demo_triage.db"
DEFAULT_OUT = ROOT / "data" / "triage_results.csv"

COLUMNS = [
    "ticket_id",
    "created_at",
    "created_date",
    "category",
    "severity",
    "confidence",
    "decision",
    "escalation_reason",
    "resolution_source",
    "latency_ms",
    "data_source",
]
DATA_SOURCE = "synthetic_mock"


def _iso_utc(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_csv(db_path: Path, out_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ticket_id, created_at, category, severity, confidence, decision, "
            "escalation_reason, resolution_source, latency_ms "
            "FROM triage_log ORDER BY created_at, id"
        ).fetchall()
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for (
            ticket_id,
            created_at,
            category,
            severity,
            confidence,
            decision,
            reason,
            source,
            ms,
        ) in rows:
            iso = _iso_utc(created_at)
            writer.writerow(
                [
                    ticket_id,
                    iso,
                    iso[:10],
                    category,
                    severity,
                    f"{confidence:.2f}",
                    decision,
                    reason or "none",
                    source,
                    f"{ms:.1f}",
                    DATA_SOURCE,
                ]
            )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    total = export_csv(args.db, args.out)
    print(f"Wrote {total} rows to {args.out}")


if __name__ == "__main__":
    main()
