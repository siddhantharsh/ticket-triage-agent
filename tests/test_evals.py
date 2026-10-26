import io
import json
import os

import pytest

from app.llm import bedrock_client
from app.tools import rag_tool
from evals import metrics, run_evals


def _case(expected_route, route, **kw):
    base = {
        "expected_route": expected_route,
        "route": route,
        "tag": "normal",
        "category_ok": True,
        "severity_ok": True,
        "route_ok": expected_route == route,
        "error": None,
        "latency_ms": 1.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    return {**base, **kw}


def test_percentile_uses_nearest_rank():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert metrics.percentile(values, 50) == 50
    assert metrics.percentile(values, 95) == 100
    assert metrics.percentile([], 50) is None


def test_escalation_confusion_counts_and_rates():
    cases = [
        _case("escalate", "escalate"),
        _case("escalate", "decide"),
        _case("decide", "escalate"),
        _case("decide", "decide"),
        _case("decide", "decide"),
    ]
    esc = metrics.escalation_confusion(cases)
    assert (esc["tp"], esc["fp"], esc["fn"], esc["tn"]) == (1, 1, 1, 2)
    assert esc["precision"] == 0.5
    assert esc["recall"] == 0.5


def test_escalation_rates_are_none_when_undefined():
    esc = metrics.escalation_confusion([_case("decide", "decide")])
    assert esc["precision"] is None
    assert esc["recall"] is None


def test_usage_summary_only_computes_cost_when_prices_are_given():
    cases = [_case("decide", "decide", input_tokens=1000, output_tokens=200)] * 2
    no_prices = metrics.usage_summary(cases, None, None)
    assert no_prices["input_tokens_per_ticket"] == 1000
    assert no_prices["cost_usd_total"] is None
    priced = metrics.usage_summary(cases, 3.0, 15.0)
    assert priced["cost_usd_total"] == pytest.approx((2000 * 3.0 + 400 * 15.0) / 1_000_000)
    assert priced["cost_usd_per_ticket"] == pytest.approx(priced["cost_usd_total"] / 2)


@pytest.fixture
def tiny_golden(tmp_path, monkeypatch):
    rows = [
        {
            "id": "T-1", "tag": "normal", "subject": "Unauthorized charge",
            "body": "I see an unauthorized charge, this is fraud.", "customer_id": "CUST-005",
            "order_id": None, "expected_category": "billing", "expected_severity": "high",
            "expected_route": "escalate", "rationale": "x",
        },
        {
            "id": "T-2", "tag": "adversarial", "subject": "Cancel my plan",
            "body": "Please cancel my plan at period end.", "customer_id": "CUST-003",
            "order_id": None, "expected_category": "account", "expected_severity": "low",
            "expected_route": "decide", "rationale": "x",
        },
    ]
    path = tmp_path / "golden.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    class FakeCollection:
        def count(self):
            return 0

    monkeypatch.setattr(rag_tool, "search_kb", lambda query, top_k=3: [])
    monkeypatch.setattr(rag_tool, "_get_collection", lambda: FakeCollection())
    return path


def test_mock_run_is_deterministic_apart_from_latency(tiny_golden):
    def stable(report):
        return {
            "metrics": {k: v for k, v in report["metrics"].items() if k != "latency_ms"},
            "cases": [{k: v for k, v in c.items() if k != "latency_ms"} for c in report["cases"]],
        }

    first = run_evals.run_eval("mock", tiny_golden)
    second = run_evals.run_eval("mock", tiny_golden)
    assert stable(first) == stable(second)
    assert first["meta"]["mode"] == "mock"
    assert first["metrics"]["usage"] is None
    assert first["metrics"]["category_accuracy"] == 1.0


def test_run_eval_restores_mock_flag_and_db_path(tiny_golden, monkeypatch):
    monkeypatch.setenv("DB_PATH", "/original/path.db")
    run_evals.run_eval("mock", tiny_golden)
    assert bedrock_client.MOCK_BEDROCK is True
    assert os.environ["DB_PATH"] == "/original/path.db"


class _FakeBedrock:
    """Stands in for the boto3 client; answers classification and resolution calls."""

    def invoke_model(self, modelId, body, contentType, accept):
        system = json.loads(body)["system"]
        if "triage" in system:
            text = json.dumps({"category": "account", "severity": "low", "confidence": 0.9})
        else:
            text = "Here is your resolution."
        payload = {"content": [{"text": text}], "usage": {"input_tokens": 100, "output_tokens": 10}}
        return {"body": io.BytesIO(json.dumps(payload).encode())}


def test_live_mode_captures_tokens_through_the_graph_and_prices_them(tiny_golden, monkeypatch):
    monkeypatch.setattr(bedrock_client, "_get_client", lambda: _FakeBedrock())

    report = run_evals.run_eval("live", tiny_golden, price_in=3.0, price_out=15.0)

    usage = report["metrics"]["usage"]
    # Both tickets classify as account/low/0.9 -> decide, so each makes two model calls.
    assert [c["input_tokens"] for c in report["cases"]] == [200, 200]
    assert [c["output_tokens"] for c in report["cases"]] == [20, 20]
    assert usage["cost_usd_total"] == pytest.approx((400 * 3.0 + 40 * 15.0) / 1_000_000)
    assert report["meta"]["model_id"] == bedrock_client.BEDROCK_MODEL_ID
    assert bedrock_client.MOCK_BEDROCK is True


def test_live_mode_without_prices_reports_tokens_but_no_cost(tiny_golden, monkeypatch):
    monkeypatch.setattr(bedrock_client, "_get_client", lambda: _FakeBedrock())
    report = run_evals.run_eval("live", tiny_golden)
    assert report["metrics"]["usage"]["input_tokens_total"] == 400
    assert report["metrics"]["usage"]["cost_usd_per_ticket"] is None


def test_a_crashing_graph_run_is_recorded_as_an_error_not_raised(tiny_golden, monkeypatch):
    from app.graph import build

    class Boom:
        def invoke(self, state):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(build, "triage_graph", Boom())
    report = run_evals.run_eval("mock", tiny_golden)

    assert report["metrics"]["errors"] == 2
    assert report["metrics"]["category_accuracy"] == 0.0
    assert all(c["route"] == "decide" and not c["route_ok"] for c in report["cases"])


def test_markdown_summary_mentions_mock_caveat_and_misses(tiny_golden):
    report = run_evals.run_eval("mock", tiny_golden)
    text = run_evals.render_markdown(report)
    assert "not a language model" in text
    assert "## By tag" in text
