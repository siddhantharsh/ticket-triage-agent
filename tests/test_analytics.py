import csv
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.llm import bedrock_client
from app.main import app
from app.tools import rag_tool
from scripts import export_triage_csv, generate_demo_tickets

END = date(2026, 1, 31)
KEY_FIELDS = [
    "ticket_id",
    "created_at",
    "category",
    "severity",
    "confidence",
    "decision",
    "resolution_source",
    "latency_ms",
]


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM triage_log ORDER BY id")]
    finally:
        conn.close()


def _post(client, ticket_id, customer_id="CUST-003"):
    return client.post(
        "/triage",
        json={
            "ticket_id": ticket_id,
            "subject": "Downgrade my plan",
            "body": "Please downgrade next cycle.",
            "customer_id": customer_id,
        },
    )


def _patch_bedrock(monkeypatch, classification, snippets=()):
    monkeypatch.setattr(bedrock_client, "classify_ticket", lambda s, b: classification)
    monkeypatch.setattr(bedrock_client, "generate_resolution", lambda **kw: "Mocked resolution.")
    monkeypatch.setattr(rag_tool, "search_kb", lambda query, top_k=3: list(snippets))


def test_triage_logs_auto_resolved_row_with_rag_source(test_db, monkeypatch):
    snippet = {"doc_id": "d", "title": "t", "text": "x", "score": 0.9}
    _patch_bedrock(
        monkeypatch, {"category": "account", "severity": "low", "confidence": 0.9}, [snippet]
    )

    assert _post(TestClient(app), "T-LOG-1").status_code == 200

    (row,) = _rows(test_db)
    assert row["ticket_id"] == "T-LOG-1"
    assert (row["category"], row["severity"], row["confidence"]) == ("account", "low", 0.9)
    assert row["decision"] == "auto_resolved"
    assert row["escalation_reason"] is None
    assert row["resolution_source"] == "RAG"
    assert row["latency_ms"] >= 0
    assert row["created_at"]


def test_triage_logs_sql_source_when_no_kb_hit(test_db, monkeypatch):
    _patch_bedrock(monkeypatch, {"category": "account", "severity": "low", "confidence": 0.9})
    _post(TestClient(app), "T-LOG-2")
    assert _rows(test_db)[0]["resolution_source"] == "SQL"


def test_triage_logs_none_source_without_kb_or_customer(test_db, monkeypatch):
    _patch_bedrock(monkeypatch, {"category": "general", "severity": "low", "confidence": 0.9})
    _post(TestClient(app), "T-LOG-3", customer_id="CUST-999")
    assert _rows(test_db)[0]["resolution_source"] == "none"


@pytest.mark.parametrize(
    ("classification", "reason"),
    [
        ({"category": "billing", "severity": "high", "confidence": 0.9}, "high_severity"),
        ({"category": "general", "severity": "low", "confidence": 0.3}, "low_confidence"),
    ],
)
def test_triage_logs_escalation_reason(test_db, monkeypatch, classification, reason):
    _patch_bedrock(monkeypatch, classification)
    _post(TestClient(app), "T-LOG-4")

    (row,) = _rows(test_db)
    assert row["decision"] == "escalated"
    assert row["escalation_reason"] == reason
    assert row["resolution_source"] == "none"


def test_logging_failure_does_not_fail_triage(test_db, monkeypatch):
    _patch_bedrock(monkeypatch, {"category": "account", "severity": "low", "confidence": 0.9})

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.main.log_triage", boom)
    assert _post(TestClient(app), "T-LOG-5").status_code == 200


@pytest.fixture
def fast_pipeline(monkeypatch):
    # Avoid loading the embedding model; the rest of the pipeline is the real mock-mode graph.
    monkeypatch.setattr(
        rag_tool,
        "search_kb",
        lambda query, top_k=3: [{"doc_id": "d", "title": "t", "text": "kb", "score": 0.5}]
        if len(query) % 2
        else [],
    )


def test_generator_row_count_and_window(tmp_path, fast_pipeline):
    db = tmp_path / "demo.db"
    assert generate_demo_tickets.run(40, 7, END, db) == 40

    rows = _rows(db)
    assert len(rows) == 40
    assert len({r["ticket_id"] for r in rows}) == 40
    stamps = sorted(r["created_at"] for r in rows)
    assert stamps[0] >= "2025-12-01" and stamps[-1] < "2026-01-31"


def test_generator_is_reproducible_for_same_seed(tmp_path, fast_pipeline):
    def snapshot(name, seed):
        db = tmp_path / name
        generate_demo_tickets.run(30, seed, END, db)
        return [{k: v for k, v in r.items() if k != "latency_ms"} for r in _rows(db)]

    assert snapshot("a.db", 1) == snapshot("b.db", 1)
    assert snapshot("a.db", 1) != snapshot("c.db", 2)


def test_generator_refuses_without_mock_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(bedrock_client, "MOCK_BEDROCK", False)
    with pytest.raises(SystemExit):
        generate_demo_tickets.run(1, 1, END, tmp_path / "x.db")


def test_csv_export_columns_and_no_nulls(tmp_path, fast_pipeline):
    db = tmp_path / "demo.db"
    out = tmp_path / "out" / "triage_results.csv"
    generate_demo_tickets.run(50, 3, END, db)

    assert export_triage_csv.export_csv(db, out) == 50

    with out.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == export_triage_csv.COLUMNS
    assert len(rows) == 50
    for row in rows:
        for field in KEY_FIELDS:
            assert row[field] != ""
        assert row["created_at"].endswith("Z")
        assert row["created_date"] == row["created_at"][:10]
        assert row["data_source"] == "synthetic_mock"
        assert row["decision"] in ("auto_resolved", "escalated")
