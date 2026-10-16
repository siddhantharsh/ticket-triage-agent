import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _default_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", ROOT / "data" / "tickets.db"))


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_customer_context(
    customer_id: str | None,
    order_id: str | None,
    db_path: Path | None = None,
) -> dict:
    db_path = db_path or _default_db_path()
    empty = {
        "customer_id": customer_id,
        "order_id": order_id,
        "status": None,
        "plan_tier": None,
        "found": False,
    }

    if not customer_id:
        return empty

    conn = _connect(db_path)
    try:
        customer_row = conn.execute(
            "SELECT customer_id, name, plan_tier FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()

        if customer_row is None:
            return empty

        status = None
        resolved_order_id = order_id

        if order_id:
            order_row = conn.execute(
                "SELECT order_id, status FROM orders WHERE order_id = ? AND customer_id = ?",
                (order_id, customer_id),
            ).fetchone()
            if order_row is not None:
                status = order_row["status"]
        else:
            order_row = conn.execute(
                "SELECT order_id, status FROM orders WHERE customer_id = ? "
                "ORDER BY order_id DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            if order_row is not None:
                resolved_order_id = order_row["order_id"]
                status = order_row["status"]

        return {
            "customer_id": customer_row["customer_id"],
            "order_id": resolved_order_id,
            "status": status,
            "plan_tier": customer_row["plan_tier"],
            "found": True,
        }
    finally:
        conn.close()
