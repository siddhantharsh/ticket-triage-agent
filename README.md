# Support Ticket Triage & Resolution Agent

An agentic service that classifies incoming support tickets, retrieves relevant
help-doc context, looks up the customer's account/order, and recommends a
resolution — or escalates to a human — with a full audit trail of what the
agent did at each step.

## Architecture

The core is a [LangGraph](https://github.com/langchain-ai/langgraph) state graph:

```
classify → retrieve → (decide → respond)
                    ↘ escalate
```

- **classify** — calls Claude on AWS Bedrock to label the ticket's `category`,
  `severity`, and a `confidence` score.
- **retrieve** — always runs next, regardless of severity. It calls two tools:
  - the **RAG tool**, semantic search (ChromaDB + `all-MiniLM-L6-v2` sentence
    embeddings) over the markdown FAQ docs in `data/kb/`
  - the **SQL tool**, a parameterized SQLite lookup against `data/tickets.db`
    for the ticket's customer/order
- **conditional routing** — after `retrieve`, a router inspects `severity` and
  `confidence`. High-severity tickets (e.g. fraud/unauthorized charges) or
  low-confidence classifications route to `escalate` instead of `decide`, so a
  human still gets the retrieved context attached to the handoff.
- **decide** — calls Claude again with the ticket, KB snippets, and customer
  context to draft a recommended resolution.
- **respond** / **escalate** — terminal nodes that shape the final response.

Every node appends an entry to `audit_trail` (node name, summary, UTC
timestamp), so the API response always carries a complete record of what the
agent did and why — this is the "audit trail" requirement.

FastAPI exposes this graph through a single `POST /triage` endpoint.

## Project layout

```
app/
  graph/        LangGraph state, nodes, and graph construction
  llm/          Bedrock Runtime client (classification + resolution generation)
  tools/        RAG tool (Chroma) and SQL tool (SQLite)
  models/       Pydantic request/response schemas
  db/           SQLite schema + seeding
data/
  kb/           Fake FAQ/help-doc markdown files, semantically indexed
  seed/         Fake customers.json, orders.json, and labeled tickets.json
scripts/
  seed_db.py    Builds data/tickets.db from data/seed/*.json
  build_index.py Builds the Chroma index from data/kb/*.md
  generate_demo_tickets.py  Synthetic tickets -> real pipeline (mock mode) -> triage_log
  export_triage_csv.py      Flattens triage_log into data/triage_results.csv
tests/          Pytest suite (classify, SQL tool, end-to-end /triage)
```

## Running locally

By default the app runs entirely offline: `MOCK_BEDROCK=true` (the default)
swaps in deterministic local stand-ins for `classify_ticket` and
`generate_resolution` instead of calling AWS, so you can run and demo the full
pipeline without any AWS setup or cost. The real `boto3`-based Bedrock calls
are fully implemented in `app/llm/bedrock_client.py` — set `MOCK_BEDROCK=false`
and provide credentials (below) to actually use them.

### 1. (Optional) Set up AWS credentials for real Bedrock calls

Only needed if you set `MOCK_BEDROCK=false`. This project calls **Anthropic
Claude on AWS Bedrock** via `boto3`. In the AWS console:

1. Go to **Bedrock → Model access**, request access to an Anthropic Claude
   model (e.g. Claude 3.5 Sonnet), and wait for it to show "Access granted".
2. Create an IAM user (or role) with the `bedrock:InvokeModel` permission for
   that model, and generate an access key.
3. Export credentials as environment variables (see `.env.example`):

   ```bash
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_REGION=us-east-1
   export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
   ```

### 2. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Seed the database and build the KB index

```bash
python scripts/seed_db.py
python scripts/build_index.py
```

### 4. Run the API

```bash
uvicorn app.main:app --reload
```

### 5. Try it

```bash
curl -X POST localhost:8000/triage \
  -H 'Content-Type: application/json' \
  -d '{
        "ticket_id": "T-1",
        "subject": "Unauthorized charge on my card",
        "body": "I see a charge I do not recognize, please refund it.",
        "customer_id": "CUST-005"
      }'
```

## Tests

```bash
pytest -v
```

Tests never call real Bedrock — the end-to-end test monkeypatches
`app.llm.bedrock_client` so classification and resolution generation are
deterministic.

## Analytics dashboard

Every `POST /triage` call appends one row to the `triage_log` table in the SQLite
database. The rows can be exported to a flat CSV and explored in a Tableau Public
dashboard.

**All data in the dashboard is synthetic.** It is produced by
`scripts/generate_demo_tickets.py`, which invents about 500 fake tickets and runs them
through the real pipeline with `MOCK_BEDROCK=true`. The classifier and resolution
text are deterministic local stand-ins, not Claude. It is not real customer data and
it says nothing about how a real model would perform. The script refuses to run
unless mock mode is on.

### Schema

`triage_log` (SQLite) and `data/triage_results.csv` share these columns:

| Column | Description |
| --- | --- |
| `ticket_id` | Ticket identifier (`SYN-0001` and so on for demo data) |
| `created_at` | UTC timestamp, ISO 8601 (`2026-08-21T07:08:47Z` in the CSV) |
| `category` | `billing`, `technical`, `account` or `general` |
| `severity` | `low`, `medium` or `high` |
| `confidence` | Classifier confidence, 0 to 1 |
| `decision` | `auto_resolved` or `escalated` |
| `escalation_reason` | `high_severity` or `low_confidence` when escalated, else `none` in the CSV (NULL in SQLite) |
| `resolution_source` | `RAG` if KB snippets were retrieved, else `SQL` if a customer record was found, else `none`. Always `none` when escalated |
| `latency_ms` | Wall-clock time of the graph run on the machine that generated the data |

The CSV adds two helper columns: `created_date` (`YYYY-MM-DD`, handy for per-day
charts) and `data_source` (always `synthetic_mock`).

### Regenerate the data

```bash
python scripts/seed_db.py           # optional, the generator seeds its own database
python scripts/build_index.py       # needed once so the RAG tool has a KB index
python scripts/generate_demo_tickets.py   # writes data/demo_triage.db (gitignored)
python scripts/export_triage_csv.py       # writes data/triage_results.csv
```

Options: `--count`, `--seed` (default 42), `--end-date YYYY-MM-DD` (last day of the
60 day window, default today UTC) and `--db`. Ticket content, timestamps and
decisions are reproducible for a given seed and end date. `latency_ms` is measured,
so it varies between runs. The committed CSV was generated with `--end-date 2026-10-20`.
CI regenerates the CSV on every run and uploads it as the `triage-results-csv`
build artifact.

### Dashboard

Step-by-step build instructions: [docs/TABLEAU_GUIDE.md](docs/TABLEAU_GUIDE.md).

- Tableau Public link: _TODO, add after publishing_
- Screenshot: `docs/dashboard.png` _(TODO, add after publishing)_

<!-- After adding the screenshot: ![Dashboard screenshot](docs/dashboard.png) -->

## Docker

```bash
docker build -t ticket-triage-agent .
docker run -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_REGION -e BEDROCK_MODEL_ID \
  ticket-triage-agent
```

## Scope

This is a weekend-sized demo: no auth, no real customer data, no cloud
deployment. GitHub Actions CI (`.github/workflows/ci.yml`) lints, runs tests,
and proves the Docker image builds — it doesn't deploy anywhere.
