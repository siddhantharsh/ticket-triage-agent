"""Fail when the latest MOCK eval is worse than evals/baseline.json.

    python -m evals.check_regression                       # run MOCK eval, exit 1 on regression
    python -m evals.check_regression --report path.json    # compare an existing report
    python -m evals.check_regression --update-baseline --reason "why the numbers moved"

Latency is not gated: it is measured wall-clock time and varies between machines.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.run_evals import DEFAULT_GOLDEN, DEFAULT_REPORT_DIR, ROOT, run_eval, write_report

DEFAULT_BASELINE = ROOT / "evals" / "baseline.json"
DEFAULT_MAX_DROP = 0.01
GATED_METRICS = (
    "category_accuracy",
    "severity_accuracy",
    "escalation_recall",
    "escalation_precision",
)
EPSILON = 1e-9


def gated_values(report: dict) -> dict:
    m = report["metrics"]
    return {
        "category_accuracy": m["category_accuracy"],
        "severity_accuracy": m["severity_accuracy"],
        "escalation_recall": m["escalation"]["recall"],
        "escalation_precision": m["escalation"]["precision"],
    }


def compare(report: dict, baseline: dict, max_drop: float | None = None) -> tuple[list, list]:
    """Return (failures, notes). An empty failure list means the gate passes."""
    max_drop = baseline.get("max_drop", DEFAULT_MAX_DROP) if max_drop is None else max_drop
    failures, notes = [], []

    if report["meta"]["mode"] != "mock":
        return [f"gate compares MOCK runs only, got mode={report['meta']['mode']}"], notes

    if report["meta"]["dataset_sha256"] != baseline["dataset_sha256"]:
        failures.append(
            "golden dataset changed since the baseline was recorded "
            f"({baseline['n_cases']} -> {report['meta']['n_cases']} cases); "
            "re-record with --update-baseline --reason"
        )

    current = gated_values(report)
    for name in GATED_METRICS:
        base, cur = baseline["metrics"][name], current[name]
        # An undefined metric (nothing predicted/expected) counts as zero.
        base_v, cur_v = base or 0.0, cur or 0.0
        drop = base_v - cur_v
        if drop > max_drop + EPSILON:
            failures.append(
                f"{name} fell {drop * 100:.1f} points ({base_v:.4f} -> {cur_v:.4f}), "
                f"allowed {max_drop * 100:.1f}"
            )
        elif drop < -EPSILON:
            notes.append(f"{name} improved ({base_v:.4f} -> {cur_v:.4f})")
    return failures, notes


def build_baseline(report: dict, reason: str, max_drop: float) -> dict:
    return {
        "mode": "mock",
        "max_drop": max_drop,
        "dataset_sha256": report["meta"]["dataset_sha256"],
        "n_cases": report["meta"]["n_cases"],
        "metrics": gated_values(report),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": report["meta"]["git_commit"],
        "reason": reason,
    }


def _fresh_report(report_dir: Path) -> dict:
    report = run_eval("mock", DEFAULT_GOLDEN)
    json_path, _ = write_report(report, report_dir)
    print(f"Wrote {json_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="existing MOCK report JSON to check")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--max-drop", type=float, help="override the baseline's allowed drop")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--reason", default="", help="required with --update-baseline")
    args = parser.parse_args()

    report = (
        json.loads(args.report.read_text(encoding="utf-8"))
        if args.report
        else _fresh_report(args.report_dir)
    )

    if args.update_baseline:
        if not args.reason.strip():
            print("--update-baseline requires --reason", file=sys.stderr)
            return 2
        if report["meta"]["mode"] != "mock":
            print("baseline must come from a MOCK run", file=sys.stderr)
            return 2
        old = json.loads(args.baseline.read_text())["metrics"] if args.baseline.exists() else {}
        baseline = build_baseline(report, args.reason.strip(), args.max_drop or DEFAULT_MAX_DROP)
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        for name in GATED_METRICS:
            print(f"{name}: {old.get(name)} -> {baseline['metrics'][name]}")
        print(f"Baseline written to {args.baseline}. Commit it with the change that caused it.")
        return 0

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures, notes = compare(report, baseline, args.max_drop)
    for note in notes:
        print(f"note: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        print("Regression gate failed.", file=sys.stderr)
        return 1
    print("Regression gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
