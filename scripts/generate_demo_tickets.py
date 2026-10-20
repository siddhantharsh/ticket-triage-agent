#!/usr/bin/env python3
"""Generate SYNTHETIC support tickets and run them through the real triage pipeline.

Everything produced here is fake and comes from the MOCK_BEDROCK stand-ins. It is not
real customer data and says nothing about real model performance.
"""

import argparse
import json
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

os.environ.setdefault("MOCK_BEDROCK", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.init_db import ROOT, SEED_DIR, init_db  # noqa: E402

DEFAULT_DB = ROOT / "data" / "demo_triage.db"
DEFAULT_COUNT = 500
DEFAULT_SEED = 42
WINDOW_DAYS = 60

TEMPLATES = {
    "billing": [
        ("Refund request for order", "I would like a refund for my last order."),
        ("Charged twice this month", "I was charged twice for the same invoice."),
        ("Unauthorized charge on my card", "There is an unauthorized charge I do not recognize."),
        ("Update payment method", "My card expired and I need to update the payment method."),
        ("Invoice download", "Where can I download last month's invoice for accounting?"),
        ("Upgrade my plan", "I want to upgrade to the next tier starting next cycle."),
        ("Cancel my subscription", "Please cancel my subscription at the end of the period."),
    ],
    "login_access": [
        ("Cannot sign in", "I cannot sign in to my account since this morning."),
        ("Password reset email missing", "The password reset email never arrives."),
        (
            "Locked out after two-factor change",
            "My authenticator app was replaced and I am locked out.",
        ),
        ("Teammate needs access", "Please give my teammate access to the shared workspace."),
        ("Login page loops", "The login page keeps redirecting me back to itself."),
    ],
    "outage": [
        (
            "Service outage in our region",
            "Everything has been unreachable for the last hour, an outage?",
        ),
        ("Dashboard is down for everyone", "The whole team sees the dashboard down since 9am."),
        (
            "API timeouts across the board",
            "Every API request times out, this looks like an outage.",
        ),
    ],
    "bug_report": [
        ("App crashes when exporting", "The app crashes every time I press export."),
        ("Error on the settings page", "I get an error when saving my notification settings."),
        ("Sync not working on mobile", "Sync is not working between my phone and laptop."),
        ("Broken layout on small screens", "The table layout is broken on narrow screens."),
        (
            "Report totals look wrong",
            "The totals on the weekly report do not match the detail rows.",
        ),
    ],
    "feature_request": [
        ("Dark mode please", "It would be great to have a dark theme for late shifts."),
        ("Bulk edit for records", "Could you add a way to edit many records at once?"),
        ("Calendar integration", "We would love a calendar integration for due dates."),
        ("Keyboard shortcuts", "Some keyboard shortcuts would speed up my daily work."),
    ],
    "security": [
        (
            "Suspicious login alert",
            "I got an alert about a login from a country I have never visited.",
        ),
        (
            "Possible account breach",
            "I think my account was hacked, there are changes I did not make.",
        ),
        (
            "Phishing email using your name",
            "I received a phishing email that pretends to be from you.",
        ),
        ("Security questionnaire", "Our auditors need your latest security questionnaire."),
    ],
}
TYPE_WEIGHTS = {
    "billing": 24,
    "login_access": 20,
    "outage": 6,
    "bug_report": 24,
    "feature_request": 14,
    "security": 12,
}
FILLER = [
    "This started a couple of days ago.",
    "I have tried again on a different device.",
    "Our team relies on this for daily work.",
    "Please let me know what information you need from me.",
    "I checked the help center but could not find a clear answer.",
    "It would be good to hear back soon.",
    "Thanks for looking into this.",
    "Happy to jump on a call if that helps.",
]


def _pick_timestamp(rng: random.Random, end: datetime) -> datetime:
    days_back = rng.choices(range(WINDOW_DAYS), k=1)[0]
    day = end - timedelta(days=days_back + 1)
    weight = 0.4 if day.weekday() >= 5 else 1.0
    if rng.random() > weight:
        day -= timedelta(days=rng.choice((1, 2)))
        if day <= end - timedelta(days=WINDOW_DAYS):
            day = end - timedelta(days=WINDOW_DAYS)
    hour = rng.choices(range(24), weights=[1] * 7 + [4] * 11 + [2] * 3 + [1] * 3)[0]
    return day.replace(hour=hour, minute=rng.randrange(60), second=rng.randrange(60))


def generate_tickets(n: int, seed: int, end_date: date) -> list[dict]:
    rng = random.Random(seed)
    end = datetime.combine(end_date, time.min, tzinfo=timezone.utc)
    customers = [c["customer_id"] for c in json.loads((SEED_DIR / "customers.json").read_text())]
    orders = json.loads((SEED_DIR / "orders.json").read_text())
    orders_by_customer: dict[str, list[str]] = {}
    for order in orders:
        orders_by_customer.setdefault(order["customer_id"], []).append(order["order_id"])

    kinds = list(TYPE_WEIGHTS)
    tickets = []
    for _ in range(n):
        kind = rng.choices(kinds, weights=[TYPE_WEIGHTS[k] for k in kinds])[0]
        subject, body = rng.choice(TEMPLATES[kind])
        extra = rng.choices((0, 1, 3), weights=(5, 3, 2))[0]
        body = " ".join([body, *rng.sample(FILLER, extra)])

        roll = rng.random()
        if roll < 0.08:
            customer_id, order_id = None, None
        elif roll < 0.12:
            customer_id, order_id = "CUST-999", None
        else:
            customer_id = rng.choice(customers)
            owned = orders_by_customer.get(customer_id, [])
            order_id = rng.choice(owned) if owned and rng.random() < 0.4 else None

        tickets.append(
            {
                "subject": subject,
                "body": body,
                "customer_id": customer_id,
                "order_id": order_id,
                "created_at": _pick_timestamp(rng, end),
            }
        )

    tickets.sort(key=lambda t: t["created_at"])
    for i, ticket in enumerate(tickets, start=1):
        ticket["ticket_id"] = f"SYN-{i:04d}"
    return tickets


def run(n: int, seed: int, end_date: date, db_path: Path) -> int:
    from app.llm import bedrock_client

    if not bedrock_client.MOCK_BEDROCK:
        raise SystemExit("Refusing to run: demo data must be generated with MOCK_BEDROCK=true.")

    os.environ["DB_PATH"] = str(db_path)
    init_db(db_path)

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM triage_log")
        conn.commit()
    finally:
        conn.close()

    from app.main import run_triage
    from app.models.schemas import TriageRequest
    from app.tools import rag_tool

    # Load the embedding model first so one-off start-up cost does not land in latency_ms.
    rag_tool.search_kb("warm up")

    tickets = generate_tickets(n, seed, end_date)
    for ticket in tickets:
        request = TriageRequest(
            ticket_id=ticket["ticket_id"],
            subject=ticket["subject"],
            body=ticket["body"],
            customer_id=ticket["customer_id"],
            order_id=ticket["order_id"],
        )
        run_triage(request, created_at=ticket["created_at"])
    return len(tickets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="Last day of the 60 day window (YYYY-MM-DD). Defaults to today (UTC).",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    total = run(args.count, args.seed, args.end_date, args.db)
    print(f"Logged {total} synthetic mock-mode triage results to {args.db}")


if __name__ == "__main__":
    main()
