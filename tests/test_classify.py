import json
from pathlib import Path

import pytest

from app.llm import bedrock_client

TICKETS_PATH = Path(__file__).resolve().parents[1] / "data" / "seed" / "tickets.json"
LABELED_TICKETS = json.loads(TICKETS_PATH.read_text())


def test_labeled_tickets_dataset_is_nonempty():
    assert len(LABELED_TICKETS) >= 10


@pytest.mark.parametrize("ticket", LABELED_TICKETS, ids=lambda t: t["ticket_id"])
def test_mock_classify_matches_expected_label_for_each_labeled_ticket(ticket):
    assert bedrock_client.MOCK_BEDROCK is True

    result = bedrock_client.classify_ticket(ticket["subject"], ticket["body"])

    assert result["category"] == ticket["expected_category"]
    assert result["severity"] == ticket["expected_severity"]
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.parametrize("ticket", LABELED_TICKETS, ids=lambda t: t["ticket_id"])
def test_bedrock_classify_parses_model_output_for_each_labeled_ticket(ticket, monkeypatch):
    monkeypatch.setattr(bedrock_client, "MOCK_BEDROCK", False)
    canned_response = json.dumps(
        {
            "category": ticket["expected_category"],
            "severity": ticket["expected_severity"],
            "confidence": 0.9,
        }
    )
    monkeypatch.setattr(
        bedrock_client,
        "_invoke_claude",
        lambda system_prompt, user_prompt, max_tokens=200: canned_response,
    )

    result = bedrock_client.classify_ticket(ticket["subject"], ticket["body"])

    assert result["category"] == ticket["expected_category"]
    assert result["severity"] == ticket["expected_severity"]
    assert result["confidence"] == 0.9


def test_bedrock_classify_clamps_out_of_range_confidence(monkeypatch):
    monkeypatch.setattr(bedrock_client, "MOCK_BEDROCK", False)
    monkeypatch.setattr(
        bedrock_client,
        "_invoke_claude",
        lambda *args, **kwargs: json.dumps(
            {"category": "billing", "severity": "high", "confidence": 1.5}
        ),
    )
    result = bedrock_client.classify_ticket("subject", "body")
    assert result["confidence"] == 1.0


def test_bedrock_classify_falls_back_safely_on_malformed_model_output(monkeypatch):
    monkeypatch.setattr(bedrock_client, "MOCK_BEDROCK", False)
    monkeypatch.setattr(bedrock_client, "_invoke_claude", lambda *args, **kwargs: "not json at all")

    result = bedrock_client.classify_ticket("subject", "body")

    assert result == {"category": "general", "severity": "high", "confidence": 0.0}


def test_bedrock_classify_falls_back_on_unknown_category_and_severity(monkeypatch):
    monkeypatch.setattr(bedrock_client, "MOCK_BEDROCK", False)
    monkeypatch.setattr(
        bedrock_client,
        "_invoke_claude",
        lambda *args, **kwargs: json.dumps(
            {
                "category": "not-a-real-category",
                "severity": "not-a-real-severity",
                "confidence": 0.5,
            }
        ),
    )

    result = bedrock_client.classify_ticket("subject", "body")

    assert result["category"] == "general"
    assert result["severity"] == "high"
