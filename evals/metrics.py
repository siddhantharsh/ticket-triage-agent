"""Pure metric functions for eval case records. No I/O and no model calls."""

import math


def rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, q in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def escalation_confusion(cases: list[dict]) -> dict:
    tp = fp = fn = tn = 0
    for case in cases:
        expected = case["expected_route"] == "escalate"
        predicted = case["route"] == "escalate"
        if expected and predicted:
            tp += 1
        elif predicted:
            fp += 1
        elif expected:
            fn += 1
        else:
            tn += 1
    return {
        "precision": rate(tp, tp + fp),
        "recall": rate(tp, tp + fn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def summarize(cases: list[dict]) -> dict:
    n = len(cases)
    return {
        "n": n,
        "category_accuracy": rate(sum(c["category_ok"] for c in cases), n),
        "severity_accuracy": rate(sum(c["severity_ok"] for c in cases), n),
        "route_accuracy": rate(sum(c["route_ok"] for c in cases), n),
        "escalation": escalation_confusion(cases),
        "errors": sum(1 for c in cases if c["error"]),
    }


def latency_summary(cases: list[dict]) -> dict:
    values = [c["latency_ms"] for c in cases]
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values) if values else None,
    }


def usage_summary(cases: list[dict], price_in: float | None, price_out: float | None) -> dict:
    """Token and cost totals. Cost is only computed from prices the caller supplies."""
    n = len(cases)
    tokens_in = sum(c["input_tokens"] for c in cases)
    tokens_out = sum(c["output_tokens"] for c in cases)
    summary = {
        "input_tokens_total": tokens_in,
        "output_tokens_total": tokens_out,
        "input_tokens_per_ticket": rate(tokens_in, n),
        "output_tokens_per_ticket": rate(tokens_out, n),
        "cost_usd_total": None,
        "cost_usd_per_ticket": None,
    }
    if price_in is not None and price_out is not None:
        total = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
        summary["cost_usd_total"] = total
        summary["cost_usd_per_ticket"] = rate(total, n) if n else None
    return summary


def by_tag(cases: list[dict]) -> dict:
    tags = sorted({c["tag"] for c in cases})
    return {tag: summarize([c for c in cases if c["tag"] == tag]) for tag in tags}
