import copy
import json

from evals import check_regression

BASELINE = {
    "mode": "mock",
    "max_drop": 0.01,
    "dataset_sha256": "abc",
    "n_cases": 80,
    "metrics": {
        "category_accuracy": 0.60,
        "severity_accuracy": 0.70,
        "escalation_recall": 0.50,
        "escalation_precision": 0.65,
    },
}


def _report(**overrides):
    values = {**BASELINE["metrics"], **overrides}
    return {
        "meta": {"mode": "mock", "dataset_sha256": "abc", "n_cases": 80, "git_commit": "x"},
        "metrics": {
            "category_accuracy": values["category_accuracy"],
            "severity_accuracy": values["severity_accuracy"],
            "escalation": {
                "recall": values["escalation_recall"],
                "precision": values["escalation_precision"],
            },
        },
    }


def test_identical_metrics_pass():
    failures, notes = check_regression.compare(_report(), BASELINE)
    assert failures == [] and notes == []


def test_drop_within_threshold_passes():
    failures, _ = check_regression.compare(_report(category_accuracy=0.595), BASELINE)
    assert failures == []


def test_drop_beyond_threshold_fails_and_names_the_metric():
    failures, _ = check_regression.compare(_report(escalation_recall=0.45), BASELINE)
    assert len(failures) == 1
    assert "escalation_recall" in failures[0]


def test_each_gated_metric_is_checked():
    for name in check_regression.GATED_METRICS:
        failures, _ = check_regression.compare(_report(**{name: 0.0}), BASELINE)
        assert any(name in f for f in failures), name


def test_improvement_passes_with_a_note():
    failures, notes = check_regression.compare(_report(severity_accuracy=0.80), BASELINE)
    assert failures == []
    assert any("severity_accuracy improved" in n for n in notes)


def test_changed_dataset_fails():
    report = _report()
    report["meta"]["dataset_sha256"] = "different"
    failures, _ = check_regression.compare(report, BASELINE)
    assert any("golden dataset changed" in f for f in failures)


def test_undefined_current_metric_counts_as_zero():
    failures, _ = check_regression.compare(_report(escalation_precision=None), BASELINE)
    assert any("escalation_precision" in f for f in failures)


def test_non_mock_report_is_rejected():
    report = _report()
    report["meta"]["mode"] = "live"
    failures, _ = check_regression.compare(report, BASELINE)
    assert failures and "MOCK" in failures[0]


def test_max_drop_override_tightens_the_gate():
    failures, _ = check_regression.compare(
        _report(category_accuracy=0.595), BASELINE, max_drop=0.001
    )
    assert failures


def test_cli_exit_codes_and_baseline_update(tmp_path, monkeypatch, capsys):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(BASELINE))
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_report()))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_report(category_accuracy=0.1)))

    def run(*args):
        argv = ["check_regression", "--baseline", str(baseline_path), *args]
        monkeypatch.setattr("sys.argv", argv)
        return check_regression.main()

    assert run("--report", str(good)) == 0
    assert run("--report", str(bad)) == 1
    assert run("--report", str(bad), "--update-baseline") == 2
    assert json.loads(baseline_path.read_text())["metrics"]["category_accuracy"] == 0.60

    assert run("--report", str(bad), "--update-baseline", "--reason", "rule rewrite") == 0
    updated = json.loads(baseline_path.read_text())
    assert updated["metrics"]["category_accuracy"] == 0.1
    assert updated["reason"] == "rule rewrite"
    assert run("--report", str(bad)) == 0
    capsys.readouterr()


def test_build_baseline_does_not_mutate_the_report():
    report = _report()
    before = copy.deepcopy(report)
    check_regression.build_baseline(report, "why", 0.01)
    assert report == before
