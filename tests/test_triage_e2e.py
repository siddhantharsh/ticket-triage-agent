from fastapi.testclient import TestClient

from app.llm import bedrock_client
from app.main import app
from app.tools import rag_tool


def test_triage_normal_ticket_returns_resolution(test_db, monkeypatch):
    monkeypatch.setattr(
        bedrock_client,
        "classify_ticket",
        lambda subject, body: {"category": "account", "severity": "low", "confidence": 0.9},
    )
    monkeypatch.setattr(
        bedrock_client,
        "generate_resolution",
        lambda **kwargs: "Mocked resolution: downgrade processed at period end.",
    )
    monkeypatch.setattr(rag_tool, "search_kb", lambda query, top_k=3: [])

    client = TestClient(app)
    response = client.post(
        "/triage",
        json={
            "ticket_id": "T-100",
            "subject": "Downgrade my plan",
            "body": "Please downgrade my plan next cycle.",
            "customer_id": "CUST-003",
            "order_id": None,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "account"
    assert data["severity"] == "low"
    assert data["escalated"] is False
    assert data["resolution"] == "Mocked resolution: downgrade processed at period end."
    assert data["customer_context"]["plan_tier"] == "enterprise"
    assert [entry["node"] for entry in data["audit_trail"]] == [
        "classify",
        "retrieve",
        "decide",
        "respond",
    ]


def test_triage_high_severity_ticket_escalates(test_db, monkeypatch):
    monkeypatch.setattr(
        bedrock_client,
        "classify_ticket",
        lambda subject, body: {"category": "billing", "severity": "high", "confidence": 0.5},
    )

    def fail_generate_resolution(**kwargs):
        raise AssertionError("generate_resolution must not be called on the escalate path")

    monkeypatch.setattr(bedrock_client, "generate_resolution", fail_generate_resolution)
    monkeypatch.setattr(rag_tool, "search_kb", lambda query, top_k=3: [])

    client = TestClient(app)
    response = client.post(
        "/triage",
        json={
            "ticket_id": "T-101",
            "subject": "Unauthorized charge",
            "body": "This charge is fraud, refund me now.",
            "customer_id": "CUST-005",
            "order_id": None,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["escalated"] is True
    assert data["resolution"] is None
    assert data["escalation_reason"] is not None
    assert [entry["node"] for entry in data["audit_trail"]] == [
        "classify",
        "retrieve",
        "escalate",
    ]
