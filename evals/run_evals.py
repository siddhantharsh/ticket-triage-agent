"""Run the golden dataset through the triage graph and report quality and latency.

    python -m evals.run_evals --mode mock
    python -m evals.run_evals --mode live --price-in-per-mtok P --price-out-per-mtok Q

MOCK uses the deterministic keyword stand-ins and measures pipeline logic, not a model.
LIVE calls the real model through app.llm.bedrock_client and needs AWS credentials.
"""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.metrics import by_tag, latency_summary, summarize, usage_summary

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "data" / "evals" / "golden.jsonl"
DEFAULT_REPORT_DIR = ROOT / "evals" / "reports"


def load_golden(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def dataset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _run_case(case: dict, graph, bedrock_client, build_initial_state, request_cls) -> dict:
    record = {
        "id": case["id"],
        "tag": case["tag"],
        "expected_category": case["expected_category"],
        "expected_severity": case["expected_severity"],
        "expected_route": case["expected_route"],
        "category": None,
        "severity": None,
        "confidence": None,
        "route": "decide",
        "error": None,
        "latency_ms": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }

    request = request_cls(
        ticket_id=case["id"],
        subject=case["subject"],
        body=case["body"],
        customer_id=case["customer_id"],
        order_id=case["order_id"],
    )
    started = time.perf_counter()
    try:
        with bedrock_client.track_usage() as usage:
            result = graph.invoke(build_initial_state(request))
        record["category"] = result["category"]
        record["severity"] = result["severity"]
        record["confidence"] = result["confidence"]
        record["route"] = "escalate" if result["escalated"] else "decide"
    except Exception as exc:
        # A failed run counts as wrong on every axis and as "no escalation".
        usage = []
        record["error"] = f"{type(exc).__name__}: {exc}"[:200]
    record["latency_ms"] = (time.perf_counter() - started) * 1000
    record["input_tokens"] = sum(u["input_tokens"] for u in usage)
    record["output_tokens"] = sum(u["output_tokens"] for u in usage)

    record["category_ok"] = record["category"] == case["expected_category"]
    record["severity_ok"] = record["severity"] == case["expected_severity"]
    record["route_ok"] = record["error"] is None and record["route"] == case["expected_route"]
    return record


def run_eval(
    mode: str,
    golden_path: Path = DEFAULT_GOLDEN,
    price_in: float | None = None,
    price_out: float | None = None,
) -> dict:
    if mode not in ("mock", "live"):
        raise ValueError(f"unknown mode {mode!r}")

    from app.db.init_db import init_db
    from app.graph.build import triage_graph
    from app.llm import bedrock_client
    from app.main import build_initial_state
    from app.models.schemas import TriageRequest
    from app.tools import rag_tool

    cases = load_golden(golden_path)
    previous_mock = bedrock_client.MOCK_BEDROCK
    previous_db = os.environ.get("DB_PATH")
    bedrock_client.MOCK_BEDROCK = mode == "mock"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "eval.db"
            init_db(db_path)
            os.environ["DB_PATH"] = str(db_path)

            # Load the embedding model before timing so start-up cost is not in the latency.
            rag_tool.search_kb("warm up")
            kb_docs = rag_tool._get_collection().count()

            records = [
                _run_case(case, triage_graph, bedrock_client, build_initial_state, TriageRequest)
                for case in cases
            ]
    finally:
        bedrock_client.MOCK_BEDROCK = previous_mock
        if previous_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = previous_db

    return {
        "meta": {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "mode": mode,
            "model_id": bedrock_client.BEDROCK_MODEL_ID if mode == "live" else None,
            "dataset": str(golden_path.relative_to(ROOT))
            if golden_path.is_relative_to(ROOT)
            else str(golden_path),
            "dataset_sha256": dataset_sha256(golden_path),
            "n_cases": len(cases),
            "kb_index_docs": kb_docs,
            "git_commit": _git_commit(),
            "prices_usd_per_mtok": {"input": price_in, "output": price_out}
            if mode == "live"
            else None,
        },
        "metrics": {
            **summarize(records),
            "latency_ms": latency_summary(records),
            "usage": usage_summary(records, price_in, price_out) if mode == "live" else None,
        },
        "by_tag": by_tag(records),
        "cases": records,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict) -> str:
    meta, m = report["meta"], report["metrics"]
    esc = m["escalation"]
    lines = [
        f"# Eval report {meta['timestamp']} ({meta['mode'].upper()})",
        "",
        f"- cases: {meta['n_cases']} from `{meta['dataset']}` "
        f"(sha256 `{meta['dataset_sha256'][:12]}`)",
        f"- commit: {meta['git_commit']}, KB docs indexed: {meta['kb_index_docs']}",
    ]
    if meta["mode"] == "mock":
        lines.append(
            "- MOCK mode scores the keyword stand-ins, not a language model. "
            "It guards pipeline and rule regressions only."
        )
    else:
        lines.append(f"- model: `{meta['model_id']}`")
    lines += [
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| category accuracy | {_pct(m['category_accuracy'])} |",
        f"| severity accuracy | {_pct(m['severity_accuracy'])} |",
        f"| route accuracy | {_pct(m['route_accuracy'])} |",
        f"| escalation precision | {_pct(esc['precision'])} |",
        f"| escalation recall | {_pct(esc['recall'])} |",
        f"| escalation tp / fp / fn / tn | {esc['tp']} / {esc['fp']} / {esc['fn']} / {esc['tn']} |",
        f"| latency p50 / p95 (ms) | {m['latency_ms']['p50']:.1f} / {m['latency_ms']['p95']:.1f} |",
        f"| errors | {m['errors']} |",
    ]
    usage = m["usage"]
    if usage:
        cost = usage["cost_usd_per_ticket"]
        cost_text = "not computed, no prices given" if cost is None else f"{cost:.6f}"
        lines += [
            f"| input / output tokens per ticket | {usage['input_tokens_per_ticket']:.0f} / "
            f"{usage['output_tokens_per_ticket']:.0f} |",
            f"| cost per ticket (USD) | {cost_text} |",
        ]
    lines += [
        "",
        "## By tag",
        "",
        "| tag | n | category | severity | route | esc. precision | esc. recall |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for tag, t in report["by_tag"].items():
        lines.append(
            f"| {tag} | {t['n']} | {_pct(t['category_accuracy'])} | {_pct(t['severity_accuracy'])} "
            f"| {_pct(t['route_accuracy'])} | {_pct(t['escalation']['precision'])} "
            f"| {_pct(t['escalation']['recall'])} |"
        )
    misses = [
        c for c in report["cases"] if not (c["category_ok"] and c["severity_ok"] and c["route_ok"])
    ]
    lines += ["", f"## Cases with at least one wrong field ({len(misses)})", ""]
    lines += [
        "| id | tag | category exp/got | severity exp/got | route exp/got |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in misses:
        lines.append(
            f"| {c['id']} | {c['tag']} | {c['expected_category']}/{c['category']} "
            f"| {c['expected_severity']}/{c['severity']} | {c['expected_route']}/{c['route']} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report['meta']['timestamp']}-{report['meta']['mode']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--price-in-per-mtok", type=float, help="USD per million input tokens")
    parser.add_argument("--price-out-per-mtok", type=float, help="USD per million output tokens")
    args = parser.parse_args()

    report = run_eval(args.mode, args.golden, args.price_in_per_mtok, args.price_out_per_mtok)
    json_path, md_path = write_report(report, args.out_dir)
    print(md_path.read_text(encoding="utf-8"))
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
