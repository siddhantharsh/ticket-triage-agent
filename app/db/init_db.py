import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data" / "tickets.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
SEED_DIR = ROOT / "data" / "seed"


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())

        customers = json.loads((SEED_DIR / "customers.json").read_text())
        conn.executemany(
            "INSERT OR REPLACE INTO customers (customer_id, name, plan_tier) "
            "VALUES (:customer_id, :name, :plan_tier)",
            customers,
        )

        orders = json.loads((SEED_DIR / "orders.json").read_text())
        conn.executemany(
            "INSERT OR REPLACE INTO orders (order_id, customer_id, status, amount_usd) "
            "VALUES (:order_id, :customer_id, :status, :amount_usd)",
            orders,
        )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Seeded database at {DB_PATH}")
