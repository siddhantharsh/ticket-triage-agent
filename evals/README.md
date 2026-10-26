# Evals

Golden dataset: `data/evals/golden.jsonl` (81 cases, labelling rules in
`data/evals/LABELING.md`).

## Run

```bash
python scripts/build_index.py          # once, so retrieval has a KB index
python -m evals.run_evals --mode mock
```

Writes `evals/reports/<timestamp>-<mode>.json` and a `.md` summary (both gitignored) and
prints the summary. Metrics: category and severity accuracy, route accuracy, escalation
precision and recall (positive class = escalate), the same per tag, p50 and p95 latency
of a graph run, and token usage when the model is real.

**MOCK** uses the deterministic keyword stand-ins. The numbers describe those rules, not
a language model, and a keyword rule cannot be prompt-injected, so MOCK scores on
adversarial cases say nothing about injection robustness of a real model. MOCK is for
catching regressions in the rules and the graph.

**LIVE** calls the real model through `app/llm/bedrock_client.py` and needs AWS
credentials and Bedrock model access:

```bash
python -m evals.run_evals --mode live --price-in-per-mtok <usd> --price-out-per-mtok <usd>
```

Cost is computed only when both prices are given. Take them from the current Bedrock
pricing page for the model in `BEDROCK_MODEL_ID`; nothing is hard-coded.

## Regression gate

```bash
python -m evals.check_regression
```

Runs a fresh MOCK eval and compares it with `evals/baseline.json`. Exit code 1 if any of
category accuracy, severity accuracy, escalation recall or escalation precision is lower
than the baseline by more than `max_drop` (0.01, one percentage point; with 81 cases one
newly wrong case is 1.2 points, so any single new miss fails). It also fails if the
golden dataset changed since the baseline was recorded. Latency is not gated.

CI runs it in the `eval-gate` job, after the unit tests.

## Updating the baseline deliberately

Do this only when a change is meant to move the numbers (new rules, new golden cases,
or an accepted trade-off):

```bash
python -m evals.check_regression --update-baseline --reason "what changed and why"
```

It prints old and new values, requires a non-empty reason, and writes the reason, commit
and timestamp into `baseline.json`. Commit the new baseline in the same commit as the
change that caused it, so the review shows both.
