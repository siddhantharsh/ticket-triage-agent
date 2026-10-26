import json
from pathlib import Path

import pytest

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "data" / "evals" / "golden.jsonl"
CASES = [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]

CATEGORIES = {"billing", "technical", "account", "general"}
SEVERITIES = {"low", "medium", "high"}
ROUTES = {"decide", "escalate"}
TAGS = {"normal", "ambiguous", "adversarial"}


def test_golden_set_has_enough_cases_and_adversarial_coverage():
    tags = [c["tag"] for c in CASES]
    assert len(CASES) >= 60
    assert tags.count("adversarial") >= 10
    assert tags.count("normal") > 0 and tags.count("ambiguous") > 0


def test_golden_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_golden_case_is_well_formed(case):
    assert case["expected_category"] in CATEGORIES
    assert case["expected_severity"] in SEVERITIES
    assert case["expected_route"] in ROUTES
    assert case["tag"] in TAGS
    assert isinstance(case["subject"], str) and isinstance(case["body"], str)
    assert case["rationale"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_high_severity_cases_expect_escalation(case):
    if case["expected_severity"] == "high":
        assert case["expected_route"] == "escalate"
