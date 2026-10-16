#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.init_db import DB_PATH, init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print(f"Seeded database at {DB_PATH}")
